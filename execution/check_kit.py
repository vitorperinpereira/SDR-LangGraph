import importlib
import sys


def check_import(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        print(f"[OK] {module_name}")
        return True
    except ImportError as exc:
        print(f"[FAIL] {module_name}: {exc}")
        return False


def main() -> None:
    print("Verificando dependencias do SDR Agent...")
    modules = [
        "fastapi",
        "uvicorn",
        "pydantic_settings",
        "langgraph",
        "langchain",
        "langchain_openai",
        "supabase",
        "googleapiclient",
        "google.auth",
        "dotenv",
        "requests",
        "httpx",
        "pytest",
        "ruff",
    ]

    failed = [module for module in modules if not check_import(module)]
    if failed:
        print(f"\nDependencias faltando: {', '.join(failed)}")
        sys.exit(1)

    print("\nKit validado com sucesso.")


if __name__ == "__main__":
    main()
