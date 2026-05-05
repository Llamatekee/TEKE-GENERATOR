import os
import sys
import json
import re

def extract_workflow_context(workflow_data):
    context = {"nodes": [], "agent_name": "", "agent_objective": ""}

    meta = workflow_data.get("metadata", {})
    context["agent_name"] = meta.get("agent_name", meta.get("name", ""))
    context["agent_objective"] = meta.get("objective", meta.get("description", ""))

    nodes = workflow_data.get("workflow", {}).get("nodes", [])
    for n in nodes:
        ndata = n.get("data", {})
        node_info = {
            "name": ndata.get("name", ""),
            "nodeClass": ndata.get("nodeClass", ""),
            "description": ndata.get("description", ""),
            "script": ndata.get("script", []),
            "branches": [b.get("name") for b in ndata.get("branches", [])],
        }
        context["nodes"].append(node_info)

    return context

def _call_llm_json(client, messages):
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=messages
    )
    raw_output = response.choices[0].message.content
    return re.sub(r"```(?:json)?\s*|\s*```", "", raw_output.strip())

def generate_base_structure(client, md_content):
    prompt = f"""
    Eres un QA Engineer. Extrae TODA la informacion del siguiente Markdown y genera la estructura base de un JSON de pruebas.
    
    REGLAS CRITICAS:
    1. Extrae y copia EXACTAMENTE todos los valores de 'metadata' y 'scoring_template'. PROHIBIDO dejarlos vacios ({{}}).
    2. Extrae todos los 'global_criteria', incluyendo los 'RF' (marcandolos con "penalty": true).
    3. No incluyas el array de 'scenarios' aqui.
    
    MARKDOWN:
    {md_content}
    
    Devuelve SOLO un JSON con las claves: "metadata", "global_criteria", y "scoring_template".
    """
    messages = [
        {"role": "system", "content": "Devuelve estrictamente JSON sin formato markdown."},
        {"role": "user", "content": prompt}
    ]
    return json.loads(_call_llm_json(client, messages))

def generate_base_structure_from_workflow(client, wf_context):
    prompt = f"""
    Eres un QA Engineer experto en agentes conversacionales.
    A partir de la estructura, genera la base de un JSON de test suite.
    
    AGENTE:
    - Nombre: {wf_context.get("agent_name", "Agente")}
    - Nodos: {json.dumps([n["name"] for n in wf_context["nodes"]], ensure_ascii=False)}
    
    INSTRUCCIONES:
    1. metadata: agent_name, version (1.0), description, created_at (auto-generated).
    2. global_criteria: al menos 5 criterios (claridad, empatia, objeciones, cierre, flujo).
    3. scoring_template: max_score (100), passing_score (70), weights, y penalty_rules.
    
    Devuelve SOLO un JSON con las claves: "metadata", "global_criteria", "scoring_template".
    """
    messages = [
        {"role": "system", "content": "Devuelve estrictamente JSON sin formato markdown."},
        {"role": "user", "content": prompt}
    ]
    return json.loads(_call_llm_json(client, messages))

def parse_md_scenarios(md_content):
    parts = re.split(r'(?=\n### SC-\d+)', md_content)
    scenarios = [p.strip() for p in parts if bool(re.search(r'^### SC-\d+', p.strip()))]
    return scenarios

def validate_branches(scenario_json, wf_context):
    errors = []
    steps = scenario_json.get("expected_agent_flow_with_commands", {}).get("steps", [])

    for step in steps:
        node_name = step.get("node")
        branch_name = step.get("expected_branch")
        node_info = next((n for n in wf_context["nodes"] if n["name"] == node_name), None)

        if not node_info:
            errors.append(f"El nodo '{node_name}' NO EXISTE en el workflow.")
            continue

        if branch_name is not None:
            valid_branches = node_info.get("branches", [])
            if branch_name not in valid_branches:
                errors.append(f"La rama '{branch_name}' NO EXISTE en el nodo '{node_name}'.")

    return errors

def generate_single_scenario(client, scenario_md, wf_context, max_retries=3):
    base_prompt = f"""
    Convierte este escenario en un objeto JSON.
    
    REGLA DE MAPEO: En "expected_branch" DEBES usar un string que exista en el WORKFLOW REAL:
    {json.dumps(wf_context, ensure_ascii=False)}
    Si es el ultimo nodo o no tiene ramas, pon null.

    ESCENARIO:
    {scenario_md}
    
    Devuelve SOLO un objeto JSON con la estructura completa del escenario.
    """
    messages = [
        {"role": "system", "content": "Devuelve estrictamente un objeto JSON valido."},
        {"role": "user", "content": base_prompt}
    ]

    last_json = None
    for _ in range(max_retries):
        try:
            raw_output = _call_llm_json(client, messages)
            scenario_json = json.loads(raw_output)
            last_json = scenario_json

            errors = validate_branches(scenario_json, wf_context)
            if not errors:
                return scenario_json
            
            error_feedback = "Corrige estos errores de mapeo contra el workflow real:\n" + "\n".join(errors)
            messages.append({"role": "assistant", "content": raw_output})
            messages.append({"role": "user", "content": error_feedback})
        except Exception:
            messages.append({"role": "user", "content": "JSON invalido. Intentalo de nuevo."})

    return last_json

def generate_synthetic_scenario(client, wf_context, existing_scenarios, scenario_index, total_scenarios, max_retries=3):
    existing_summary = ""
    if existing_scenarios:
        existing_summary = "ESCENARIOS EXISTENTES:\n"
        for sc in existing_scenarios:
            existing_summary += f"- {sc.get('id')} '{sc.get('name')}'\n"

    prompt = f"""
    Crea el escenario sintético {scenario_index} de {total_scenarios}.
    
    WORKFLOW REAL:
    {json.dumps(wf_context, ensure_ascii=False)}

    {existing_summary}

    INSTRUCCIONES:
    1. Crea un escenario NUEVO y realista.
    2. USA UNICAMENTE los nodos y ramas del WORKFLOW REAL.
    3. Asigna el ID: "SC-{scenario_index:02d}".
    """
    messages = [
        {"role": "system", "content": "Devuelve estrictamente un objeto JSON valido."},
        {"role": "user", "content": prompt}
    ]

    last_json = None
    for _ in range(max_retries):
        try:
            raw_output = _call_llm_json(client, messages)
            scenario_json = json.loads(raw_output)
            scenario_json["id"] = f"SC-{scenario_index:02d}"
            last_json = scenario_json

            errors = validate_branches(scenario_json, wf_context)
            if not errors:
                return scenario_json

            error_feedback = "Corrige estos errores:\n" + "\n".join(errors)
            messages.append({"role": "assistant", "content": raw_output})
            messages.append({"role": "user", "content": error_feedback})
        except Exception:
            messages.append({"role": "user", "content": "JSON invalido. Intentalo de nuevo."})

    return last_json

def generate_tests(md_path, workflow_path, output_path, total_tests, client, verbose=False):
    if verbose:
        print("[Paso 6] Generando escenarios de QA...")
    
    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow_data = json.load(f)

    wf_context = extract_workflow_context(workflow_data)
    md_content = None

    if md_path and os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()

    final_json = generate_base_structure(client, md_content) if md_content else generate_base_structure_from_workflow(client, wf_context)
    final_json["scenarios"] = []
    scenarios = []

    if md_content:
        scenario_blocks = parse_md_scenarios(md_content)
        for block in scenario_blocks:
            scenario_data = generate_single_scenario(client, block, wf_context)
            if scenario_data:
                scenarios.append(scenario_data)

    if total_tests is not None:
        needed = total_tests - len(scenarios)
        for i in range(needed):
            next_idx = len(scenarios) + 1
            synthetic = generate_synthetic_scenario(client, wf_context, scenarios, next_idx, total_tests)
            if synthetic:
                scenarios.append(synthetic)

    final_json["scenarios"] = scenarios

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_json, f, indent=4, ensure_ascii=False)