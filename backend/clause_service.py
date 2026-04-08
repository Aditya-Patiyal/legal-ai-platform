from __future__ import annotations

import os

from .embeddings import query_document_chunks

CLAUSE_QUERIES = {
    "termination": "termination clause contract termination notice expiry end agreement",
    "penalty": "penalty late fee damages fine default breach liquidated",
    "payment": "payment fees amount invoice due date price consideration",
    "confidentiality": "confidentiality non-disclosure secrecy private information NDA",
    "liability": "liability indemnity responsible damages loss limitation cap",
    "renewal": "renewal extension automatic renew term duration period",
    "jurisdiction": "jurisdiction governing law dispute resolution court arbitration",
    "ip": "intellectual property ownership rights assignment copyright trademark",
    "non_compete": "non-compete non-solicitation restrictive covenant",
}

RISK_KEYWORDS = {
    "high": [
        "immediately terminate", "unlimited liability", "penalty", "forfeit",
        "sole discretion", "without cause", "waive all rights",
        "indemnify and hold harmless", "irrevocably assign",
    ],
    "medium": [
        "fee", "damages", "indemnify", "non-refundable", "notice period",
        "automatic renewal", "may amend", "right to modify", "non-compete",
    ],
}

_EXPLAIN_PROMPT = """You are a legal plain-language expert. Explain the following {clause_type} clause from a legal document to a non-lawyer.

CLAUSE TEXT:
"{snippet}"

Explain in this format:
1. **What it means**: (1-2 plain English sentences)
2. **Your obligations**: (what you must do or are restricted from doing)
3. **Key risk**: (the main concern, if any)

Keep it under 150 words. No legal jargon."""


def _explain_with_groq(clause_type: str, snippet: str) -> str | None:
    """Use Groq to explain a clause in plain English. Returns None if unavailable."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your_groq_api_key_here":
        return None
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        prompt = _EXPLAIN_PROMPT.format(
            clause_type=clause_type.replace("_", " "),
            snippet=snippet[:1500],
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=350,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None


def classify_risk(text: str) -> str:
    lowered = text.lower()
    if any(kw in lowered for kw in RISK_KEYWORDS["high"]):
        return "High"
    if any(kw in lowered for kw in RISK_KEYWORDS["medium"]):
        return "Medium"
    return "Low"


def explain_clause(clause_type: str, text: str) -> str:
    ai_explanation = _explain_with_groq(clause_type, text)
    if ai_explanation:
        return ai_explanation
    return (
        f"This is the {clause_type.replace('_', ' ')} clause. It describes how the agreement handles "
        f"{clause_type.replace('_', ' ')} and what obligations or consequences may apply. "
        f"Consult a lawyer to understand your specific rights and obligations under this clause."
    )


def extract_clause(document_id: int, clause_type: str) -> dict[str, object]:
    query = CLAUSE_QUERIES.get(clause_type.lower(), clause_type)
    matches = query_document_chunks(document_id=document_id, query=query, limit=2)
    if not matches:
        return {
            "clause_type": clause_type,
            "snippet": "",
            "explanation": "No matching clause was found in the document.",
            "risk_level": "Low",
            "source": None,
        }
    match = matches[0]
    snippet = str(match["text"])
    return {
        "clause_type": clause_type,
        "snippet": snippet,
        "explanation": explain_clause(clause_type, snippet),
        "risk_level": classify_risk(snippet),
        "source": match["metadata"],
    }
