"""
CLI: rebuild the Chroma vector store from app/data/catalog.

Usage:
    python -m app.ingestion.ingest --rebuild
"""
import argparse
import logging
import sys

from app.ingestion.catalog_renderer import render_all_chunks
from app.retrieval.bm25_index import clear_cache as clear_bm25_cache
from app.vectorstore.chroma_client import rebuild_collection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.ingestion.ingest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="Drop and rebuild the collection from scratch.")
    args = parser.parse_args()

    if not args.rebuild:
        logger.info("Nothing to do — pass --rebuild to (re)build the vector store from the catalog.")
        return

    chunks = render_all_chunks()
    logger.info("Rendered %d chunks from the catalog.", len(chunks))

    by_family: dict = {}
    for _, meta in chunks:
        by_family[meta["family"]] = by_family.get(meta["family"], 0) + 1
    for family, count in sorted(by_family.items()):
        logger.info("  %-16s %d chunks", family, count)

    count = rebuild_collection(chunks)
    clear_bm25_cache()
    logger.info("Indexed %d chunks into Chroma collection at the configured CHROMA_PATH.", count)


if __name__ == "__main__":
    sys.exit(main() or 0)
