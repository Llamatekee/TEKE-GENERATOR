import os
import json
import argparse
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def add_conditionals(md_path, input_json_path, output_json_path):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: Falta 'OPENAI_API_KEY' en el .env")
        return

    # 1. Leer archivos
    try:
        with open(md_path, 'r', encoding='utf-8') as f: md_content = f.read()
        with open(input_json_path, 'r', encoding='utf-8') as f: workflow_json = json.load(f)
    except FileNotFoundError as e:
        print(f"❌ Error leyendo archivos: {str(e)}")
        return

    print("🧠 1. GPT extrayendo Objeciones y FAQs en formato limpio...")
    client = OpenAI(api_key=api_key)

    system_prompt = """
    Eres un analizador de datos. Lee el Markdown y extrae SOLO las secciones "5. OBJECIONES" y "6. FAQs".
    
    Devuelve un JSON estricto con esta estructura:
    {
      "conditionals": [
        {
          "id": "<ID único, ej. obj_tiempo o faq_precio>",
          "name": "<Nombre de la objeción o FAQ>",
          "keywords": ["<palabra1>", "<palabra2>", "<palabra3>"],
          "systemMessage": "<Formatea la respuesta y directivas juntas. Empieza siempre con 'GESTIÓN DE OBJECIÓN:' o 'FAQ INLINE:', luego pon la frase literal que dice el agente, y termina con la directiva (ej. 'y continúa por donde ibas').>"
        }
      ]
    }
    
    REGLA CLAVE PARA KEYWORDS: Extrae la raíz de la palabra para maximizar coincidencias. 
    Ejemplo: Para "correo", usa "corre". Para "ocupado", usa "ocup". Para "LinkedIn", usa "linkedin". Incluye siempre 3 o 4 variaciones lógicas.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={ "type": "json_object" },
            temperature=0.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extrae condicionales del MD:\n\n{md_content}"}
            ]
        )
        parsed_data = json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ Error API: {str(e)}")
        return

    print("🏗️ 2. Python construyendo los Nodos Condicionales y sus Reglas Lógicas...")
    
    # Coordenadas para poner estos nodos flotantes abajo o a un lado del flujo principal
    x_pos = 0
    y_pos = 1200 
    
    conditional_nodes = []
    
    for cond in parsed_data.get("conditionals", []):
        node_id = f"node-{cond['id']}"
        data_id = f"data-{cond['id']}"
        
        # --- CONSTRUCCIÓN DEL ÁRBOL DE REGLAS (React Flow Logic) ---
        # Por cada keyword, creamos un grupo OR independiente a nivel raíz
        rules = []
        for kw in cond.get("keywords", []):
            rule = {
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
            }
            rules.append(rule)

        # --- ENSAMBLAJE DEL NODO CONDICIONAL ---
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
                "rules": rules,  # Aquí inyectamos la lógica
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
        
        # Posicionamiento visual
        x_pos += 450
        if x_pos > 1800:
            x_pos = 0
            y_pos += 400

    # 3. Inyectar en el JSON principal (sin tocar lo que ya existe)
    workflow_json["workflow"]["nodes"].extend(conditional_nodes)
    # No hace falta tocar los "edges" porque estos nodos interceptan por variables, no por cables

    with open(output_json_path, 'w', encoding='utf-8') as out_file:
        json.dump(workflow_json, out_file, indent=2, ensure_ascii=False)
        
    print(f"✅ ¡Éxito! Objeciones y FAQs añadidas. Workflow finalizado en: {output_json_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_md", help="Markdown con el diseño del Agente")
    parser.add_argument("input_json", help="JSON del workflow base (generado en el paso anterior)")
    parser.add_argument("output_json", help="Nombre del JSON final con todo incluido")
    args = parser.parse_args()
    add_conditionals(args.input_md, args.input_json, args.output_json)