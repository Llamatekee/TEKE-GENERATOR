import json
from openai import OpenAI

def generate_minimal_json(md_content, output_json_path, client):
    print("[Paso 1] Generando JSON base, config global y postCallExtractions inferidas...")
    
    system_prompt = """
    Eres un procesador de datos estricto. Lee el Markdown y rellena los huecos en la plantilla JSON.
    Devuelve la plantilla EXACTAMENTE con la misma estructura.
    ATENCION: Los campos como globalInstructions o globalGuardrails DEBEN ser un string de texto plano.
    
    INSTRUCCIONES PARA 'postCallExtractions':
    Debes proponer una lista de datos de interes (extracciones) que el cliente querria ver en su CRM tras la llamada.
    1. Incluye las extracciones que se mencionen explicitamente en el documento.
    2. INFIERE nuevas extracciones leyendo el guion. Si el agente pregunta por el modelo de venta (B2B/B2C), el canal actual, el reto principal, o si agenda una reunion, crea una extraccion para cada uno de esos datos clave.
    3. El formato de cada extraccion debe ser estrictamente: {"name": "...", "description": "...", "type": "..."}
    4. Los unicos valores permitidos para "type" son: "boolean", "integer", "string", "enum".

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
            "genericFillPhrases": ["Claro.", "Entiendo.", "Perfecto."],
            "globalIdentity": "[[EXTRAE_LA_IDENTIDAD_Y_OBJETIVO_DEL_MARKDOWN]]",
            "globalStyle": "[[EXTRAE_EL_ESTILO_DE_VOZ_Y_ADAPTACION_DEL_MARKDOWN]]",
            "globalGuardrails": "[[EXTRAE_LOS_GUARDRAILS_DEL_MARKDOWN]]",
            "globalInstructions": "[[EXTRAE_LAS_REGLAS_GLOBALES_DEL_MARKDOWN]]",
            "personalityLanguage": "es-ES",
            "callProblemThreshold": 300,
            "callProblemProtocol": "transfer",
            "postCallExtractions": [
                {
                    "name": "ejemplo_inferido",
                    "description": "ejemplo",
                    "type": "string"
                }
            ],
            "voice": "HIYif4jehvc9P9A8DYbX",
            "voiceSynthesizer": "elevenlabs",
            "voiceSynthesizerModel": "eleven_turbo_v2_5",
            "stability": 0.5,
            "similarityBoost": 0.75,
            "speed": 1,
            "capabilities": {"inboundCalls": true, "outboundCalls": true, "email": false, "messaging": false},
            "responseReplacements": [],
            "inputReplacements": [],
            "memoryConfig": {"sessionsCount": 0, "lifeTimeSummaryEnabled": false, "messagesPerSessionCount": 10},
            "ragConfig": {"ragType": "keywords", "maxDocuments": 3, "reranking": false, "backflow": false}
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
            {"role": "user", "content": f"Lee este Markdown y rellena la plantilla JSON infiriendo las postCallExtractions:\n\n{md_content}"}
        ]
    )
    
    result_json = json.loads(response.choices[0].message.content)
    with open(output_json_path, 'w', encoding='utf-8') as out_file:
        json.dump(result_json, out_file, indent=2, ensure_ascii=False)