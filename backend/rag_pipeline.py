from __future__ import annotations

import os
import re
from typing import Any

from .embeddings import OLLAMA_HOST, query_document_chunks
from .hybrid_retrieval import search_with_expansion, hybrid_search
from .indian_law_kb import lookup_section, search_law_by_topic, semantic_search_laws

CHAT_MODEL = "mistral"

# Lazy initialization for Ollama client
_ollama_client = None


def get_ollama_client():
    """Get Ollama client, initializing lazily."""
    global _ollama_client
    if _ollama_client is None:
        from ollama import Client
        _ollama_client = Client(host=OLLAMA_HOST)
    return _ollama_client

SYSTEM_PROMPT = """You are a legal document assistant helping non-lawyers understand their documents and Indian law.

CRITICAL INSTRUCTIONS:
1. Answer based on the provided context (document excerpts and/or Indian law references).
2. If the context doesn't contain enough information, say so clearly.
3. Quote specific text from the context when relevant.
4. Explain legal terms in plain English.
5. When citing law sections, use the format: "Section X of [Act Name]".
6. If both old law (IPC/CrPC) and new law (BNS/BNSS) apply, mention both.
7. Always remind users this is AI assistance, not legal advice from a licensed lawyer.

Do NOT invent names, parties, sections, or details that are not explicitly in the provided context."""

DOCUMENT_ONLY_PROMPT = """You are a legal document assistant helping non-lawyers understand their documents.

CRITICAL INSTRUCTIONS:
1. ONLY answer based on the document excerpts provided below. Do NOT make up information.
2. If the context doesn't contain enough information to answer, say "I couldn't find this information in the uploaded document."
3. Quote specific text from the context when relevant.
4. Explain legal terms in plain English.
5. Always remind users this is AI assistance, not legal advice from a licensed lawyer.

Do NOT invent names, parties, or details that are not explicitly in the provided context."""

LAW_KNOWLEDGE_PROMPT = """You are an Indian law expert assistant helping non-lawyers understand legal concepts and statutes.

CRITICAL INSTRUCTIONS:
1. Answer based on the Indian law references provided below.
2. Explain legal concepts in plain, easy-to-understand English.
3. When citing sections, always mention both the section number and the Act name.
4. If the new criminal laws (BNS/BNSS/BSA) have replaced old laws (IPC/CrPC/Evidence Act), mention both.
5. Provide the punishment/penalty if applicable and available.
6. Always remind users this is AI assistance, not legal advice from a licensed lawyer.

Do NOT invent section numbers, punishments, or legal provisions not in the provided context."""


def detect_query_type(question: str) -> str:
    """
    Detect whether the query is about:
    - 'law_only': General Indian law question (IPC, BNS, CrPC, etc.)
    - 'document_only': Question about uploaded document
    - 'document_plus_law': Question combining both
    """
    question_lower = question.lower()
    
    law_indicators = [
        r"\bipc\b", r"\bbns\b", r"\bcrpc\b", r"\bbnss\b",
        r"\bsection\s*\d+", r"\bsec\.?\s*\d+",
        r"\bindian\s*penal\s*code\b", r"\bcriminal\s*procedure\b",
        r"\bwhat\s*is\s*(?:the\s*)?(?:punishment|penalty)\b",
        r"\bwhich\s*(?:section|law|act)\b",
        r"\bunder\s*which\s*(?:section|law)\b",
        r"\bconstitution\b", r"\bfundamental\s*right",
        r"\bconsumer\s*protection\b", r"\bcheque\s*bounce\b",
        r"\b138\s*ni\s*act\b", r"\bnegotiable\s*instrument",
        r"\bit\s*act\b", r"\bcyber\s*crime\b",
    ]
    
    doc_indicators = [
        r"\bthis\s*(?:document|contract|agreement)\b",
        r"\bmy\s*(?:document|contract|agreement)\b",
        r"\buploaded\b", r"\bin\s*the\s*(?:document|contract|file)\b",
        r"\baccording\s*to\s*(?:this|the)\s*(?:document|contract)\b",
        r"\bwhat\s*does\s*(?:this|the)\s*(?:document|contract)\s*say\b",
        r"\bclause\s*(?:in|of)\s*(?:this|the|my)\b",
    ]
    
    has_law = any(re.search(p, question_lower) for p in law_indicators)
    has_doc = any(re.search(p, question_lower) for p in doc_indicators)
    
    if has_law and has_doc:
        return "document_plus_law"
    elif has_law:
        return "law_only"
    else:
        return "document_only"


def extract_section_references(question: str) -> list[str]:
    """Extract potential section references from the question."""
    patterns = [
        r"(?:section|sec\.?)\s*(\d+[a-zA-Z]?)\s*(?:of\s*)?(?:ipc|bns|crpc|bnss)?",
        r"(?:ipc|bns|crpc|bnss)\s*(?:section|sec\.?)?\s*(\d+[a-zA-Z]?)",
        r"\b(\d+[a-zA-Z]?)\s*(?:ipc|bns|crpc|bnss)\b",
    ]
    
    refs = []
    question_lower = question.lower()
    for pattern in patterns:
        matches = re.findall(pattern, question_lower, re.IGNORECASE)
        refs.extend(matches)
    
    return list(set(refs))


def get_law_context(question: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Get relevant Indian law context for the question.
    Returns (section_lookups, semantic_results).
    """
    section_lookups = []
    
    section_result = lookup_section(question)
    if section_result:
        section_lookups.append(section_result)
    
    section_refs = extract_section_references(question)
    for ref in section_refs:
        for prefix in ["IPC", "BNS", "CrPC", "BNSS"]:
            result = lookup_section(f"{prefix} {ref}")
            if result and result not in section_lookups:
                section_lookups.append(result)
                break
    
    topic_results = search_law_by_topic(question, limit=3)
    
    semantic_results = semantic_search_laws(question, limit=3)
    
    combined_semantic = []
    seen_sections = {(s.get("act_short", ""), s.get("section", "")) for s in section_lookups}
    
    for result in topic_results:
        key = (result.get("act", ""), result.get("section", ""))
        if key not in seen_sections:
            combined_semantic.append({
                "source": "topic_search",
                "act": result.get("act"),
                "section": result.get("section"),
                "title": result.get("title"),
                "description": result.get("description"),
                "score": result.get("score", 0),
            })
            seen_sections.add(key)
    
    for result in semantic_results:
        meta = result.get("metadata", {})
        key = (meta.get("act_short", ""), meta.get("section", ""))
        if key not in seen_sections:
            combined_semantic.append({
                "source": "semantic_search",
                "act": meta.get("act"),
                "section": meta.get("section"),
                "title": meta.get("title"),
                "text": result.get("text"),
                "relevance_score": result.get("relevance_score", 0),
            })
            seen_sections.add(key)
    
    return section_lookups, combined_semantic[:5]


def format_law_context(section_lookups: list[dict[str, Any]], semantic_results: list[dict[str, Any]]) -> str:
    """Format law context for the prompt."""
    parts = []
    
    if section_lookups:
        parts.append("=== EXACT SECTION MATCHES ===")
        for i, section in enumerate(section_lookups, 1):
            text = f"\n--- Section {i} ---\n"
            text += f"Section {section.get('section')} of {section.get('act')}\n"
            text += f"Title: {section.get('title')}\n"
            text += f"Description: {section.get('description')}\n"
            if section.get('punishment'):
                text += f"Punishment: {section.get('punishment')}\n"
            if section.get('new_law'):
                new = section['new_law']
                text += f"New Law Equivalent: Section {new['section']} of {new['act']}\n"
            if section.get('old_law'):
                old = section['old_law']
                text += f"Old Law Equivalent: Section {old['section']} of {old['act']}\n"
            parts.append(text)
    
    if semantic_results:
        parts.append("\n=== RELATED LAW REFERENCES ===")
        for i, result in enumerate(semantic_results, 1):
            text = f"\n--- Reference {i} ---\n"
            text += f"Section {result.get('section')} of {result.get('act')}\n"
            if result.get('title'):
                text += f"Title: {result.get('title')}\n"
            if result.get('description'):
                text += f"Description: {result.get('description')}\n"
            if result.get('text'):
                text += f"Text: {result.get('text')}\n"
            parts.append(text)
    
    return "\n".join(parts)


def format_document_context(chunks: list[dict[str, Any]]) -> str:
    """Format document chunks for the prompt with rich metadata."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        text = f"--- Document Excerpt {i}"
        metadata = chunk.get("metadata", {})
        
        if metadata.get("page_number"):
            text += f" (Page {metadata['page_number']})"
        if metadata.get("section_heading"):
            text += f" [{metadata['section_heading']}]"
        
        text += f" ---\n{chunk['text']}"
        parts.append(text)
    
    return "\n\n".join(parts)


def build_prompt(question: str, context_chunks: list[dict[str, object]]) -> str:
    if not context_chunks:
        return f"{DOCUMENT_ONLY_PROMPT}\n\nNo relevant context was found in the document.\n\nQuestion: {question}\nAnswer: I couldn't find relevant information in the uploaded document to answer your question. Please try rephrasing or ask about a different aspect of the document."
    
    context_text = format_document_context(context_chunks)
    return f"{DOCUMENT_ONLY_PROMPT}\n\nHere are the relevant excerpts from the uploaded document:\n\n{context_text}\n\nBased ONLY on the above excerpts, answer this question: {question}\n\nAnswer:"


def build_combined_prompt(
    question: str,
    doc_chunks: list[dict[str, Any]],
    section_lookups: list[dict[str, Any]],
    semantic_results: list[dict[str, Any]],
    query_type: str,
) -> str:
    """Build a prompt combining document and law knowledge."""
    
    if query_type == "law_only":
        law_context = format_law_context(section_lookups, semantic_results)
        if not law_context.strip():
            return f"{LAW_KNOWLEDGE_PROMPT}\n\nNo specific law references were found for your query.\n\nQuestion: {question}\n\nAnswer: I couldn't find specific Indian law sections matching your query. Please try asking about a specific section number (e.g., 'What is IPC 420?') or describe the legal issue you want to understand."
        
        return f"{LAW_KNOWLEDGE_PROMPT}\n\nHere are the relevant Indian law references:\n\n{law_context}\n\nBased on the above legal references, answer this question: {question}\n\nAnswer:"
    
    elif query_type == "document_only":
        if not doc_chunks:
            return f"{DOCUMENT_ONLY_PROMPT}\n\nNo relevant context was found in the document.\n\nQuestion: {question}\nAnswer: I couldn't find relevant information in the uploaded document to answer your question."
        
        doc_context = format_document_context(doc_chunks)
        return f"{DOCUMENT_ONLY_PROMPT}\n\nHere are the relevant excerpts from the uploaded document:\n\n{doc_context}\n\nBased ONLY on the above excerpts, answer this question: {question}\n\nAnswer:"
    
    else:
        doc_context = format_document_context(doc_chunks) if doc_chunks else "No relevant document excerpts found."
        law_context = format_law_context(section_lookups, semantic_results) if (section_lookups or semantic_results) else "No specific law references found."
        
        return f"""{SYSTEM_PROMPT}

=== UPLOADED DOCUMENT EXCERPTS ===
{doc_context}

=== INDIAN LAW REFERENCES ===
{law_context}

Based on BOTH the document excerpts AND the Indian law references above, answer this question: {question}

Provide a comprehensive answer that:
1. Addresses what the document says (if relevant)
2. Explains the applicable Indian law provisions
3. Connects the document content to relevant legal provisions (if applicable)

Answer:"""


def answer_question(document_id: int, question: str) -> dict[str, object]:
    """Answer a question using hybrid retrieval and Indian law knowledge."""
    
    query_type = detect_query_type(question)
    
    doc_sources: list[dict[str, Any]] = []
    section_lookups: list[dict[str, Any]] = []
    semantic_law_results: list[dict[str, Any]] = []
    
    if query_type in ["document_only", "document_plus_law"]:
        try:
            doc_sources = search_with_expansion(document_id, question, top_k=4)
        except Exception:
            doc_sources = query_document_chunks(document_id=document_id, query=question)
    
    if query_type in ["law_only", "document_plus_law"]:
        section_lookups, semantic_law_results = get_law_context(question)
    
    prompt = build_combined_prompt(
        question=question,
        doc_chunks=doc_sources,
        section_lookups=section_lookups,
        semantic_results=semantic_law_results,
        query_type=query_type,
    )
    
    response = get_ollama_client().generate(model=CHAT_MODEL, prompt=prompt)
    answer = response.get("response", "I could not generate a response.").strip()
    
    return {
        "answer": answer,
        "sources": doc_sources,
        "law_references": {
            "section_lookups": section_lookups,
            "semantic_results": semantic_law_results,
        },
        "query_type": query_type,
    }


def answer_law_question(question: str) -> dict[str, Any]:
    """
    Answer a pure Indian law question without document context.
    Useful for general legal queries.
    """
    section_lookups, semantic_results = get_law_context(question)
    
    prompt = build_combined_prompt(
        question=question,
        doc_chunks=[],
        section_lookups=section_lookups,
        semantic_results=semantic_results,
        query_type="law_only",
    )
    
    response = get_ollama_client().generate(model=CHAT_MODEL, prompt=prompt)
    answer = response.get("response", "I could not generate a response.").strip()
    
    return {
        "answer": answer,
        "law_references": {
            "section_lookups": section_lookups,
            "semantic_results": semantic_results,
        },
    }
