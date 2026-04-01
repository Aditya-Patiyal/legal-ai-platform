from __future__ import annotations

from .embeddings import query_document_chunks

CLAUSE_QUERIES = {
    "termination": "termination clause contract termination notice expiry",
    "penalty": "penalty late fee damages fine default breach",
    "payment": "payment fees amount invoice due date",
    "confidentiality": "confidentiality non-disclosure secrecy private information",
    "liability": "liability indemnity responsible damages loss",
    "renewal": "renewal extension automatic renew term",
}

RISK_KEYWORDS = {
    "high": ["immediately terminate", "unlimited liability", "penalty", "forfeit", "sole discretion"],
    "medium": ["fee", "damages", "indemnify", "non-refundable", "notice period"],
}


def classify_risk(text: str) -> str:
    lowered = text.lower()
    if any(keyword in lowered for keyword in RISK_KEYWORDS["high"]):
        return "High"
    if any(keyword in lowered for keyword in RISK_KEYWORDS["medium"]):
        return "Medium"
    return "Low"


def explain_clause(clause_type: str, text: str) -> str:
    return (
        f"This appears to be the {clause_type} clause. In plain English, it describes "
        f"how the agreement handles {clause_type.replace('_', ' ')} and what obligations or consequences may apply."
    )


def extract_clause(document_id: int, clause_type: str) -> dict[str, object]:
    query = CLAUSE_QUERIES.get(clause_type.lower(), clause_type)
    matches = query_document_chunks(document_id=document_id, query=query, limit=1)
    if not matches:
        return {
            "clause_type": clause_type,
            "snippet": "",
            "explanation": "No matching clause was found.",
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
