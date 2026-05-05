import json

def build_workflow_nodes(md_content, base_json_path, output_json_path, client, verbose=False):
    if verbose:
        print("[Paso 4] Construccion de nodos y calculo de conexiones...")
    
    system_prompt = """
    Eres un analizador de flujos. Extrae TODOS los nodos del Markdown a este JSON estricto:
    {
      "nodes": [
        {
          "id": "<ID exacto del MD>",
          "name": "<Nombre del nodo>",
          "is_start": true/false,
          "is_end": true/false,
          "systemMessage": "<DEBES incluir el Script (frases literales) exacto que viene en el MD y sus directivas>",
          "direct_next": "<ID destino si no hay opciones. Null si usa branches>",
          "branches": [
            {
              "id": "<ID slugificado>",
              "name": "<Condicion>",
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
                            "id": branch_id, "name": b["name"], "next": target_id, "description": "", "fillPhrases": ["Claro."]
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

    with open(output_json_path, 'w', encoding='utf-8') as out_file:
        json.dump(base_json, out_file, indent=2, ensure_ascii=False)