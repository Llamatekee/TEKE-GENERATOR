import os
import sys
import argparse
import importlib
from dotenv import load_dotenv
from openai import OpenAI

# Añadimos src al path para que encuentre los modulos con numeros
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

minimal = importlib.import_module("01_minimal")
workflow = importlib.import_module("02_workflow")
conditionals = importlib.import_module("03_conditionals")

def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY no encontrada.")
        return

    client = OpenAI(api_key=api_key)

    parser = argparse.ArgumentParser()
    parser.add_argument("md_path", help="Ruta relativa al MD (ej: docs/md/archivo.md)")
    parser.add_argument("final_json_path", help="Ruta relativa al JSON de salida (ej: docs/json/final.json)")
    args = parser.parse_args()

    # Validacion simple desde la raiz del proyecto
    if not os.path.exists(args.md_path):
        print(f"Error: No se encuentra el archivo en {args.md_path}")
        return

    with open(args.md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # Definimos temporales en la misma carpeta de destino para evitar lios
    output_dir = os.path.dirname(args.final_json_path)
    temp_1 = os.path.join(output_dir, "temp_1.json")
    temp_2 = os.path.join(output_dir, "temp_2.json")

    print("Procesando flujo...")

    try:
        minimal.generate_minimal_json(md_content, temp_1, client)
        workflow.build_workflow_nodes(md_content, temp_1, temp_2, client)
        conditionals.add_conditionals(md_content, temp_2, args.final_json_path, client)

        # Limpieza de temporales
        for t in [temp_1, temp_2]:
            if os.path.exists(t):
                os.remove(t)

        print(f"Exito. Archivo generado en: {args.final_json_path}")

    except Exception as e:
        print(f"Error en la pipeline: {str(e)}")

if __name__ == "__main__":
    main()