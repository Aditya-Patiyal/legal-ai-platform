from __future__ import annotations

import os
import re
from typing import Any

from .embeddings import OLLAMA_HOST, query_document_chunks
from .hybrid_retrieval import search_with_expansion, hybrid_search
from .indian_law_kb import lookup_section, search_law_by_topic, semantic_search_laws

GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"
OLLAMA_CHAT_MODEL = "mistral"

# Lazy initialization for LLM clients
_ollama_client = None
_groq_client: object = None
_groq_init_attempted = False


def get_ollama_client():
    """Get Ollama client, initializing lazily."""
    global _ollama_client
    if _ollama_client is None:
        from ollama import Client
        _ollama_client = Client(host=OLLAMA_HOST)
    return _ollama_client


def get_groq_client():
    """Get Groq client when GROQ_API_KEY is set, else return None."""
    global _groq_client, _groq_init_attempted
    if _groq_init_attempted:
        return _groq_client
    _groq_init_attempted = True
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your_groq_api_key_here":
        return None
    try:
        from groq import Groq
        _groq_client = Groq(api_key=api_key)
    except Exception:
        _groq_client = None
    return _groq_client


def generate_llm_response(prompt: str) -> str:
    """Generate a response using Groq if available, otherwise fall back to Ollama."""
    groq = get_groq_client()
    if groq:
        response = groq.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()
    response = get_ollama_client().generate(model=OLLAMA_CHAT_MODEL, prompt=prompt)
    return response.get("response", "I could not generate a response.").strip()

SYSTEM_PROMPT = """You are a legal assistant helping non-lawyers understand Indian law and legal documents.

RESPONSE FORMAT — always structure your answer like this:
**Direct Answer:** [One clear sentence answering the question]
**Explanation:** [Plain English explanation, 2-4 sentences, no jargon]
**Legal Basis:** [Cite the exact section, act, or document excerpt you are drawing from]
**Important Note:** [Any limitation, uncertainty, or caveat; always end with: "This is AI assistance, not legal advice from a licensed lawyer."]

RULES:
- Every legal claim must be backed by the provided context. If unsupported, say "I am uncertain about this — please verify with a lawyer."
- Do NOT invent section numbers, punishments, names, or parties not in the provided context.
- If both old law (IPC/CrPC) and new law (BNS/BNSS/BSA) apply, mention both."""

DOCUMENT_ONLY_PROMPT = """You are a legal document assistant helping non-lawyers understand their uploaded documents.

RESPONSE FORMAT — always structure your answer like this:
**Direct Answer:** [One clear sentence answering the question]
**Explanation:** [Plain English explanation of what the document says, 2-4 sentences]
**Source:** [Quote the exact relevant text from the document: \"...\"]
**Important Note:** [Any limitation or caveat; always end with: "This is AI assistance, not legal advice from a licensed lawyer."]

RULES:
- ONLY use information from the document excerpts below. Do NOT add outside knowledge.
- If the document doesn't contain the answer, say: "I couldn't find this information in the uploaded document."
- Do NOT invent names, parties, dates, or amounts not in the document."""

LAW_KNOWLEDGE_PROMPT = """You are an Indian law expert assistant helping non-lawyers understand legal concepts and statutes.

RESPONSE FORMAT — always structure your answer like this:
**Direct Answer:** [One clear sentence answering the question]
**Explanation:** [Plain English explanation, 2-4 sentences]
**Legal Basis:** [Cite: "Section X of [Act Name]" — include both old and new law if applicable (IPC↔BNS, CrPC↔BNSS)]
**Punishment/Consequence:** [If applicable, state the exact penalty from the provided context]
**Important Note:** [Always end with: "This is AI assistance, not legal advice from a licensed lawyer."]

RULES:
- Cite only sections that appear in the provided law references below.
- If a section has been replaced by BNS/BNSS/BSA, mention both the old and new section numbers.
- If the context is insufficient, say: "I don't have enough information about this specific provision — please consult a lawyer."
- Do NOT invent section numbers, punishments, or provisions not in the provided context."""


LEGAL_ISSUE_CATEGORIES: dict[str, list[str]] = {
    "fraud_cheating": ["fraud", "cheat", "deceive", "misrepresentation", "420", "false promise", "scam"],
    "breach_contract": ["breach", "default", "not paid", "didn't deliver", "violation", "broke the agreement"],
    "employment": ["salary", "fired", "terminated", "employer", "employee", "retrenchment", "labour", "workman", "notice period"],
    "tenancy_property": ["rent", "tenant", "landlord", "eviction", "lease", "property", "possession"],
    "consumer": ["product", "defective", "consumer", "refund", "service deficiency", "online purchase"],
    "criminal": ["murder", "theft", "assault", "rape", "robbery", "arrested", "fir", "bail", "accused"],
    "family_matrimonial": ["divorce", "maintenance", "alimony", "custody", "marriage", "dowry", "cruelty"],
    "cyber_it": ["hacking", "cyber", "online fraud", "password", "data", "social media", "defamatory post"],
    "fundamental_rights": ["fundamental right", "discrimination", "article 21", "liberty", "free speech"],
    "child_protection": ["child", "minor", "pocso", "juvenile"],
}


def spot_legal_issues(question: str) -> list[str]:
    """Identify which legal issue categories the question falls into."""
    question_lower = question.lower()
    detected = []
    for category, patterns in LEGAL_ISSUE_CATEGORIES.items():
        if any(p in question_lower for p in patterns):
            detected.append(category)
    return detected


def detect_query_type(question: str) -> str:
    """
    Detect whether the query is about:
    - 'law_only': General Indian law question (IPC, BNS, CrPC, etc.)
    - 'document_only': Question about uploaded document
    - 'document_plus_law': Question combining both
    """
    question_lower = question.lower()
    
    law_indicators = [
        r"\bipc\b", r"\bbns\b", r"\bcrpc\b", r"\bbnss\b", r"\bbsa\b",
        r"\bsection\s*\d+", r"\bsec\.?\s*\d+",
        r"\bindian\s*penal\s*code\b", r"\bcriminal\s*procedure\b",
        r"\bwhat\s*is\s*(?:the\s*)?(?:punishment|penalty)\b",
        r"\bwhich\s*(?:section|law|act)\b",
        r"\bunder\s*which\s*(?:section|law)\b",
        r"\bconstitution\b", r"\bfundamental\s*right", r"\barticle\s*\d+",
        r"\bconsumer\s*protection\b", r"\bcheque\s*bounce\b",
        r"\b138\s*ni\s*act\b", r"\bnegotiable\s*instrument",
        r"\bit\s*act\b", r"\bcyber\s*crime\b",
        r"\brti\b", r"\bright\s*to\s*information\b",
        r"\bpocso\b", r"\bchild\s*(?:sexual|abuse|protection)\b",
        r"\bdomestic\s*violence\b", r"\bpwdva\b",
        r"\btransfer\s*of\s*property\b", r"\btpa\b",
        r"\bindustrial\s*disputes?\b", r"\bretrenchment\b",
        r"\bmaintenance\s*(?:wife|children|parents)\b",
        r"\bstalking\b", r"\bvoyeurism\b", r"\bforgery\b",
        r"\bcriminal\s*conspiracy\b", r"\bdacoity\b",
        r"\bevidence\s*act\b", r"\bsakshya\b",
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
    
    try:
        semantic_results = semantic_search_laws(question, limit=3)
    except Exception:
        semantic_results = []
    
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
    issue_tags = spot_legal_issues(question)
    issue_hint = (
        f"\n[Detected legal issue categories: {', '.join(issue_tags)}]\n"
        if issue_tags else ""
    )

    if query_type == "law_only":
        law_context = format_law_context(section_lookups, semantic_results)
        if not law_context.strip():
            return (
                f"{LAW_KNOWLEDGE_PROMPT}{issue_hint}\n\nNo specific law references were found for your query.\n\n"
                f"Question: {question}\n\nAnswer: I couldn't find specific Indian law sections matching your query. "
                f"Please try asking about a specific section number (e.g., 'What is IPC 420?') or describe the legal issue you want to understand."
            )
        return (
            f"{LAW_KNOWLEDGE_PROMPT}{issue_hint}\n\nHere are the relevant Indian law references:\n\n"
            f"{law_context}\n\nBased on the above legal references, answer this question: {question}\n\nAnswer:"
        )

    elif query_type == "document_only":
        if not doc_chunks:
            return (
                f"{DOCUMENT_ONLY_PROMPT}{issue_hint}\n\nNo relevant context was found in the document.\n\n"
                f"Question: {question}\nAnswer: I couldn't find relevant information in the uploaded document to answer your question."
            )
        doc_context = format_document_context(doc_chunks)
        return (
            f"{DOCUMENT_ONLY_PROMPT}{issue_hint}\n\nHere are the relevant excerpts from the uploaded document:\n\n"
            f"{doc_context}\n\nBased ONLY on the above excerpts, answer this question: {question}\n\nAnswer:"
        )

    else:
        doc_context = format_document_context(doc_chunks) if doc_chunks else "No relevant document excerpts found."
        law_context = format_law_context(section_lookups, semantic_results) if (section_lookups or semantic_results) else "No specific law references found."

        return f"""{SYSTEM_PROMPT}{issue_hint}

=== UPLOADED DOCUMENT EXCERPTS ===
{doc_context}

=== INDIAN LAW REFERENCES ===
{law_context}

Based on BOTH the document excerpts AND the Indian law references above, answer this question: {question}

Follow the response format exactly: Direct Answer → Explanation → Legal Basis → Important Note.

Answer:"""


def build_law_fallback_answer(
    question: str,
    section_lookups: list[dict[str, Any]],
    semantic_results: list[dict[str, Any]],
) -> str:
    parts: list[str] = []

    if section_lookups:
        primary = section_lookups[0]
        parts.append(
            f"Based on the legal references available, the closest exact match is Section {primary.get('section')} of {primary.get('act')} - {primary.get('title')}."
        )
        if primary.get("description"):
            parts.append(primary["description"])
        if primary.get("punishment"):
            parts.append(f"Punishment/Penalty: {primary['punishment']}.")
        if primary.get("new_law"):
            new_law = primary["new_law"]
            parts.append(
                f"New law equivalent: Section {new_law.get('section')} of {new_law.get('act')}."
            )
        if primary.get("old_law"):
            old_law = primary["old_law"]
            parts.append(
                f"Old law equivalent: Section {old_law.get('section')} of {old_law.get('act')}."
            )
    elif semantic_results:
        primary = semantic_results[0]
        title = primary.get("title")
        act = primary.get("act")
        section = primary.get("section")
        label = f"Section {section} of {act}" if act and section else title or "the closest available legal reference"
        parts.append(f"Based on the legal references available, the closest match is {label}.")
        if title and label != title:
            parts.append(f"Title: {title}.")
        if primary.get("description"):
            parts.append(primary["description"])
        elif primary.get("text"):
            parts.append(primary["text"])
    else:
        parts.append(
            f"I couldn't find a specific Indian law section matching your question: \"{question}\"."
        )
        parts.append(
            "Try asking with a section number, Act name, or a more specific legal issue so I can match it against the built-in legal knowledge base."
        )

    related_references = semantic_results[:3]
    if related_references:
        related_lines = []
        for ref in related_references:
            act = ref.get("act") or "Unknown Act"
            section = ref.get("section") or "Unknown Section"
            title = ref.get("title")
            description = ref.get("description") or ref.get("text")
            line = f"- Section {section} of {act}"
            if title:
                line += f": {title}"
            if description:
                line += f" — {description}"
            related_lines.append(line)
        parts.append("Related legal references:\n" + "\n".join(related_lines))

    parts.append(
        "This answer is based on the built-in legal knowledge base available in the deployed app and is not legal advice from a licensed lawyer."
    )
    return "\n\n".join(parts)


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
    
    try:
        answer = generate_llm_response(prompt)
    except Exception:
        if query_type in ["law_only", "document_plus_law"] and (section_lookups or semantic_law_results):
            answer = build_law_fallback_answer(question, section_lookups, semantic_law_results)
        elif doc_sources:
            answer = "I couldn't generate a full AI response right now, but I did find relevant excerpts in your uploaded document. Please try again in a moment or ask a more specific question."
        else:
            answer = "I couldn't generate a response right now. Please try again in a moment."
    
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
    
    try:
        answer = generate_llm_response(prompt)
    except Exception:
        answer = build_law_fallback_answer(question, section_lookups, semantic_results)
    
    return {
        "answer": answer,
        "law_references": {
            "section_lookups": section_lookups,
            "semantic_results": semantic_results,
        },
    }
