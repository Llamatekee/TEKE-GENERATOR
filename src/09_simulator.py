"""
Simulador de conversaciones del agente Tolvia.

Uso:
  python src/09_simulator.py <workflow_json> [--tests <tests_json>] [--scenarios N] [--verbose] [--output reporte.json] [--fix]

  Sin --tests: el usuario-LLM es libre (usa personas predefinidas).
  Con --tests:  el usuario-LLM sigue los escenarios del tests JSON.
  Con --fix:    intenta corregir los systemMessages de los nodos con errores y guarda una version nueva del workflow.
"""
import os
import sys
import re
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from dotenv import load_dotenv

MAX_TURNS = 20
DEFAULT_MODEL = "gpt-4o"

_FREE_PERSONAS = [
    "Director comercial B2B. Curioso pero esceptico. Poco tiempo. Respuestas cortas.",
    "CEO de startup. Interes genuino. Hace preguntas sobre el proceso y los resultados.",
    "Gerente ocupado. Se puede convencer si el pitch es claro y rapido.",
    "Prospecto que pide informacion por correo antes de comprometerse a nada.",
    "Prospecto que ya tiene proveedor pero esta abierto a escuchar si hay valor claro.",
    "Prospecto que objeta que no tiene presupuesto. Necesita ver ROI primero.",
    "Prospecto que no es el tomador de decisiones pero puede conectarte con quien sí lo es.",
]

# ---------------------------------------------------------------------------
# Carga y utilidades
# ---------------------------------------------------------------------------

def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _build_node_map(workflow_data):
    return {n["id"]: n["data"] for n in workflow_data.get("workflow", {}).get("nodes", [])}

def _get_start_id(node_map):
    return next((nid for nid, d in node_map.items() if d.get("nodeClass") == "start"), None)

def _get_conditional_nodes(node_map):
    return {nid: d for nid, d in node_map.items() if d.get("type") == "conversational_conditional"}

def _check_conditionals(text, conditional_nodes):
    lower = text.lower()
    for nid, data in conditional_nodes.items():
        for rule in data.get("rules", []):
            for group in rule.get("conditions", {}).get("groups", []):
                for cond in group.get("conditions", []):
                    kw = cond.get("value", "").lower()
                    if kw and kw in lower:
                        return nid, data.get("name", nid)
    return None, None

def _history_text(history):
    return "\n".join(f"{'AGENTE' if m['role']=='assistant' else 'USUARIO'}: {m['content']}" for m in history)

# ---------------------------------------------------------------------------
# Llamadas LLM
# ---------------------------------------------------------------------------

def _call(client, system, user, temperature=0.7, model=DEFAULT_MODEL):
    resp = client.chat.completions.create(
        model=model, temperature=temperature,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}]
    )
    return resp.choices[0].message.content.strip()

def _call_json(client, system, user, model=DEFAULT_MODEL):
    resp = client.chat.completions.create(
        model=model, temperature=0.0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}]
    )
    return json.loads(resp.choices[0].message.content)

# ---------------------------------------------------------------------------
# Roles de la simulacion
# ---------------------------------------------------------------------------

def _agent_speak(client, node_data, history, model=DEFAULT_MODEL):
    system_msg = node_data.get("systemMessage", "")
    if not system_msg:
        return None
    system = (
        "Eres un agente de ventas conversacional de voz. "
        "Sigue ESTRICTAMENTE las instrucciones de tu nodo. "
        "USA las frases literales del script cuando las haya. "
        "NO improvises ni respondas a cortesias sociales: ve directo al script.\n\n"
        + system_msg
    )
    user = (
        f"Historial:\n{_history_text(history)}\n\nGenera tu proxima respuesta como agente."
        if history else "Genera la primera respuesta del agente."
    )
    return _call(client, system, user, temperature=0.3, model=model)

def _user_speak(client, agent_utterance, history, persona, model=DEFAULT_MODEL):
    system = (
        f"Eres un prospecto en una llamada de ventas. Perfil: {persona}\n"
        "Responde de forma NATURAL y BREVE, como en una llamada real. "
        "No hagas preguntas largas. Reacciona a lo que acaba de decir el agente."
    )
    user = (
        f"Historial:\n{_history_text(history)}\n\n"
        f"EL AGENTE ACABA DE DECIR:\n{agent_utterance}\n\n¿Que respondes?"
    )
    return _call(client, system, user, temperature=0.8, model=model)

def _route(client, node_data, agent_text, user_text, model=DEFAULT_MODEL):
    connector = node_data.get("connector")
    branches = node_data.get("branches", [])

    if connector and not branches:
        return connector, None

    if not branches:
        return None, None

    options = "\n".join(f"- id: {b['id']} | condicion: {b['name']} | siguiente: {b['next']}" for b in branches)
    result = _call_json(client,
        "Eres un router de flujo conversacional. Output: JSON puro.",
        f'Agente dijo: "{agent_text}"\nUsuario respondio: "{user_text}"\n\nRamas:\n{options}\n\n'
        '¿Que rama se debe tomar? {"branch_id":"...","next_node":"...","reason":"..."}'
    )
    return result.get("next_node"), result.get("branch_id")

def _analyze_agent_turn(client, node_data, agent_text, model=DEFAULT_MODEL):
    system_msg = node_data.get("systemMessage", "")
    if not system_msg:
        return []
    result = _call_json(client,
        "Eres un auditor de calidad de agentes de voz. Output: JSON puro.",
        f"INSTRUCCIONES DEL NODO:\n{system_msg}\n\n"
        f"LO QUE DIJO EL AGENTE:\n{agent_text}\n\n"
        "Detecta SOLO errores reales. Tipos posibles: "
        "script_ignorado, pitch_omitido, pregunta_multiple, cortesia_respondida, improvisacion.\n"
        '{"errors":[{"type":"...","description":"..."}],"ok":true}'
    )
    return result.get("errors", [])

# ---------------------------------------------------------------------------
# Simulacion de un escenario
# ---------------------------------------------------------------------------

def run_simulation(client, workflow_data, scenario, model=DEFAULT_MODEL):
    node_map = _build_node_map(workflow_data)
    conditional_nodes = _get_conditional_nodes(node_map)
    start_id = _get_start_id(node_map)
    if not start_id:
        return {"scenario": scenario["name"], "error": "No se encontro nodo start", "errors": []}

    agent_config = workflow_data.get("agentConfig", {})
    answer_phrase = agent_config.get("answerPhrase", "")
    persona = scenario.get("persona", "Prospecto B2B generico.")
    expected_path = scenario.get("expected_path", [])

    history = []
    all_errors = []
    route_taken = [start_id]
    turns = 0

    # La answerPhrase es el primer turno del agente (fuera del loop)
    if answer_phrase:
        history.append({"role": "assistant", "content": answer_phrase})
        user_reply = _user_speak(client, answer_phrase, history, persona, model=model)
        history.append({"role": "user", "content": user_reply})

    # Primer nodo conversacional
    current_id = node_map[start_id].get("connector")

    while current_id and turns < MAX_TURNS:
        node_data = node_map.get(current_id, {})
        turns += 1

        # Agente habla
        agent_text = _agent_speak(client, node_data, history, model=model)
        if not agent_text:
            current_id = node_data.get("connector")
            continue

        history.append({"role": "assistant", "content": agent_text})

        # Analizar calidad del turno del agente
        errors = _analyze_agent_turn(client, node_data, agent_text, model=model)
        for e in errors:
            e["node"] = current_id
            e["node_name"] = node_data.get("name", current_id)
            all_errors.append(e)

        # Nodo end: no esperar respuesta del usuario
        if node_data.get("isEndNode") or not node_data.get("branches") and not node_data.get("connector"):
            route_taken.append(current_id)
            break

        # Usuario responde
        user_text = _user_speak(client, agent_text, history, persona, model=model)
        history.append({"role": "user", "content": user_text})

        # Verificar condicionales
        cond_id, cond_name = _check_conditionals(user_text, conditional_nodes)
        if cond_id:
            route_taken.append(f"[COND:{cond_name}]")

        # Routear siguiente nodo
        next_id, branch_taken = _route(client, node_data, agent_text, user_text, model=model)

        route_taken.append(current_id)

        # Verificar vs ruta esperada
        if expected_path:
            idx = len(route_taken) - 1
            if idx < len(expected_path) and next_id and next_id != expected_path[idx]:
                all_errors.append({
                    "node": current_id,
                    "node_name": node_data.get("name", current_id),
                    "type": "ruta_incorrecta",
                    "description": f"Esperado: '{expected_path[idx]}' | Real: '{next_id}'"
                })

        current_id = next_id

    if turns >= MAX_TURNS:
        all_errors.append({
            "node": current_id or "?",
            "node_name": node_map.get(current_id or "", {}).get("name", "?"),
            "type": "bucle_o_timeout",
            "description": f"Se alcanzo el limite de {MAX_TURNS} turnos sin llegar a un nodo end"
        })

    return {
        "scenario": scenario["name"],
        "turns": turns,
        "route": " → ".join(route_taken),
        "errors": all_errors,
        "transcript": history,
    }

# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------

def print_report(results):
    sep = "=" * 62
    print(f"\n{sep}\nREPORTE DE SIMULACION\n{sep}")
    total_errors = 0
    for r in results:
        print(f"\n{sep}")
        print(f"ESCENARIO : {r.get('scenario', '?')}")
        print(f"Turnos    : {r.get('turns', 0)}")
        print(f"Ruta      : {r.get('route', '?')}")
        errors = r.get("errors", [])
        total_errors += len(errors)
        if not errors:
            print("RESULTADO : Sin errores detectados ✓")
        else:
            print(f"RESULTADO : {len(errors)} error(es) ✗")
            for e in errors:
                print(f"  [{e.get('node_name', e.get('node', '?'))}] "
                      f"{e['type']}: {e['description']}")
    print(f"\n{sep}")
    print(f"Total: {len(results)} escenario(s) | {total_errors} error(es) detectado(s)")
    print(sep)

# ---------------------------------------------------------------------------
# Auto-fix
# ---------------------------------------------------------------------------

# Patrones de falsos positivos que no se deben intentar corregir
_FP_PATTERNS = [
    r"\{available_slot",
    r"\{user_first_name",
    r"\{user_is_female",
    r"\{company",
    r"\{position",
    r"\{Job Title",
    r"marcador de posici",
    r"variable de template",
    r"placeholder",
]

def _is_false_positive(error):
    desc = error.get("description", "").lower()
    return any(re.search(p, desc, re.IGNORECASE) for p in _FP_PATTERNS)

def _versioned_path(original_path):
    """Genera el siguiente nombre versionado: nombre_v1.json, nombre_v2.json, ..."""
    base = re.sub(r'_v\d+$', '', original_path.replace('.json', ''))
    v = 1
    while os.path.exists(f"{base}_v{v}.json"):
        v += 1
    return f"{base}_v{v}.json"

def _fix_node_system_message(client, current_sm, errors, model=DEFAULT_MODEL):
    error_list = "\n".join(f"- {e['type']}: {e['description']}" for e in errors)
    fixed = _call(client,
        "Eres un experto en systemMessages para agentes de voz Tolvia. "
        "Devuelve SOLO el systemMessage corregido, sin explicaciones ni markdown. "
        "Conserva toda la estructura y contenido valido existente. "
        "Solo modifica lo estrictamente necesario para solucionar los errores indicados.",
        f"ERRORES A CORREGIR:\n{error_list}\n\n"
        f"SYSTEM MESSAGE ACTUAL:\n{current_sm}",
        temperature=0.2, model=model,
    )
    return fixed

def apply_fixes(client, workflow_data, results, workflow_path, model=DEFAULT_MODEL, verbose=False):
    # Agrupar errores reales por node_id
    errors_by_node = {}
    for r in results:
        for e in r.get("errors", []):
            if _is_false_positive(e):
                continue
            nid = e.get("node")
            if nid:
                errors_by_node.setdefault(nid, []).append(e)

    if not errors_by_node:
        print("\nNo hay errores corregibles (todos son falsos positivos o variables de template).")
        return

    print(f"\nCorrigiendo {len(errors_by_node)} nodo(s) con errores reales...")

    # Construir mapa node_id → indice en workflow nodes
    node_index = {n["id"]: i for i, n in enumerate(workflow_data["workflow"]["nodes"])}

    def fix_node(nid, errors):
        idx = node_index.get(nid)
        if idx is None:
            return nid, None
        current_sm = workflow_data["workflow"]["nodes"][idx]["data"].get("systemMessage", "")
        if not current_sm:
            return nid, None
        fixed_sm = _fix_node_system_message(client, current_sm, errors, model=model)
        return nid, fixed_sm

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fix_node, nid, errs): nid for nid, errs in errors_by_node.items()}
        for future in as_completed(futures):
            nid = futures[future]
            try:
                nid, fixed_sm = future.result()
                if fixed_sm:
                    idx = node_index[nid]
                    workflow_data["workflow"]["nodes"][idx]["data"]["systemMessage"] = fixed_sm
                    if verbose:
                        node_name = workflow_data["workflow"]["nodes"][idx]["data"].get("name", nid)
                        print(f"  Corregido: {node_name}")
            except Exception as exc:
                print(f"  Error corrigiendo {nid}: {exc}")

    output_path = _versioned_path(workflow_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(workflow_data, f, indent=2, ensure_ascii=False)
    print(f"Workflow corregido guardado en: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY no encontrada.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Simulador de conversaciones del agente Tolvia")
    parser.add_argument("workflow_json", help="Ruta al workflow JSON generado")
    parser.add_argument("--tests", help="Ruta al tests JSON (usa sus escenarios como personas)")
    parser.add_argument("--scenarios", type=int, default=3, help="Numero de escenarios libres si no hay --tests (default: 3)")
    parser.add_argument("--verbose", action="store_true", help="Muestra los transcripts completos")
    parser.add_argument("--output", help="Guarda el reporte en un JSON (opcional)")
    parser.add_argument("--fix", action="store_true", help="Intenta corregir los nodos con errores y guarda una version nueva del workflow")
    args = parser.parse_args()

    client = OpenAI(api_key=api_key)
    workflow_data = _load_json(args.workflow_json)
    agent_name = workflow_data.get("agentName", workflow_data.get("agentConfig", {}).get("name", "Agente"))
    print(f"Agente: {agent_name}")

    # Construir escenarios
    scenarios = []
    if args.tests:
        tests_data = _load_json(args.tests)
        for sc in tests_data.get("scenarios", [])[:args.scenarios]:
            steps = sc.get("expected_agent_flow_with_commands", {}).get("steps", [])
            scenarios.append({
                "name": sc.get("name", sc.get("id", "?")),
                "persona": sc.get("description", "Prospecto B2B."),
                "expected_path": [s.get("node", "") for s in steps if s.get("node")],
            })
    
    needed = args.scenarios - len(scenarios)
    for i in range(needed):
        scenarios.append({
            "name": f"Libre-{i + 1}",
            "persona": _FREE_PERSONAS[i % len(_FREE_PERSONAS)],
            "expected_path": [],
        })

    print(f"Ejecutando {len(scenarios)} escenario(s) en paralelo...\n")

    results = []
    with ThreadPoolExecutor(max_workers=min(len(scenarios), 3)) as executor:
        futures = {executor.submit(run_simulation, client, workflow_data, sc): sc["name"] for sc in scenarios}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"scenario": name, "turns": 0, "route": "?",
                                 "errors": [{"type": "excepcion", "description": str(exc), "node": "?", "node_name": "?"}],
                                 "transcript": []})

    results.sort(key=lambda r: r.get("scenario", ""))
    print_report(results)

    if args.verbose:
        for r in results:
            sep = "-" * 62
            print(f"\n{sep}\nTRANSCRIPT: {r.get('scenario')}\n{sep}")
            for msg in r.get("transcript", []):
                role = "AGENTE" if msg["role"] == "assistant" else "USUARIO"
                print(f"\n{role}:\n{msg['content']}")

    if args.output:
        report = [{"scenario": r["scenario"], "route": r.get("route"), "errors": r["errors"]} for r in results]
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nReporte guardado en: {args.output}")

    if args.fix:
        apply_fixes(client, workflow_data, results, args.workflow_json,
                    model=DEFAULT_MODEL, verbose=args.verbose)

if __name__ == "__main__":
    main()
