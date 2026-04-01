from __future__ import annotations

from .database import fetch_one

RISK_PATTERNS = {
    "One-sided termination rights": ["sole discretion", "terminate at any time", "without cause"],
    "Hidden or heavy penalties": ["penalty", "late fee", "liquidated damages", "forfeit"],
    "Broad liability exposure": ["unlimited liability", "indemnify", "hold harmless"],
    "Weak notice protections": ["immediate effect", "without notice"],
    "Non-refundable obligations": ["non-refundable", "no refund"],
}


def analyze_document_text(text: str) -> dict[str, object]:
    lowered = text.lower()
    findings: list[str] = []
    score = 1
    for label, patterns in RISK_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            findings.append(label)
            score += 2
    score = min(score, 10)
    if not findings:
        findings.append("No major high-risk patterns were detected by the MVP heuristic engine.")
    return {"risk_score": score, "findings": findings}


def analyze_document(document_id: int) -> dict[str, object]:
    row = fetch_one("SELECT extracted_text FROM documents WHERE id = ?", (document_id,))
    text = row["extracted_text"] if row else ""
    result = analyze_document_text(text)
    result["summary"] = (
        "This risk score is a heuristic estimate based on clause patterns in the uploaded document. "
        "Please consult a licensed lawyer for legal advice."
    )
    return result
