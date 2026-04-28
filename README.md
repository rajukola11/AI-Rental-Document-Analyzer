# 🏠 Rental Document Analyzer

> **AI-powered SaaS for analyzing German rental contracts.**  
> Upload a PDF or DOCX, get back a structured summary, key clauses, risk highlights, and a plain-English explanation — in seconds.

🔗 **Live Demo:** [https://ai-rental-document-analyzer.vercel.app](https://ai-rental-document-analyzer.vercel.app)

---

## ✨ Features

- 📄 **Document Upload** — Accepts PDF and DOCX rental contracts
- 🤖 **AI Analysis** — GPT-4o extracts clauses, risks, and summaries tailored for German tenancy law (BGB §§ 535–580a)
- 🔴 **Risk Scoring** — Rates contracts `low`, `medium`, or `high` risk
- 💳 **Credit-Based Billing** — Stripe-powered pay-as-you-go + bundle packages
- 🆓 **Free Tier** — 2 free analyses per verified account
- 📧 **Email Verification** — Disposable email blocking, secure token expiry
- 👑 **Admin Panel** — Manage users, view all documents, monitor usage
- ⚡ **Async Processing** — Celery + Redis task queue for non-blocking analysis
- ☁️ **Cloud Storage** — Documents stored in AWS S3
- 🚀 **CI/CD** — GitHub Actions → Railway (backend) + Vercel (frontend)

---

## 🗂️ Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Database | PostgreSQL 16 + SQLAlchemy 2 |
| Migrations | Alembic |
| Task Queue | Celery + Redis |
| File Storage | AWS S3 |
| AI | OpenAI GPT-4o |
| Auth | JWT (python-jose) + bcrypt |
| Payments | Stripe Checkout + Webhooks |
| Email | Resend |
| Frontend | React 18 + Vite |
| Deployment | Docker + docker-compose |
| CI/CD | GitHub Actions → Railway + Vercel |

---

## 🚀 Quick Start (Local)

### Prerequisites

- Docker & docker-compose
- Node.js 20+
- An OpenAI API key, AWS S3 bucket, Stripe account, and Resend API key

---

### 1. Clone & configure

```bash
git clone https://github.com/your-username/AI-Rental-Document-Analyzer.git
cd AI-Rental-Document-Analyzer

cp backend/.env.example backend/.env
# Edit backend/.env — fill in your real secrets (see Environment Variables below)
```

---

### 2. Start all backend services

```bash
docker-compose up --build
```

This starts:

| Service | URL | Description |
|---|---|---|
| `db` | `:5432` | PostgreSQL 16 |
| `redis` | `:6379` | Redis 7 |
| `api` | `http://localhost:8000` | FastAPI + Swagger at `/docs` |
| `worker` | — | Celery document processor |
| `beat` | — | Celery scheduled tasks |
| `flower` | `http://localhost:5555` | Celery monitoring UI |

---

### 3. Run database migrations

```bash
docker-compose exec api alembic upgrade head
```

---

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at **http://localhost:5173**

---

## ⚙️ Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in the values:

```env
# App
APP_ENV=development
DEBUG=true

# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/ai_rental_analyzer

# Security
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# AWS S3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=eu-central-1
S3_BUCKET_NAME=rental-analyzer-docs

# Celery / Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
REDIS_URL=redis://localhost:6379/0

# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Resend (email)
RESEND_API_KEY=re_...
EMAIL_FROM=noreply@yourdomain.com

# Frontend
FRONTEND_URL=http://localhost:5173
ALLOWED_ORIGINS=http://localhost:5173

# Email security
VERIFICATION_TOKEN_EXPIRE_HOURS=1
BLOCK_DISPOSABLE_EMAILS=true
```

---

## 🗃️ Project Structure

```
rental-analyzer/
├── backend/
│   ├── app/
│   │   ├── main.py                   ← FastAPI app factory
│   │   ├── core/
│   │   │   ├── config.py             ← All env-var settings
│   │   │   ├── security.py           ← JWT + bcrypt
│   │   │   ├── logging.py            ← Structured JSON logging
│   │   │   ├── exceptions.py         ← Domain exceptions + handlers
│   │   │   └── dependencies.py       ← FastAPI deps (auth, DB session)
│   │   ├── api/routes/
│   │   │   ├── auth.py               ← /auth endpoints
│   │   │   ├── documents.py          ← /documents endpoints
│   │   │   ├── payments.py           ← /payments + Stripe webhook
│   │   │   └── admin.py              ← /admin endpoints
│   │   ├── models/                   ← SQLAlchemy ORM models
│   │   ├── schemas/                  ← Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── ai_service.py         ← OpenAI GPT-4o analysis
│   │   │   ├── document_processor.py ← PDF/DOCX text extraction
│   │   │   ├── document_service.py   ← Document business logic
│   │   │   ├── s3_service.py         ← AWS S3 upload/download
│   │   │   ├── stripe_service.py     ← Stripe checkout + webhooks
│   │   │   ├── email_service.py      ← Resend transactional email
│   │   │   └── disposable_email_service.py ← Blocklist enforcement
│   │   ├── workers/
│   │   │   ├── celery_app.py         ← Celery app + queue config
│   │   │   └── tasks.py              ← Async document analysis task
│   │   └── db/                       ← Session factory + declarative base
│   ├── alembic/                      ← DB migration versions
│   ├── tests/                        ← Full pytest test suite
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/                         ← React 18 + Vite SPA
│   └── src/
│       ├── pages/
│       │   ├── Landing/              ← Marketing landing page
│       │   ├── Auth/                 ← Login / Register
│       │   ├── Dashboard/            ← Document list
│       │   ├── Upload/               ← File upload
│       │   ├── Analysis/             ← Analysis results view
│       │   ├── Billing/              ← Credit packages + payment
│       │   └── Admin/                ← Admin dashboard
│       ├── components/               ← Shared UI components
│       ├── hooks/                    ← useAuth and other hooks
│       └── api/                      ← API client
├── docker-compose.yml
└── .github/workflows/deploy.yml      ← CI/CD pipeline
```

---

## 🔌 API Reference

### Auth

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Register a new user |
| `POST` | `/auth/login` | Login → returns access + refresh token |
| `POST` | `/auth/refresh` | Refresh access token |
| `GET` | `/auth/me` | Current user profile |
| `GET` | `/auth/verify-email` | Verify email via token |

### Documents

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/documents/upload` | Upload PDF/DOCX → triggers async analysis |
| `GET` | `/documents` | List current user's documents |
| `GET` | `/documents/{id}` | Get document + analysis result |
| `DELETE` | `/documents/{id}` | Delete a document |

### Payments

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/payments/billing` | Current billing status & credits |
| `GET` | `/payments/packages` | List available credit packages |
| `POST` | `/payments/checkout` | Create Stripe checkout session |
| `POST` | `/payments/webhook` | Stripe webhook handler |

### Admin

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/admin/users` | List all users |
| `GET` | `/admin/documents` | List all documents |
| `PATCH` | `/admin/users/{id}` | Update user role / status |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |

> Full interactive docs available at `http://localhost:8000/docs` (development only)

---

## 💳 Pricing Tiers

| Package | Credits | Price | Notes |
|---|---|---|---|
| Free | 2 | €0 | Included on signup (verified accounts) |
| Pay-As-You-Go | 1 | €1 | — |
| Popular | 6 | €4 | Save 43% — +1 bonus credit on first purchase |
| Best Value | 20 | €10 | Save 57% — +3 bonus credits on first purchase |

---

## 🧪 Running Tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

The test suite covers auth, documents, AI service, Stripe payments, S3, Celery tasks, admin routes, and more.

---

## 🚢 Deployment

The project deploys automatically via GitHub Actions on push to `main`:

- **Backend** (API + Worker) → [Railway](https://railway.app)
- **Frontend** → [Vercel](https://vercel.com)

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `RAILWAY_TOKEN` | Railway API token |
| `VERCEL_TOKEN` | Vercel API token |
| `VITE_API_URL` | Production backend URL |

### Promoting an admin

```bash
docker-compose exec api python scripts/make_admin.py user@example.com
```

---

## 🛡️ Security Notes

- All passwords are hashed with **bcrypt**
- Access tokens expire after **30 minutes**; refresh tokens after **7 days**
- Disposable/throwaway email addresses are blocked on registration
- Email verification is required before uploading documents
- Stripe webhooks are verified with the `STRIPE_WEBHOOK_SECRET`
- Swagger/ReDoc docs are **disabled in production**

---

## 📄 License

MIT