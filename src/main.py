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

def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY no encontrada.")
        return

    client = OpenAI(api_key=api_key)

    parser = argparse.ArgumentParser(description="Pipeline Completa TOLVIA")
    parser.add_argument("input_file", help="Ruta al archivo DOCX o MD de origen")
    parser.add_argument("--tests", type=int, default=None, help="Numero de tests QA a generar (opcional)")
    
    # Nuevas flags para rutas personalizadas
    parser.add_argument("--md_dir", help="Directorio personalizado para los archivos Markdown")
    parser.add_argument("--json_dir", help="Directorio personalizado para los archivos JSON")
    parser.add_argument("--output_name", help="Nombre base personalizado para los archivos de salida")
    
    args = parser.parse_args()

    input_path = os.path.abspath(args.input_file)
    if not os.path.exists(input_path):
        print(f"Error: No se encuentra el archivo en {input_path}")
        return

    # Calculo de directorios por defecto
    src_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(src_dir)
    default_files_dir = os.path.join(project_root, "files")
    
    # Aplicar directorios personalizados si se proveen
    md_dir = os.path.abspath(args.md_dir) if args.md_dir else os.path.join(default_files_dir, "md")
    json_dir = os.path.abspath(args.json_dir) if args.json_dir else os.path.join(default_files_dir, "json")

    os.makedirs(md_dir, exist_ok=True)
    os.makedirs(json_dir, exist_ok=True)

    # Nomenclatura base (usa la custom si existe, si no extrae la del archivo)
    base_name = args.output_name if args.output_name else os.path.splitext(os.path.basename(input_path))[0]
    
    raw_md_path = os.path.join(md_dir, f"{base_name}_raw.md")
    structured_md_path = os.path.join(md_dir, f"{base_name}_structured.md")
    
    final_json_path = os.path.join(json_dir, f"{base_name}_workflow.json")
    qa_json_path = os.path.join(json_dir, f"{base_name}_tests_scenarios.json")
    
    temp_1 = os.path.join(json_dir, "temp_1.json")
    temp_2 = os.path.join(json_dir, "temp_2.json")

    print(f"Iniciando Pipeline para: {base_name}")
    print(f"Directorio MD: {md_dir}")
    print(f"Directorio JSON: {json_dir}\n")

    try:
        # PASO 1: DOCX a MD
        if input_path.lower().endswith('.docx'):
            print("[Paso 1] Convirtiendo DOCX a Markdown en bruto...")
            raw_content = docx_to_md.docx_to_md(input_path)
            with open(raw_md_path, 'w', encoding='utf-8') as f:
                f.write(raw_content)
            current_raw_md = raw_md_path
        else:
            print("[Paso 1] Omitido (el input ya es Markdown)")
            current_raw_md = input_path

        # PASO 2: Estructurador
        print("[Paso 2] Estructurando el documento...")
        structurer.run_structurer(current_raw_md, structured_md_path, client)

        with open(structured_md_path, 'r', encoding='utf-8') as f:
            structured_md_content = f.read()

        # PASO 3: JSON Minimal
        print("[Paso 3] Generando config global y extracciones...")
        minimal.generate_minimal_json(structured_md_content, temp_1, client)

        # PASO 4: Workflow
        print("[Paso 4] Construyendo flujo conversacional...")
        workflow.build_workflow_nodes(structured_md_content, temp_1, temp_2, client)

        # PASO 5: Condicionales
        print("[Paso 5] Inyectando objeciones y FAQs...")
        conditionals.add_conditionals(structured_md_content, temp_2, final_json_path, client)

        # PASO 6: Tests
        if args.tests is not None:
            print(f"[Paso 6] Construyendo {args.tests} escenarios de QA...")
            tests_gen.generate_tests(structured_md_path, final_json_path, qa_json_path, args.tests, client)

        # Limpieza de temporales
        for t in [temp_1, temp_2]:
            if os.path.exists(t):
                os.remove(t)

        print("\nPROCESO FINALIZADO CON EXITO.")
        print(f"-> MD Estructurado: {structured_md_path}")
        print(f"-> Agente Listo: {final_json_path}")
        if args.tests is not None:
            print(f"-> Tests QA: {qa_json_path}")

    except Exception as e:
        print(f"\nError fatal en la ejecucion: {str(e)}")

if __name__ == "__main__":
    main()