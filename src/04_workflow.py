import json

def build_workflow_nodes(md_content, base_json_path, output_json_path, client, verbose=False):
    if verbose:
        print("[Paso 4] Construccion de nodos y calculo de conexiones...")
    
    system_prompt = """
    Eres un arquitecto de agentes conversacionales de voz para la plataforma Tolvia.
    Extrae TODOS los nodos del Markdown al siguiente JSON estricto.

    VARIABLES DE TEMPLATE DISPONIBLES EN TOLVIA (usaLas en systemMessage cuando aplique):
    - {user_first_name}          nombre del contacto
    - {user_is_female?la:el}     articulo segun genero del contacto
    - {Job Title}                cargo del contacto (fuente: LinkedIn/CRM)
    - {company}                  empresa del contacto
    - {position}                 posicion/cargo del contacto
    - {development?TEXTO:}       texto que solo se muestra en modo desarrollo
    - {VARIABLE?texto_si:texto_no}  condicional generica sobre cualquier variable capturada
    - {available_slot_0!valor_defecto}  primer hueco de agenda disponible

    ESTRUCTURA OBLIGATORIA DEL systemMessage:
    Cada systemMessage debe tener estas secciones en orden:
    1. OBJETIVO: lista de bullets con lo que el agente debe lograr en este nodo.
    2. SUPUESTO (opcional): lo que ya se ha hecho antes de llegar a este nodo.
    3. Las frases literales del script entre comillas, con CUANDO usarlas y reglas de uso.
    4. Reglas de clasificacion de respuesta si aplica (SI / NO / OBJECION / PREGUNTA / AMBIGUO).
    5. Instruccion de rama al final: indica exactamente que rama tomar segun cada resultado.
       Esta instruccion debe incluir el ID de la rama y ser CLARA: "no digas nada y toma la rama X".
       Si omites esta instruccion, el agente no sabra cuando salir del nodo.

    REGLAS GENERALES:
    - Usa variables de template donde el script original hace referencia al nombre, cargo o empresa del usuario.
    - El systemMessage es una instruccion operacional para un LLM, no un resumen: debe ser accionable.
    - No inventes frases que no esten en el MD. Usa las literales del script.

    REGLA CRITICA DEL NODO START:
    El nodo con is_start=true es SOLO el punto de entrada tecnico del flujo. NO tiene systemMessage.
    NO tiene branches. NO tiene extractions. SIEMPRE tiene direct_next con el ID del primer nodo
    conversacional. Si omites direct_next en el start, el agente quedara flotando desconectado.

    SCHEMA JSON:
    {
      "nodes": [
        {
          "id": "<ID exacto del MD>",
          "name": "<Nombre del nodo>",
          "is_start": true/false,
          "is_end": true/false,
          "systemMessage": "<systemMessage estructurado. VACIO ('') si is_start=true>",
          "direct_next": "<ID destino si no hay branches. OBLIGATORIO si is_start=true. Null si usa branches>",
          "branches": [
            {
              "id": "<ID slugificado>",
              "name": "<Condicion>",
              "fill_phrase": "<frase MUY breve que el agente dice EN VOZ ALTA al usuario al tomar esta rama. Debe sonar natural si se escucha. Maximo 4 palabras. VALIDO: 'Perfecto,', 'Entendido,', 'Claro,', 'Ya veo,', 'De acuerdo,'. INVALIDO: 'Prospecto interesado', 'Usuario no disponible', cualquier descripcion del estado interno.>",
              "next_node": "<ID destino>"
            }
          ],
          "extractions": [
            {
              "name": "<nombre variable>",
              "type": "<enum | string | boolean>",
              "choices": ["opcion1"],
              "description": "<descripcion>"
            }
          ]
        }
      ]
    }
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Extrae el flujo completo:\n\n{md_content}"}
        ]
    )
    parsed_data = json.loads(response.choices[0].message.content)

    with open(base_json_path, 'r', encoding='utf-8') as f:
        base_json = json.load(f)

    workflow_nodes = []
    workflow_edges = []
    x_pos, y_pos = 0, 0
    
    for raw_node in parsed_data.get("nodes", []):
        node_id = f"node-{raw_node['id']}"
        data_id = f"data-{raw_node['id']}"
        
        if raw_node.get("is_start"):
            n_type, n_class = "start", "start"
        elif raw_node.get("extractions") and not raw_node.get("branches"):
            n_type, n_class = "extractor", "extractor"
        else:
            n_type, n_class = "conversational", "ask_and_branch"

        if n_class == "start":
            system_msg = ""
        else:
            system_msg = raw_node.get("systemMessage", "")
            if raw_node.get("is_end"):
                system_msg += "\n\nDIRECTIVA CRITICA: Despidete del usuario y CUELGA LA LLAMADA inmediatamente."

        module_card = {
            "id": node_id,
            "type": "moduleCard",
            "position": {"x": x_pos, "y": y_pos},
            "data": {
                "id": data_id,
                "name": raw_node["name"],
                "type": n_type,
                "nodeClass": n_class,
                "systemMessage": system_msg,
                "rules": [],
                "params": {},
                "autoNext": False,
                "isEndNode": False,
                "isGlobalNode": False,
                "maxIterations": 3 if n_class == "start" else 300,
                "asyncExecution": False,
                "blockUserInput": False,
                "cannedStarters": [],
                "knowledgeBaseIds": [],
                "inputReplacements": [],
                "responseReplacements": [],
                "overrideLlmTimeout": 30,
                "branches": [],
                "extractions": []
            }
        }

        if n_class in ["start", "extractor"] and raw_node.get("direct_next"):
            target_id = f"node-{raw_node['direct_next']}"
            source_handle = f"{data_id}-conversational-connector"
            module_card["data"]["connector"] = target_id
            workflow_edges.append({
                "id": f"xy-edge__{node_id}{source_handle}-{target_id}",
                "source": node_id,
                "target": target_id,
                "sourceHandle": source_handle
            })
        elif n_class == "ask_and_branch":
            if raw_node.get("branches"):
                for b in raw_node["branches"]:
                    if b.get("next_node"):
                        target_id = f"node-{b['next_node']}"
                        branch_id = b["id"]
                        module_card["data"]["branches"].append({
                            "id": branch_id, "name": b["name"], "next": target_id, "description": "", "fillPhrases": [b.get("fill_phrase", "Claro.")]
                        })
                        workflow_edges.append({
                            "id": f"xy-edge__{node_id}{branch_id}-{target_id}", "source": node_id, "target": target_id, "sourceHandle": branch_id
                        })
            elif raw_node.get("direct_next"):
                target_id = f"node-{raw_node['direct_next']}"
                branch_id = "branch_continuar"
                module_card["data"]["branches"].append({
                    "id": branch_id, "name": "Continuar", "next": target_id, "description": "Transicion automatica", "fillPhrases": ["Claro."]
                })
                workflow_edges.append({
                    "id": f"xy-edge__{node_id}{branch_id}-{target_id}", "source": node_id, "target": target_id, "sourceHandle": branch_id
                })

        for ext in raw_node.get("extractions", []):
            module_card["data"]["extractions"].append({
                "name": ext["name"], "type": ext["type"], "choices": ext.get("choices", []), "examples": [], "required": False, "description": ext.get("description", "")
            })
            
        workflow_nodes.append(module_card)
        x_pos += 450
        if x_pos > 1800:
            x_pos = 0
            y_pos += 400

    base_json["workflow"]["nodes"] = workflow_nodes
    base_json["workflow"]["edges"] = workflow_edges

    start_node = next((n for n in workflow_nodes if n["data"]["nodeClass"] == "start"), None)
    if start_node and "connector" not in start_node["data"]:
        first_other = next((n for n in workflow_nodes if n["id"] != start_node["id"]), None)
        if first_other:
            target_id = first_other["id"]
            data_id = start_node["data"]["id"]
            source_handle = f"{data_id}-conversational-connector"
            start_node["data"]["connector"] = target_id
            workflow_edges.append({
                "id": f"xy-edge__{start_node['id']}{source_handle}-{target_id}",
                "source": start_node["id"],
                "target": target_id,
                "sourceHandle": source_handle
            })
            print(f"[Paso 4] AVISO: el nodo start no tenia direct_next. Conectado automaticamente a '{target_id}'.")

    with open(output_json_path, 'w', encoding='utf-8') as out_file:
        json.dump(base_json, out_file, indent=2, ensure_ascii=False)

    issues = _validate_graph(workflow_nodes, workflow_edges)
    if issues:
        print(f"[Paso 4] ADVERTENCIA: se encontraron {len(issues)} referencia(s) rota(s) en el grafo:")
        for issue in issues:
            print(f"  - {issue}")
    elif verbose:
        print("[Paso 4] Validacion del grafo: OK (sin referencias rotas)")


def _validate_graph(nodes, edges):
    existing_ids = {n["id"] for n in nodes}
    issues = []

    for node in nodes:
        nid = node["id"]
        data = node.get("data", {})

        connector = data.get("connector")
        if connector and connector not in existing_ids:
            issues.append(f"Nodo '{nid}': connector '{connector}' no existe")

        for branch in data.get("branches", []):
            target = branch.get("next")
            if target and target not in existing_ids:
                issues.append(f"Nodo '{nid}' rama '{branch.get('id', '?')}': next '{target}' no existe")

    for edge in edges:
        if edge.get("source") not in existing_ids:
            issues.append(f"Edge '{edge.get('id', '?')}': source '{edge.get('source')}' no existe")
        if edge.get("target") not in existing_ids:
            issues.append(f"Edge '{edge.get('id', '?')}': target '{edge.get('target')}' no existe")

    return issues