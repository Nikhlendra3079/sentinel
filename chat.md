# Conversation Handoff — Resume, Projects, and Sentinel

**Prepared:** 15 November 2026  
**Purpose:** Continue the previous ChatGPT conversation in a new chat without repeating the background.

---

## 1. Current task: Fix the LaTeX resume layout

The active task is refining a **one-page LaTeX resume** for junior Software Engineer / Backend Engineer roles.

The user reports that the compiled resume is **two pages, with the first page blank**. The exact cause has not been established. A previous response suggested that a negative `\\vspace` command in the preamble might be involved, but that was only a hypothesis.

**Next step:** Ask for and inspect the actual `.tex` source and compiled PDF. Check for stray `\\newpage` / `\\clearpage`, content or commands before `\\begin{document}`, page-breaking settings, header/environment definitions, and vertical spacing. Fix the actual cause, then verify that the result is exactly one page and readable. Do not blindly apply the earlier spacing suggestion.

Resume goals:
- One page, readable, and ATS-friendly without keyword stuffing.
- Sound like an engineer wrote it, not AI-generated.
- Show real technical depth.
- Avoid unsupported claims, invented metrics, and exaggerated production-readiness claims.

## 2. Education and job direction

- B.Tech in Computer Science, Vellore Institute of Technology (VIT), Vellore.
- 2022–2026; CGPA: **8.13**.
- Rashtriya Indian Military College, Dehradun.
- SSE and SSCE, 2017–2021.
- Target roles: junior Software Engineer / Backend Engineer / SDE.
- Preferred locations mentioned: Hyderabad and Bengaluru.
- Wants to secure a job as soon as possible.

## 3. Projects

Recommended order:
1. **Sentinel** — multi-tenant API rate-limiting gateway.
2. **DocReader** — multi-user RAG document application.
3. **Vector Database Engine** — custom in-memory vector database.

### 3.1 Sentinel

Repository: <https://github.com/Nikhlendra3079/sentinel>

**Stack**
- Python, FastAPI, Pydantic Settings
- PostgreSQL, async SQLAlchemy, Alembic
- Redis, Redis Lua scripts
- Docker Compose
- Pytest, Locust, cProfile
- Prometheus, Grafana

**Architecture and functionality**
- Multi-tenant API rate-limiting gateway.
- Supports Token Bucket, Fixed Window, and Sliding Window Log algorithms.
- PostgreSQL stores durable tenant data, API-key metadata/hash, and policies; Redis stores shared quota state.
- Redis Lua scripts atomically check and update quota state on a Redis primary.
- Redis server time is used for time calculations.
- Middleware handles authentication, policy lookup, rate-limit decisions, and response headers.
- Policy resolution order: exact match, longest prefix, then catch-all.
- API keys use a 16-hex-character public lookup prefix and a 256-bit random secret. The secret is hashed with SHA-256 and returned only once.
- Configurable fail-open / fail-closed behavior for Redis failures; default is fail-closed.
- Quota exceeded responses use HTTP 429; fail-closed Redis errors result in HTTP 503.
- Emits headers such as `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`, `X-RateLimit-*`, and `Retry-After` on 429.
- Docker Compose includes PostgreSQL, Redis, and API services; Prometheus and Grafana are available through a monitoring profile.
- API container runs Alembic migrations before starting Uvicorn.

**Milestones**
- M1: FastAPI foundation, database, Redis, health checks, migrations, Compose.
- M2: tenants, API-key issuance, hashing, authentication, revoke/rotate.
- M3: in-process Token Bucket, Fixed Window, Sliding Window Log; policy CRUD/matching.
- M4: Redis Lua algorithms, middleware, fail-open/fail-closed behavior, metrics.
- M5: load testing, benchmarks, profiling, Redis diagnostics, Prometheus/Grafana.

**Recorded benchmark results**

| Locust users / duration | Requests | Throughput | Median | Average | p95 | p99 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5 users / 60s | 2,366 | 131.9 RPS | 8 ms | 8.93 ms | 14 ms | 16 ms | 46 ms |
| 10 users / 60s | 14,825 | 258.3 RPS | 10 ms | 11.53 ms | 20 ms | 26 ms | 60 ms |
| 25 users / 60s | 19,895 | 343.6 RPS | 42 ms | 46.21 ms | 83 ms | 110 ms | 176 ms |

Benchmark caveats:
- Locust counts HTTP 200 and 429 as successful, so zero failures does not mean every request received 200.
- At 25 users, one Docker stats snapshot showed API CPU around 98.76%, PostgreSQL around 48.52%, and Redis around 4.02%. This is one observation, not a comprehensive bottleneck analysis.
- Do not describe these results as production-scale or imply a production capacity.
- A historical test run reported 95 passed, 1 warning, 0 skipped; it was not a fresh run at the time.
- Manual fail-closed check: stopping Redis caused protected requests to return 503; restoring Redis returned the service to normal.
- Manual fail-open test allowed a request to continue, but exact status was not captured.
- Four Uvicorn workers were started, but a manual quota test was inconclusive due to a fixed-window boundary. A dedicated cross-process integration test exists.

**Known limitations**
- Every request has a fixed cost of 1.
- Policy data is read from the database on each authenticated request; no policy cache yet.
- Sliding Window Log has O(n) work relative to entries in the active window.
- In-process state does not currently evict entries.
- Admin secret is a bootstrap mechanism, not a full RBAC system.
- Key rotation immediately revokes the old key; no grace period.
- This is an API rate-limiting gateway, not a complete reverse proxy.
- Metrics are process-local; dashboard is intended for a single worker unless multiprocess aggregation is added.
- Redis Lua atomicity applies on one Redis primary; it is not consensus or guaranteed durability across failover.

**Candidate resume bullets — verify against current code**
- Built a multi-tenant API rate-limiting gateway using FastAPI, PostgreSQL, and Redis, supporting Token Bucket, Fixed Window, and Sliding Window Log algorithms.
- Implemented atomic quota enforcement with Redis Lua scripts, tenant-scoped keys, policy versioning, and Redis server timestamps to coordinate rate limits across workers.
- Developed asynchronous authentication and policy middleware with hashed API keys, endpoint policy resolution, rate-limit headers, and configurable fail-open/fail-closed behavior.
- Added concurrency and integration tests, Locust load tests, algorithm benchmarks, and profiling; containerized services with Docker Compose and instrumented them using Prometheus and Grafana.

### 3.2 DocReader

Repository: <https://github.com/Nikhlendra3079/docreader>

User-described functionality:
- Multi-user RAG application for document ingestion, semantic search, and context-aware AI conversations using FAISS and LangChain.
- Persistent vector storage with per-user isolation, snapshot persistence, and document deletion.
- Asynchronous REST APIs using FastAPI, PostgreSQL, and SQLAlchemy for authentication, document management, and persistent chat history.
- Real-time AI response streaming using Server-Sent Events (SSE), modular frontend architecture, session management, and integration testing.

Treat these as user-provided claims. Inspect the repository before adding more detail or embellishing.

### 3.3 Vector Database Engine

Repository: <https://github.com/Nikhlendra3079/my-vector-db-v1>

Latest user-provided description:
- Custom in-memory vector database using Python and FastAPI, with 768-dimensional LLM embeddings.
- NumPy-vectorized similarity search, Top-K retrieval, metadata filtering, and namespace isolation; exploration of Flat / IVF indexing.
- Scalar quantization from float32 to int8.
- Asynchronous embeddings using Ollama with `nomic-embed-text`, binary persistence, WAL, and snapshot recovery.
- Batch ingestion, concurrent requests, Pydantic validation, and benchmark comparisons of latency, throughput, and recall against FAISS.

**Verification warning:** Some of these may have been explored, planned, or partially implemented. Do not put WAL, snapshot recovery, IVF, FAISS comparison, or other claims on the resume until repository code and tests confirm them.

## 4. LaTeX resume structure previously discussed

The user wanted each project title on the left and repository link aligned right, with a smaller technology-stack line below the title.

Proposed macro:

```latex
\\newcommand{\\resumeProject}[4]{
  \\vspace{0.5mm}\\item
  \\begin{tabular*}{0.98\\textwidth}[t]{l@{\\extracolsep{\\fill}}r}
    \\textbf{#1} & \\footnotesize{#3} \\
    {\\scriptsize\\textit{#2}} & \\footnotesize{#4}
  \\end{tabular*}
  \\vspace{-2.4mm}
}
```

Argument order:
1. Project name
2. Technology stack
3. Repository link
4. Date

Previously discussed geometry:

```latex
\\geometry{left=1.4cm, top=0.8cm, right=1.2cm, bottom=1cm}
```

A previous response speculated that `\\vspace{-8.5mm}` in the preamble might relate to the blank page and suggested moving negative vertical space after `\\begin{document}`. This is **not verified**. Inspect the actual source and PDF first.

## 5. Candidate skills section

Only retain skills the user can confidently discuss and demonstrate.

- **Programming Languages:** Python, Java, Go, TypeScript, SQL
- **Backend:** FastAPI, Spring Boot, SQLAlchemy, Pydantic, REST APIs, asynchronous programming, SSE
- **AI / ML:** LangChain, FAISS, PyTorch, NumPy, RAG, vector search, Ollama, OpenAI API
- **Databases:** PostgreSQL, Redis, MongoDB
- **Infrastructure / Tools:** Docker, Docker Compose, Redis Lua, Alembic, Git/GitHub, Pytest, Locust, Prometheus, Grafana, cProfile, Postman

React, Tailwind, and JWT were mentioned in the user's broader technical background, but include them only if relevant and genuinely used in the projects being presented.

## 6. Certifications and profiles

- Microsoft Azure Data Fundamentals (DP-900).
- Microsoft Azure AI Fundamentals (AI-900).
- LeetCode: <https://leetcode.com/u/NIKHLENDRA/>

## 7. Sentinel GitHub migration history

- Sentinel Python was migrated into an existing GitHub repository that previously contained a Java API rate limiter.
- Repository was renamed to `sentinel`: <https://github.com/Nikhlendra3079/sentinel>.
- Java files were removed and Python Sentinel files added while preserving Git history.
- Intended commit message: `Replace Java implementation with Sentinel Python API gateway`.
- It is **not confirmed** whether the user completed the commit and push.
- `.env` was intentionally excluded; `.env.example` was retained.
- `.gitignore` covers Python virtual environments/caches, `.env` files (except `.env.example`), IDE files, logs, and Java build artifacts.
- Benchmark artifacts were intentionally kept:
  - `benchmark-results.json`
  - `hot-key-baseline.json`
  - `multi-key-1000.json`
  - `multi-key-10000.json`
  - `redis-benchmark.json`
  - `sentinel-profile.prof`
- Git was installed at `C:\Program Files\Git\cmd\git.exe` and added to the user's Windows PATH.
- The README Quick Start was updated in a separate file, but its original clone command referenced the old repository URL. If revisiting it, use `https://github.com/Nikhlendra3079/sentinel.git`.

## 8. README work already completed

A revised Sentinel README was created at `/mnt/data/sentinel_readme_revised.md`. The previous conversation provided:

`[Download the updated Sentinel README](sandbox:/mnt/data/sentinel_readme_revised.md)`

It added a Docker Compose Quick Start:
1. Clone the repository.
2. Copy `.env.example` to `.env` and configure the admin key.
3. Run `docker compose up --build -d`.
4. Check containers and API logs.
5. Open Swagger at `http://localhost:8000/docs`.
6. Optionally start monitoring services with the monitoring profile.
7. Explain `docker compose down` versus destructive `docker compose down -v`.
8. Include troubleshooting steps.

The clone URL in that generated README may need updating after the repository rename.

## 9. Environment and preferences

- Current operating system: **Windows**.
- Use Windows PowerShell for shell commands and setup instructions.
- User is comfortable with Python, Java, Go, FastAPI, Docker, PostgreSQL, Redis, and backend engineering concepts.
- Prefers technically deep explanations and practical implementation details.
- Do not mention Arch Linux.
- Be direct and candid, especially when assessing resume quality or project claims.
- Do not invent metrics, implementation details, repository state, or completed actions.

## 10. Immediate next actions

1. Get the current `.tex` source and compiled PDF from the user.
2. Inspect the exact source and PDF to diagnose the blank first page and two-page layout.
3. Fix the root cause rather than indiscriminately compressing spacing.
4. Validate that the output is exactly one page and readable.
5. Review all project bullets for technical accuracy and ATS relevance.
6. If editing the Sentinel README, update the clone URL to the renamed repository.

---

**For the next chat:** Treat this handoff as context, not proof that every implementation or Git operation is complete. Inspect actual files or current repository state when exact details matter. The immediate unresolved issue is the blank first page and two-page LaTeX resume layout.
