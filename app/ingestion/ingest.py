import argparse
from pathlib import Path

from app.ingestion.document_loader import load_all_pdfs
from app.ingestion.document_cleaner import clean_documents
from app.ingestion.metadata import enrich_metadata
from app.ingestion.chunker import split_documents
from app.vectorstore.index_manager import IndexManager
from app.config import settings


def get_data_path() -> Path:
    candidates = [
        Path("app/data"),
        Path(__file__).resolve().parent.parent / "data",
        Path("data"),
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    return Path(__file__).resolve().parent.parent / "data"


def run_ingestion(rebuild: bool = False, strategy: str = None):
    """
    Full ingestion pipeline: load PDFs -> clean -> enrich metadata -> chunk -> index.

    Args:
        rebuild: If True, clear existing ChromaDB collection before indexing.
        strategy: Chunking strategy. "smart" (structure-aware, default) or "character" (legacy).
                  Falls back to CHUNKING_STRATEGY env var if not specified.
    """
    chunking_strategy = strategy or settings.CHUNKING_STRATEGY

    data_path = get_data_path()
    print(f"\n=== e& Egypt KB Ingestion Pipeline ===")
    print(f"  Data path  : {data_path}")
    print(f"  Strategy   : {chunking_strategy}")
    print(f"  Rebuild    : {rebuild}")

    print(f"\n=== Loading Documents from {data_path} ===")
    documents = load_all_pdfs(str(data_path))
    print(f"Loaded pages: {len(documents)}")

    print("\n=== Cleaning ===")
    documents = clean_documents(documents)
    print(f"Clean documents: {len(documents)}")

    print("\n=== Adding Metadata ===")
    documents = enrich_metadata(documents)

    print(f"\n=== Chunking (strategy={chunking_strategy!r}) ===")
    chunks = split_documents(documents, strategy=chunking_strategy)
    print(f"Created chunks: {len(chunks)}")

    # Print chunk type distribution for observability
    from collections import Counter
    type_dist = Counter(c.metadata.get("chunk_type", "general") for c in chunks)
    print(f"  Chunk types: {dict(type_dist)}")

    print("\n=== Indexing into ChromaDB ===")
    index_manager = IndexManager()
    if rebuild:
        print("Rebuild requested: clearing existing collection...")
        index_manager.clear_collection()

    count = index_manager.add_documents(chunks)
    print(f"\n=== Ingestion Complete! ({count} chunks indexed) ===")
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Ingest PDFs into the e& Egypt ChromaDB knowledge base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.ingestion.ingest                         # Smart chunking (default)
  python -m app.ingestion.ingest --strategy character    # Legacy character chunking
  python -m app.ingestion.ingest --rebuild               # Clear + re-index
  python -m app.ingestion.ingest --rebuild --strategy smart  # Full rebuild with smart chunking
"""
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Clear existing ChromaDB collection before ingestion",
    )
    parser.add_argument(
        "--strategy",
        choices=["smart", "character"],
        default=None,
        help='Chunking strategy: "smart" (structure-aware, default) or "character" (legacy)',
    )
    args = parser.parse_args()

    run_ingestion(rebuild=args.rebuild, strategy=args.strategy)


if __name__ == "__main__":
    main()