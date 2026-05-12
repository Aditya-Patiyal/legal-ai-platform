from __future__ import annotations

import os
from typing import Any, TYPE_CHECKING

import chromadb
from chromadb.api.models.Collection import Collection

from .database import CHROMA_DIR

if TYPE_CHECKING:
    from .document_parser import StructuredChunk

OLLAMA_EMBED_MODEL = "nomic-embed-text"
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
COLLECTION_NAME = "legal_documents"

HF_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HF_EMBED_URL = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{HF_EMBED_MODEL}"

# Lazy initialization - only create clients when needed
_ollama_client = None
_chroma_client = None


def get_ollama_client():
    """Get Ollama client, initializing lazily."""
    global _ollama_client
    if _ollama_client is None:
        from ollama import Client
        _ollama_client = Client(host=OLLAMA_HOST)
    return _ollama_client


def get_chroma_client():
    """Get ChromaDB client, initializing lazily."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _chroma_client


def get_collection() -> Collection:
    return get_chroma_client().get_or_create_collection(name=COLLECTION_NAME)


def _embed_text_ollama(text: str) -> list[float]:
    response = get_ollama_client().embeddings(model=OLLAMA_EMBED_MODEL, prompt=text)
    return response["embedding"]


def _embed_batch_hf(texts: list[str], api_key: str) -> list[list[float]]:
    """Call HuggingFace Inference API to embed a batch of texts."""
    import httpx
    response = httpx.post(
        HF_EMBED_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"inputs": texts, "options": {"wait_for_model": True}},
        timeout=60.0,
    )
    response.raise_for_status()
    result = response.json()
    if isinstance(result, list) and result and isinstance(result[0], list):
        return result
    return [[v for v in result]]


GROQ_EMBED_MODEL = "text-embedding-3-small" # placeholder if using another provider later or Groq's model
# Groq currently does not provide an official embedding endpoint in the same way OpenAI does.
# We will use HuggingFace as the primary cloud-only provider and remove Ollama fallbacks.

def embed_text(text: str) -> list[float] | None:
    """Embed a single text. Returns None if no embedding provider is available."""
    hf_key = os.getenv("HUGGINGFACE_API_KEY", "").strip()
    if hf_key:
        try:
            return _embed_batch_hf([text], hf_key)[0]
        except Exception as e:
            print(f"[EMBED] HuggingFace embedding failed: {e}")
    return None


def embed_texts(texts: list[str], batch_size: int = 20) -> list[list[float]] | None:
    """Embed multiple texts efficiently. Returns None if no provider is available."""
    if not texts:
        return []
    hf_key = os.getenv("HUGGINGFACE_API_KEY", "").strip()
    if hf_key:
        try:
            all_embeddings: list[list[float]] = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                all_embeddings.extend(_embed_batch_hf(batch, hf_key))
            return all_embeddings
        except Exception as e:
            print(f"[EMBED] HuggingFace batch embedding failed: {e}")
    return None


def add_document_chunks(user_id: int, document_id: int, filename: str, chunks: list[str]) -> None:
    if not chunks:
        return
    collection = get_collection()
    ids = [f"doc-{document_id}-chunk-{index}" for index in range(len(chunks))]
    metadatas: list[dict[str, Any]] = [
        {
            "user_id": user_id,
            "document_id": document_id,
            "filename": filename,
            "chunk_index": index,
        }
        for index in range(len(chunks))
    ]
    embeddings = embed_texts(chunks)
    if embeddings and len(embeddings) == len(chunks):
        collection.upsert(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
    else:
        # Let ChromaDB use its built-in default embedding function
        collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)


def add_structured_chunks(
    user_id: int,
    document_id: int,
    filename: str,
    chunks: list["StructuredChunk"],
) -> None:
    """Add structured chunks with rich metadata to the vector store."""
    if not chunks:
        return
    
    collection = get_collection()
    ids = [f"doc-{document_id}-chunk-{chunk.chunk_index}" for chunk in chunks]
    documents = [chunk.text for chunk in chunks]
    embeddings = embed_texts(documents)
    
    metadatas: list[dict[str, Any]] = []
    for chunk in chunks:
        meta = {
            "user_id": user_id,
            "document_id": document_id,
            "filename": filename,
            "chunk_index": chunk.chunk_index,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
        }
        if chunk.page_number is not None:
            meta["page_number"] = chunk.page_number
        if chunk.section_heading:
            meta["section_heading"] = chunk.section_heading
        if chunk.clause_number:
            meta["clause_number"] = chunk.clause_number
        metadatas.append(meta)
    
    if embeddings and len(embeddings) == len(documents):
        collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
    else:
        # Let ChromaDB use its built-in default embedding function
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


def query_document_chunks(document_id: int, query: str, limit: int = 4) -> list[dict[str, Any]]:
    collection = get_collection()
    try:
        embedding = embed_text(query)
        if embedding:
            results = collection.query(
                query_embeddings=[embedding],
                n_results=limit,
                where={"document_id": document_id},
                include=["documents", "metadatas", "distances"],
            )
        else:
            # Fall back to ChromaDB's default embedding via query_texts
            results = collection.query(
                query_texts=[query],
                n_results=limit,
                where={"document_id": document_id},
                include=["documents", "metadatas", "distances"],
            )
    except Exception as e:
        print(f"[EMBED] ChromaDB query failed: {e}")
        return []
    
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    ids = results.get("ids", [[]])[0]
    
    payload: list[dict[str, Any]] = []
    for doc_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        payload.append(
            {
                "id": doc_id,
                "text": document,
                "metadata": metadata,
                "distance": distance,
            }
        )
    return payload


def delete_document_chunks(document_id: int) -> None:
    """Delete all chunks for a document from the vector store."""
    collection = get_collection()
    try:
        results = collection.get(
            where={"document_id": document_id},
            include=[],
        )
        ids = results.get("ids", [])
        if ids:
            collection.delete(ids=ids)
    except Exception:
        pass
