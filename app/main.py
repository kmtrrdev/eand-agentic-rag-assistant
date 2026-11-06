"""
CLI test harness — run a single question through the agent without starting
the HTTP server.

Usage:
    python -m app.main "What is the price of Aqwa Card 19?"
    python -m app.main            # interactive loop
"""
import sys

from app.agent.graph import get_agent


def ask(question: str) -> None:
    agent = get_agent()
    result = agent.invoke({"question": question, "history": [], "conversation_id": None})
    print(f"\nQ: {question}")
    print(f"A: {result.get('answer')}")
    print(f"[intent={result.get('intent')} strategy={result.get('strategy')} "
          f"validation={result.get('validation_result')} confidence={result.get('confidence')}]")


def main() -> None:
    if len(sys.argv) > 1:
        ask(" ".join(sys.argv[1:]))
        return

    print("e& Egypt Agentic KB — interactive mode. Ctrl+C to exit.")
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question:
            ask(question)


if __name__ == "__main__":
    main()
