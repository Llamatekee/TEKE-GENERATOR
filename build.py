import os
import json
import argparse
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def build_workflow(md_path, base_json_path, output_json_path):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: Falta 'OPENAI_API_KEY' en el .env")
        return

    try:
        with open(md_path, 'r', encoding='utf-8') as f: md_content = f.read()
        with open(base_json_path, 'r', encoding='utf-8') as f: base_json = json.load(f)
    except FileNotFoundError as e:
        print(f"❌ Error leyendo archivos: {str(e)}")
        return

    print("🧠 1. GPT extrayendo la lógica pura...")
    client = OpenAI(api_key=api_key)

    system_prompt = """
    Eres un analizador de flujos. Extrae TODOS los nodos del Markdown a este JSON estricto:
    {
      "nodes": [
        {
          "id": "<ID exacto del MD>",
          "name": "<Nombre del nodo>",
          "is_start": true/false,
          "is_end": true/false,
          "systemMessage": "DEBES incluir el 'Script (frases literales)' exacto que viene en el MD.",
          "direct_next": "<ID destino si no hay opciones. Null si usa branches>",
          "branches": [
            {
              "id": "<ID slugificado>",
              "name": "<Condición>",
              "next_node": "<ID destino>"
            }
          ],
          "extractions": [{"name": "var", "type": "enum", "choices": ["a"], "description": ""}]
        }
      ]
    }
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={ "type": "json_object" },
            temperature=0.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extrae el flujo completo:\n\n{md_content}"}
            ]
        )
        parsed_data = json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ Error API: {str(e)}")
        return

    print("🏗️ 2. Python construyendo el mapa adaptado a la plataforma...")
    
    workflow_nodes = []
    workflow_edges = []
    
    x_pos, y_pos = 0, 0
    
    for raw_node in parsed_data.get("nodes", []):
        node_id = f"node-{raw_node['id']}"
        data_id = f"data-{raw_node['id']}"
        
        # --- LÓGICA DE TRADUCCIÓN A LA PLATAFORMA ---
        if raw_node.get("is_start"):
            n_type, n_class = "start", "start"
        elif raw_node.get("extractions") and not raw_node.get("branches"):
            n_type, n_class = "extractor", "extractor"
        else:
            n_type, n_class = "conversational", "ask_and_branch"

        # TRUCO PARA COLGAR: Forzamos la orden explícita en el prompt si es el último nodo
        system_msg = raw_node.get("systemMessage", "")
        if raw_node.get("is_end"):
            system_msg += "\n\nDIRECTIVA CRÍTICA: Despídete del usuario y CUELGA LA LLAMADA inmediatamente."

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
                "cannedStarters": [],
                "knowledgeBaseIds": [],
                "inputReplacements": [],
                "responseReplacements": [],
                "overrideLlmTimeout": 30,
                "branches": [],
                "extractions": []
            }
        }
        
        # --- LÓGICA DE CONEXIONADO (Evitar nodos sueltos) ---
        if n_class in ["start", "extractor"] and raw_node.get("direct_next"):
            # Start y Extractor sí usan connector directo
            target_id = f"node-{raw_node['direct_next']}"
            source_handle = f"{data_id}-conversational-connector"
            module_card["data"]["connector"] = target_id
            
            workflow_edges.append({
                "id": f"xy-edge__{node_id}{source_handle}-{target_id}",
                "source": node_id,
                "target": target_id,
                "sourceHandle": source_handle
            })
            
        elif n_class == "ask_and_branch":
            # Los ask_and_branch NO pueden usar connector, deben usar ramas
            if raw_node.get("branches"):
                for b in raw_node["branches"]:
                    if b.get("next_node"):
                        target_id = f"node-{b['next_node']}"
                        branch_id = b["id"]
                        module_card["data"]["branches"].append({
                            "id": branch_id,
                            "name": b["name"],
                            "next": target_id,
                            "description": "",
                            "fillPhrases": ["Claro."]
                        })
                        workflow_edges.append({
                            "id": f"xy-edge__{node_id}{branch_id}-{target_id}",
                            "source": node_id,
                            "target": target_id,
                            "sourceHandle": branch_id
                        })
            elif raw_node.get("direct_next"):
                # Si es conversacional y va directo, creamos una rama fantasma
                target_id = f"node-{raw_node['direct_next']}"
                branch_id = "branch_continuar"
                module_card["data"]["branches"].append({
                    "id": branch_id,
                    "name": "Continuar",
                    "next": target_id,
                    "description": "Transición automática",
                    "fillPhrases": ["Claro."]
                })
                workflow_edges.append({
                    "id": f"xy-edge__{node_id}{branch_id}-{target_id}",
                    "source": node_id,
                    "target": target_id,
                    "sourceHandle": branch_id
                })

        # Cargar extracciones si existen
        for ext in raw_node.get("extractions", []):
            module_card["data"]["extractions"].append({
                "name": ext["name"],
                "type": ext["type"],
                "choices": ext.get("choices", []),
                "examples": [],
                "required": False,
                "description": ext.get("description", "")
            })
            
        workflow_nodes.append(module_card)
        
        # Matemáticas visuales para organizar la cuadrícula
        x_pos += 450
        if x_pos > 1800:
            x_pos = 0
            y_pos += 400

    # 3. Empaquetar
    base_json["workflow"] = {
        "nodes": workflow_nodes,
        "edges": workflow_edges,
        "variables": {}
    }

    with open(output_json_path, 'w', encoding='utf-8') as out_file:
        json.dump(base_json, out_file, indent=2, ensure_ascii=False)
        
    print(f"✅ ¡Éxito! Workflow generado en: {output_json_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_md")
    parser.add_argument("base_json")
    parser.add_argument("output_json")
    args = parser.parse_args()
    build_workflow(args.input_md, args.base_json, args.output_json)