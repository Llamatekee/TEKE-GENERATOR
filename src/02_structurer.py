import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from dotenv import load_dotenv

DEFAULT_MODEL = "gpt-4o"
DEFAULT_MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_P1_SYS = "Eres un analizador experto de guiones de venta conversacional. Output: JSON puro sin fences."
_P1_USR = """\
Analiza este documento Markdown de un guion de agente de voz y produce el siguiente JSON:

{{
  "document_type": "<structured_script|implicit_prompt|hybrid>",
  "agent_name": "<nombre del agente>",
  "company_name": "<empresa>",
  "primary_objective": "<objetivo principal en una frase>",
  "detected_sections": ["identidad","flujo","objeciones","faqs","reglas_globales","adaptacion_audiencia"],
  "missing_sections": ["<secciones implicitas o ausentes>"],
  "flow_implicit": <true si el flujo no esta numerado/explicito>,
  "flow_nodes_approximate": <numero estimado de nodos>,
  "objections_count_approximate": <numero>,
  "faqs_count_approximate": <numero>,
  "notes": "<observaciones para el procesamiento>"
}}

document_type:
- structured_script: fases numeradas, guion explicito paso a paso
- implicit_prompt: instrucciones de comportamiento sin flujo conversacional explicito
- hybrid: mezcla de ambos

DOCUMENTO:
---
{raw_md}
---
"""

_P2A_SYS = "Eres un extractor de identidad de agentes conversacionales de venta. Output: JSON puro."
_P2A_USR = """\
Extrae identidad, estilo, guardrails y reglas globales del siguiente guion.

ANALISIS PREVIO: {analysis}

DOCUMENTO:
---
{raw_md}
---

Produce:
{{
  "agent": {{
    "name": "<nombre>",
    "company": "<empresa>",
    "objective": "<objetivo real>",
    "identity": "<como debe percibirse>",
    "style": "<estilo de voz>",
    "guardrails": ["<prohibicion 1>", "<prohibicion 2>"]
  }},
  "global_rules": ["<regla 1>", "<regla 2>"],
  "audience_adaptation": [
    {{"profile": "<perfil>", "tone": "<tono>", "focus": "<enfoque>"}}
  ]
}}
Si un campo no esta en el documento, usa null. NO inventes empresa ni identidad.
"""

_P2B_SYS = "Eres un arquitecto de flujos conversacionales de venta. Output: JSON puro."
_P2B_USR = """\
Modela el FLUJO PRINCIPAL de la conversacion como nodos discretos.

ANALISIS PREVIO: {analysis}

REGLAS CRITICAS:
1. Un nodo = un turno del agente donde habla y espera respuesta.
2. EL NODO "start" ES ESTRICTAMENTE LINEAL. NUNCA le anadas "branches". Siempre debe avanzar usando "next" apuntando al ID del siguiente nodo (normalmente el nodo distribuidor).
3. NODO DISTRIBUIDOR OBLIGATORIO: Despues de "start", DEBES crear el nodo conversacional (ej. "detectar_intencion") que haga la primera gran pregunta y contenga los "branches" hacia todos los caminos posibles.
4. NINGUN NODO HUERFANO: Todos los nodos deben estar conectados. El flujo debe ser un grafo continuo y rastreable desde "start" hasta los distintos finales. Ningun camino puede flotar sin conexion.
5. EXHAUSTIVIDAD OBLIGATORIA (CERO PEREZA): Si en el nodo distribuidor creas 6 "branches", ES OBLIGATORIO crear y desarrollar los 6 nodos de destino. Mapea el arbol completo sin omitir nada.
6. REFERENCIAS CRUZADAS EXACTAS: El valor que pongas en "next" DEBE ser exactamente el "id" del nodo destino. 
7. FALLBACK DE RAMAS: Si el documento menciona una opcion pero no detalla el paso a paso, crea el "branch" y mapealo a un nodo donde el agente diga "Tomo nota para derivarlo al equipo", seguido de un nodo "end".
8. Objeciones y FAQs NO van aqui, tienen su propia seccion.

Por cada nodo:
{{
  "id": "<snake_case unico>",
  "name": "<nombre legible>",
  "type": "<tipo>",
  "objective": "<que logra el agente>",
  "script": ["<frase literal 1>", "<frase literal 2>"],
  "directives": ["<instruccion interna>"],
  "branches": [{{"condition": "<cuando>", "next": "<id_nodo>", "note": "<nota>"}}],
  "next": "<id_nodo_siguiente si no hay branches>",
  "extractions": []
}}

DOCUMENTO:
---
{raw_md}
---

Produce: {{"flow": [<lista de nodos>]}}
"""

_P2B_SKELETON_SYS = "Eres un arquitecto de grafos conversacionales. Output: JSON puro sin fences."
_P2B_SKELETON_USR = """\
Modela el grafo de nodos del flujo principal. SOLO estructura: sin scripts, sin directives, sin objectives.

ANALISIS PREVIO: {analysis}

REGLAS CRITICAS:
1. Un nodo = un turno del agente donde habla y espera respuesta.
2. Nodo "start" LINEAL: nunca branches, siempre "next" al nodo distribuidor.
3. NODO DISTRIBUIDOR obligatorio tras start: primera gran pregunta, con branches a todos los caminos.
4. NINGUN NODO HUERFANO: grafo continuo desde start hasta todos los finales.
5. EXHAUSTIVIDAD: si el distribuidor tiene 6 branches, crea los 6 nodos destino.
6. Referencias exactas: el valor de "next" DEBE ser un id existente.
7. FALLBACK: opciones sin detalle → nodo "Tomo nota, te derivo" + nodo end.
8. Objeciones y FAQs NO van aqui.

Schema por nodo:
{{
  "id": "<snake_case unico>",
  "name": "<nombre legible>",
  "type": "<tipo>",
  "next": "<id_nodo o null>",
  "branches": [{{"condition": "<cuando>", "next": "<id_nodo>", "note": "<nota>"}}]
}}

DOCUMENTO:
---
{raw_md}
---

Produce: {{"flow": [<lista de nodos>]}}
"""

_P2B_CONTENT_SYS = "Eres un escritor de guiones para agentes conversacionales de venta. Output: JSON puro sin fences."
_P2B_CONTENT_USR = """\
Rellena el contenido de los nodos indicados. USA EXCLUSIVAMENTE frases literales del documento.

ESQUELETO COMPLETO DEL GRAFO (contexto de conexiones):
{skeleton_summary}

NODOS A COMPLETAR (ids): {batch_ids}

DOCUMENTO ORIGINAL:
---
{raw_md}
---

Por cada nodo indicado produce:
{{
  "id": "<mismo id del esqueleto>",
  "type": "<tipo>",
  "objective": "<que logra el agente en este nodo>",
  "script": ["<frase literal 1>", "<frase literal 2>"],
  "directives": ["<instruccion interna para el agente>"],
  "extractions": []
}}

Produce: {{"nodes": [<lista solo de los {n} nodos solicitados>]}}
"""

_REVIEWER_USR = """\
Eres un Auditor de Grafos Conversacionales. Tu único trabajo es arreglar y completar el flujo generado por otra IA.

DOCUMENTO ORIGINAL:
---
{raw_md}
---

FLUJO GENERADO (CON POSIBLES ERRORES):
---
{generated_flow}
---

INSTRUCCIONES DE AUDITORÍA:
1. NODOS FANTASMA: Revisa minuciosamente cada "branch" y cada "next". Si apuntan a un "id" que NO existe en la lista de nodos principal, CREA ese nodo faltante basándote en el documento original.
2. DESARROLLO INCOMPLETO: Si un camino se quedó a medias (por "pereza" de la IA anterior) y no llega hasta una resolución o una despedida, añade los nodos necesarios para terminar ese proceso según el manual.
3. CONEXIÓN: Asegúrate de que el nodo "start" conecta correctamente con el menú principal.

Devuelve ÚNICAMENTE el JSON corregido con la estructura estricta:
{{"flow": [<lista de nodos correcta y completa>]}}
"""

_P2C_SYS = "Eres un experto en objeciones de venta conversacional B2B outbound. Output: JSON puro."
_P2C_USR = """\
Extrae TODAS las objeciones del siguiente guion (explicitas E IMPLICITAS).

ANALISIS PREVIO: {analysis}
IDs DE NODOS DEL FLUJO (para el campo next_node): {flow_ids}

SCOPE posibles:
- global: puede aparecer en cualquier momento
- fase_apertura: solo antes de las preguntas/calificacion
- fase_preguntas: solo durante calificacion
- fase_cierre: solo en cierre/agendado

REGLAS CRITICAS:
1. Si la misma objecion tiene respuesta diferente segun la fase, creala DOS VECES con distinto id y scope.
2. Keywords: raices de UNA sola palabra, sin tildes ni espacios. Maximo 6 caracteres cuando sea posible.
3. is_global = true solo si puede aparecer en CUALQUIER momento de la llamada.
4. OBLIGATORIO inferir objeciones universales de llamada fria si aplican al contexto.

Por cada objecion:
{{
  "id": "<snake_case>",
  "name": "<titulo>",
  "trigger": "<como la expresa el prospecto>",
  "keywords": ["<raiz1>", "<raiz2>"],
  "scope": "<global|fase_apertura|fase_preguntas|fase_cierre>",
  "is_global": <true|false>,
  "response": "<respuesta del agente>",
  "directives": ["<instruccion interna>"],
  "next_node": "<id_nodo_flow donde continua>"
}}

DOCUMENTO:
---
{raw_md}
---

Produce: {{"objections": [<lista>]}}
"""

_P2D_SYS = "Eres un extractor de FAQs de guiones de agentes de venta. Output: JSON puro."
_P2D_USR = """\
Extrae las preguntas frecuentes que un prospecto puede hacer durante la llamada.

ANALISIS PREVIO: {analysis}

REGLAS CRITICAS:
1. Las FAQs son preguntas sobre el producto/servicio que el agente responde inline y luego retoma el flujo.
2. NO incluyas objeciones.
3. Infiere FAQs universales si el contexto lo permite (precios, duracion, empresa).

Por cada FAQ:
{{
  "id": "<snake_case>",
  "question": "<pregunta del prospecto>",
  "keywords": ["<raiz1>", "<raiz2>"],
  "scope": "global",
  "response": "<respuesta inline del agente>",
  "redirect_to_meeting": <true si la respuesta redirige a la reunion>
}}

DOCUMENTO:
---
{raw_md}
---

Produce: {{"faqs": [<lista>]}}
"""

_P2E_SYS = "Eres un experto en diseno de extraccion de datos en agentes conversacionales. Output: JSON puro."
_P2E_USR = """\
Infiere que datos debe capturar el agente durante y despues de la llamada.

ANALISIS PREVIO: {analysis}
NODOS DEL FLUJO: {flow_summary}

TIPOS: string | boolean | enum | number
Para enum incluye choices[].

Produce:
{{
  "node_extractions": [
    {{
      "node_id": "<id>",
      "extractions": [
        {{"name": "<var>", "type": "<tipo>", "description": "<que es>", "choices": []}}
      ]
    }}
  ],
  "post_call_extractions": [
    {{"name": "<var>", "type": "<tipo>", "description": "<que es>", "choices": []}}
  ]
}}

OBLIGATORIO en post_call_extractions si aplica:
- prospect_name (string)
- company_name (string)
- interest_level (enum: bajo|medio|alto)
- appointment_confirmed (boolean)
- objection_raised (string)

DOCUMENTO:
---
{raw_md}
---
"""

# ---------------------------------------------------------------------------
# LLM caller
# ---------------------------------------------------------------------------

def _call_llm(client, model, system, user, phase, max_retries=DEFAULT_MAX_RETRIES):
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=msgs,
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            raw = resp.choices[0].message.content or "{}"
            return json.loads(raw)
        except Exception as exc:
            last_exc = exc
            print(f"[{phase}] Intento {attempt} fallo: {exc}")
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"Fase {phase} fallo tras {max_retries} intentos: {last_exc}")

# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def phase1_analyze(client, model, raw_md):
    user = _P1_USR.format(raw_md=raw_md)
    return _call_llm(client, model, _P1_SYS, user, "phase1")

def phase2a_identity(client, model, raw_md, analysis):
    user = _P2A_USR.format(raw_md=raw_md, analysis=json.dumps(analysis, ensure_ascii=False))
    return _call_llm(client, model, _P2A_SYS, user, "phase2c")

def _flow_skeleton_summary(skeleton_nodes):
    lines = []
    for n in skeleton_nodes:
        conns = []
        if n.get("next"):
            conns.append(f"-> {n['next']}")
        for b in n.get("branches", []):
            conns.append(f"[{b.get('condition','?')}]->{b.get('next','?')}")
        lines.append(f"{n['id']} ({n.get('type','node')}): {', '.join(conns) or 'terminal'}")
    return "\n".join(lines)


_FLOW_BATCH_SIZE = 8

def phase2b_flow(client, model, raw_md, analysis):
    # --- Fase skeleton: solo grafo, sin contenido ---
    skeleton_user = _P2B_SKELETON_USR.format(
        raw_md=raw_md,
        analysis=json.dumps(analysis, ensure_ascii=False),
    )
    skeleton = _call_llm(client, model, _P2B_SKELETON_SYS, skeleton_user, "phase2b_skeleton")
    skeleton_nodes = skeleton.get("flow", [])

    # --- Reviewer sobre el esqueleto (JSON compacto, sin scripts) ---
    try:
        reviewer_messages = [
            {"role": "system", "content": "Eres un auditor estricto de grafos. Devuelve solo JSON valido."},
            {"role": "user", "content": _REVIEWER_USR.format(
                raw_md=raw_md,
                generated_flow=json.dumps(skeleton, ensure_ascii=False, indent=2),
            )},
        ]
        resp = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            temperature=0.1,
            messages=reviewer_messages,
        )
        skeleton = json.loads(resp.choices[0].message.content.strip())
        skeleton_nodes = skeleton.get("flow", skeleton_nodes)
    except Exception as e:
        print(f"    Auditoria omitida, usando esqueleto original: {e}")

    skeleton_summary = _flow_skeleton_summary(skeleton_nodes)

    # --- Fase contenido: lotes paralelos ---
    batches = [skeleton_nodes[i:i + _FLOW_BATCH_SIZE] for i in range(0, len(skeleton_nodes), _FLOW_BATCH_SIZE)]

    def process_batch(batch):
        batch_ids = [n["id"] for n in batch]
        user = _P2B_CONTENT_USR.format(
            skeleton_summary=skeleton_summary,
            batch_ids=", ".join(batch_ids),
            raw_md=raw_md,
            n=len(batch_ids),
        )
        result = _call_llm(client, model, _P2B_CONTENT_SYS, user, f"phase2b_content_{batch_ids[0]}")
        return {n["id"]: n for n in result.get("nodes", [])}

    content_map = {}
    with ThreadPoolExecutor(max_workers=min(len(batches), 6)) as executor:
        futures = {executor.submit(process_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            try:
                content_map.update(future.result())
            except Exception as exc:
                print(f"    Error en lote de contenido: {exc}")

    # --- Fusion esqueleto + contenido ---
    merged = []
    for skel in skeleton_nodes:
        nid = skel["id"]
        content = content_map.get(nid, {})
        merged.append({
            "id":          nid,
            "name":        skel.get("name", nid),
            "type":        content.get("type", skel.get("type", "conversational")),
            "objective":   content.get("objective", ""),
            "script":      content.get("script", []),
            "directives":  content.get("directives", []),
            "branches":    skel.get("branches", []),
            "next":        skel.get("next"),
            "extractions": content.get("extractions", []),
        })

    return {"flow": merged}

def phase2c_objections(client, model, raw_md, analysis, flow):
    flow_ids = [n.get("id", "?") for n in flow.get("flow", [])]
    user = _P2C_USR.format(raw_md=raw_md, analysis=json.dumps(analysis, ensure_ascii=False), flow_ids=", ".join(flow_ids))
    return _call_llm(client, model, _P2C_SYS, user, "phase2c")

def phase2d_faqs(client, model, raw_md, analysis):
    user = _P2D_USR.format(raw_md=raw_md, analysis=json.dumps(analysis, ensure_ascii=False))
    return _call_llm(client, model, _P2D_SYS, user, "phase2d")


# ---------------------------------------------------------------------------
# Funciones de generacion de extras (llamadas independientes post-extraccion)
# ---------------------------------------------------------------------------

_EXTRA_OBJ_SYS = "Eres un experto en objeciones de venta outbound. Output: JSON puro sin fences."
_EXTRA_OBJ_USR = """\
Genera {n} objeciones ADICIONALES de llamada fria para el siguiente agente.
NO repitas ninguna de las ya existentes.

AGENTE: {agent_info}
IDs DE NODOS DISPONIBLES (para next_node): {flow_ids}
OBJECIONES YA EXISTENTES (ids a evitar): {existing_ids}

Cada objecion debe tener el sufijo '_extra' en su id.
Mismo schema que las regulares:
{{
  "id": "<snake_case_extra>",
  "name": "<titulo>",
  "trigger": "<como la expresa el prospecto>",
  "keywords": ["<raiz1>", "<raiz2>"],
  "scope": "<global|fase_apertura|fase_preguntas|fase_cierre>",
  "is_global": <true|false>,
  "response": "<respuesta del agente>",
  "directives": ["<instruccion interna>"],
  "next_node": "<id_nodo_flow>"
}}

Produce: {{"objections": [<lista de {n} objeciones>]}}
"""

_EXTRA_FAQ_SYS = "Eres un experto en FAQs de agentes de venta conversacional. Output: JSON puro sin fences."
_EXTRA_FAQ_USR = """\
Genera {n} FAQs ADICIONALES que un prospecto podria hacer durante la llamada.
NO repitas ninguna de las ya existentes.

AGENTE: {agent_info}
FAQs YA EXISTENTES (preguntas a evitar): {existing_questions}

Cada FAQ debe tener el sufijo '_extra' en su id.
Mismo schema que las regulares:
{{
  "id": "<snake_case_extra>",
  "question": "<pregunta del prospecto>",
  "keywords": ["<raiz1>", "<raiz2>"],
  "scope": "global",
  "response": "<respuesta inline del agente>",
  "redirect_to_meeting": <true|false>
}}

Produce: {{"faqs": [<lista de {n} faqs>]}}
"""


def _agent_info_summary(analysis):
    return (
        f"Nombre: {analysis.get('agent_name', '?')} | "
        f"Empresa: {analysis.get('company_name', '?')} | "
        f"Objetivo: {analysis.get('primary_objective', '?')}"
    )


def generate_extra_objections(client, model, analysis, flow, existing_objections, n):
    flow_ids = ", ".join(node.get("id", "?") for node in flow.get("flow", []))
    existing_ids = ", ".join(o.get("id", "?") for o in existing_objections)
    user = _EXTRA_OBJ_USR.format(
        n=n,
        agent_info=_agent_info_summary(analysis),
        flow_ids=flow_ids or "N/A",
        existing_ids=existing_ids or "ninguna",
    )
    result = _call_llm(client, model, _EXTRA_OBJ_SYS, user, "extra_objections")
    return result.get("objections", [])


def generate_extra_faqs(client, model, analysis, existing_faqs, n):
    existing_questions = " | ".join(f.get("question", "?") for f in existing_faqs)
    user = _EXTRA_FAQ_USR.format(
        n=n,
        agent_info=_agent_info_summary(analysis),
        existing_questions=existing_questions or "ninguna",
    )
    result = _call_llm(client, model, _EXTRA_FAQ_SYS, user, "extra_faqs")
    return result.get("faqs", [])

def phase2e_extractions(client, model, raw_md, analysis, flow):
    flow_summary = json.dumps([{"id": n.get("id"), "name": n.get("name"), "type": n.get("type")} for n in flow.get("flow", [])], ensure_ascii=False)
    user = _P2E_USR.format(raw_md=raw_md, analysis=json.dumps(analysis, ensure_ascii=False), flow_summary=flow_summary)
    return _call_llm(client, model, _P2E_SYS, user, "phase2e")

# ---------------------------------------------------------------------------
# Ensamblado
# ---------------------------------------------------------------------------

def _fmt_list(items, indent=0):
    prefix = "  " * indent
    return "\n".join(f"{prefix}- {item}" for item in items) if items else f"{prefix}*(ninguna)*"

def _fmt_script(lines):
    if not lines:
        return "*(sin script)*"
    return "\n".join(f'  - "{l}"' for l in lines)

def _fmt_branches(branches):
    if not branches:
        return "  *(sin branches)*"
    out = []
    for b in branches:
        out.append(f"  - Si: {b.get('condition','?')} -> `{b.get('next','?')}`")
        if b.get("note"):
            out.append(f"    *(nota: {b['note']})*")
    return "\n".join(out)

def phase3_assemble(source_file, analysis, identity, flow, objections, faqs, extractions):
    agent = identity.get("agent", {})
    global_rules = identity.get("global_rules", [])
    audience = identity.get("audience_adaptation", [])
    nodes = flow.get("flow", [])
    obj_list = objections.get("objections", [])
    faq_list = faqs.get("faqs", [])
    
    node_exts = {
        e["node_id"]: e["extractions"]
        for e in extractions.get("node_extractions", [])
        if isinstance(e, dict) and e.get("node_id") and e.get("extractions")
    }
    post_exts = extractions.get("post_call_extractions", [])

    if isinstance(audience, dict):
        audience = [
            {"profile": k, "tone": v.get("Tono", v.get("tone", "")), "focus": v.get("Enfoque Principal", v.get("focus", ""))}
            for k, v in audience.items() if isinstance(v, dict)
        ]

    for node in nodes:
        nid = node.get("id")
        if nid in node_exts:
            node["extractions"] = node_exts[nid]

    parts = []
    parts.append(f"# GUION ESTRUCTURADO: {agent.get('name', '?')} - {agent.get('company', '?')}")
    parts.append(f"\n> Generado por pipeline | Fuente: `{source_file}` | Tipo: `{analysis.get('document_type', '?')}`\n")
    parts.append("---")

    parts.append("\n## 1. IDENTIDAD DEL AGENTE\n")
    parts.append(f"- **Nombre**: {agent.get('name', 'N/A')}")
    parts.append(f"- **Empresa**: {agent.get('company', 'N/A')}")
    parts.append(f"- **Objetivo**: {agent.get('objective', 'N/A')}")
    parts.append(f"- **Identidad percibida**: {agent.get('identity', 'N/A')}")
    parts.append(f"- **Estilo de voz**: {agent.get('style', 'N/A')}")
    guardrails = agent.get("guardrails", [])
    if guardrails:
        parts.append("- **Guardrails**:")
        parts.append(_fmt_list(guardrails, indent=1))

    parts.append("\n---\n\n## 2. REGLAS GLOBALES\n")
    parts.append(_fmt_list(global_rules) if global_rules else "*(ninguna detectada)*")

    parts.append("\n---\n\n## 3. ADAPTACION POR AUDIENCIA\n")
    if audience:
        parts.append("| Perfil | Tono | Enfoque Principal |")
        parts.append("|---|---|---|")
        for a in audience:
            parts.append(f"| {a.get('profile','?')} | {a.get('tone','?')} | {a.get('focus','?')} |")
    else:
        parts.append("*(no especificada)*")

    parts.append("\n---\n\n## 4. FLUJO PRINCIPAL\n")
    for i, node in enumerate(nodes, 1):
        nid = node.get("id", f"nodo_{i}")
        ntype = node.get("type", "conversational")
        nname = node.get("name", nid)
        parts.append(f"\n### [NODO-{i:02d}] {ntype} - {nname}\n")
        parts.append(f"**ID**: `{nid}`")
        parts.append(f"**Objetivo**: {node.get('objective', 'N/A')}\n")
        parts.append("**Script** (frases literales del agente):")
        parts.append(_fmt_script(node.get("script", [])))
        directives = node.get("directives", [])
        if directives:
            parts.append("\n**Directivas**:")
            parts.append(_fmt_list(directives, indent=1))
        exts = node.get("extractions", [])
        if exts:
            parts.append("\n**Extracciones en este nodo**:")
            for e in exts:
                if not isinstance(e, dict): continue
                choices_val = e.get("choices", [])
                choices = f" (opciones: {', '.join(str(c) for c in choices_val)})" if isinstance(choices_val, list) and choices_val else ""
                parts.append(f"  - `{e.get('name', '?')}` ({e.get('type','string')}){choices}: {e.get('description','')}")
        branches = node.get("branches", [])
        next_node = node.get("next")
        if branches:
            parts.append("\n**Branches (decision)**:")
            parts.append(_fmt_branches(branches))
        elif next_node:
            parts.append(f"\n**Rama siguiente**: -> `{next_node}`")
        parts.append("")

    parts.append("---\n\n## 5. OBJECIONES\n")
    if obj_list:
        for obj in obj_list:
            parts.append(f"\n### [OBJ] {obj.get('name', obj.get('id', '?'))}\n")
            parts.append(f"**ID**: `{obj.get('id', '?')}`")
            parts.append(f"**Alcance**: `{obj.get('scope', 'global')}` | **Es Global?**: {'Si' if obj.get('is_global') else 'No'}")
            parts.append(f"**Trigger**: {obj.get('trigger', 'N/A')}")
            kws = obj.get("keywords", [])
            if isinstance(kws, list) and kws:
                parts.append(f"**Keywords de deteccion**: `{'`, `'.join(kws)}`")
            parts.append(f"**Respuesta del agente**: {obj.get('response', 'N/A')}")
            directives = obj.get("directives", [])
            if directives:
                parts.append("**Directivas**:")
                parts.append(_fmt_list(directives, indent=1))
            if obj.get("next_node"):
                parts.append(f"**Continuar en**: -> `{obj['next_node']}`")
            parts.append("")
    else:
        parts.append("*(ninguna detectada)*")

    parts.append("---\n\n## 6. FAQs\n")
    if faq_list:
        for faq in faq_list:
            parts.append(f"\n### [FAQ] {faq.get('question', faq.get('id', '?'))}\n")
            parts.append(f"**ID**: `{faq.get('id', '?')}`")
            kws = faq.get("keywords", [])
            if kws:
                parts.append(f"**Keywords**: `{'`, `'.join(kws)}`")
            parts.append(f"**Respuesta inline**: {faq.get('response', 'N/A')}")
            if faq.get("redirect_to_meeting"):
                parts.append("**Redirige a reunion**: Si")
            parts.append("")
    else:
        parts.append("*(ninguna detectada)*")

    parts.append("---\n\n## 7. EXTRACCIONES POST-LLAMADA\n")
    if post_exts:
        for e in post_exts:
            if not isinstance(e, dict): continue
            choices_val = e.get("choices", [])
            choices = f" (opciones: {', '.join(str(c) for c in choices_val)})" if isinstance(choices_val, list) and choices_val else ""
            parts.append(f"- `{e.get('name', '?')}` ({e.get('type','string')}){choices}: {e.get('description','')}")
    else:
        parts.append("*(ninguna detectada)*")

    return "\n".join(parts) + "\n"

def run_structurer(raw_md_path, output_path, client, model=DEFAULT_MODEL, verbose=False, extra_faqs=0, extra_objections=0):
    if not os.path.exists(raw_md_path):
        print(f"Error: No se encuentra {raw_md_path}")
        return False

    with open(raw_md_path, 'r', encoding='utf-8') as f:
        raw_md = f.read()

    source_name = os.path.basename(raw_md_path)
    
    if verbose:
        print(f"Procesando estructuracion de: {source_name}")

    if verbose:
        print("  Fase 1: Analisis del documento...")
    analysis = phase1_analyze(client, model, raw_md)

    if verbose:
        print("  Fase 2B: Extrayendo esqueleto, auditando y rellenando contenido en paralelo...")
    flow = phase2b_flow(client, model, raw_md, analysis)
    if verbose:
        print(f"  Fase 2B completada: {len(flow.get('flow', []))} nodos.")

    if verbose:
        print("  Fases 2A/2C/2D/2E: Extraccion en paralelo...")
    results = {}
    tasks = {
        "identity":    lambda: phase2a_identity(client, model, raw_md, analysis),
        "objections":  lambda: phase2c_objections(client, model, raw_md, analysis, flow),
        "faqs":        lambda: phase2d_faqs(client, model, raw_md, analysis),
        "extractions": lambda: phase2e_extractions(client, model, raw_md, analysis, flow),
    }
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
                if verbose:
                    print(f"    Completado: {name}")
            except Exception as exc:
                print(f"    Error en {name}: {exc}")
                results[name] = {}

    # Extras: llamadas independientes que no tocan los prompts anteriores
    if extra_objections > 0:
        if verbose:
            print(f"  Extras: generando {extra_objections} objeciones adicionales...")
        try:
            extra_objs = generate_extra_objections(
                client, model, analysis, flow,
                results.get("objections", {}).get("objections", []),
                extra_objections,
            )
            results["objections"].setdefault("objections", []).extend(extra_objs)
            if verbose:
                print(f"    {len(extra_objs)} objeciones extra añadidas.")
        except Exception as exc:
            print(f"    Error generando objeciones extra: {exc}")

    if extra_faqs > 0:
        if verbose:
            print(f"  Extras: generando {extra_faqs} FAQs adicionales...")
        try:
            extra_fqs = generate_extra_faqs(
                client, model, analysis,
                results.get("faqs", {}).get("faqs", []),
                extra_faqs,
            )
            results["faqs"].setdefault("faqs", []).extend(extra_fqs)
            if verbose:
                print(f"    {len(extra_fqs)} FAQs extra añadidas.")
        except Exception as exc:
            print(f"    Error generando FAQs extra: {exc}")

    if verbose:
        print("  Fase 3: Ensamblando MD estructurado...")
    structured_md = phase3_assemble(
        source_file=source_name,
        analysis=analysis,
        identity=results.get("identity", {}),
        flow=flow,
        objections=results.get("objections", {}),
        faqs=results.get("faqs", {}),
        extractions=results.get("extractions", {}),
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(structured_md)
        
    if verbose:
        print(f"Exito. MD Estructurado guardado en: {output_path}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Estructurador de MD bruto a semantico")
    parser.add_argument("raw_md_path", help="Ruta al MD en bruto")
    parser.add_argument("output_path", help="Ruta de salida del MD estructurado")
    parser.add_argument("--faqs", type=int, default=0, dest="extra_faqs", help="FAQs extra a inferir mas alla de las del guion")
    parser.add_argument("--objections", type=int, default=0, dest="extra_objections", help="Objeciones extra universales a inferir mas alla de las del guion")
    parser.add_argument("--verbose", action="store_true", help="Activa el log detallado de procesos")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY no encontrada.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    run_structurer(args.raw_md_path, args.output_path, client, verbose=args.verbose,
                   extra_faqs=args.extra_faqs, extra_objections=args.extra_objections)