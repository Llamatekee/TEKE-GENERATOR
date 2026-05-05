import json

def add_conditionals(md_content, input_json_path, output_json_path, client):
    print("Ejecutando Paso 3: Procesamiento y anclaje de objeciones y FAQs...")
    
    system_prompt = """
    Eres un analizador de datos. Lee el Markdown y extrae SOLO las secciones "5. OBJECIONES" y "6. FAQs".
    Es vital que extraigas todas las opciones presentes en el documento.
    
    Devuelve un JSON estricto con esta estructura:
    {
      "conditionals": [
        {
          "id": "<ID unico, ej. obj_tiempo o faq_precio>",
          "name": "<Nombre de la objecion o FAQ>",
          "keywords": ["<raiz1>", "<raiz2>", "<raiz3>"],
          "systemMessage": "<Formatea la respuesta y directivas juntas. Empieza siempre con 'GESTION DE OBJECION:' o 'FAQ INLINE:', luego pon la frase literal que dice el agente, y termina con la directiva (ej. 'y continua por donde ibas').>"
        }
      ]
    }
    
    REGLA CLAVE PARA KEYWORDS: Extrae la raiz de la palabra para maximizar coincidencias. 
    Ejemplo: Para 'correo', usa 'corre'. Para 'ocupado', usa 'ocup'. Para 'LinkedIn', usa 'linkedin'. Incluye siempre 3 o 4 variaciones logicas.
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