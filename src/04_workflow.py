import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

BATCH_SIZE = 8

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
            conns.append(f"[{b['id']}]->{b.get('next_node','?')}")
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

ESTRUCTURA OBLIGATORIA del systemMessage (en orden):
1. OBJETIVO: bullets con lo que el agente logra en este nodo.
2. SUPUESTO (opcional): lo ya hecho antes de llegar aqui.
3. Frases literales del script entre comillas + CUANDO usarlas.
4. Reglas de clasificacion si aplica (SI / NO / OBJECION / PREGUNTA / AMBIGUO).
5. Instruccion de rama al final: "no digas nada y toma la rama X".

REGLA START: is_start=true → systemMessage siempre "" (vacio).

REGLA DE PRESENTACION (CRITICA):
El nodo start suele tener 2 o mas frases. La 1ra ya la dice el agente al descolgar (answerPhrase).
Las frases 2+ SON EL PITCH y DEBEN ir literalmente al PRINCIPIO EXACTO del systemMessage del PRIMER nodo conversacional.
El systemMessage de ese primer nodo debe comenzar con esas frases y luego incluir el OBJETIVO y las reglas de clasificacion.
IMPORTANTE: ese nodo debe incluir la directiva "NO respondas a saludos ni cortesias sociales del prospecto. Di el pitch de apertura de inmediato."

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
                            "description": "", "fillPhrases": [b.get("fill_phrase", "Claro.")]
                        })
                        workflow_edges.append({
                            "id": f"xy-edge__{node_id}{branch_id}-{target_id}",
                            "source": node_id, "target": target_id, "sourceHandle": branch_id
                        })
            elif raw_node.get("direct_next"):
                target_id = f"node-{raw_node['direct_next']}"
                branch_id = "branch_continuar"
                module_card["data"]["branches"].append({
                    "id": branch_id, "name": "Continuar", "next": target_id,
                    "description": "Transicion automatica", "fillPhrases": ["Claro."]
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
