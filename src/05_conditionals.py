import json

def add_conditionals(md_content, input_json_path, output_json_path, client, verbose=False):
    if verbose:
        print("[Paso 5] Procesamiento y anclaje de objeciones y FAQs...")
    
    system_prompt = """
    Eres un analizador de datos. Lee el Markdown y extrae SOLO las secciones "5. OBJECIONES" y "6. FAQs".
    Es vital que extraigas todas las opciones presentes en el documento.
    
    Devuelve un JSON estricto con esta estructura:
    {
      "conditionals": [
        {
          "id": "<ID unico, ej. obj_tiempo o faq_precio>",
          "name": "<Nombre de la objecion o FAQ>",
          "keywords": ["<raiz1>", "<raiz2>", "<raiz3>", "<raiz4>", "<raiz5>", "<raiz6>"],
          "systemMessage": "<Empieza con 'GESTION DE OBJECION:' o 'FAQ INLINE:', luego la frase literal del agente, termina con la directiva (ej. 'y continua por donde ibas').>"
        }
      ]
    }
    
    REGLAS PARA KEYWORDS (MINIMO 6, MAXIMO 8 por condicional):
    - Extrae la raiz de la palabra para maximizar coincidencias: 'correo' -> 'corre', 'ocupado' -> 'ocup'.
    - Incluye sinonimos y variantes: si la objecion es sobre tiempo, incluye raices de 'tiempo', 'ahora', 'momento', 'prisa', 'rapido', 'luego'.
    - Incluye variantes en distinto idioma si el prospecto puede hablar en otro: 'time', 'busy', 'later'.
    - Incluye formas verbales distintas: 'llama' y 'llamo' son raices distintas, incluye ambas si aplican.
    - Si el trigger tiene una palabra muy especifica (nombre propio, marca), incluye esa palabra completa ademas de su raiz.
    - Nunca repitas la misma raiz dos veces. Cada keyword debe aportar cobertura nueva.
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Extrae todas las condicionales del MD a formato JSON:\n\n{md_content}"}
        ]
    )
    parsed_data = json.loads(response.choices[0].message.content)

    with open(input_json_path, 'r', encoding='utf-8') as f:
        workflow_json = json.load(f)
    
    x_pos, y_pos = 0, 1200 
    conditional_nodes = []
    
    for cond in parsed_data.get("conditionals", []):
        node_id = f"node-{cond['id']}"
        data_id = f"data-{cond['id']}"
        
        rules = []
        for kw in cond.get("keywords", []):
            rules.append({
                "conditions": {
                    "groups": [
                        {
                            "operator": "AND", 
                            "conditions": [
                                {
                                    "value": kw.lower(), 
                                    "operator": "contains", 
                                    "variable": "{{_chat_history_3}}", 
                                    "valueType": "string"
                                }
                            ]
                        }
                    ], 
                    "operator": "AND"
                },
                "description": ""
            })

        module_card = {
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
        }
        conditional_nodes.append(module_card)
        
        x_pos += 450
        if x_pos > 1800:
            x_pos = 0
            y_pos += 400

    workflow_json["workflow"]["nodes"].extend(conditional_nodes)

    with open(output_json_path, 'w', encoding='utf-8') as out_file:
        json.dump(workflow_json, out_file, indent=2, ensure_ascii=False)