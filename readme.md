# TOLVIA Pipeline: Generador Automático de Agentes Conversacionales

Herramienta end-to-end diseñada para transformar guiones comerciales en bruto (formato `.docx` o `.md`) en agentes conversacionales completamente funcionales (formato `.json`) y generar baterías de pruebas de QA sintéticas de forma automatizada.

## Arquitectura de la Pipeline

El orquestador (`src/main.py`) ejecuta un proceso secuencial de 6 fases:

1. **Extracción (01_docx_to_md):** convierte el documento `.docx` original en un archivo Markdown en bruto, preservando la jerarquía básica y el formato del texto.
2. **Estructuración semántica (02_structurer):** analiza el Markdown bruto mediante LLM para extraer y clasificar la identidad del agente, el flujo de la conversación, las objeciones, FAQs y extracciones necesarias. Genera un Markdown estructurado.
3. **Configuración base (03_minimal):** inicializa la plantilla JSON del agente, configurando las reglas globales, los guardrails y deduciendo las variables post-llamada (`postCallExtractions`) a partir del contexto general.
4. **Construcción del flujo (04_workflow):** traduce los pasos del Markdown estructurado a nodos lógicos y ramas condicionales (`branches`) en el esquema JSON, conectando las transiciones del agente.
5. **Inyección de condicionales (05_conditionals):** integra las objeciones y preguntas frecuentes detectadas como reglas condicionales (inline) dentro del flujo conversacional.
6. **Generación de QA (06_test_generator):** evalúa el flujo final del agente y genera una suite de escenarios de pruebas automatizadas (tests sintéticos) garantizando la cobertura de los distintos casos de uso.

## Requisitos y configuración

1. Instalación de dependencias:
  ```bash
   pip install openai python-docx python-dotenv

  ```
2. Configuración del entorno:
  Crea un archivo `.env` en la raíz del proyecto e incluye tu clave de API:
  ```env
   OPENAI_API_KEY=tu_clave_api_aqui
   
  ``` 

## Uso básico

El script determina automáticamente las rutas de salida (carpeta `files/`) y el nombre base de los archivos utilizando el nombre del documento de entrada.

```bash
python src/main.py files/docs/Guion_Comercial.docx
```

## Referencia de parámetros (Flags)


| Argumento / Flag | Tipo       | Descripción                                                                                                                    |
| ---------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `input_file`     | Posicional | (Obligatorio) Ruta al archivo de origen `.docx` o `.md`.                                                                       |
| `--tests`        | Entero     | Número de escenarios de prueba QA sintéticos a generar. Si se omite, no se generará el archivo de tests.                       |
| `--md_dir`       | Ruta       | Sobrescribe el directorio destino para los archivos intermedios `.md`.                                                         |
| `--json_dir`     | Ruta       | Sobrescribe el directorio destino para los archivos finales `.json`.                                                           |
| `--output_name`  | Cadena     | Sobrescribe el nombre base asignado a los archivos de salida generados.                                                        |
| `--verbose`      | Booleano   | Activa el modo de registro detallado. Útil para depurar y ver la traza paso a paso de las llamadas al LLM y procesos internos. |


## Ejemplos de Ejecución Avanzada

**Generar el agente y 5 escenarios de prueba:**

```bash
python src/main.py files/docs/Guion.docx --tests 5
```

**Guardar los resultados en directorios personalizados con un nombre específico:**

```bash
python src/main.py docs/raw_script.md --json_dir ./produccion/agentes --output_name Agente_Ventas_V2
```

**Ejecución con log detallado (Debug):**

```bash
python src/main.py files/docs/Guion.docx --verbose
```

