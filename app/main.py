from app.agent.graph import get_agent


def ask_agent(question: str):
    """Query the e& Egypt agentic knowledge base."""
    agent = get_agent()
    return agent.invoke({
        "question": question,
        "history": [],
        "retry_count": 0,
    })


if __name__ == "__main__":
    question = input("Ask about e& Egypt: ")
    result = ask_agent(question)

    print("\nANSWER:")
    print(result.get("answer"))

    print("\nCONFIDENCE:")
    print(result.get("confidence"))

    print("\nSOURCES:")
    for source in result.get("sources", []):
        print(source)
