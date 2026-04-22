## 🚀 Live Demo
👉 https://ai-rental-document-analyzer.vercel.app/

---

# Rental Document Analyzer

AI-powered SaaS for analyzing German rental contracts. Upload a PDF/DOCX, get back a structured summary, key clauses, risk highlights, and a plain-English explanation.

---

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Database | PostgreSQL 16 + SQLAlchemy 2 |
| Migrations | Alembic |
| Task queue | Celery + Redis |
| File storage | AWS S3 |
| AI | OpenAI GPT-4o |
| Auth | JWT (python-jose) + bcrypt |
| Frontend | React 18 + Vite |
| Deployment | Docker + docker-compose |

---

## Quick start (local)

### 1. Clone and configure
```bash
cp backend/.env.example backend/.env
# Edit backend/.env — fill in your real secrets
```

### 2. Start all services
```bash
docker-compose up --build
```

This starts:
- `db` — PostgreSQL on :5432
- `redis` — Redis on :6379
- `api` — FastAPI on :8000  →  http://localhost:8000/docs
- `worker` — Celery document processor
- `flower` — Celery monitoring UI on :5555

### 3. Run migrations
```bash
docker-compose exec api alembic upgrade head
```

### 4. Start the frontend (separate terminal)
```bash
cd frontend
npm install
npm run dev
```
Frontend runs at http://localhost:5173

---

## Project structure

```
rental-analyzer/
├── backend/
│   ├── app/
│   │   ├── main.py               ← FastAPI app factory
│   │   ├── core/
│   │   │   ├── config.py         ← All env-var settings
│   │   │   ├── security.py       ← JWT + bcrypt
│   │   │   ├── logging.py        ← Structured JSON logging
│   │   │   ├── exceptions.py     ← Domain exceptions + handlers
│   │   │   └── dependencies.py   ← FastAPI deps (auth, DB session)
│   │   ├── api/routes/
│   │   │   ├── auth.py           ← /auth endpoints
│   │   │   ├── documents.py      ← /documents endpoints
│   │   │   └── admin.py          ← /admin endpoints
│   │   ├── models/               ← SQLAlchemy ORM models
│   │   ├── schemas/              ← Pydantic request/response schemas
│   │   ├── services/             ← Business logic (S3, AI, doc processing)
│   │   ├── workers/              ← Celery app + tasks
│   │   └── db/                   ← Session factory + declarative base
│   ├── alembic/                  ← DB migrations
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/                     ← React + Vite app
└── docker-compose.yml
```

---

## API overview

```
POST   /auth/register       Register new user
POST   /auth/login          Login → returns access + refresh token
GET    /auth/me             Current user profile

POST   /documents/upload    Upload PDF/DOCX → triggers analysis
GET    /documents           List user's documents
GET    /documents/{id}      Get document + analysis result

GET    /admin/users         List all users (admin only)
GET    /admin/documents     List all documents (admin only)
```

---
