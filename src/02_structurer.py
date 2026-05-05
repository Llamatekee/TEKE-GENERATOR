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
2. EL NODO "start" ES ESTRICTAMENTE LINEAL. NUNCA le anadas "branches". Siempre debe avanzar usando "next" hacia el siguiente nodo.
3. DESGLOSE DE EXTRACCIONES: NUNCA agrupes multiples preguntas de precalificacion o extraccion de datos en un solo nodo. Cada pregunta (ej. modelo de venta, canal, dolor, etc.) DEBE ser un nodo de tipo "extractor" independiente, conectados uno tras otro secuencialmente con "next".
4. Cada punto de decision importante = nodo separado.
5. Objeciones y FAQs NO van aqui, tienen su propia seccion.

TIPOS:
- start: unico nodo inicial (Lineal, usar "next").
- conversational: agente habla y espera respuesta con posibles branches.
- conversational_linear: agente habla y avanza automaticamente sin evaluar.
- extractor: recoge UN SOLO dato del prospecto (Lineal, usar "next").
- end: SOLO para despedidas finales donde se cuelga.

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
    return _call_llm(client, model, _P2A_SYS, user, "phase2a")

def phase2b_flow(client, model, raw_md, analysis):
    user = _P2B_USR.format(raw_md=raw_md, analysis=json.dumps(analysis, ensure_ascii=False))
    return _call_llm(client, model, _P2B_SYS, user, "phase2b")

def phase2c_objections(client, model, raw_md, analysis, flow):
    flow_ids = [n.get("id", "?") for n in flow.get("flow", [])]
    user = _P2C_USR.format(raw_md=raw_md, analysis=json.dumps(analysis, ensure_ascii=False), flow_ids=", ".join(flow_ids))
    return _call_llm(client, model, _P2C_SYS, user, "phase2c")

def phase2d_faqs(client, model, raw_md, analysis):
    user = _P2D_USR.format(raw_md=raw_md, analysis=json.dumps(analysis, ensure_ascii=False))
    return _call_llm(client, model, _P2D_SYS, user, "phase2d")

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

def run_structurer(raw_md_path, output_path, client, model=DEFAULT_MODEL, verbose=False):
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
        print("  Fase 2B: Extrayendo flujo principal...")
    flow = phase2b_flow(client, model, raw_md, analysis)

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
    parser.add_argument("--verbose", action="store_true", help="Activa el log detallado de procesos")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY no encontrada.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    run_structurer(args.raw_md_path, args.output_path, client, verbose=args.verbose)