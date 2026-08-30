import re
from typing import List

from langchain_core.documents import Document


def clean_text(text: str) -> str:
    """
    Basic cleanup: normalize whitespace and drop empty lines
    left over from PDF extraction.
    """

    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def clean_documents(
    documents: List[Document]
) -> List[Document]:

    cleaned = []

    for doc in documents:

        text = clean_text(doc.page_content)

        if not text:
            continue

        doc.page_content = text
        cleaned.append(doc)

    return cleaned
