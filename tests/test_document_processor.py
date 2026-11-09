from langchain_core.documents import Document

from services.document_processor import chunk_documents, extract_text


def test_chunk_metadata_injected():
    docs = [Document(page_content="Some test content for chunking.", metadata={})]
    chunks = chunk_documents(docs, "abc-123", "notes.txt")
    assert all(c.metadata["doc_id"] == "abc-123" for c in chunks)
    assert all(c.metadata["filename"] == "notes.txt" for c in chunks)
    assert all(c.metadata["file_type"] == ".txt" for c in chunks)


def test_chunk_page_number_normalized():
    docs = [
        Document(page_content="First page content.", metadata={"page": 0}),
        Document(page_content="Second page content.", metadata={"page": 1}),
    ]
    chunks = chunk_documents(docs, "abc-123", "report.pdf")
    page_numbers = {c.metadata.get("page_number") for c in chunks}
    assert 1 in page_numbers
    assert 2 in page_numbers


def test_chunk_size_respected():
    long_text = "word " * 500  # ~2500 chars; default chunk_size=1000
    docs = [Document(page_content=long_text, metadata={})]
    chunks = chunk_documents(docs, "abc-123", "long.txt")
    assert len(chunks) >= 2


def test_extract_text_txt(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("Hello from a text file.", encoding="utf-8")
    docs = extract_text(str(f), ".txt")
    assert len(docs) >= 1
    assert "Hello from a text file." in docs[0].page_content


def test_extract_text_unsupported_type(tmp_path):
    f = tmp_path / "bad.xyz"
    f.write_text("data")
    try:
        extract_text(str(f), ".xyz")
        raise AssertionError("Expected ValueError")
    except ValueError as e:
        assert ".xyz" in str(e)
