from __future__ import annotations

import re
from typing import Any

from rank_bm25 import BM25Okapi

from .embeddings import embed_text, get_collection, OLLAMA_HOST
from .database import fetch_one


def tokenize(text: str) -> list[str]:
    """Simple tokenizer for BM25."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    return [t for t in tokens if len(t) > 1]


def get_document_chunks(document_id: int) -> list[dict[str, Any]]:
    """Retrieve all chunks for a document from ChromaDB."""
    collection = get_collection()
    results = collection.get(
        where={"document_id": document_id},
        include=["documents", "metadatas"],
    )
    
    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])
    ids = results.get("ids", [])
    
    chunks = []
    for doc, meta, chunk_id in zip(documents, metadatas, ids):
        chunks.append({
            "id": chunk_id,
            "text": doc,
            "metadata": meta,
        })
    return chunks


def bm25_search(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int = 10,
) -> list[tuple[dict[str, Any], float]]:
    """Perform BM25 lexical search over chunks."""
    if not chunks:
        return []
    
    corpus = [tokenize(chunk["text"]) for chunk in chunks]
    bm25 = BM25Okapi(corpus)
    query_tokens = tokenize(query)
    scores = bm25.get_scores(query_tokens)
    
    scored_chunks = list(zip(chunks, scores))
    scored_chunks.sort(key=lambda x: x[1], reverse=True)
    return scored_chunks[:top_k]


def vector_search(
    document_id: int,
    query: str,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Perform vector similarity search."""
    collection = get_collection()
    try:
        embedding = embed_text(query)
        if embedding:
            results = collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                where={"document_id": document_id},
                include=["documents", "metadatas", "distances"],
            )
        else:
            # Fall back to ChromaDB's default embedding via query_texts
            results = collection.query(
                query_texts=[query],
                n_results=top_k,
                where={"document_id": document_id},
                include=["documents", "metadatas", "distances"],
            )
    except Exception as e:
        print(f"[HYBRID] Vector search failed: {e}")
        return []
    
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    ids = results.get("ids", [[]])[0]
    
    chunks = []
    for doc, meta, dist, chunk_id in zip(documents, metadatas, distances, ids):
        chunks.append({
            "id": chunk_id,
            "text": doc,
            "metadata": meta,
            "vector_distance": dist,
            "vector_score": 1.0 / (1.0 + dist),
        })
    return chunks


def reciprocal_rank_fusion(
    results_list: list[list[dict[str, Any]]],
    k: int = 60,
) -> list[dict[str, Any]]:
    """
    Combine multiple ranked lists using Reciprocal Rank Fusion.
    Higher k means less emphasis on top ranks.
    """
    scores: dict[str, float] = {}
    chunk_map: dict[str, dict[str, Any]] = {}
    
    for results in results_list:
        for rank, chunk in enumerate(results):
            chunk_id = chunk["id"]
            if chunk_id not in chunk_map:
                chunk_map[chunk_id] = chunk
            scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (k + rank + 1)
    
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    
    fused = []
    for chunk_id in sorted_ids:
        chunk = chunk_map[chunk_id].copy()
        chunk["rrf_score"] = scores[chunk_id]
        fused.append(chunk)
    
    return fused


def rerank_chunks(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int = 4,
) -> list[dict[str, Any]]:
    """
    Rerank chunks based on query relevance signals.
    Uses a simple scoring heuristic combining multiple factors.
    """
    if not chunks:
        return []
    
    query_lower = query.lower()
    query_tokens = set(tokenize(query))
    
    scored = []
    for chunk in chunks:
        text = chunk["text"]
        text_lower = text.lower()
        text_tokens = set(tokenize(text))
        
        token_overlap = len(query_tokens & text_tokens) / max(len(query_tokens), 1)
        
        exact_match_bonus = 0.0
        for token in query_tokens:
            if token in text_lower:
                exact_match_bonus += 0.1
        
        section_bonus = 0.0
        metadata = chunk.get("metadata", {})
        if metadata.get("section_heading"):
            heading_lower = metadata["section_heading"].lower()
            if any(t in heading_lower for t in query_tokens):
                section_bonus = 0.2
        
        rrf_score = chunk.get("rrf_score", 0.5)
        vector_score = chunk.get("vector_score", 0.5)
        
        final_score = (
            0.3 * rrf_score * 10 +
            0.2 * vector_score +
            0.25 * token_overlap +
            0.15 * exact_match_bonus +
            0.1 * section_bonus
        )
        
        chunk_copy = chunk.copy()
        chunk_copy["rerank_score"] = final_score
        scored.append(chunk_copy)
    
    scored.sort(key=lambda x: x["rerank_score"], reverse=True)
    return scored[:top_k]


def hybrid_search(
    document_id: int,
    query: str,
    top_k: int = 4,
    vector_candidates: int = 15,
    bm25_candidates: int = 15,
) -> list[dict[str, Any]]:
    """
    Perform hybrid search combining vector and BM25 retrieval.
    
    1. Get candidates from vector search
    2. Get candidates from BM25 search
    3. Fuse results with RRF
    4. Rerank top results
    """
    all_chunks = get_document_chunks(document_id)
    
    if not all_chunks:
        return []
    
    vector_results = vector_search(document_id, query, top_k=vector_candidates)
    
    bm25_results_raw = bm25_search(query, all_chunks, top_k=bm25_candidates)
    bm25_results = [chunk for chunk, score in bm25_results_raw if score > 0]
    
    for i, chunk in enumerate(bm25_results):
        chunk["bm25_rank"] = i
    
    fused = reciprocal_rank_fusion([vector_results, bm25_results])
    
    reranked = rerank_chunks(query, fused, top_k=top_k)
    
    return reranked


def expand_legal_query(query: str) -> str:
    """
    Expand query with legal synonyms and related terms.
    """
    expansions = {
        "ipc": "indian penal code section crime criminal offense",
        "bns": "bharatiya nyaya sanhita criminal code",
        "crpc": "criminal procedure code procedural",
        "bnss": "bharatiya nagarik suraksha sanhita procedure",
        "cpc": "civil procedure code civil suit",
        "420": "cheating dishonest inducement fraud",
        "302": "murder culpable homicide death",
        "304": "culpable homicide death",
        "306": "abetment suicide",
        "376": "rape sexual assault",
        "498a": "cruelty husband relatives dowry harassment",
        "termination": "end terminate cancel expiry notice period",
        "penalty": "fine damages liquidated compensation",
        "indemnity": "indemnify hold harmless liability protection",
        "confidentiality": "confidential secret non-disclosure nda proprietary",
        "arbitration": "dispute resolution arbitrator mediation",
        "jurisdiction": "court venue governing law applicable",
        "breach": "violation default non-compliance failure",
        "notice period": "prior notice termination advance intimation",
        "force majeure": "act of god unforeseen circumstances",
        "landlord": "lessor owner property rental",
        "tenant": "lessee renter occupant",
        "eviction": "vacate possession removal",
        "rti": "right to information public authority transparency government records",
        "pocso": "child sexual offence minor protection special court",
        "domestic violence": "PWDVA protection order shared household monetary relief",
        "maintenance": "alimony monthly allowance wife children parents 125 crpc",
        "mortgage": "home loan property loan security bank TPA",
        "retrenchment": "layoff termination notice compensation IDA labour",
        "evidence": "admissibility witness burden proof BSA electronic record",
        "stalking": "following harassment cyberstalking 354D BNS 78",
        "sexual harassment": "workplace POSH unwelcome advances 354A BNS 75",
        "forgery": "fake document false record 463 467 468 BNS 334",
        "conspiracy": "criminal conspiracy 120B joint plan abetment",
        "dacoity": "gang robbery five persons 395 BNS 310",
    }
    
    query_lower = query.lower()
    expanded_terms = []
    
    for term, expansion in expansions.items():
        if term in query_lower:
            expanded_terms.append(expansion)
    
    if expanded_terms:
        return query + " " + " ".join(expanded_terms)
    return query


def search_with_expansion(
    document_id: int,
    query: str,
    top_k: int = 4,
) -> list[dict[str, Any]]:
    """
    Perform hybrid search with query expansion for legal terms.
    """
    expanded_query = expand_legal_query(query)
    return hybrid_search(document_id, expanded_query, top_k=top_k)
