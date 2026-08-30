"""
app/ingestion/chunker.py
------------------------
Two-strategy document chunker for the e& Egypt telecom knowledge base.

Strategy 1 — TelecomStructureChunker (default, "smart"):
  Detects natural document structure — package headers, USSD code blocks,
  numbered sections, table-like patterns — and preserves complete semantic
  units (e.g. a full package description with its price, quota, and code).
  Falls back to RecursiveCharacterTextSplitter for unstructured pages.

Strategy 2 — Character-based ("character"):
  The original RecursiveCharacterTextSplitter behaviour.
  Preserved for backward compatibility and A/B testing.

Both strategies:
  - Assign deterministic chunk_id metadata.
  - Preserve all incoming metadata (source_file, page, category, etc.).
  - Add chunk_type, section_title, and parent_doc_id for the smart strategy.
"""
import hashlib
import re
from typing import List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings

# ─── Telecom-domain package & section headers ───────────────────────────────
_PACKAGE_HEADER_PATTERNS = [
    re.compile(r"^\s*Recharge:\s*(?:Aqwa Card|أقوى كارت)\s*\d+(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"^\s*(?:باقة|Bundle|Package|Plan):\s*(?:حكاية|Hekaya|إمرالد|Emerald|داتا لاين|DataLine|أهلاً|Ahlan)\s*\d+", re.IGNORECASE),
    re.compile(r"^\s*\d+\.\s+(?:Overview|Aqwa Card|Hekaya|Emerald|DataLine|Ahlan|Menu El Geneh|Daily Plans|Monthly Bundles)", re.IGNORECASE),
    re.compile(r"^\s*#{1,3}\s+\S"),
]

_EXACT_PLAN_PATTERNS = [
    (re.compile(r"(?:Aqwa Card|أقوى كارت|اقوى كارت)\s*(\d+(?:\.\d+)?)", re.IGNORECASE), "Aqwa Card {}"),
    (re.compile(r"(?:Hekaya Mixat|حكاية مكسات|حكاية ميكسات)\s*(\d+)", re.IGNORECASE), "Hekaya Mixat {}"),
    (re.compile(r"(?:Hekaya Internet|حكاية إنترنت|حكاية انترنت)\s*(\d+)", re.IGNORECASE), "Hekaya Internet {}"),
    (re.compile(r"(?:Emerald|إمرالد|امرالد)\s*(\d+)", re.IGNORECASE), "Emerald {}"),
    (re.compile(r"(?:DataLine|Data Line|داتا لاين)\s*(\d+(?:\.\d+)?(?:\s*GB)?)", re.IGNORECASE), "DataLine {}"),
    (re.compile(r"(?:Ahlan 15 Piastres|أهلاً 15 قرش|أهلا 15 قرش)", re.IGNORECASE), "Ahlan 15 Piastres"),
    (re.compile(r"(?:Ahlan Super Yes|أهلاً سوبر يエス|أهلاً سوبر يس)", re.IGNORECASE), "Ahlan Super Yes"),
    (re.compile(r"(?:Menu El Geneh|منيو الجنيه)", re.IGNORECASE), "Menu El Geneh"),
]

_USSD_RE = re.compile(r"\*\d+[#*\d]*#")

# ─── Legacy Hekaya Mixat detection (ingestion-time tagging) ─────────────────
# The KB contains two Hekaya Mixat naming systems that must never be mixed:
#   CURRENT  (active): 52 | 69 | 92 | 120 | 180 | 270  EGP
#   LEGACY (retired):  35 | 50 | 65 | 100 | 150 | 200  EGP
# Chunks belonging to the legacy system are tagged so the retrieval layer
# can exclude them from results for current-plan queries.
_LEGACY_CHUNK_PHRASES = [
    "legacy naming system",
    "older naming system",
    "old naming system",
    "may differ from current active plans",
    "النظام القديم",
    "الباقات القديمة",
    "الأسماء القديمة",
    "weekly consumption",
    "weekly max consumption",
    "الاستهلاك الأسبوعي",
    "الحد الأسبوعي",
]
_LEGACY_MIXAT_TIER_RE = re.compile(
    r"(?:Hekaya\s+Mixat|حكاية\s+مكسات|حكاية\s+ميكسات)\s*(35|50|65|100|150|200)\b",
    re.IGNORECASE,
)
_CURRENT_MIXAT_TIERS_RE = re.compile(
    r"(?:Hekaya\s+Mixat|حكاية\s+مكسات|حكاية\s+ميكسات)\s*(52|69|92|120|180|270)\b",
    re.IGNORECASE,
)


def _tag_legacy_status(meta: dict, content: str, source_file: str) -> None:
    """
    Stamps chunk metadata with plan_status and applies_to_current_plans.

    Only Hekaya Mixat source documents are eligible for the legacy tag to
    prevent false positives in other documents (e.g. a price of 150 EGP in
    a DataLine or Emerald chunk should not be flagged).

    Sets:
        meta["plan_status"]              = "legacy" | "current"
        meta["applies_to_current_plans"] = False | True
        meta["legacy_reason"]            = str (populated when legacy)
    """
    is_mixat_source = "mixat" in source_file.lower()

    # Default: current / applicable
    meta["plan_status"] = "current"
    meta["applies_to_current_plans"] = True

    if not is_mixat_source:
        return  # Only tag Hekaya Mixat documents

    c_lower = content.lower()

    # 1. Explicit self-declaration phrase (highest confidence)
    for phrase in _LEGACY_CHUNK_PHRASES:
        if phrase in c_lower:
            meta["plan_status"] = "legacy"
            meta["applies_to_current_plans"] = False
            meta["legacy_reason"] = f"explicit phrase: {phrase!r}"
            return

    # 2. Contains a legacy-tier plan name AND no current-tier plan name
    has_legacy_tier = bool(_LEGACY_MIXAT_TIER_RE.search(content))
    has_current_tier = bool(_CURRENT_MIXAT_TIERS_RE.search(content))
    if has_legacy_tier and not has_current_tier:
        meta["plan_status"] = "legacy"
        meta["applies_to_current_plans"] = False
        m = _LEGACY_MIXAT_TIER_RE.search(content)
        meta["legacy_reason"] = f"legacy tier reference: Hekaya Mixat {m.group(1) if m else '?'}"


def _doc_hash(doc: Document) -> str:
    """Stable hash of a document's source + page for parent tracking."""
    key = f"{doc.metadata.get('source_file', '')}:{doc.metadata.get('page', 0)}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def _is_package_boundary(line: str) -> bool:
    """Return True only when line marks the beginning of a NEW package or major section."""
    line = line.strip()
    if not line:
        return False
    # Never split on individual attribute lines like Price, Core content, Validity, Code
    if any(line.lower().startswith(prefix) for prefix in [
        "price of", "core content", "validity of", "subscription code", "no extra minutes",
        "video, entertainment", "hekaya mini", "سعر", "محتوى", "صلاحية", "كود", "المبلغ"
    ]):
        return False
    return any(pat.search(line) for pat in _PACKAGE_HEADER_PATTERNS)


def _extract_plan_name(text: str) -> Optional[str]:
    """Extract exact canonical plan name from chunk text."""
    for pat, template in _EXACT_PLAN_PATTERNS:
        m = pat.search(text)
        if m:
            if "{}" in template:
                return template.format(m.group(1))
            return template
    return None


def _extract_section_title(lines: List[str]) -> str:
    """Extract a representative title from the first few lines of a chunk."""
    for line in lines[:5]:
        line = line.strip()
        if len(line) > 3 and not line.startswith("---"):
            return line[:120]
    return ""


def _smart_split_page(doc: Document, chunk_size: int, chunk_overlap: int) -> List[Document]:
    text = doc.page_content.strip()
    if not text:
        return []

    parent_id = _doc_hash(doc)
    base_meta = dict(doc.metadata)
    base_meta["parent_doc_id"] = parent_id

    lines = text.split("\n")
    chunks: List[Document] = []
    buffer: List[str] = []
    buffer_len = 0

    def _emit(buf: List[str], chunk_type: str = "section") -> None:
        raw = "\n".join(buf).strip()
        if not raw:
            return

        plan_name = _extract_plan_name(raw)
        src_file = base_meta.get("source_file", "")

        if len(raw) > chunk_size * 2.0:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            sub_chunks = splitter.create_documents([raw])
            for sub in sub_chunks:
                meta = dict(base_meta)
                meta["chunk_type"] = "package" if plan_name else chunk_type
                meta["section_title"] = _extract_section_title(buf)
                if plan_name:
                    meta["package_name"] = plan_name
                    meta["plan_name"] = plan_name
                # ── Ingestion-time legacy status tagging ──
                _tag_legacy_status(meta, sub.page_content, src_file)
                chunks.append(Document(page_content=sub.page_content, metadata=meta))
        else:
            meta = dict(base_meta)
            meta["chunk_type"] = "package" if plan_name else chunk_type
            meta["section_title"] = _extract_section_title(buf)
            if plan_name:
                meta["package_name"] = plan_name
                meta["plan_name"] = plan_name
            # ── Ingestion-time legacy status tagging ──
            _tag_legacy_status(meta, raw, src_file)
            chunks.append(Document(page_content=raw, metadata=meta))

    for line in lines:
        if _is_package_boundary(line) and buffer_len > 150:
            _emit(buffer, "section")
            buffer = [line]
            buffer_len = len(line)
        else:
            buffer.append(line)
            buffer_len += len(line) + 1

    if buffer:
        _emit(buffer, "general")

    return chunks


class TelecomStructureChunker:
    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        self._fallback_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", "## ", ". ", " ", ""],
        )

    def split_documents(self, documents: List[Document]) -> List[Document]:
        all_chunks: List[Document] = []

        for doc in documents:
            text = (doc.page_content or "").strip()
            if not text:
                continue

            has_structure = (
                bool(_extract_plan_name(text))
                or any(pat.search(text) for pat in _PACKAGE_HEADER_PATTERNS)
                or bool(_USSD_RE.search(text))
                or text.count("\n") > 3
            )

            if has_structure:
                page_chunks = _smart_split_page(doc, self.chunk_size, self.chunk_overlap)
            else:
                page_chunks = self._fallback_splitter.split_documents([doc])
                for c in page_chunks:
                    c.metadata["chunk_type"] = "general"
                    c.metadata.setdefault("parent_doc_id", _doc_hash(doc))
                    src_file = c.metadata.get("source_file", "")
                    _tag_legacy_status(c.metadata, c.page_content, src_file)

            all_chunks.extend(page_chunks)

        for idx, chunk in enumerate(all_chunks):
            chunk.metadata["chunk_id"] = idx

        return all_chunks


def split_documents(
    documents: List[Document],
    strategy: str = "smart",
) -> List[Document]:
    if strategy == "character":
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", "## ", ". ", " ", ""],
        )
        chunks = splitter.split_documents(documents)
        for idx, chunk in enumerate(chunks):
            chunk.metadata["chunk_id"] = idx
            chunk.metadata["chunk_type"] = "general"
            src_file = chunk.metadata.get("source_file", "")
            _tag_legacy_status(chunk.metadata, chunk.page_content, src_file)
        return chunks

    chunker = TelecomStructureChunker()
    return chunker.split_documents(documents)
