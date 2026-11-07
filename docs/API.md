# API contract

Run the backend and open [interactive OpenAPI](http://127.0.0.1:8000/docs) or [OpenAPI JSON](http://127.0.0.1:8000/openapi.json). The generated schema is the authoritative field/type contract. All routes except health, registration and login require the HttpOnly `loanwise_session` cookie. Send requests through the same-origin frontend proxy, or use a cookie jar. Mutating browser requests must use `ALLOWED_ORIGIN`.

| Group | Endpoints | Authorization |
|---|---|---|
| Authentication | POST `/api/auth/register`, `/login`, `/logout`; GET `/api/auth/me` | New accounts are analysts |
| Products | GET `/api/products`; PUT `/api/products/{id}/criteria` | Criteria updates: admin |
| Applicants | GET/POST `/api/applicants`; GET/PUT `/api/applicants/{id}` | Owner or admin |
| Applications | GET/POST `/api/applications`; GET/PUT `/api/applications/{id}` | Owner or admin |
| Documents | POST `/api/documents/upload`; GET `/api/documents`, `/{id}`, `/{id}/download`; POST `/{id}/extract`, `/{id}/review` | Owner/admin; shared policies visible to authenticated staff; policy changes admin only |
| Financial | POST `/api/financial/analyze`; GET `/api/financial/{application_id}` | Owner or admin |
| Risk | POST `/api/credit-risk/predict`; GET `/api/credit-risk/{application_id}` | Owner or admin |
| Explanations | POST `/api/explainability/shap`; GET `/api/explainability/{application_id}` | Owner or admin |
| Assessment | POST `/api/eligibility/assess`; GET `/api/eligibility/{application_id}` | Owner or admin |
| Agents | POST `/api/agents/run`; GET `/api/agents/executions`, `/{id}` | Authorized application scope |
| RAG | POST `/api/rag/ingest`, `/api/rag/query`; GET `/api/rag/documents`, `/api/rag/evidence/{query_id}` | Ingest admin; query evidence restricted to query owner |
| Review | POST/GET `/api/reviews`; PUT `/api/reviews/{id}`; POST `/api/reviews/{id}/decision` | Review/decision changes require reviewer/admin plus record access |
| Reports | GET `/api/reports/dashboard`, `/applications`, `/model-performance`, `/fairness`, `/retrieval`; `/api/models/evaluation` | Authenticated; applicant reports scoped to ownership |
| Settings | GET `/api/settings`; PUT `/api/users/{id}/role?role=reviewer` | Admin |

## Examples

`POST /api/eligibility/assess` body:

```json
{"application_id": 2}
```

`POST /api/rag/query` body:

```json
{"question": "What is the minimum monthly income?", "product_id": 1}
```

Policy upload uses multipart `file`, `kind=policy`, `product_id`, `version`, `effective_date` (YYYY-MM-DD). Financial upload uses `file`, `kind=financial`, `application_id`. Uploading never marks the extracted values verified. A separate review indexes policy text. Review does not automatically copy extraction candidates into application financial inputs.

Application/applicant lists accept `q`, `page`, and bounded `limit` (maximum 100) and return `{items,total}`. Document lists return a 30-record page; execution/review/audit lists are bounded. Small lookup collections such as products are unpaginated. Validation failures are HTTP 422, missing/inaccessible resources 404, authentication 401, role failures 403, duplicates/finalized records 409, and rate limits 429. Assessment failures are 503 and produce no unsupported final result.

`PUT /api/documents/{id}/entities/{index}` accepts `{value,reason}` to correct a financial extraction candidate. It preserves source text and the original quote, appends reviewer/timestamp correction history, and resets the document review flag. It never silently overwrites application data.

AI criterion statuses: `SATISFIED`, `NOT_SATISFIED`, `UNKNOWN`, `CONFLICTING`, `NEEDS_HUMAN_REVIEW`. No AI endpoint returns an autonomous approval/rejection. Final human decisions use `APPROVED`, `REJECTED`, or `DEFERRED` only in a separate reviewer-authored record; this triggers no downstream financial action.

## Normalized records and history

| Endpoint | Contract |
|---|---|
| GET/PUT `/api/applications/{id}/financial-records` | Typed income, employment, expense, liability, credit-account and repayment collections; owner/admin; verified sources require a reviewed document in the same application |
| PUT `/api/documents/{id}/permissions` | Admin policy-source role permissions; revocations apply to retrieval and archived evidence access |
| POST `/api/products` | Admin product provisioning with jurisdiction and policy configuration |
| POST `/api/applications/{id}/feedback` | Authorized application feedback |
| GET `/api/credit-risk/{id}/history` | Stored prediction features, model version and SHAP; no new inference |
| GET `/api/models/versions` | Registered model versions and local artifact availability |
| GET `/api/eligibility/{id}/history` | Assessment IDs, current-input status and access-aware summary |
| GET `/api/assessments/{id}` | Exact archived assessment after current ownership and source permission checks |

Financial summaries remain response DTOs over normalized records. Summary edits cannot silently consolidate multiple financial sources; use the financial-record endpoint for explicit changes. Historical criteria refer to their exact policy configuration revision.

RAG queries may include `application_id` for authorized applicant context. Financial answers use verified financial inputs and current assessments; stale assessments request a refresh. Source evidence retains page revision, quoted text and retrieval scores.

Uploads accept PDF, DOCX, TXT, CSV, JSON, PNG and JPEG, with an 8 MiB file limit. Image-only PDFs and images use local OCR in a bounded parser subprocess. Responses include page extraction method and raw recognition scores. OCR outputs remain unverified candidates; document review does not automatically verify application inputs. Source reindexing preserves historical chunk references.

`MODEL_FEATURE_POLICIES` configures jurisdiction-specific inference feature allowlists. An unconfigured jurisdiction or excluded required feature produces insufficient information without model inference. Configuration is a technical control, not a determination that any feature is lawful.
