import json

def generate_minimal_json(md_content, output_json_path, client):
    print("Ejecutando Paso 1: Generacion de JSON base y configuracion global...")
    
    system_prompt = """
    Eres un procesador de datos estricto. Tu UNICA tarea es leer el Markdown proporcionado y rellenar los huecos marcados con "[[...]]" en la siguiente plantilla JSON.
    
    REGLA DE ORO: Devuelve la plantilla JSON EXACTAMENTE con la misma estructura. NO anadas ni quites campos, arrays, diccionarios ni IDs. Manten el formato intacto, solo cambia los textos dentro de los "[[...]]".
    
    ATENCION: Los campos como globalInstructions o globalGuardrails DEBEN ser un string de texto plano, NUNCA un array o lista JSON.

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
            "globalGuardrails": "[[EXTRAE_LOS_GUARDRAILS_DEL_MARKDOWN_EN_FORMATO_PARRAFO_PLANO]]",
            "globalInstructions": "[[EXTRAE_LAS_REGLAS_GLOBALES_DEL_MARKDOWN_EN_FORMATO_PARRAFO_PLANO]]",
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
            "nodes": [],
            "edges": [],
            "variables": {}
        }
    }
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Lee este Markdown y rellena la plantilla JSON:\n\n{md_content}"}
        ]
    )
    
    result_json = json.loads(response.choices[0].message.content)
    with open(output_json_path, 'w', encoding='utf-8') as out_file:
        json.dump(result_json, out_file, indent=2, ensure_ascii=False)