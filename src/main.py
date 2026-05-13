import os
import sys
import argparse
import importlib
from dotenv import load_dotenv
from openai import OpenAI

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

docx_to_md = importlib.import_module("01_docx_to_md")
structurer = importlib.import_module("02_structurer")
minimal = importlib.import_module("03_minimal")
workflow = importlib.import_module("04_workflow")
conditionals = importlib.import_module("05_conditionals")
tests_gen = importlib.import_module("06_test")
rag_briefing = importlib.import_module("07_rag_briefing")

def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY no encontrada.")
        return

    client = OpenAI(api_key=api_key)

    parser = argparse.ArgumentParser(description="Pipeline Completa TOLVIA")
    # Cambiamos input_file a input_files con nargs='+' para aceptar multiples rutas
    parser.add_argument("input_files", nargs='+', help="Ruta al archivo principal, seguido de archivos extra opcionales (.docx o .md)")
    parser.add_argument("--tests", type=int, default=None, help="Numero de tests QA a generar (opcional)")
    parser.add_argument("--rag", action="store_true", help="Genera un RAG Briefing con objetivos y candidatos de documentos (.md)")
    parser.add_argument("--md_dir", help="Directorio personalizado para los archivos Markdown")
    parser.add_argument("--json_dir", help="Directorio personalizado para los archivos JSON")
    parser.add_argument("--output_name", help="Nombre base personalizado para los archivos de salida")
    parser.add_argument("--verbose", action="store_true", help="Activa el log detallado de procesos")
    
    args = parser.parse_args()
    verbose = args.verbose

    # Validacion de todos los archivos
    for filepath in args.input_files:
        if not os.path.exists(os.path.abspath(filepath)):
            print(f"Error: No se encuentra el archivo en {filepath}")
            return

    # El primer archivo es el main
    main_file = os.path.abspath(args.input_files[0])

    src_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(src_dir)
    default_files_dir = os.path.join(project_root, "files")
    
    md_dir = os.path.abspath(args.md_dir) if args.md_dir else os.path.join(default_files_dir, "md")
    json_dir = os.path.abspath(args.json_dir) if args.json_dir else os.path.join(default_files_dir, "json")

    os.makedirs(md_dir, exist_ok=True)
    os.makedirs(json_dir, exist_ok=True)

    base_name = args.output_name if args.output_name else os.path.splitext(os.path.basename(main_file))[0]
    
    raw_md_path = os.path.join(md_dir, f"{base_name}_raw.md")
    structured_md_path = os.path.join(md_dir, f"{base_name}_structured.md")
    final_json_path = os.path.join(json_dir, f"{base_name}_workflow.json")
    qa_json_path = os.path.join(json_dir, f"{base_name}_tests.json")
    temp_1 = os.path.join(json_dir, "temp_1.json")
    temp_2 = os.path.join(json_dir, "temp_2.json")

    if verbose:
        print(f"Iniciando Pipeline para: {base_name}")
        print(f"Archivos de entrada detectados: {len(args.input_files)}")

    try:
        # PASO 1: Procesar y concatenar todos los documentos
        combined_raw_content = ""
        for i, filepath in enumerate(args.input_files):
            abs_path = os.path.abspath(filepath)
            
            # Añadir separador si no es el primer documento
            if i > 0:
                combined_raw_content += "\n\n---\n\n"
            
            if abs_path.lower().endswith('.docx'):
                if verbose: print(f"[Paso 1] Convirtiendo DOCX: {os.path.basename(abs_path)}")
                combined_raw_content += docx_to_md.docx_to_md(abs_path)
            elif abs_path.lower().endswith('.md'):
                if verbose: print(f"[Paso 1] Leyendo MD: {os.path.basename(abs_path)}")
                with open(abs_path, 'r', encoding='utf-8') as f:
                    combined_raw_content += f.read()
            else:
                if verbose: print(f"[Paso 1] Aviso: Extension no soportada en {os.path.basename(abs_path)}")

        # Guardar el MD bruto combinado
        with open(raw_md_path, 'w', encoding='utf-8') as f:
            f.write(combined_raw_content)

        # PASOS 2 al 6: Se pasa la flag de verbose
        if verbose: print("\n[Paso 2] Estructurando el documento...")
        structurer.run_structurer(raw_md_path, structured_md_path, client, model="gpt-4o", verbose=verbose)

        with open(structured_md_path, 'r', encoding='utf-8') as f:
            structured_md_content = f.read()

        if verbose: print("[Paso 3] Generando config global y extracciones...")
        minimal.generate_minimal_json(structured_md_content, temp_1, client, verbose=verbose)

        if verbose: print("[Paso 4] Construyendo flujo conversacional...")
        workflow.build_workflow_nodes(structured_md_content, temp_1, temp_2, client, verbose=verbose)

        if verbose: print("[Paso 5] Inyectando objeciones y FAQs...")
        conditionals.add_conditionals(structured_md_content, temp_2, final_json_path, client, verbose=verbose)

        if args.tests is not None:
            if verbose: print(f"[Paso 6] Construyendo {args.tests} escenarios de QA...")
            tests_gen.generate_tests(structured_md_path, final_json_path, qa_json_path, args.tests, client, verbose=verbose)

        if args.rag:
            rag_path = os.path.join(md_dir, f"{base_name}_rag_briefing.md")
            if verbose: print("[Paso 7] Generando RAG Briefing...")
            with open(raw_md_path, 'r', encoding='utf-8') as f:
                raw_for_rag = f.read()
            rag_briefing.generate_rag_briefing(raw_for_rag, rag_path, client, source_name=base_name, verbose=verbose)

        for t in [temp_1, temp_2]:
            if os.path.exists(t):
                os.remove(t)

        if verbose:
            print("\nPROCESO FINALIZADO CON EXITO.")
            print(f"-> MD Estructurado: {structured_md_path}")
            print(f"-> Agente Listo: {final_json_path}")
            if args.tests is not None:
                print(f"-> Tests QA: {qa_json_path}")
            if args.rag:
                print(f"-> RAG Briefing: {rag_path}")

    except Exception as e:
        print(f"\nError fatal en la ejecucion: {str(e)}")

if __name__ == "__main__":
    main()