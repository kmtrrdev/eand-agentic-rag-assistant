from pathlib import Path
from typing import List

from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader


def load_pdf(file_path: str) -> List[Document]:
    """
    Load a PDF file and return LangChain documents.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    loader = PyPDFLoader(str(path))

    documents = loader.load()

    for doc in documents:
        doc.metadata["source_file"] = path.name
        doc.metadata["source_path"] = str(path)

    return documents


def load_all_pdfs(directory: str) -> List[Document]:
    """
    Load all PDFs from a directory.
    """

    directory_path = Path(directory)

    if not directory_path.exists():
        raise FileNotFoundError(directory)

    all_documents = []

    for pdf_file in sorted(
        directory_path.glob("*.pdf")
    ):
        print(f"Loading: {pdf_file.name}")

        docs = load_pdf(str(pdf_file))

        all_documents.extend(docs)

    return all_documents