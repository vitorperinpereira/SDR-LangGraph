import asyncio
from pathlib import Path

from langchain_core.messages import HumanMessage

from app.graph import app_graph, draw_workflow_png
from app.graph.nodes.classifier import classify_intent
from app.graph.tools.calendar import buscar_horarios_disponiveis
from app.graph.tools.kb_retriever import kb_gmv


async def main() -> None:
    classification = classify_intent("Qual o preco do clareamento?")
    print(f"classifier={classification.model_dump()}")

    kb_result = kb_gmv.invoke({"query": "formas de pagamento", "top_k": 2})
    print(f"kb_gmv={kb_result}")

    slots = buscar_horarios_disponiveis.invoke({"periodo": "tarde", "limit": 2})
    print(f"slots={slots}")

    config = {"configurable": {"thread_id": "phase2-check-thread"}}
    result = await app_graph.ainvoke(
        {
            "messages": [HumanMessage(content="Meu nome e Carlos e estou com dor de dente.")],
            "clinic_id": "clinic-1",
            "thread_id": "phase2-check-thread",
        },
        config=config,
    )
    print(f"workflow_stage={result.get('stage')}")
    print(f"workflow_intent={result.get('intent')}")

    try:
        png_bytes = draw_workflow_png()
        output_path = Path("execution/phase2-workflow.png")
        output_path.write_bytes(png_bytes)
        print(f"graph_png=ok path={output_path}")
    except Exception as exc:
        print(f"graph_png=error detail={exc}")


if __name__ == "__main__":
    asyncio.run(main())
