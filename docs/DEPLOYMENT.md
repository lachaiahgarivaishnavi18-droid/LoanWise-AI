# Vercel and Neon deployment

Production frontend: https://loanwise-ai-eta.vercel.app

API: https://loanwise-api.vercel.app/api/health

The deployment uses two Vercel projects in the existing `resume-project3` team: `loanwise-ai` (React/Vite) and `loanwise-api` (Python 3.12). The API and the dedicated free Neon database `loanwise-postgres` use Singapore. The frontend forwards `/api/*` to the API, preserving same-origin browser cookies. SPA deep links resolve to `index.html`.

The Neon database contains the 48 domain tables, migration revision `0003`, 500 synthetic applications, typed financial records and 6,000 repayment observations. It is separate from local development and test databases. Original uploaded documents are stored as deferred binary data in `financial_documents.content_bytes`; uploads, re-extraction and downloads therefore survive serverless restarts. Local development continues to use filesystem storage by default. The retention command clears either form of source storage.

Cloud backend settings include `DATABASE_URL` from Neon, `ALLOWED_ORIGIN=https://loanwise-ai-eta.vercel.app`, secure cookies, database document storage and synthetic seeding disabled at runtime. Database credentials remain backend-only. Initialization was run once explicitly; the generated cloud administrator credential is in ignored `runtime/cloud-bootstrap/demo-credentials.txt`. It differs from the local development password. Never commit either credential file.

`deploy/vercel/` contains the Python entrypoint, function configuration and uv dependency lock. The lock excludes desktop OpenCV in favor of headless OpenCV and pins the scientific packages used to serialize the packaged selected model. Optional neural weights are not deployed; the cloud uses local BM25/TF-IDF and extractive answers. The packaged model remains synthetic and supports research review only.

To stage a backend update:

```powershell
.\.venv\Scripts\python.exe scripts/prepare-vercel-backend.py
vercel deploy --prod --cwd runtime/vercel/backend --scope resume-project3
vercel deploy --prod --cwd frontend --scope resume-project3
```

Use an authenticated official Vercel CLI. The backend staging helper includes source and packaged model artifacts, excluding local database files, uploaded originals, credentials and neural caches. Environment files and `.vercel` credentials are ignored. Deployments are CLI-based; no Git repository was published or connected.

When updating the database, run Alembic migrations using the dedicated Neon URL in a protected process environment before deploying code that needs them. Do not put database URLs into Vite variables. If the frontend domain changes, update the backend allowed origin and redeploy it. Only public API URLs may use `VITE_API_BASE_URL`.

Run the deployed integration check:

```powershell
.\.venv\Scripts\python.exe scripts/test-vercel.py
```

The check uses the local cloud credential file without printing it and writes `runtime/verification/vercel.json`. It signs in, reads all 500 applications, runs a 12-agent assessment and SHAP, retrieves cited policies, uploads a clearly labeled synthetic OCR fixture and verifies the downloaded original. It does not submit a human lending decision.

Vercel's request body ceiling is lower than the local 8 MiB file limit; keep cloud uploads below 4 MiB. Parser time/memory budgets still apply. Uploaded originals consume Neon storage; monitor the free plan's usage and retention. Cold starts and long database transactions can affect latency. Docker remains a separate local deployment option; its engine was unavailable during local verification.

The serverless API selects `PARSER_PROCESS_MODE=subprocess`, a dedicated bounded parser module that avoids re-running Vercel's server bootstrap. Local mode defaults to multiprocessing spawn. Both paths retain parser concurrency, timeout, memory, page and pixel budgets. The dedicated path passed the four real OCR/budget tests and two cloud-storage/configuration tests locally.

The live integration check passed after a clean rebuild of the locked headless dependency set. A warm synthetic check completed login, assessment, SHAP, citations, OCR and original-byte download in 5.95 seconds. Vercel automatically enabled its large-function beta because the scientific/OCR dependency bundle exceeds the standard size; `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` is configured. Keep that deployment requirement when reproducing the backend.
