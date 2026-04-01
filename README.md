# Legal AI Platform

A local-first FastAPI web app that helps non-lawyers upload legal documents, chat with them using RAG, extract important clauses, analyze risk, and generate structured legal drafts.

## Features

- PDF and DOCX upload
- Local text extraction and chunking
- ChromaDB-backed semantic retrieval
- Ollama-powered legal Q&A
- Clause extraction with plain-English explanation and risk label
- Risk analysis score with bullet findings
- Template-based legal document generation with PDF export
- Email/password authentication with SQLite persistence

## Requirements

- Python 3.10+
- Ollama installed and running
- Ollama models:
  - `mistral`
  - `nomic-embed-text`

## Local Setup

```bash
source .venv/bin/activate
uvicorn backend.app:app --reload
```

Open `http://127.0.0.1:8000`

## Project Structure

```text
backend/
frontend/
database/
storage/
chroma/
```

## Notes

- This platform provides AI-generated legal assistance and does not replace a licensed lawyer.
- SMTP email integration is deferred in this MVP.
- Hindi support is deferred in this MVP.
