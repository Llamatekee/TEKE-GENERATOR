import json
import re
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

BATCH_SIZE = 8

# Patrones que indican una etiqueta interna, no una frase natural de voz
_UNSAFE_FILL_PATTERNS = [
    r'\d',              # contiene números
    r'\bfase\b',        # "Fase X"
    r'\bpaso\b',        # "Paso X"
    r'\bnodo\b',        # "Nodo X"
    r'\betapa\b',
    r'\bir\s+a\b',      # "Ir a"
    r'\bcierre\b',
    r'\bmanejo\b',
    r'\breprograma',
    r'\bprospecto\b',
    r'\busuario\b',
    r'->',              # flechas
    r'_',               # snake_case
]

_FILL_FALLBACKS = [
    "Claro.", "Entendido.", "Perfecto.", "De acuerdo.", "Ya veo.",
    "Comprendo.", "Estupendo.", "Muy bien.", "Por supuesto.", "Anotado.",
]

def _safe_fill_phrase(phrase):
    if not phrase or not phrase.strip():
        return random.choice(_FILL_FALLBACKS)
    lower = phrase.lower()
    if any(re.search(p, lower) for p in _UNSAFE_FILL_PATTERNS):
        return random.choice(_FILL_FALLBACKS)
    if len(phrase.split()) > 5:
        return random.choice(_FILL_FALLBACKS)
    return phrase

# ---------------------------------------------------------------------------
# Utilidades MD
# ---------------------------------------------------------------------------

def _extract_section(md, section_number):
    m = re.search(rf'(## {section_number}\..*?)(?=\n---|\Z)', md, re.DOTALL)
    return m.group(1).strip() if m else md

def _extract_node_blocks(section4_md, node_ids):
    """Devuelve solo los bloques ### [NODO-XX] que corresponden a los IDs indicados."""
    blocks = re.split(r'(?=### \[NODO-)', section4_md)
    result = []
    for block in blocks:
        for nid in node_ids:
            if f'`{nid}`' in block:
                result.append(block.strip())
                break
    return "\n\n".join(result) if result else section4_md

def _skeleton_summary(skeleton_nodes):
    lines = []
    for n in skeleton_nodes:
        tag = "START" if n.get("is_start") else ("END" if n.get("is_end") else "node")
        conns = []
        if n.get("direct_next"):
            conns.append(f"-> {n['direct_next']}")
        for b in n.get("branches", []):
            conns.append(f"[{b['id']}:{b.get('name','?')}]->{b.get('next_node','?')}")
        lines.append(f"{n['id']} ({tag}): {', '.join(conns) or 'terminal'}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SKELETON_SYS = "Eres un arquitecto de grafos conversacionales. Output: JSON puro sin fences."
_SKELETON_USR = """\
Extrae la estructura de TODOS los nodos del flujo del siguiente Markdown.
SOLO estructura: sin systemMessage ni extractions.

REGLA CRITICA START: nodo is_start=true → direct_next obligatorio, branches vacio.

Schema:
{{
  "nodes": [
    {{
      "id": "<ID exacto del MD>",
      "name": "<nombre>",
      "is_start": true/false,
      "is_end": true/false,
      "direct_next": "<id o null>",
      "direct_next_name": "<slug snake_case de la condicion observable del usuario, ej: 'user_agrees_to_continue' — SOLO si direct_next existe Y branches esta vacio; omitir en caso contrario>",
      "direct_next_description": "<condicion concreta y observable: que dice o hace el usuario para activar esta transicion, ej: 'El usuario responde afirmativamente a la pregunta del agente' — SOLO si direct_next existe Y branches esta vacio; omitir en caso contrario>",
      "branches": [
        {{"id": "<slug>", "name": "<condicion>", "fill_phrase": "<max 4 palabras naturales>", "next_node": "<id>"}}
      ]
    }}
  ]
}}

MARKDOWN:
---
{section}
---
"""

_CONTENT_SYS = "Eres un escritor de systemMessages para agentes de voz Tolvia. Output: JSON puro sin fences."
_CONTENT_USR = """\
VARIABLES TOLVIA: {{user_first_name}}, {{user_is_female?la:el}}, {{Job Title}}, {{company}}, {{position}}, {{available_slot_0!valor_defecto}}

ESTRUCTURA del systemMessage (en orden):
1. OBJETIVO: bullets con lo que el agente logra en este nodo.
2. SUPUESTO (opcional): lo ya hecho antes de llegar aqui.
3. Frases literales del script entre comillas + CUANDO usarlas.
4. REGLAS DE CLASIFICACION si el nodo tiene branches Y su bloque MD tiene script propio con respuestas del usuario.
5. Instruccion de rama al final: "no digas nada y toma la rama X".

REGLA START: is_start=true → systemMessage siempre "" (vacio).

REGLA DE PRESENTACION:
Si el nodo es el primero conversacional (direct_next del start en el esqueleto) Y tiene script en el MD,
comienza su systemMessage con las frases de pitch del nodo start (las que siguen al answerPhrase).

ESQUELETO COMPLETO (para referencias cruzadas):
{skeleton}

NODOS A PROCESAR (IDs): {batch_ids}

MARKDOWN DE ESTOS NODOS:
---
{batch_md}
---

Produce:
{{
  "nodes": [
    {{
      "id": "<id>",
      "systemMessage": "<texto completo o '' si is_start>",
      "extractions": [{{"name": "...", "type": "...", "choices": [], "description": "..."}}]
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# Llamada LLM
# ---------------------------------------------------------------------------

def _call(client, system, user):
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    return json.loads(response.choices[0].message.content)

# ---------------------------------------------------------------------------
# Refinamiento de branches
# ---------------------------------------------------------------------------

_BRANCH_REFINE_SYS = "Eres un especialista en condiciones de transicion para agentes conversacionales de voz. Output: JSON puro sin fences."
_BRANCH_REFINE_USR = """\
Revisa las ramas (branches) de los nodos indicados y mejora su 'name' y 'description' para que sean condiciones CONCRETAS y OBSERVABLES desde el punto de vista del comportamiento del usuario.

REGLAS:
1. 'name': slug snake_case que describe la accion/respuesta del usuario. Ej: 'user_says_yes', 'user_agrees_to_demo', 'user_asks_for_callback'.
2. 'description': condicion comportamental precisa. NO describas el flujo interno. Describe QUE dice o hace el usuario para activar esa rama.
   - MALO: "Cuando el usuario accede" / "Transicion automatica" / "El usuario da consentimiento"
   - BUENO: "El usuario responde afirmativamente (si, claro, por supuesto, de acuerdo) a la pregunta de si quiere escuchar las tres preguntas"
3. Si la rama ya tiene name/description concretos y especificos, devuelvelos tal cual.
4. Usa el systemMessage del nodo para inferir exactamente que pregunta hace el agente y escribir la condicion ajustada a esa pregunta.
5. NO modifiques 'id' ni 'next_node' bajo ningun concepto.

ESQUELETO COMPLETO (contexto de conexiones):
{skeleton}

NODOS A REVISAR:
{batch_nodes}

Produce:
{{
  "nodes": [
    {{
      "id": "<id del nodo>",
      "branches": [
        {{"id": "<mismo id de rama — no cambiar>", "name": "<name mejorado>", "description": "<description concreta>"}}
      ]
    }}
  ]
}}
"""


def _refine_branches(client, merged_nodes, skeleton_str, section4=""):
    """Refina name y description de branches para que sean condiciones concretas y observables."""
    nodes_with_branches = [n for n in merged_nodes if n.get("branches")]
    if not nodes_with_branches:
        return merged_nodes

    batches = [nodes_with_branches[i:i + BATCH_SIZE] for i in range(0, len(nodes_with_branches), BATCH_SIZE)]

    def process_batch(batch):
        batch_data = []
        for n in batch:
            sm = n.get("systemMessage", "")
            # si el systemMessage esta vacio, usar el bloque MD como contexto
            if not sm and section4:
                sm = _extract_node_blocks(section4, [n["id"]])
            batch_data.append({"id": n["id"], "systemMessage": sm, "branches": n.get("branches", [])})
        user = _BRANCH_REFINE_USR.format(
            skeleton=skeleton_str,
            batch_nodes=json.dumps(batch_data, ensure_ascii=False, indent=2),
        )
        result = _call(client, _BRANCH_REFINE_SYS, user)
        return {n["id"]: n.get("branches", []) for n in result.get("nodes", [])}

    refined_map = {}
    with ThreadPoolExecutor(max_workers=min(len(batches), 6)) as executor:
        futures = {executor.submit(process_batch, batch): i for i, batch in enumerate(batches)}
        for future in as_completed(futures):
            try:
                refined_map.update(future.result())
            except Exception as exc:
                print(f"  Error en refinamiento de branches: {exc}")

    # Aplicar: solo name y description; next_node permanece intacto del skeleton
    for node in merged_nodes:
        nid = node["id"]
        if nid in refined_map:
            refined_by_id = {b["id"]: b for b in refined_map[nid]}
            for orig_branch in node.get("branches", []):
                bid = orig_branch["id"]
                if bid in refined_by_id:
                    orig_branch["name"] = refined_by_id[bid].get("name", orig_branch["name"])
                    orig_branch["description"] = refined_by_id[bid].get("description", orig_branch.get("description", ""))

    return merged_nodes


# ---------------------------------------------------------------------------
# Relleno de nodos distribuidor sin systemMessage — paso dedicado
# ---------------------------------------------------------------------------

_FILL_BRANCH_SYS = "Eres un escritor especialista en systemMessages de nodos distribuidores para agentes de voz Tolvia. Output: JSON puro sin fences."
_FILL_BRANCH_USR = """\
Genera el systemMessage de nodos ask_and_branch que NO tienen script propio en el MD.
Estos nodos son distribuidores: su unica funcion es escuchar la respuesta del usuario y tomar la rama correcta.

PRIMER NODO CONVERSACIONAL (direct_next del start): {first_conv_id}

ESQUELETO COMPLETO con nombres de ramas:
{skeleton}

NODOS A COMPLETAR (incluyen su bloque MD y sus ramas del esqueleto):
{batch_nodes}

Para cada nodo produce:
1. Si is_first=true:
   - Extrae del bloque MD del nodo start las frases de pitch (las que siguen al answerPhrase del agente).
   - Ponlas al inicio del systemMessage como pitch de apertura.
   - Añade la directiva: "NO respondas a saludos ni cortesias sociales del prospecto. Di el pitch de apertura de inmediato."
2. OBJETIVO en 1 linea.
3. REGLAS DE CLASIFICACION por cada rama del esqueleto:
   - Usa las condiciones del bloque MD (lineas '- Si: X -> Y') y mapealas al branch_id del esqueleto.
   - Si no hay condiciones en el MD, infierelas del 'name' de la rama (ej: user_is_busy → "El usuario dice que esta ocupado").
   - Formato exacto: "SI <condicion observable> → no digas nada y toma la rama <branch_id>"
4. Mejora tambien la 'description' de cada rama con la condicion concreta inferida.

Produce:
{{
  "nodes": [
    {{
      "id": "<id>",
      "systemMessage": "<texto completo>",
      "branches": [
        {{"id": "<mismo id de rama>", "description": "<condicion concreta observable>"}}
      ]
    }}
  ]
}}
"""


def _fill_empty_branch_nodes(client, merged_nodes, skeleton_str, section4, first_conv_id, verbose=False):
    """Genera systemMessage+descriptions para nodos ask_and_branch con SM vacio."""
    targets = [
        n for n in merged_nodes
        if n.get("branches")
        and "\u2192" not in n.get("systemMessage", "")
        and "toma la rama" not in n.get("systemMessage", "")
    ]
    if not targets:
        return merged_nodes

    if verbose:
        ids = [n["id"] for n in targets]
        print(f"  [fill_branch] Completando {len(targets)} nodo(s) distribuidor sin systemMessage: {ids}")

    batch_data = []
    for n in targets:
        md_block = _extract_node_blocks(section4, [n["id"]])
        batch_data.append({
            "id": n["id"],
            "is_first": n["id"] == first_conv_id,
            "branches": [{"id": b["id"], "name": b.get("name", b["id"]), "next_node": b.get("next_node", "")} for b in n.get("branches", [])],
            "md_block": md_block,
        })

    user = _FILL_BRANCH_USR.format(
        first_conv_id=first_conv_id or "ninguno",
        skeleton=skeleton_str,
        batch_nodes=json.dumps(batch_data, ensure_ascii=False, indent=2),
    )
    try:
        result = _call(client, _FILL_BRANCH_SYS, user)
        result_map = {n["id"]: n for n in result.get("nodes", [])}
        for node in merged_nodes:
            nid = node["id"]
            if nid in result_map:
                node["systemMessage"] = result_map[nid].get("systemMessage", node["systemMessage"])
                branch_updates = {b["id"]: b for b in result_map[nid].get("branches", [])}
                for b in node.get("branches", []):
                    if b["id"] in branch_updates:
                        b["description"] = branch_updates[b["id"]].get("description", b.get("description", ""))
    except Exception as exc:
        print(f"  Error en _fill_empty_branch_nodes: {exc}")

    return merged_nodes


# ---------------------------------------------------------------------------
# Construccion de nodos Tolvia
# ---------------------------------------------------------------------------

def _build_tolvia_nodes(merged_nodes):
    workflow_nodes = []
    workflow_edges = []
    x_pos, y_pos = 0, 0

    for raw_node in merged_nodes:
        node_id = f"node-{raw_node['id']}"
        data_id = f"data-{raw_node['id']}"

        if raw_node.get("is_start"):
            n_type, n_class = "start", "start"
        elif raw_node.get("extractions") and not raw_node.get("branches"):
            n_type, n_class = "extractor", "extractor"
        else:
            n_type, n_class = "conversational", "ask_and_branch"

        system_msg = "" if n_class == "start" else raw_node.get("systemMessage", "")
        if raw_node.get("is_end") and system_msg:
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
                "isEndNode": bool(raw_node.get("is_end")),
                "isGlobalNode": False,
                "maxIterations": 3 if n_class == "start" else (1 if n_class == "extractor" else 300),
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
                "source": node_id, "target": target_id, "sourceHandle": source_handle
            })
        elif n_class == "ask_and_branch":
            if raw_node.get("branches"):
                for b in raw_node["branches"]:
                    if b.get("next_node"):
                        target_id = f"node-{b['next_node']}"
                        branch_id = b["id"]
                        module_card["data"]["branches"].append({
                            "id": branch_id, "name": b["name"], "next": target_id,
                            "description": b.get("description", ""), "fillPhrases": [_safe_fill_phrase(b.get("fill_phrase", ""))]
                        })
                        workflow_edges.append({
                            "id": f"xy-edge__{node_id}{branch_id}-{target_id}",
                            "source": node_id, "target": target_id, "sourceHandle": branch_id
                        })
            elif raw_node.get("direct_next"):
                target_id = f"node-{raw_node['direct_next']}"
                # usar name/description inferidos por el LLM en el skeleton
                branch_id = raw_node.get("direct_next_name") or "branch_continuar"
                branch_name = raw_node.get("direct_next_name") or "Continuar"
                branch_desc = raw_node.get("direct_next_description") or "Transicion automatica"
                module_card["data"]["branches"].append({
                    "id": branch_id, "name": branch_name, "next": target_id,
                    "description": branch_desc, "fillPhrases": [_safe_fill_phrase("")]
                })
                workflow_edges.append({
                    "id": f"xy-edge__{node_id}{branch_id}-{target_id}",
                    "source": node_id, "target": target_id, "sourceHandle": branch_id
                })

        if n_class != "start":
            for ext in raw_node.get("extractions", []):
                module_card["data"]["extractions"].append({
                    "name": ext["name"], "type": ext["type"],
                    "choices": ext.get("choices", []), "examples": [],
                    "required": False, "description": ext.get("description", "")
                })

        workflow_nodes.append(module_card)
        x_pos += 450
        if x_pos > 1800:
            x_pos = 0
            y_pos += 400

    return workflow_nodes, workflow_edges

# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------

def build_workflow_nodes(md_content, base_json_path, output_json_path, client, verbose=False):
    if verbose:
        print("[Paso 4] Extrayendo esqueleto del grafo...")

    section4 = _extract_section(md_content, 4)

    # Fase A: esqueleto completo (1 llamada)
    skeleton_data = _call(client, _SKELETON_SYS, _SKELETON_USR.format(section=section4))
    skeleton_nodes = skeleton_data.get("nodes", [])

    if verbose:
        print(f"  Esqueleto: {len(skeleton_nodes)} nodos detectados.")

    skeleton_str = _skeleton_summary(skeleton_nodes)

    # Fase B: contenido en lotes paralelos
    batches = [skeleton_nodes[i:i + BATCH_SIZE] for i in range(0, len(skeleton_nodes), BATCH_SIZE)]

    if verbose:
        print(f"  Procesando contenido en {len(batches)} lote(s) de hasta {BATCH_SIZE} nodos en paralelo...")

    def process_batch(batch):
        batch_ids = [n["id"] for n in batch]
        batch_md = _extract_node_blocks(section4, batch_ids)
        user = _CONTENT_USR.format(
            skeleton=skeleton_str,
            batch_ids=", ".join(batch_ids),
            batch_md=batch_md,
        )
        result = _call(client, _CONTENT_SYS, user)
        return {n["id"]: n for n in result.get("nodes", [])}

    content_map = {}
    with ThreadPoolExecutor(max_workers=min(len(batches), 6)) as executor:
        futures = {executor.submit(process_batch, batch): i for i, batch in enumerate(batches)}
        for future in as_completed(futures):
            batch_idx = futures[future]
            try:
                content_map.update(future.result())
                if verbose:
                    print(f"  Lote {batch_idx + 1}/{len(batches)} completado.")
            except Exception as exc:
                print(f"  Error en lote {batch_idx + 1}: {exc}")

    # Fusion esqueleto + contenido
    merged_nodes = []
    for skel in skeleton_nodes:
        nid = skel["id"]
        content = content_map.get(nid, {})
        merged_nodes.append({**skel,
            "systemMessage": content.get("systemMessage", ""),
            "extractions":   content.get("extractions", []),
        })

    # Calcular first_conv_id una sola vez para todos los pasos posteriores
    _start = next((n for n in merged_nodes if n.get("is_start")), None)
    first_conv_id = _start.get("direct_next") if _start else None

    # Paso A: refinar name/description de branches con systemMessage como contexto
    if verbose:
        print("  Refinando condiciones de transicion de branches...")
    try:
        merged_nodes = _refine_branches(client, merged_nodes, skeleton_str, section4=section4)
    except Exception as exc:
        print(f"  Refinamiento de branches omitido: {exc}")

    # Paso B: completar nodos distribuidor sin systemMessage (pitch + reglas de clasificacion)
    try:
        merged_nodes = _fill_empty_branch_nodes(client, merged_nodes, skeleton_str, section4, first_conv_id, verbose=verbose)
    except Exception as exc:
        print(f"  Fill branch nodes omitido: {exc}")

    # Paso C: limpiar directiva de apertura de nodos que no son el primero conversacional
    _PITCH_DIRECTIVE = "NO respondas a saludos ni cortesias sociales del prospecto. Di el pitch de apertura de inmediato."
    for node in merged_nodes:
        if node["id"] != first_conv_id and _PITCH_DIRECTIVE in node.get("systemMessage", ""):
            node["systemMessage"] = node["systemMessage"].replace(_PITCH_DIRECTIVE, "").strip()

    # Paso D (safety net): si el primer nodo sigue sin systemMessage, forzar regeneracion
    first_conv = next((n for n in merged_nodes if n["id"] == first_conv_id), None) if first_conv_id else None
    if first_conv and not first_conv.get("systemMessage"):
        if verbose:
            print(f"  [safety] Primer nodo '{first_conv_id}' sin systemMessage tras todos los pasos — regenerando...")
        try:
            merged_nodes = _fill_empty_branch_nodes(client, merged_nodes, skeleton_str, section4, first_conv_id, verbose=verbose)
        except Exception as exc:
            print(f"  Error en safety regeneration: {exc}")

    # Construccion Tolvia
    workflow_nodes, workflow_edges = _build_tolvia_nodes(merged_nodes)

    with open(base_json_path, 'r', encoding='utf-8') as f:
        base_json = json.load(f)

    base_json["workflow"]["nodes"] = workflow_nodes
    base_json["workflow"]["edges"] = workflow_edges

    # Fallback: conectar start si quedó sin connector
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
                "source": start_node["id"], "target": target_id, "sourceHandle": source_handle
            })
            print(f"[Paso 4] AVISO: nodo start sin direct_next. Conectado automaticamente a '{target_id}'.")

    with open(output_json_path, 'w', encoding='utf-8') as out_file:
        json.dump(base_json, out_file, indent=2, ensure_ascii=False)

    issues = _validate_graph(workflow_nodes, workflow_edges)
    if issues:
        print(f"[Paso 4] ADVERTENCIA: {len(issues)} referencia(s) rota(s):")
        for issue in issues:
            print(f"  - {issue}")
    elif verbose:
        print("[Paso 4] Validacion del grafo: OK")

# ---------------------------------------------------------------------------
# Validacion
# ---------------------------------------------------------------------------

def _validate_graph(nodes, edges):
    existing_ids = {n["id"] for n in nodes}
    issues = []
    for node in nodes:
        nid = node["id"]
        data = node.get("data", {})
        if data.get("connector") and data["connector"] not in existing_ids:
            issues.append(f"Nodo '{nid}': connector '{data['connector']}' no existe")
        for branch in data.get("branches", []):
            if branch.get("next") and branch["next"] not in existing_ids:
                issues.append(f"Nodo '{nid}' rama '{branch.get('id','?')}': next '{branch['next']}' no existe")
    for edge in edges:
        if edge.get("source") not in existing_ids:
            issues.append(f"Edge '{edge.get('id','?')}': source '{edge.get('source')}' no existe")
        if edge.get("target") not in existing_ids:
            issues.append(f"Edge '{edge.get('id','?')}': target '{edge.get('target')}' no existe")
    return issues
