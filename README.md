# LoanWise AI

**An Explainable Retrieval-Augmented Generation Architecture for Intelligent Loan Eligibility Assessment and Credit Decision Support**

LoanWise AI is a full-stack research application for authorized analysts. It combines financial records, explicit calculations, versioned policy evidence, synthetic credit-risk models, SHAP explanations and a twelve-node LangGraph workflow. Assessments support human review; they never execute lending or contractual actions.

All bundled applicants, financial records, lending policies, training labels and model outcomes are synthetic. The model has not been validated for real-world lending, fairness or individual default probability. Final decisions are separately recorded by authorized human reviewers.

## Implemented capabilities

- React workspace: authentication, dashboard, applicant directory, applications, document intelligence, financial analysis, credit risk, explainability, knowledge base, assessment, scoped assistant, human review, reports, agent monitoring and settings.
- Persistent **48-table relational domain schema**, SQLite and PostgreSQL, migrations/backfill, foreign keys, money precision, constraints and immutable policy configuration revisions.
- Separate income, employment, expense, liability, credit-account and repayment records. The existing profile API is a compatibility view over those rows, not JSON-backed input storage.
- Document pages/revisions, extraction entities/correction history, policy sources/permissions, criteria/results, financial features, model registry/evaluations/predictions, SHAP contributions, citations and reviewer comments are relational records.
- 500 synthetic applicants/applications, three products/policies, 500 financial source documents and 6,000 synthetic repayment observations. A separate 1,600-row synthetic dataset trains five classifiers.
- Local CPU OCR for scanned PDFs and PNG/JPEG images, selectable PDF/DOCX/TXT/CSV/JSON extraction, per-page provenance, raw recognition scores, manual review and source-preserving corrections.
- Parser subprocesses, wall-time/RSS/pixel/page/byte budgets, Unix resource limits and bounded parser concurrency. OCR values are never silently verified or copied into applicant inputs.
- Reviewed-income gates, DTI/LTI/LTV, EMI including zero-interest cases, repayment burden and disposable-income estimates.
- Logistic regression, decision tree, random forest, gradient boosting and XGBoost; training-only preprocessing, split/leakage diagnostics, outlier analysis, calibration metrics, versioned model artifacts and exact logistic SHAP contributions.
- BM25 + TF-IDF retrieval by default; optional **tested CPU Sentence Transformers + persisted FAISS + cross-encoder reranking**. Both paths preserve source metadata and abstain without relevant evidence.
- Exact extractive policy answers and deterministic applicant-specific calculations. The assistant scopes private records to a selected authorized application and never looks up another applicant from instructions in a question.
- Twelve separately validated agent payload schemas, structured state, persisted execution traces, retries and withholding after repeated failures.
- Product-specific numeric/document-count criteria, explicit unknown/conflicting/review statuses, source/threshold validation and no autonomous approval/rejection.
- Human review, comments, separately stored human decisions, assessment/model/explanation history, audit logs and report export.
- Session-token hashing, scrypt passwords, role/ownership checks, source permissions and rechecks for historical evidence, strict mutating-request Origin validation, rate limiting and parameter-hiding database logs.
- Docker/Compose, Nginx, PostgreSQL health dependencies, persistent volumes, core dependency constraints, CI jobs and reproducible local/PostgreSQL/neural/container verification scripts.

## Project layout

```text
frontend/
  src/components/       # reusable UI, corrections, permissions, prediction history
  src/pages/            # routed workspaces
  src/hooks/            # authorized application selection
  src/api.ts, types.ts, App.tsx, styles.css
  Dockerfile, nginx.conf, package.json, pnpm-lock.yaml
backend/
  app/                  # APIs, schemas, security, relational models/access/services
  ai/                   # OCR, parsing, retrieval, calculations, criteria, agents
  ml/                   # synthetic generation, training, evaluation, SHAP/fairness
  alembic/versions/      # 0001 legacy schema; 0002 normalized backfill
  tests/
  data/                 # synthetic JSON/CSV, sample policies/documents
  runtime/              # ignored DB, credentials, documents, model/HF/FAISS caches
scripts/                # launchers, dependency constraints and integration tests
docs/                   # architecture, database/API guides and verified results
docker-compose.yml
.env.example
.github/workflows/ci.yml
```

## Stack and architecture

Frontend: React, Vite, TypeScript, Tailwind CSS, React Router, Axios, Recharts, Lucide, React Hook Form and Zod. Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy and Alembic. AI/ML: NumPy, Pandas, SciPy, scikit-learn, XGBoost, Joblib, SHAP and LangGraph. Neural retrieval uses Sentence Transformers, FAISS and a cross encoder. OCR uses bundled RapidOCR ONNX models, PDFium and Pillow.

The client calls a same-origin API proxy. Authorization precedes applicant or source retrieval. Uploaded content is data, never executable instructions. Approved policy passages and typed financial facts flow through the agent graph into immutable assessment documents; an authorized reviewer records a separate human decision.

See [architecture and workflow diagrams](docs/ARCHITECTURE.md), [database design](docs/DATABASE.md), [API contracts](docs/API.md), and [verification results](docs/VERIFICATION.md).

## Install locally

Use **Python 3.12**, **Node.js 24**, and pnpm 11.25.0. Python 3.15 is unsuitable for this tested scientific dependency set. No paid API credentials are needed.

From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -c backend\requirements-lock.txt
Copy-Item .env.example backend\.env
Set-Location frontend
pnpm install --frozen-lockfile
Set-Location ..
```

The existing `.venv` on this computer is already installed. If `python` resolves to another version, use your Python 3.12 executable to create it. Linux/macOS use `.venv/bin/python` instead of the Windows executable.

## Start backend and frontend

Run these in **separate terminals**, from the root:

```powershell
.\scripts\start-backend.ps1
```

```powershell
.\scripts\start-frontend.ps1
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The exact browser origin must match `ALLOWED_ORIGIN`.

Equivalent backend commands, inside `backend`:

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Inside `frontend`, use `pnpm dev`. The PowerShell launcher invokes Vite directly if pnpm is unavailable on PATH.

A fresh demo database generates admin credentials in **`backend/runtime/demo-credentials.txt`**. There is no shared default password or public credentials endpoint. Keep that ignored file private. New registrations are analysts and see their own records; administrators can assign reviewer privileges.

## Database setup and upgrade

SQLite defaults to `sqlite:///./runtime/loanwise.db`, relative to the backend working directory. The startup script runs migrations. A fresh direct API/CLI bootstrap creates the current schema and stamps its migration version; an older JSON-backed database must be upgraded explicitly.

**Revision 0002 backfills existing profiles, pages, corrections, policy criteria, assessments, predictions, citations and comments before removing legacy JSON input columns.** SQLite migrations use explicit transactional DDL and a foreign-key integrity check. PostgreSQL migrations run transactionally. Historical report/agent JSON remains an archival materialized document, not the mutable operational source of truth.

Back up an existing database before upgrade. This workspace has a consistent pre-upgrade backup under `backend/runtime/backups/`. A lossy normalization downgrade is intentionally refused; restore the backup if rollback is necessary.

For PostgreSQL, set `DATABASE_URL=postgresql+psycopg://...` in `backend/.env`, then run `python -m alembic upgrade head`. Alternatively provide `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` and optional `POSTGRES_PORT` with no explicit `DATABASE_URL`. The latter constructs an escaped URL, including passwords with special characters. Explicit `DATABASE_URL` takes precedence.

For a non-demo bootstrap, set `DEMO_MODE=false`, run migrations and `python -m app.cli create-admin`. Add products in Settings, upload/review their policies and configure criteria. No synthetic seed is automatically inserted in non-demo mode.

Existing synthetic repayment files can be imported idempotently from `backend`:

```powershell
..\.venv\Scripts\python.exe -m app.cli import-synthetic-repayments data/synthetic/financial_records.json
```

The importer accepts only explicitly synthetic records mapped to synthetic applications. Migration does not invent repayment histories from aggregate missed-payment counts.

## Document ingestion and OCR

Administrators upload policies through Knowledge base with product, version and effective date. Review extracted text before indexing. Only reviewed, authorized, effective sources matching the configured product version enter retrieval. Financial documents belong to one application and never enter the shared policy corpus.

Financial uploads accept PDF, DOCX, TXT, CSV, JSON, PNG and JPEG up to 8 MiB. OCR is enabled by default for image-only PDF pages and images; selectable PDF text is preserved. PDF pages retain original page numbers. DOCX/TXT/CSV/JSON use logical extraction pages.

OCR recognition scores are raw engine diagnostics, **not calibrated confidence that financial values are correct**. Entities remain unverified, even after a document review. Corrections preserve original quotes, reviewer identity, timestamps and previous values. Application financial inputs require explicit correction and verification.

Default budgets: 200 PDF pages total, 20 OCR pages, 20 million rendered/image pixels per page, 60 seconds per parser, 2 GiB monitored RSS and at most two parser workers per backend process. Unix also enforces address-space/CPU limits. Exceeding a budget rejects the extraction instead of accepting a partial result.

OCR was checked on clean synthetic English scans. Handwriting, complex bank-statement tables and other languages need separate evaluation/model configuration. Entity extraction is a conservative field matcher, not a claim of general document understanding.

CLI policy ingestion, from `backend`:

```powershell
..\.venv\Scripts\python.exe -m app.cli ingest data/sample_policies/1.txt --product 1 --version DEMO-2026.1 --effective-date 2026-01-01
```

CLI uploads also require administrator review before indexing. Knowledge-base permissions can be restricted by role; reindexing retires old chunks rather than deleting historical citation targets.

## Financial records and formulae

The existing application form provides a declared financial summary. Typed financial-record APIs support multiple income sources, liabilities, employment entries, credit accounts and repayment observations. Unknown values remain unknown; zero debt is stored as an explicit zero record. Full ledger updates are explicit replacements; source documents and assessment snapshots retain their own history.

Monthly income conversions: monthly amount unchanged; annual / 12; weekly × 52 / 12; fortnightly × 26 / 12. Income-based calculations require reviewed income and no unresolved income conflict. Multiple account utilization percentages are not averaged without credit-limit weights; aggregate utilization is then unknown. Conflicting reliable scores are not guessed or merged.

| Indicator | Formula / missing behavior |
|---|---|
| DTI | Existing monthly debt / reviewed gross monthly income × 100 |
| LTI | Principal / annual gross income |
| LTV | Principal / verified asset value × 100 |
| EMI | `P × r / (1 − (1+r)^(-n))`, `r = annual_percent / 1200` |
| Zero-interest EMI | `P / n` |
| Repayment burden | `(existing debt + proposed EMI) / monthly income × 100` |
| Disposable income | Income − debt − expenses − proposed EMI; unknown if any term is missing |

Demo money is INR. The annual rate is an explicit illustration input, not a bank offer. Product thresholds come only from configured source quotations. Predictive feature allowlists are configured per jurisdiction with MODEL_FEATURE_POLICIES; unconfigured jurisdictions or excluded required features produce no model estimate. An allowlist is not evidence of legal/fairness approval. A documentation-count rule counts reviewed, non-quarantined, nonempty financial documents; it does not independently certify their legal sufficiency or type.

## ML training, SHAP and fairness

From `backend`:

```powershell
..\.venv\Scripts\python.exe -m ml.pipeline
```

Training uses 1,600 synthetic observations, seed 42, and a disjoint stratified 60/20/20 train/validation/test split. All five classifiers have training-fitted imputation; logistic regression also scales numeric inputs. Reports include class balance, approved features, missing/outlier diagnostics, accuracy, precision, recall, F1, ROC-AUC, PR-AUC, specificity, confusion matrices, Brier score and calibration bins. No temporal validation is claimed for independent synthetic records.

The logistic baseline is chosen a priori for exact additive SHAP, not selected on test performance. Model and explanation snapshots persist separately. Training versions are content-derived, artifacts are retained per version, and the active artifact is replaced atomically. Restart the backend after CLI retraining to refresh its artifact cache.

SHAP baseline plus feature contributions equals model log-odds. Contributions describe model behavior, not causation or a legal lending reason. Scores remain uncalibrated synthetic indicators, not an individual default probability. Missing required model features produce `INSUFFICIENT INFORMATION`.

Random synthetic cohort diagnostics exercise parity/opportunity/odds and group FPR/FNR calculations and persist in `fairness_evaluations`. They are not demographic fairness evidence. Real-world fairness remains `NOT_EVALUATED`; sensitive characteristics are not inferred or used as predictive features.

## Retrieval and providers

The tested default combines BM25 and TF-IDF with reciprocal-rank fusion. The optional neural path uses CPU Sentence Transformers, a persisted FAISS index and cross-encoder reranking. Access/product/version/effective-date filters precede scoring. RRF, cosine and cross-encoder scores are relevance diagnostics, not financial confidence.

Install the optional stack from `backend`:

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements-neural.txt
```

For CPU-only Torch, install it first from the official PyTorch CPU index. Set `RETRIEVAL_MODE=neural` and restart. Public model weights cache under `runtime/huggingface`, with `trust_remote_code=false`; indexes live under `runtime/vectors`. A model download needs network access, not a paid API key.

The neural path was exercised with real local embeddings, persisted FAISS, reranking, the twelve-agent workflow and the synthetic benchmark. See verification notes for the limited scope of that evidence.

OpenAI-compatible, Gemini and Anthropic HTTP transports exist behind environment configuration. The default answer path deliberately uses deterministic calculations and exact extractive policy passages. External credentials are not present, live external calls were not tested, and configuring a provider does not silently replace grounded output with unsupported generated claims.

## Assessment and review

Create/select an application, review documents, verify declared financial inputs and run AI assessment. Inspect numeric conditions, unknown/conflicting inputs, source quotations, model contributions and review requirements. The assistant can explain the selected application's actual DTI or current assessment, using only authorized records.

An empty policy configuration cannot satisfy eligibility. Missing values never become satisfied criteria. Every outcome requires human review. Reviewer comments and final human decisions are stored separately; neither an assessment nor a recorded decision executes a financial action.

Snapshots retain policy configuration IDs/revisions and an input fingerprint. Changed profiles, documents or policy configurations require a fresh assessment before a human decision can be recorded. Prediction/explanation and assessment-history endpoints expose stored snapshots, not invented or silently recomputed history.

## Tests and reproducible verification

Inside `backend`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ai.evaluation
```

Inside `frontend`: `pnpm test` and `pnpm build`. Direct Node alternatives are `node node_modules/vitest/vitest.mjs run`, `node node_modules/typescript/bin/tsc -b`, and `node node_modules/vite/bin/vite.js build`.

From the root, with official portable PostgreSQL binaries:

```powershell
.\scripts\test-postgres.ps1 -PgBin .\runtime\tools\pg16\pgsql\bin
.\.venv\Scripts\python.exe scripts/test-neural.py
```

The PostgreSQL script initializes a random isolated cluster, uses SCRAM authentication and a generated password, binds loopback port 55432, runs migrations/seed and the API suite against disposable databases, then stops its own server. It does not install a Windows service or change your development database. PostgreSQL binaries are available from [EDB's official archive](https://productsdl.enterprisedb.com/download-postgresql-binaries).

Backend tests cover schema/backfill/rollback, foreign keys, ownership, source revocation, exact citations, OCR, upload budgets, calculations, criteria, model training/SHAP, agent failures, history, stale reviews and human decisions. Frontend tests cover authentication gating, validation before writes, error states and financial display. Benchmarks are small synthetic fixtures, not real lending performance claims.

## Docker and deployment preparation

Compose uses PostgreSQL 16, a Python 3.12 backend, a Node 24 frontend build and Nginx. Database/runtime/data volumes persist across container recreation. Backend and frontend startup depend on health checks. `.env` and runtime data are excluded from build contexts. TLS is supplied by your production ingress; configure secure cookies and the exact HTTPS origin there.

```powershell
$env:POSTGRES_PASSWORD = 'SET_A_LONG_RANDOM_PASSWORD'
docker compose up --build
docker compose exec backend python -m ml.pipeline
docker compose restart backend
```

Open `http://localhost:8080`. Read the generated container demo credentials locally with `docker compose exec backend cat runtime/demo-credentials.txt`; do not publish them.

The full disposable container test is:

```powershell
.\.venv\Scripts\python.exe scripts/test-containers.py
```

It builds/starts a uniquely named test stack, trains the model, checks PostgreSQL-backed APIs, OCR, SHAP, citations and frontend serving, then removes only that test stack and its volumes. `--config-only` validates configuration and probes engine availability. An optional `--compose-executable` accepts a standalone Compose CLI path.

**Local Docker runtime verification is blocked by the missing Docker engine.** The official Compose CLI checksum/configuration were checked; its engine probe fails because `docker_engine` is absent. No hypervisor settings were changed or reboot forced. Start a working Docker engine, then rerun the container test. The CI workflow also contains PostgreSQL and full-container jobs; those remote jobs have not been run from this chat.

## Configuration and retention

Copy `.env.example` to `backend/.env`. Important fields: `DATABASE_URL` or the `POSTGRES_*` connection fields; `DEMO_MODE`; `ALLOWED_ORIGIN`; `COOKIE_SECURE`; `SESSION_HOURS`; `STORAGE_DIR`; `MODEL_DIR`; `RETENTION_DAYS`; `OCR_ENABLED`; OCR/parser budgets; retrieval/embedding/reranker settings; synthetic score thresholds; MODEL_FEATURE_POLICIES; and optional LLM provider configuration. Secrets are backend-only and never returned to the frontend.

From `backend`, `python -m app.cli retention-preview` lists the source retention cutoff; `python -m app.cli purge-expired-documents` purges expired financial files, every stored page revision, entity values/quotes, correction values and financial chunk text, preserving IDs and minimal audit metadata. It also removes expired sessions. Historical assessment/model snapshots have a separate governance purpose and are not purged by this source-only command. Adapt derived-record retention, legal holds and institution-specific policy before using real data.

## Verification limits

This is a research prototype, not a bank system certification. Real-world model calibration, proxy/fairness review, governed datasets, credit-bureau verification, malware scanning, distributed rate limits/jobs, SSO/account recovery, external LLM validation and broader load/accessibility testing require additional institutional work. No claim of legal compliance or real-world lending accuracy is made. The only attempted local deployment test still blocked is Docker image/runtime execution; detailed results are in [VERIFICATION.md](docs/VERIFICATION.md).

## Deployed workspace

The Vercel/Neon workspace is at https://loanwise-ai-eta.vercel.app. See [deployment configuration and operations](docs/DEPLOYMENT.md) for the dedicated database, cloud credentials, durable uploads, deployment commands and platform limits. The cloud password differs from the local demo password.
