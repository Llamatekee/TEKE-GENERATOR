import os
import json
import argparse
from openai import OpenAI
from dotenv import load_dotenv

# Cargamos variables de entorno (.env)
load_dotenv()

def generate_minimal_json(md_path, output_json_path):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: No se encontró 'OPENAI_API_KEY' en el archivo .env")
        return

    try:
        with open(md_path, 'r', encoding='utf-8') as file:
            md_content = file.read()
    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo {md_path}")
        return

    print("🧠 Usando patrón de 'Plantilla Estricta' con GPT...")
    client = OpenAI(api_key=api_key)

    # Inyectamos el JSON perfecto como plantilla inmutable
    system_prompt = """
    Eres un procesador de datos estricto. Tu ÚNICA tarea es leer el Markdown proporcionado y rellenar los huecos marcados con "[[...]]" en la siguiente plantilla JSON.
    
    REGLA DE ORO: Devuelve la plantilla JSON EXACTAMENTE con la misma estructura. NO añadas ni quites campos, arrays, diccionarios ni IDs. Mantén el formato intacto, solo cambia los textos dentro de los "[[...]]".

    PLANTILLA JSON:
    {
        "version": "2.0",
        "exportedAt": "2026-05-04T18:00:00.000Z",
        "agentName": "[[NOMBRE_DEL_AGENTE_EJ_LinkedUpSales]]",
        "agentConfig": {
            "name": "[[NOMBRE_DEL_AGENTE]]",
            "language": "es-ES",
            "timeZone": "Europe/Madrid",
            "serviceLlm": "openai/gpt-oss-20b",
            "nodeLlm": "llama-3.3-70b-versatile",
            "postCallExtractionsLlm": "openai/gpt-oss-120b",
            "llmTemperature": 0.57,
            "conversationalMode": null,
            "llmStreamMode": true,
            "answerPhrase": "[[SALUDO_LITERAL_DEL_NODO_START_DEL_MARKDOWN]]",
            "hangupPhrase": "Gracias por tu tiempo y hasta pronto.",
            "genericFillPhrases": [
                "Claro.",
                "Entiendo.",
                "Perfecto."
            ],
            "globalIdentity": "[[EXTRAE_LA_IDENTIDAD_Y_OBJETIVO_DEL_MARKDOWN]]",
            "globalStyle": "[[EXTRAE_EL_ESTILO_DE_VOZ_Y_ADAPTACION_DEL_MARKDOWN]]",
            "globalGuardrails": "[[EXTRAE_LOS_GUARDRAILS_DEL_MARKDOWN_EN_FORMATO_PARRAFO]]",
            "globalInstructions": "[[EXTRAE_LAS_REGLAS_GLOBALES_DEL_MARKDOWN_EN_FORMATO_LISTA]]",
            "personalityLanguage": "es-ES",
            "callProblemThreshold": 300,
            "callProblemProtocol": "transfer",
            "postCallExtractions": [],
            "voice": "HIYif4jehvc9P9A8DYbX",
            "voiceSynthesizer": "elevenlabs",
            "voiceSynthesizerModel": "eleven_turbo_v2_5",
            "stability": 0.5,
            "similarityBoost": 0.75,
            "speed": 1,
            "capabilities": {
                "inboundCalls": true,
                "outboundCalls": true,
                "email": false,
                "messaging": false
            },
            "responseReplacements": [],
            "inputReplacements": [],
            "memoryConfig": {
                "sessionsCount": 0,
                "lifeTimeSummaryEnabled": false,
                "messagesPerSessionCount": 10
            },
            "ragConfig": {
                "ragType": "keywords",
                "maxDocuments": 3,
                "reranking": false,
                "backflow": false
            }
        },
        "workflow": {
            "nodes": [
                {
                    "id": "node-1111",
                    "type": "moduleCard",
                    "position": { "x": 0, "y": 0 },
                    "data": {
                        "id": "data-start",
                        "name": "Inicio",
                        "type": "start",
                        "rules": [],
                        "params": {},
                        "autoNext": false,
                        "branches": [],
                        "connector": "node-2222",
                        "isEndNode": false,
                        "nodeClass": "start",
                        "extractions": [],
                        "isGlobalNode": false,
                        "maxIterations": 3,
                        "asyncExecution": false,
                        "blockUserInput": false,
                        "cannedStarters": [],
                        "knowledgeBaseIds": [],
                        "inputReplacements": [],
                        "overrideLlmTimeout": 30,
                        "responseReplacements": []
                    }
                },
                {
                    "id": "node-2222",
                    "type": "moduleCard",
                    "position": { "x": 400, "y": 0 },
                    "data": {
                        "id": "data-intro",
                        "name": "Introducción",
                        "type": "conversational",
                        "rules": [],
                        "params": {},
                        "autoNext": false,
                        "branches": [
                            {
                                "id": "branch-yes",
                                "name": "muestra_interes",
                                "next": "node-3333",
                                "description": "Si el usuario muestra interés",
                                "fillPhrases": ["Genial."]
                            }
                        ],
                        "isEndNode": false,
                        "nodeClass": "ask_and_branch",
                        "extractions": [],
                        "isGlobalNode": false,
                        "maxIterations": 300,
                        "systemMessage": "[[EXTRAE_EL_SCRIPT_LITERAL_Y_DIRECTIVAS_DEL_NODO_INTRODUCCION_DEL_MARKDOWN]]",
                        "asyncExecution": false,
                        "blockUserInput": false,
                        "cannedStarters": [],
                        "knowledgeBaseIds": [],
                        "inputReplacements": [],
                        "overrideLlmTimeout": 30,
                        "responseReplacements": []
                    }
                },
                {
                    "id": "node-3333",
                    "type": "moduleCard",
                    "position": { "x": 800, "y": 0 },
                    "data": {
                        "id": "data-end",
                        "name": "Cierre",
                        "type": "conversational",
                        "rules": [],
                        "params": {},
                        "autoNext": false,
                        "branches": [],
                        "isEndNode": false,
                        "nodeClass": "ask_and_branch",
                        "extractions": [],
                        "isGlobalNode": false,
                        "maxIterations": 300,
                        "systemMessage": "Despídete y finaliza la conversación agradeciendo el tiempo.",
                        "asyncExecution": false,
                        "blockUserInput": false,
                        "cannedStarters": [],
                        "knowledgeBaseIds": [],
                        "inputReplacements": [],
                        "overrideLlmTimeout": 30,
                        "responseReplacements": []
                    }
                }
            ],
            "edges": [
                {
                    "id": "xy-edge__node-1111data-start-conversational-connector-node-2222",
                    "source": "node-1111",
                    "target": "node-2222",
                    "sourceHandle": "data-start-conversational-connector"
                },
                {
                    "id": "xy-edge__node-2222branch-yes-node-3333",
                    "source": "node-2222",
                    "target": "node-3333",
                    "sourceHandle": "branch-yes"
                }
            ]
        }
    }
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={ "type": "json_object" },
            temperature=0.0, # 0.0 garantiza que no se ponga creativo con la estructura
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Lee este Markdown y rellena la plantilla JSON:\n\n{md_content}"}
            ]
        )
        
        result_json = json.loads(response.choices[0].message.content)
        
        with open(output_json_path, 'w', encoding='utf-8') as out_file:
            json.dump(result_json, out_file, indent=4, ensure_ascii=False)
            
        print(f"✅ ¡Éxito! JSON generado y guardado en: {output_json_path}")
        
    except Exception as e:
        print(f"❌ Error durante la generación: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Conversor seguro de MD a JSON Minimalista")
    parser.add_argument("input_md", help="Path del archivo .md (ej. LinkedUpSales_structured.md)")
    parser.add_argument("output_json", help="Path del archivo .json de salida")
    
    args = parser.parse_args()
    generate_minimal_json(args.input_md, args.output_json)