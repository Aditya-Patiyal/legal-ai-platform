from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
load_dotenv()

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

from backend.auth import authenticate_user, create_session, create_user, delete_session, get_user_by_session
from backend.clause_service import extract_clause
from backend.database import (
    GENERATED_DIR,
    UPLOADS_DIR,
    dumps_json,
    execute,
    fetch_all,
    fetch_one,
    init_db,
    row_to_dict,
    rows_to_dicts,
)
from backend.document_parser import chunk_text, chunk_text_structured, extract_text
from backend.embeddings import add_document_chunks, add_structured_chunks
from backend.indian_law_kb import lookup_section, search_law_by_topic, semantic_search_laws, index_law_knowledge
from backend.rag_pipeline import answer_law_question
from backend.generator import build_pdf, render_template
from backend.ai_generator import smart_generate, classify_intent, get_groq_api_key, get_groq_client
from backend.rag_pipeline import answer_question
from backend.risk_engine import analyze_document

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Legal AI Platform", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.endswith(('.html', '.css', '.js')):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

app.add_middleware(NoCacheMiddleware)
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChatRequest(BaseModel):
    document_id: int
    question: str


class ClauseRequest(BaseModel):
    document_id: int
    clause_type: str


class RiskRequest(BaseModel):
    document_id: int


class GenerateRequest(BaseModel):
    template_type: str
    name: str
    address: str
    issue_description: str
    date: str
    force_generate: bool = False


def sanitize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in user.items() if key != "password_hash"}


def get_current_user(
    session_token: str | None = Cookie(default=None),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token")
) -> dict[str, Any]:
    # Try header first (for cross-origin requests), then cookie
    token = x_session_token or session_token
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return user


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.get("/health")
def health_check() -> dict[str, str]:
    """Simple health check endpoint that doesn't require any dependencies."""
    return {"status": "ok", "message": "Server is running"}


@app.get("/api/debug/groq-status")
def groq_status() -> dict[str, Any]:
    groq_api_key = get_groq_api_key()
    _, groq_error = get_groq_client()
    return {
        "has_groq_api_key": bool(groq_api_key),
        "groq_api_key_length": len(groq_api_key),
        "groq_client_ready": groq_error is None,
        "groq_error": groq_error,
    }


@app.get("/")
def root() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/dashboard")
def dashboard_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "dashboard.html")


@app.get("/chat")
def chat_page() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "chat.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@app.get("/generator")
def generator_page() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "generator.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@app.post("/api/auth/signup")
def signup(payload: SignupRequest) -> dict[str, Any]:
    existing = fetch_one("SELECT id FROM users WHERE email = ?", (payload.email.lower(),))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = create_user(payload.name, payload.email, payload.password)
    token = create_session(user["id"])
    sanitized = sanitize_user(user)
    return {"user": sanitized, "session_token": token}


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    user = authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_session(user["id"])
    return {"user": sanitize_user(user), "session_token": token}


@app.post("/api/auth/logout")
def logout(session_token: str | None = Cookie(default=None)) -> dict[str, str]:
    if session_token:
        delete_session(session_token)
    return {"message": "Logged out"}


@app.get("/api/me")
def me(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": sanitize_user(current_user)}


@app.post("/api/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")
    saved_name = f"{uuid4().hex}{suffix}"
    saved_path = UPLOADS_DIR / saved_name
    with saved_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    document_id = execute(
        "INSERT INTO documents (user_id, filename, saved_path, file_type, upload_status) VALUES (?, ?, ?, ?, ?)",
        (current_user["id"], file.filename or saved_name, str(saved_path), suffix.replace(".", ""), "processing"),
    )
    extracted_text = extract_text(str(saved_path))
    
    structured_chunks = chunk_text_structured(str(saved_path))
    if structured_chunks:
        add_structured_chunks(current_user["id"], document_id, file.filename or saved_name, structured_chunks)
        chunk_count = len(structured_chunks)
    else:
        chunks = chunk_text(extracted_text)
        add_document_chunks(current_user["id"], document_id, file.filename or saved_name, chunks)
        chunk_count = len(chunks)
    
    execute(
        "UPDATE documents SET extracted_text = ?, chunk_count = ?, upload_status = ? WHERE id = ?",
        (extracted_text, chunk_count, "ready", document_id),
    )
    document = row_to_dict(fetch_one("SELECT * FROM documents WHERE id = ?", (document_id,)))
    return {"document": document}


@app.get("/api/documents")
def list_documents(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    rows = fetch_all(
        "SELECT * FROM documents WHERE user_id = ? ORDER BY created_at DESC",
        (current_user["id"],),
    )
    return {"documents": rows_to_dicts(rows)}


@app.get("/api/documents/{document_id}")
def get_document(document_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM documents WHERE id = ? AND user_id = ?",
        (document_id, current_user["id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document": row_to_dict(row)}


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    row = fetch_one(
        "SELECT * FROM documents WHERE id = ? AND user_id = ?",
        (document_id, current_user["id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    
    saved_path = Path(row["saved_path"])
    if saved_path.exists():
        saved_path.unlink()
    
    execute("DELETE FROM chat_history WHERE document_id = ?", (document_id,))
    execute("DELETE FROM documents WHERE id = ?", (document_id,))
    
    return {"message": "Document deleted successfully"}


@app.delete("/api/chat-history/{document_id}")
def delete_chat_history(document_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    document = fetch_one(
        "SELECT id FROM documents WHERE id = ? AND user_id = ?",
        (document_id, current_user["id"]),
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    execute("DELETE FROM chat_history WHERE document_id = ? AND user_id = ?", (document_id, current_user["id"]))
    
    return {"message": "Chat history cleared"}


@app.post("/api/chat")
def chat(payload: ChatRequest, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    document = fetch_one(
        "SELECT * FROM documents WHERE id = ? AND user_id = ?",
        (payload.document_id, current_user["id"]),
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    result = answer_question(document_id=payload.document_id, question=payload.question)
    execute(
        "INSERT INTO chat_history (user_id, document_id, question, answer, sources_json) VALUES (?, ?, ?, ?, ?)",
        (current_user["id"], payload.document_id, payload.question, result["answer"], dumps_json(result["sources"])),
    )
    return result


@app.post("/api/clauses/extract")
def clauses(payload: ClauseRequest, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    document = fetch_one(
        "SELECT id FROM documents WHERE id = ? AND user_id = ?",
        (payload.document_id, current_user["id"]),
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return extract_clause(payload.document_id, payload.clause_type)


@app.post("/api/risk/analyze")
def risk(payload: RiskRequest, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    document = fetch_one(
        "SELECT id FROM documents WHERE id = ? AND user_id = ?",
        (payload.document_id, current_user["id"]),
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return analyze_document(payload.document_id)


@app.post("/api/generate-document")
def generate_document(payload: GenerateRequest, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    result = smart_generate(
        template_type=payload.template_type,
        name=payload.name,
        address=payload.address,
        date=payload.date,
        issue_description=payload.issue_description,
        force_generate=payload.force_generate,
    )
    
    if result["status"] == "mismatch":
        classification = result["classification"]
        return {
            "status": "mismatch",
            "message": classification.get("message_to_user", "Your description doesn't match the selected document type."),
            "suggested_type": classification.get("suggested_type"),
            "mismatch_reason": classification.get("mismatch_reason"),
            "detected_intent": classification.get("detected_intent"),
        }
    
    if result["status"] == "needs_info":
        classification = result["classification"]
        return {
            "status": "needs_info",
            "message": classification.get("message_to_user", "More information is needed to generate this document."),
            "missing_info": classification.get("missing_info", []),
        }
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to generate document"))
    
    content = result["content"]
    output_name = f"{payload.template_type}-{uuid4().hex}.pdf"
    output_path = build_pdf(output_name, content)
    file_id = execute(
        "INSERT INTO generated_documents (user_id, template_type, output_path, input_json) VALUES (?, ?, ?, ?)",
        (
            current_user["id"],
            payload.template_type,
            str(output_path),
            dumps_json(payload.model_dump()),
        ),
    )
    return {"status": "success", "file_id": file_id, "preview": content, "download_url": f"/api/download/{file_id}"}


@app.get("/api/generated-documents")
def generated_documents(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    rows = fetch_all(
        "SELECT * FROM generated_documents WHERE user_id = ? ORDER BY created_at DESC",
        (current_user["id"],),
    )
    return {"generated_documents": rows_to_dicts(rows)}


@app.get("/api/download/{file_id}")
def download(file_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> FileResponse:
    row = fetch_one(
        "SELECT * FROM generated_documents WHERE id = ? AND user_id = ?",
        (file_id, current_user["id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    path = Path(row["output_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generated file missing")
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))


@app.get("/api/chat-history/{document_id}")
def chat_history(document_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    rows = fetch_all(
        "SELECT * FROM chat_history WHERE user_id = ? AND document_id = ? ORDER BY created_at DESC",
        (current_user["id"], document_id),
    )
    return {"messages": rows_to_dicts(rows)}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class LawLookupRequest(BaseModel):
    query: str


class LawSearchRequest(BaseModel):
    topic: str
    limit: int = 5


class LawQuestionRequest(BaseModel):
    question: str


@app.post("/api/law/lookup")
def law_lookup(payload: LawLookupRequest) -> dict[str, Any]:
    """Look up a specific law section (e.g., 'IPC 420', 'Section 302 IPC', 'BNS 318')."""
    result = lookup_section(payload.query)
    if not result:
        return {
            "found": False,
            "message": f"Could not find section matching '{payload.query}'. Try formats like 'IPC 420', 'Section 302 IPC', or 'BNS 318'.",
        }
    return result


@app.post("/api/law/search")
def law_search(payload: LawSearchRequest) -> dict[str, Any]:
    """Search for law sections by topic/keyword."""
    topic_results = search_law_by_topic(payload.topic, limit=payload.limit)
    semantic_results = semantic_search_laws(payload.topic, limit=payload.limit)
    
    return {
        "topic_matches": topic_results,
        "semantic_matches": [
            {
                "text": r.get("text"),
                "metadata": r.get("metadata"),
                "relevance_score": r.get("relevance_score"),
            }
            for r in semantic_results
        ],
    }


@app.post("/api/law/ask")
def law_ask(payload: LawQuestionRequest) -> dict[str, Any]:
    """Ask a question about Indian law without needing a document."""
    result = answer_law_question(payload.question)
    return result


@app.post("/api/law/index")
def law_index() -> dict[str, Any]:
    """Index/re-index the Indian law knowledge base."""
    count = index_law_knowledge()
    return {"message": f"Indexed {count} law entries.", "count": count}
