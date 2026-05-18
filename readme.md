# TEKE_GENERATOR — Referencia técnica

## Instalación

```bash
pip install openai python-docx python-dotenv
```

Crea `.env` en la raíz:
```env
OPENAI_API_KEY=tu_clave_api
```

---

## Pipeline principal — `src/main.py`

### Input
- Uno o varios archivos `.docx` o `.md` (el primero define el nombre base de salida)
- Si se pasan varios, se concatenan antes de procesar

### Output
| Archivo | Siempre | Descripción |
|---------|---------|-------------|
| `{nombre}_raw.md` | ✓ | Markdown bruto extraído del input |
| `{nombre}_structured.md` | ✓ | Markdown semántico con identidad, flujo, objeciones, FAQs y extracciones |
| `{nombre}_workflow.json` | ✓ | Workflow Tolvia listo para importar |
| `{nombre}_tests.json` | Solo con `--tests` | Batería de escenarios QA |
| `{nombre}_rag_briefing.md` | Solo con `--rag` | Objetivos del agente y candidatos de documentos RAG |

### Uso

```bash
python src/main.py <archivo(s)> [opciones]
```

### Parámetros

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `input_files` | posicional+ | — | Uno o varios `.docx` / `.md`. El primero define el nombre base. |
| `--tests N` | int | — | Genera `N` escenarios QA. Incluye los del guion + sintéticos hasta llegar a N. |
| `--extra-faqs N` | int | 0 | FAQs extra a inferir más allá de las del guion (llamada LLM independiente). |
| `--extra-objections N` | int | 0 | Objeciones universales extra más allá de las del guion (llamada LLM independiente). |
| `--extra-extractions N` | int | 0 | Post-call extractions extra más allá de las inferidas del guion. |
| `--rag` | flag | — | Genera el briefing RAG. |
| `--output_name` | string | nombre del primer archivo | Nombre base personalizado para todos los archivos de salida. |
| `--md_dir` | ruta | `files/md/` | Directorio para archivos `.md`. |
| `--json_dir` | ruta | `files/json/` | Directorio para archivos `.json`. |
| `--verbose` | flag | — | Log detallado paso a paso. |

### Ejemplos

```bash
# Básico
python src/main.py guion.docx

# Con tests QA y RAG
python src/main.py guion.docx --tests 5 --rag

# Múltiples documentos fusionados
python src/main.py guion.docx faqs.docx objeciones.docx

# Con extras y nombre personalizado
python src/main.py guion.docx --extra-faqs 3 --extra-objections 2 --extra-extractions 5 --output_name Agente_v2

# Directorios y nombre custom
python src/main.py guion.md --json_dir ./produccion/ --output_name Sofia_Prod --verbose
```

---

## Fases internas de la pipeline

| Fase | Archivo | Descripción |
|------|---------|-------------|
| 1 | `01_docx_to_md.py` | Convierte `.docx` → Markdown (sin LLM) |
| 2 | `02_structurer.py` | Extrae esqueleto del grafo → auditor → contenido en lotes paralelos → modularización conversacional (`phase2f`) → extracción paralela de identidad, objeciones, FAQs y extracciones de nodo |
| 3 | `03_minimal.py` | Genera la config base del agente (`agentConfig`, `postCallExtractions`) |
| 4 | `04_workflow.py` | Construye nodos y edges Tolvia en lotes paralelos (skeleton + contenido) |
| 5 | `05_conditionals.py` | Genera nodos `conversational_conditional` para objeciones y FAQs en paralelo |
| 6 | `06_test.py` | Genera la batería de tests QA |
| 7 | `07_rag.py` | Genera el briefing RAG |

---

## Scripts standalone

### `02_structurer.py` — Reestructurar un MD bruto

```bash
python src/02_structurer.py <raw_md> <output_md> [--extra-faqs N] [--extra-objections N] [--verbose]
```

**Input:** MD bruto  
**Output:** MD estructurado semántico

---

### `07_rag.py` — Generar briefing RAG

```bash
python src/07_rag.py <md_o_docx> [--output ruta.md] [--verbose]
```

**Input:** MD estructurado (o raw)  
**Output:** `_rag_briefing.md` con objetivos del agente y candidatos de documentos priorizados

---

### `09_simulator.py` — Simular y validar conversaciones

Ejecuta conversaciones simuladas contra el workflow generado para detectar errores de comportamiento del agente.

```bash
python src/09_simulator.py <workflow_json> [opciones]
```

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `workflow_json` | posicional | — | Ruta al workflow JSON generado. |
| `--tests` | ruta | — | Usa los escenarios del tests JSON como personas del usuario-LLM. |
| `--scenarios N` | int | 3 | Número de escenarios libres si no se pasa `--tests`. |
| `--fix` | flag | — | Intenta corregir los `systemMessage` de los nodos con errores y guarda una versión nueva del workflow (`_v1`, `_v2`, ...). |
| `--output` | ruta | — | Guarda el reporte de errores en un JSON. |
| `--verbose` | flag | — | Muestra los transcripts completos de cada simulación. |

**Errores detectados:** `script_ignorado`, `pitch_omitido`, `pregunta_multiple`, `cortesia_respondida`, `improvisacion`, `ruta_incorrecta`, `bucle_o_timeout`

**Ejemplos:**

```bash
# 3 escenarios libres, solo reporte
python src/09_simulator.py files/json/Sofia_workflow.json

# Con tests generados, reporte en JSON
python src/09_simulator.py files/json/Sofia_workflow.json --tests files/json/Sofia_tests.json --output report.json

# Simular + corregir automáticamente (guarda _v1.json)
python src/09_simulator.py files/json/Sofia_workflow.json --fix

# Iterar: simular sobre la versión corregida
python src/09_simulator.py files/json/Sofia_workflow_v1.json --fix --verbose
```

---

## Estructura de archivos

```
TEKE_GENERATOR/
├── src/
│   ├── main.py              # Orquestador principal
│   ├── 01_docx_to_md.py
│   ├── 02_structurer.py     # Standalone disponible
│   ├── 03_minimal.py
│   ├── 04_workflow.py
│   ├── 05_conditionals.py
│   ├── 06_test.py
│   ├── 07_rag.py            # Standalone disponible
│   └── 09_simulator.py      # Standalone — validación y auto-fix
├── files/
│   ├── md/                  # Outputs intermedios y finales .md
│   ├── json/                # Workflows, tests y temporales
│   └── examples/            # Ejemplos de workflows mínimos
├── .env                     # OPENAI_API_KEY (no versionado)
└── readme.md
```
