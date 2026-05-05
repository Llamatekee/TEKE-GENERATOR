"""
00_docx_to_md.py
----------------
Convierte cualquier .docx a Markdown en bruto, preservando toda la información
tal cual: headings, párrafos, bold/italic, tablas y listas.

Uso:
    python 00_docx_to_md.py <ruta_al_docx> [ruta_salida.md]

Si no se especifica ruta de salida, el .md se guarda junto al .docx con el mismo nombre.

Dependencias:
    pip install python-docx
"""

import sys
import os
import argparse
from docx import Document
from docx.oxml.ns import qn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runs_to_md(paragraph) -> str:
    """Convierte los runs de un párrafo a texto con marcado MD básico."""
    parts = []
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue
        # Bold e italic
        if run.bold and run.italic:
            text = f"***{text}***"
        elif run.bold:
            text = f"**{text}**"
        elif run.italic:
            text = f"*{text}*"
        parts.append(text)
    return "".join(parts)


def _heading_level(paragraph) -> int:
    """Devuelve el nivel numérico de un heading (1-6), o 0 si no es heading."""
    style_name = paragraph.style.name  # e.g. "Heading 1", "Título 1"
    for word in style_name.split():
        if word.isdigit():
            return min(int(word), 6)
    # Normalizado en minúsculas por si acaso
    lower = style_name.lower()
    if "heading" in lower or "título" in lower or "titulo" in lower:
        return 1  # fallback: nivel 1
    return 0


def _is_list_paragraph(paragraph) -> bool:
    """Detecta si el párrafo es un item de lista."""
    style_lower = paragraph.style.name.lower()
    if "list" in style_lower or "lista" in style_lower or "bullet" in style_lower:
        return True
    # Detectar via formato XML (numPr)
    pPr = paragraph._element.find(qn("w:pPr"))
    if pPr is not None and pPr.find(qn("w:numPr")) is not None:
        return True
    return False


def _table_to_md(table) -> str:
    """Convierte una tabla docx a tabla Markdown."""
    lines = []
    for i, row in enumerate(table.rows):
        cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            # Separador de cabecera
            lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Conversor principal
# ---------------------------------------------------------------------------

def docx_to_md(docx_path: str) -> str:
    """Lee el .docx y devuelve el contenido como string Markdown en bruto."""
    doc = Document(docx_path)
    output_lines = []

    # Índice de elementos de nivel de bloque (párrafos + tablas en orden)
    # python-docx expone doc.element.body, que contiene ambos entrelazados
    for child in doc.element.body:
        tag = child.tag.split("}")[-1]  # 'p' o 'tbl'

        # ── TABLA ──────────────────────────────────────────────────────────
        if tag == "tbl":
            from docx.table import Table
            table = Table(child, doc)
            output_lines.append("")
            output_lines.append(_table_to_md(table))
            output_lines.append("")
            continue

        # ── PÁRRAFO ────────────────────────────────────────────────────────
        if tag == "p":
            from docx.text.paragraph import Paragraph
            paragraph = Paragraph(child, doc)

            text = _runs_to_md(paragraph)
            raw_text = paragraph.text.strip()

            # Ignorar párrafos completamente vacíos
            if not raw_text:
                output_lines.append("")
                continue

            # Heading
            level = _heading_level(paragraph)
            if level > 0:
                output_lines.append(f"\n{'#' * level} {raw_text}\n")
                continue

            # Lista
            if _is_list_paragraph(paragraph):
                # Intentar detectar listas numeradas
                style_lower = paragraph.style.name.lower()
                if "number" in style_lower or "número" in style_lower or "numerada" in style_lower:
                    output_lines.append(f"1. {text}")
                else:
                    output_lines.append(f"- {text}")
                continue

            # Párrafo normal
            output_lines.append(text)

    return "\n".join(output_lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convierte un .docx a Markdown en bruto (sin LLM)."
    )
    parser.add_argument("docx_path", help="Ruta al archivo .docx de entrada")
    parser.add_argument(
        "output_md",
        nargs="?",
        default=None,
        help="Ruta de salida .md (opcional). Por defecto: mismo nombre junto al .docx"
    )
    args = parser.parse_args()

    if not os.path.exists(args.docx_path):
        print(f"Error: no se encuentra el archivo '{args.docx_path}'")
        sys.exit(1)

    if not args.docx_path.lower().endswith(".docx"):
        print("Aviso: el archivo no tiene extensión .docx, se intentará procesar igualmente.")

    # Ruta de salida
    if args.output_md:
        output_path = args.output_md
    else:
        base = os.path.splitext(args.docx_path)[0]
        output_path = base + "_raw.md"

    print(f"Convirtiendo: {args.docx_path}")
    md_content = docx_to_md(args.docx_path)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"✓ Markdown en bruto guardado en: {output_path}")


if __name__ == "__main__":
    main()
