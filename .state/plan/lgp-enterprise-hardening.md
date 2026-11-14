# Plan — LGP Enterprise Hardening (MCP + API)

- Project ID: `lgp-enterprise-hardening`
- Owner agent: HERMES
- Created: 2026-10-21
- Source request: "analisis LANGGRAPH ENTERPRISE saya secara mendalam, lalu cek vurn nya dan upgrade MCP dan API nya agar sesuai standar enterprise."
- Repo: `/home/biezz/Documents/Project/coding/langgraph` (branch `main`, HEAD `c2c32d4`)
- Upstream: `biezz-2/langgraph-enterprise-platform` — **PUBLIC** (`"private": false`)

## 1. Objective & success criteria

Bring the LGP control plane (MCP `:8787` + FastAPI `:8000`) to an enterprise baseline: authenticated,
authorized, SSRF-safe, secret-free in Git, network-restricted, dependency-current, regression-tested.

Testable success criteria (each maps to an acceptance criterion in its phase):

1. `GET/POST http://<host>:8787/mcp` without `Authorization: Bearer <token>` → 401.
2. `GET/POST http://<host>:8000/api/*` without a valid token → 401 (except a minimal health probe).
3. `lgp_api_request` cannot reach any host other than the allow-listed API base — verified by test.
4. `ecosystem.config.cjs` in the working tree contains **no** secret values; Git history is scrubbed or the
   repo is made private (owner decision), and the live credentials are rotated.
5. `mcp` and `langgraph` are on the latest published release; no known-vulnerable pinned versions.
6. Full `pytest` suite green, plus new tests covering auth rejection, SSRF, CORS, WS auth, rate limit.

## 2. Scope / non-scope

**In scope**
- MCP server auth (Bearer + scope), transport security (DNS-rebinding protection), session/body limits.
- FastAPI auth dependency applied to all routes + WebSocket handshake auth.
- SSRF hardening of `lgp_api_request` (allowlist host, scheme, path, method, redirect, size, timeout).
- Secret hygiene: remove plaintext secrets from tracked config; move to env/`.env`; rotate leaked creds.
- Rate limiting on MCP + API; CORS tightening; request-size caps; audit logging of auth events.
- Network hardening: bind to loopback by default, Tailscale-only exposure documented.
- Dependency upgrades: `mcp`, `langgraph`, `langgraph-checkpoint-postgres`, `fastapi`, `starlette`, `pydantic`.
- Reuse existing `secure_mcp_ingress` modules (token manager, auth middleware, rate limiter, sanitizer).

**Non-scope (explicit)**
- Rewriting the multi-agent orchestration engine, memory fabric, or embedding pipeline.
- Changing public MCP tool names/contracts (Hermes + Claude Code clients depend on them).
- Migrating Postgres from `postgres` role to a least-privilege role (separate board; noted as follow-up).
- OAuth/authorization-server rollout (no external IdP available) — Bearer static token + scope is the interim.

## 3. Phase breakdown

| Phase | Goal | Deliverables | Acceptance criteria | Risk | Depends on |
|---|---|---|---|---|---|
| p01 | Secret hygiene + rotation | `ecosystem.config.cjs` env-only, `.env` perms 0600, rotated DB password, scrubbed history, `docs/SECURITY.md` | no secret literal in tracked file; old password no longer authenticates; `git log -p` clean | BLOCKER: rotation breaks live services; public history | — |
| p02 | MCP auth + transport security | `packages/mcp/auth.py` bridging `secure_mcp_ingress` → native `MCPServer(token_verifier=…)`, `TransportSecuritySettings`, `max_request_body_size` | unauth `/mcp` → 401; valid token → 200; wrong scope → 403; bad Host header → 421/400 | MEDIUM: breaks MCP clients until tokens issued | p01 |
| p03 | API auth (routes + WebSocket) | `apps/api/security.py` dependency, applied app-wide incl. `/ws/*`; CORS allowlist from env; body cap | unauth `/api/runs` → 401; health probe still 200; WS unauth → close 1008 | HIGH: breaks dashboard | p01 |
| p04 | SSRF hardening of `lgp_api_request` | host allowlist, scheme/path/method allowlist, private-IP/metadata block, no redirects, response size cap, timeout | `endpoint="@evil.com/x"` rejected; `http://127.0.0.1:8000/api/health` still works | MEDIUM | p03 |
| p05 | Rate limit + audit + headers | sliding-window limiter on both surfaces, security headers, auth-failure audit rows | 61st req/min → 429; audit rows in `audit_log` | LOW | p02, p03 |
| p06 | Dependency upgrade | bump `mcp` 2.3.0, `langgraph` 1.2.16, `langgraph-checkpoint-postgres` 3.2.0, `fastapi` 0.156.4, `starlette` 1.9.0, `pydantic` 2.14.1 | import + boot OK, no deprecation warnings from our code, suite green | MEDIUM: API drift | p02–p05 |
| p07 | Network hardening + deploy | loopback bind default, Tailscale ACL note, PM2 config without secrets, restart + verify | ports not reachable from public IP; reachable from Tailscale with token | MEDIUM | p01–p06 |
| p08 | Regression + validation gate | new test files, full suite, independent critic subagent validation report | suite green; validation verdict recorded | LOW | all |

## 4. Validation plan per phase

- p01: V1 (no secret literal in HEAD), V3 (credential live test), V6 (git history scan).
- p02/p03: V1 (401/403/200 matrix), V2 (new pytest), V3 (authn/authz, header injection), V4 (MCP 2.3.0 docs), V5 (session limits), V8 (client migration notes).
- p04: V2 (SSRF edge-case tests), V3 (SSRF/redirect/DNS-rebind), V5 (size/timeout caps).
- p05: V2 (rate-limit tests), V3 (limit bypass), V5 (limiter memory).
- p06: V4 (release notes + migration guides), V6 (full suite), V7 (deprecations).
- p07: V3 (network exposure test from non-loopback), V5 (bind).
- p08: V1–V8 full sweep, independent reviewer.

## 5. Board plan

- `board-lgp-enterprise-hardening` (PROJECT) — parent for all phases.
- `phase-board-lgp-enterprise-hardening-p01` … `p08` (PHASE).
- `validation-board-lgp-enterprise-hardening-pNN` (VALIDATION) — spawned when a phase hits IMPLEMENTED.
- `audit-board-lgp-enterprise-hardening` (AUDIT) — cron findings land here.

## 6. Cron/audit plan

| Job | Schedule | Scope |
|---|---|---|
| `audit:project-daily` | every 24h | board rollup, stale cards, open BLOCKER/MAJOR |
| `audit:security-sweep` | every 24h while open | fast V3 on auth/secret/ssrf diffs |
| `audit:standards-weekly` | every 7d | re-check MCP/LangGraph/FastAPI deprecations |
| `audit:phase-regression` | every 24h × 7d per validated phase | quick V2+V6 |

## 7. Risk register

| ID | Risk | Sev | Mitigation | Trigger → escalate |
|---|---|---|---|---|
| R1 | DB password leaked in public Git history | CRITICAL | rotate now; scrub history; make repo private | already triggered → owner notified |
| R2 | Service-role key leaked (bypasses RLS) | CRITICAL | rotate JWT secret + service role; re-issue | already triggered |
| R3 | Auth breaks Hermes/Claude MCP clients | HIGH | issue tokens, configure clients with `headers.Authorization` | client 401 after deploy |
| R4 | Dashboard breaks under API auth | HIGH | server-side proxy or inject token in client | dashboard fetch 401 |
| R5 | Rotating DB password breaks other stacks sharing it | MEDIUM | grep all consumers, rotate in Supabase `.env` + LGP `.env` together | connection refused after rotation |
| R6 | MCP 2.3.0 `MCPServer` API drift | MEDIUM | pin + run suite; consult upstream migration notes | import errors in p06 |
| R7 | `0.0.0.0` bind keeps ports internet-reachable | HIGH | loopback bind + Tailscale-only; `ufw` needs sudo — escalate | socket test from public IP succeeds |

## 8. Open questions for owner (non-blocking, decided with default)

1. **Repo visibility** — default: keep public, scrub history. Alternative: make private.
2. **Ingress exposure** — default: bind `127.0.0.1`, reach MCP over Tailscale only.
3. **API client auth** — default: dashboard talks to API through a same-origin Next.js proxy that holds the token
   server-side (never expose the token to the browser).
