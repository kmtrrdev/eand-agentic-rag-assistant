from pathlib import Path
from typing import List
from langchain_core.documents import Document

SOURCE_METADATA = {
    "PrepaidSystems.pdf": {
        "category": "mobile",
        "service": "prepaid",
        "product": "Simple Prepaid Plans (Aqwa Card, Ahlan Pay As You Go, Daily Bundles, Menu El Geneh)",
        "line_type": "mobile_phone",
        "plan_status": "current",
        "applies_to_current_plans": True,
    },
    "HekayaInternet.pdf": {
        "category": "mobile",
        "service": "internet",
        "product": "Hekaya Internet (Monthly & Mini Plans)",
        "line_type": "mobile_phone",
        "plan_status": "current",
        "applies_to_current_plans": True,
    },
    "HekayaMixat.pdf": {
        "category": "mobile",
        "service": "mobile_bundle",
        "product": "Hekaya Mixat (Monthly Bundles, Super Connect, Family Lines)",
        "line_type": "mobile_phone",
        # Note: plan_status is intentionally NOT forced here — individual chunks
        # inside HekayaMixat.pdf may be overridden to "legacy" by _tag_legacy_status()
        # in chunker.py based on content analysis.  The default below applies only
        # to pages that don't match any legacy signal.
        "plan_status": "current",
        "applies_to_current_plans": True,
    },
    "DataLine.pdf": {
        "category": "internet",
        "service": "data_line",
        "product": "Data Line (Dedicated MiFi & USB Modem SIM)",
        "line_type": "mifi_router",
        "plan_status": "current",
        "applies_to_current_plans": True,
    },
    "Emerald (2).pdf": {
        "category": "postpaid",
        "service": "emerald",
        "product": "Emerald Postpaid Plans (430, 780, 1120, 1725, 3450)",
        "line_type": "mobile_phone",
        "plan_status": "current",
        "applies_to_current_plans": True,
    },
}


def enrich_metadata(documents: List[Document]) -> List[Document]:
    """Enrich document chunks with validated telecom metadata."""
    enriched = []

    for doc in documents:
        source_name = Path(doc.metadata.get("source_file", "unknown")).name

        metadata = SOURCE_METADATA.get(
            source_name,
            {
                "category": "general",
                "service": "general",
                "product": "unknown",
                "line_type": "mobile_phone",
                "plan_status": "current",
                "applies_to_current_plans": True,
            }
        )

        doc.metadata.update(metadata)
        enriched.append(doc)

    return enriched