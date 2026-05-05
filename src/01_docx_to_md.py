import sys
import os
import argparse
from docx import Document
from docx.oxml.ns import qn

def runs_to_md(paragraph) -> str:
    parts = []
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue
        if run.bold and run.italic:
            text = f"***{text}***"
        elif run.bold:
            text = f"**{text}**"
        elif run.italic:
            text = f"*{text}*"
        parts.append(text)
    return "".join(parts)

def heading_level(paragraph) -> int:
    # ESCUDO: Si no hay estilo definido, no es un título
    if not paragraph.style or not paragraph.style.name:
        return 0
        
    style_name = paragraph.style.name
    for word in style_name.split():
        if word.isdigit():
            return min(int(word), 6)
    lower = style_name.lower()
    if "heading" in lower or "título" in lower or "titulo" in lower:
        return 1
    return 0

def is_list_paragraph(paragraph) -> bool:
    # ESCUDO: Protegemos la lectura del estilo
    if paragraph.style and paragraph.style.name:
        style_lower = paragraph.style.name.lower()
        if "list" in style_lower or "lista" in style_lower or "bullet" in style_lower:
            return True
            
    pPr = paragraph._element.find(qn("w:pPr"))
    if pPr is not None and pPr.find(qn("w:numPr")) is not None:
        return True
    return False

def table_to_md(table) -> str:
    lines = []
    for i, row in enumerate(table.rows):
        cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return "\n".join(lines)

def docx_to_md(docx_path: str) -> str:
    doc = Document(docx_path)
    output_lines = []

    for child in doc.element.body:
        tag = child.tag.split("}")[-1]

        if tag == "tbl":
            from docx.table import Table
            table = Table(child, doc)
            output_lines.append("")
            output_lines.append(table_to_md(table))
            output_lines.append("")
            continue

        if tag == "p":
            from docx.text.paragraph import Paragraph
            paragraph = Paragraph(child, doc)

            text = runs_to_md(paragraph)
            raw_text = paragraph.text.strip()

            if not raw_text:
                output_lines.append("")
                continue

            level = heading_level(paragraph)
            if level > 0:
                output_lines.append(f"\n{'#' * level} {raw_text}\n")
                continue

            if is_list_paragraph(paragraph):
                style_name = paragraph.style.name.lower() if paragraph.style and paragraph.style.name else ""
                if "number" in style_name or "número" in style_name or "numerada" in style_name:
                    output_lines.append(f"1. {text}")
                else:
                    output_lines.append(f"- {text}")
                continue

            output_lines.append(text)

    return "\n".join(output_lines)