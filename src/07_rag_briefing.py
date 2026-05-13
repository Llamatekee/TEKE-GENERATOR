import json
import os
import argparse
from openai import OpenAI
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYS = (
    "Eres un arquitecto de agentes conversacionales de voz. "
    "Tu trabajo es leer un guion y producir ÚNICAMENTE JSON puro sin markdown fences."
)

_USR = """\
Analiza el siguiente guion de agente conversacional y produce un JSON con dos secciones:

1. "objectives": los objetivos reales del agente, extraídos del guion + inferidos.
2. "rag_candidates": documentos o bases de conocimiento que el agente necesitaría en su RAG
   para responder correctamente a cualquier pregunta fuera del flujo principal.

INSTRUCCIONES PARA "objectives":
- "primary": el objetivo principal de la llamada (máximo 1 frase, muy concreto).
- "secondary": lista de objetivos secundarios o condicionados (ej. si no cierra, dejar email).
- "kpis": métricas clave con las que se mediría el éxito del agente (ej. tasa de agendado, email capturado).

INSTRUCCIONES PARA "rag_candidates":
Cada candidato debe tener:
  - "id": snake_case, único.
  - "name": nombre del documento o base de conocimiento.
  - "description": qué contiene y para qué sirve en contexto de llamada.
  - "why_needed": qué pregunta concreta del prospecto no podría responder el agente sin este doc.
  - "example_queries": lista de 2-4 preguntas que el RAG respondería con este documento.
  - "priority": "alta" | "media" | "baja" — según impacto en la conversación.
  - "source": "explicito" (mencionado en el guion) | "inferido" (no está pero debería estar).
  - "suggested_format": "FAQ_md" | "tabla_precios" | "ficha_producto" | "politica_texto" | "otro".

REGLAS:
1. Incluye TODOS los candidatos explícitos en el guion (precios, catálogos, condiciones, etc.).
2. Infiere candidatos universales si aplican: política de privacidad/RGPD, horarios, casos de éxito, comparativa con competidores, onboarding/proceso de contratación.
3. Ordena los candidatos de mayor a menor prioridad.
4. No inventes información que no esté en el guion ni sea razonablemente inferible.

GUION:
---
{md_content}
---

Produce exactamente este JSON:
{{
  "objectives": {{
    "primary": "<frase>",
    "secondary": ["<obj2>", "<obj3>"],
    "kpis": ["<kpi1>", "<kpi2>"]
  }},
  "rag_candidates": [
    {{
      "id": "<snake_case>",
      "name": "<nombre>",
      "description": "<descripcion>",
      "why_needed": "<razon>",
      "example_queries": ["<q1>", "<q2>"],
      "priority": "<alta|media|baja>",
      "source": "<explicito|inferido>",
      "suggested_format": "<formato>"
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_llm(client, md_content):
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": _SYS},
            {"role": "user", "content": _USR.format(md_content=md_content)},
        ],
    )
    return json.loads(response.choices[0].message.content)

# ---------------------------------------------------------------------------
# Formateo Markdown del output
# ---------------------------------------------------------------------------

_PRIORITY_LABEL = {"alta": "Alta", "media": "Media", "baja": "Baja"}
_SOURCE_LABEL   = {"explicito": "Explícito en guion", "inferido": "Inferido"}

def _render_md(data: dict, source_file: str) -> str:
    obj  = data.get("objectives", {})
    cands = data.get("rag_candidates", [])

    lines = []
    lines.append(f"# RAG Briefing — {source_file}\n")
    lines.append("---\n")

    # --- Objetivos ---
    lines.append("## Objetivos del agente\n")
    lines.append(f"**Objetivo principal:** {obj.get('primary', 'N/A')}\n")

    secondary = obj.get("secondary", [])
    if secondary:
        lines.append("**Objetivos secundarios:**")
        for s in secondary:
            lines.append(f"- {s}")
        lines.append("")

    kpis = obj.get("kpis", [])
    if kpis:
        lines.append("**KPIs de éxito:**")
        for k in kpis:
            lines.append(f"- {k}")
        lines.append("")

    lines.append("---\n")

    # --- Candidatos RAG ---
    lines.append(f"## Candidatos para el RAG ({len(cands)} documentos)\n")

    # Resumen tabla
    lines.append("| # | Nombre | Prioridad | Fuente | Formato sugerido |")
    lines.append("|---|--------|-----------|--------|-----------------|")
    for i, c in enumerate(cands, 1):
        prio = _PRIORITY_LABEL.get(c.get("priority", "baja"), "Baja")
        src  = _SOURCE_LABEL.get(c.get("source", "inferido"), "Inferido")
        lines.append(
            f"| {i} | {c.get('name', '?')} | {prio} "
            f"| {src} | `{c.get('suggested_format', '?')}` |"
        )
    lines.append("")
    lines.append("---\n")

    # Fichas detalladas
    lines.append("## Fichas detalladas\n")
    for i, c in enumerate(cands, 1):
        prio   = _PRIORITY_LABEL.get(c.get("priority", "baja"), "Baja")
        src    = _SOURCE_LABEL.get(c.get("source", "inferido"), "Inferido")
        lines.append(f"### {i}. {c.get('name', '?')}")
        lines.append(f"**ID:** `{c.get('id', '?')}` · **Prioridad:** {prio} · **Fuente:** {src}")
        lines.append(f"**Formato sugerido:** `{c.get('suggested_format', '?')}`\n")
        lines.append(f"**Descripción:** {c.get('description', 'N/A')}\n")
        lines.append(f"**¿Por qué lo necesita el agente?** {c.get('why_needed', 'N/A')}\n")
        queries = c.get("example_queries", [])
        if queries:
            lines.append("**Preguntas que respondería este documento:**")
            for q in queries:
                lines.append(f"- *{q}*")
        lines.append("")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Función principal (importable desde main.py)
# ---------------------------------------------------------------------------

def generate_rag_briefing(md_content: str, output_path: str, client, source_name: str = "", verbose: bool = False) -> bool:
    """
    Genera un MD con los objetivos del agente y los candidatos RAG.

    Args:
        md_content:   Contenido del MD estructurado (o raw si no hay structured).
        output_path:  Ruta del archivo .md de salida.
        client:       Cliente OpenAI inicializado.
        source_name:  Nombre del archivo origen (para la cabecera del MD).
        verbose:      Activa logs detallados.

    Returns:
        True si se generó con éxito, False si hubo error.
    """
    if verbose:
        print("[Paso 7] Extrayendo objetivos y candidatos RAG...")

    try:
        data = _call_llm(client, md_content)
    except Exception as e:
        print(f"[Paso 7] Error en llamada LLM: {e}")
        return False

    n_cands = len(data.get("rag_candidates", []))
    if verbose:
        print(f"  -> {n_cands} candidatos RAG identificados.")

    md_output = _render_md(data, source_name or os.path.basename(output_path))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_output)

    if verbose:
        print(f"  -> RAG Briefing guardado en: {output_path}")

    return True

# ---------------------------------------------------------------------------
# Uso standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera un RAG Briefing (objetivos + candidatos de documentos) a partir de un guion."
    )
    parser.add_argument(
        "input_file",
        help="Ruta al MD estructurado o raw (.md) — o al .docx si se combina con 01_docx_to_md.",
    )
    parser.add_argument(
        "--output",
        help="Ruta de salida del .md. Por defecto: mismo directorio que input con sufijo _rag_briefing.md",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY no encontrada en el entorno.")
        raise SystemExit(1)

    input_path = os.path.abspath(args.input_file)
    if not os.path.exists(input_path):
        print(f"Error: No se encuentra el archivo {input_path}")
        raise SystemExit(1)

    # Soporte .docx standalone (importa 01_docx_to_md si está disponible)
    if input_path.lower().endswith(".docx"):
        try:
            import importlib, sys
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            docx_mod = importlib.import_module("01_docx_to_md")
            content = docx_mod.docx_to_md(input_path)
        except Exception as e:
            print(f"Error convirtiendo DOCX: {e}")
            raise SystemExit(1)
    else:
        with open(input_path, "r", encoding="utf-8") as f:
            content = f.read()

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    # Quitar sufijo _structured o _raw para el nombre base limpio
    for suffix in ("_structured", "_raw"):
        if base_name.endswith(suffix):
            base_name = base_name[: -len(suffix)]

    if args.output:
        out_path = os.path.abspath(args.output)
    else:
        out_dir = os.path.dirname(input_path)
        out_path = os.path.join(out_dir, f"{base_name}_rag_briefing.md")

    client = OpenAI(api_key=api_key)
    ok = generate_rag_briefing(content, out_path, client, source_name=os.path.basename(input_path), verbose=args.verbose)
    if ok:
        print(f"\n✅ RAG Briefing generado: {out_path}")
    else:
        print("\n❌ El proceso finalizó con errores.")
        raise SystemExit(1)
