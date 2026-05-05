import os
import sys
import argparse
import importlib
from dotenv import load_dotenv
from openai import OpenAI

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

minimal = importlib.import_module("01_minimal")
workflow = importlib.import_module("02_workflow")
conditionals = importlib.import_module("03_conditionals")
tests_gen = importlib.import_module("04_test")

def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY no encontrada.")
        return

    client = OpenAI(api_key=api_key)

    parser = argparse.ArgumentParser()
    parser.add_argument("md_path", help="Ruta relativa al MD de diseño")
    parser.add_argument("final_json_path", help="Ruta relativa al JSON del workflow")
    parser.add_argument("--tests", type=int, default=None, help="Numero total de tests QA a generar (opcional)")
    args = parser.parse_args()

    if not os.path.exists(args.md_path):
        print(f"Error: No se encuentra el archivo en {args.md_path}")
        return

    with open(args.md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()

    output_dir = os.path.dirname(args.final_json_path)
    temp_1 = os.path.join(output_dir, "temp_1.json")
    temp_2 = os.path.join(output_dir, "temp_2.json")
    
    # Nombre dinamico para el archivo de tests
    base_name = os.path.splitext(os.path.basename(args.final_json_path))[0]
    qa_json_path = os.path.join(output_dir, f"{base_name}_tests.json")

    print("Procesando flujo completo...")

    try:
        minimal.generate_minimal_json(md_content, temp_1, client)
        workflow.build_workflow_nodes(md_content, temp_1, temp_2, client)
        conditionals.add_conditionals(md_content, temp_2, args.final_json_path, client)

        if args.tests is not None:
            # Si tiene escenarios en el MD, los leera. Si no, los inventara todos.
            tests_gen.generate_tests(args.md_path, args.final_json_path, qa_json_path, args.tests, client)

        for t in [temp_1, temp_2]:
            if os.path.exists(t):
                os.remove(t)

        print(f"Exito. Workflow generado en: {args.final_json_path}")
        if args.tests is not None:
            print(f"Exito. Tests generados en: {qa_json_path}")

    except Exception as e:
        print(f"Error en la pipeline: {str(e)}")

if __name__ == "__main__":
    main()