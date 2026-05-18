import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Extraccion de secciones del MD estructurado
# ---------------------------------------------------------------------------

def _extract_section(md_content, section_number):
    pattern = rf'(## {section_number}\..*?)(?=\n---|\Z)'
    match = re.search(pattern, md_content, re.DOTALL)
    return match.group(1).strip() if match else ""

# ---------------------------------------------------------------------------
# Prompts independientes por tipo
# ---------------------------------------------------------------------------

_OBJ_SYS = "Eres un analizador de objeciones de venta conversacional. Output: JSON puro sin fences."
_OBJ_USR = """\
Lee la siguiente seccion de OBJECIONES de un guion de agente de voz.
Extrae TODAS las objeciones y conviertelas al formato indicado.

REGLAS PARA KEYWORDS (MINIMO 6, MAXIMO 8 por objecion):
- Extrae la raiz de la palabra: 'ocupado' -> 'ocup', 'tiempo' -> 'tiemp'.
- Incluye sinonimos, variantes de idioma y formas verbales distintas.
- Si hay una palabra muy especifica (marca, nombre propio), incluye la palabra completa.
- Nunca repitas la misma raiz. Cada keyword aporta cobertura nueva.

Schema de cada item:
{{
  "id": "obj_<snake_case>",
  "name": "<nombre de la objecion>",
  "keywords": ["<raiz1>", ..., "<raiz6>"],
  "systemMessage": "GESTION DE OBJECION: <frase literal del agente> y continua por donde ibas."
}}

SECCION:
---
{section}
---

Produce: {{"conditionals": [<lista>]}}
"""

_FAQ_SYS = "Eres un analizador de FAQs de agentes de venta conversacional. Output: JSON puro sin fences."
_FAQ_USR = """\
Lee la siguiente seccion de FAQs de un guion de agente de voz.
Extrae TODAS las FAQs y conviertelas al formato indicado.

REGLAS PARA KEYWORDS (MINIMO 6, MAXIMO 8 por FAQ):
- Extrae la raiz de la palabra: 'precio' -> 'preci', 'duracion' -> 'durac'.
- Incluye sinonimos, variantes de idioma y formas verbales distintas.
- Nunca repitas la misma raiz. Cada keyword aporta cobertura nueva.

Schema de cada item:
{{
  "id": "faq_<snake_case>",
  "name": "<pregunta resumida>",
  "keywords": ["<raiz1>", ..., "<raiz6>"],
  "systemMessage": "FAQ INLINE: <respuesta literal del agente> y continua por donde ibas."
}}

SECCION:
---
{section}
---

Produce: {{"conditionals": [<lista>]}}
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
# Constructor de nodos
# ---------------------------------------------------------------------------

def _build_nodes(conditionals, x_start, y_start):
    nodes = []
    x_pos, y_pos = x_start, y_start
    for cond in conditionals:
        node_id = f"node-{cond['id']}"
        data_id = f"data-{cond['id']}"
        rules = [
            {
                "conditions": {
                    "groups": [{"operator": "AND", "conditions": [
                        {"value": kw.lower(), "operator": "contains",
                         "variable": "{{_chat_history_3}}", "valueType": "string"}
                    ]}],
                    "operator": "AND"
                },
                "description": ""
            }
            for kw in cond.get("keywords", [])
        ]
        nodes.append({
            "id": node_id,
            "type": "moduleCard",
            "position": {"x": x_pos, "y": y_pos},
            "data": {
                "id": data_id,
                "name": cond["name"],
                "type": "conversational_conditional",
                "nodeClass": "action",
                "systemMessage": cond.get("systemMessage", ""),
                "rules": rules,
                "params": {},
                "autoNext": False,
                "isEndNode": False,
                "isGlobalNode": False,
                "maxIterations": 3,
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
        })
        x_pos += 450
        if x_pos > 1800:
            x_pos = 0
            y_pos += 400
    return nodes

# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------

def add_conditionals(md_content, input_json_path, output_json_path, client, verbose=False):
    if verbose:
        print("[Paso 5] Procesando objeciones y FAQs en paralelo...")

    section_obj = _extract_section(md_content, 5)
    section_faq = _extract_section(md_content, 6)

    tasks = {}
    if section_obj:
        tasks["objections"] = lambda: _call(client, _OBJ_SYS, _OBJ_USR.format(section=section_obj))
    if section_faq:
        tasks["faqs"] = lambda: _call(client, _FAQ_SYS, _FAQ_USR.format(section=section_faq))

    results = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
                if verbose:
                    count = len(results[name].get("conditionals", []))
                    print(f"  {name}: {count} elementos extraidos.")
            except Exception as exc:
                print(f"  Error en {name}: {exc}")
                results[name] = {"conditionals": []}

    obj_conditionals = results.get("objections", {}).get("conditionals", [])
    faq_conditionals = results.get("faqs", {}).get("conditionals", [])

    obj_nodes = _build_nodes(obj_conditionals, x_start=0, y_start=1200)
    faq_nodes = _build_nodes(faq_conditionals, x_start=0, y_start=1200 + 400 * (len(obj_nodes) // 5 + 1))

    with open(input_json_path, 'r', encoding='utf-8') as f:
        workflow_json = json.load(f)

    workflow_json["workflow"]["nodes"].extend(obj_nodes + faq_nodes)

    with open(output_json_path, 'w', encoding='utf-8') as out_file:
        json.dump(workflow_json, out_file, indent=2, ensure_ascii=False)
