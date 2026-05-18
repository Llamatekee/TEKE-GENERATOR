import json
from openai import OpenAI

def generate_minimal_json(md_content, output_json_path, client, verbose=False):
    
    if verbose:
        print("[Paso 3] Generando JSON base, config global y postCallExtractions inferidas...")
    
    system_prompt = """
    Eres un procesador de datos estricto. Lee el Markdown y rellena los huecos en la plantilla JSON.
    Devuelve la plantilla EXACTAMENTE con la misma estructura.
    ATENCION: Los campos como globalInstructions o globalGuardrails DEBEN ser un string de texto plano.
    
    INSTRUCCIONES PARA 'postCallExtractions':
    Propón una lista COMPLETA de datos de interes que el responsable querria ver en el CRM tras la llamada.
    Minimo 10 extracciones. Si el guion es complejo, genera 15-20.

    REGLAS DE INFERENCIA (aplica todas):
    1. Cada pregunta que el agente hace en el guion debe generar UNA extraccion para la respuesta del usuario.
    2. El resultado de cada rama principal debe tener una extraccion (cita agendada, rechazo, objecion concreta...).
    3. Incluye SIEMPRE estas categorias si aplican al guion:
       - Cualificacion: nombre, cargo, empresa, sector, tamano de equipo, modelo B2B/B2C.
       - Interes: nivel de interes mostrado, si acepto escuchar, si hizo preguntas.
       - Objeciones: tipo de objecion planteada (enum), si fue resuelta (boolean).
       - Agenda: si se agendo cita (boolean), dia, hora, email, numero confirmado.
       - Resultado: razon de cierre (enum: agendado / rechazo / ocupado / reprogramar / no_localizado).
    4. Usa "boolean" para SI/NO, "enum" para lista cerrada de valores, "string" para texto libre.
    5. Formato estricto de cada extraccion: {"name": "snake_case", "description": "descripcion breve en espanol", "type": "..."}
    6. No dupliques. No uses nombres vagos como "dato_1" o "info_extra".

    {
        "version": "2.0",
        "exportedAt": "2026-05-04T18:00:00.000Z",
        "agentName": "[[NOMBRE_DEL_AGENTE_EJ_LinkedUpSales]]",
        "agentConfig": {
            "name": "[[NOMBRE_DEL_AGENTE]]",
            "language": "es-ES",
            "timeZone": "Europe/Madrid",
            "serviceLlm": "openai/gpt-oss-20b",
            "nodeLlm": "openai/gpt-oss-120b",
            "postCallExtractionsLlm": "gpt-4o-mini",
            "llmTemperature": 0.57,
            "conversationalMode": null,
            "llmStreamMode": true,
            "answerPhrase": "[[APERTURA COMPLETA: todo lo que dice el agente antes de que el usuario hable por primera vez. Puede ser 1-2 frases. NO incluyas la frase de presentacion del producto/servicio si el usuario ya ha respondido antes de que el agente la diga. Copia las frases literales del guion.]]",
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