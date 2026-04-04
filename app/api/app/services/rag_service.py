from chroma.search_pipeline import build_search_plan


def make_rag_response(question: str) -> dict:
    search_plan = build_search_plan(question)

    return {
        "question": question,
        "search_plan": search_plan,
        "message": "Search plan generated successfully."
    }