# SyncSnitch — Features

Everything SyncSnitch does, who builds it (the WORK.md prompt), and how it's shown to judges.
Status **Core** means it's in the submission. **Stretch** means only if coins and time allow.
- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Workflow: [WORKFLOW.md](WORKFLOW.md)
- Prompts: [WORK.md](WORK.md)

---

## 1. Product features

### Detection: what changed upstream
| # | Feature | Status | Built in | Shown in the demo |
|---|---|---|---|---|
| F1 | **REST/OpenAPI drift**: removed or added properties, type changes, enum values removed or added, schemas added or removed (with `$ref` resolution) | Core | P3-1 | PR #1 comment, S1 output, website replay |
| F2 | **gRPC/protobuf drift** by **field and enum number**: removed, added, renamed or retyped fields; enum renames flagged "wire-compatible, source-breaking" | Core | P3-1 | same |
| F3 | **DB migration drift** from Alembic `upgrade()`: columns added, dropped or renamed; value renames from `UPDATE … SET x='NEW' WHERE x='OLD'` | Core | P3-1 | same |
| F4 | **Breaking vs non-breaking classification** on every change, with stable change IDs (`surface:location:kind`) | Core | P3-1 | drift table |

### Ripple mapping: who breaks, and how
| # | Feature | Status | Built in | Shown in the demo |
|---|---|---|---|---|
| F5 | **Consumer tracing**: Python AST (subscripts, `.get`, attributes, Pydantic fields, keywords, literals), SQL files, vendored `.proto`, JSON fixtures | Core | P3-1 | S2 output, try-it |
| F6 | **Endpoint mapping**: each usage is mapped to the FastAPI route it breaks via a 3-hop reference graph | Core | P3-1 | impact map on the website |
| F7 | **Loud vs silent classification** by the 🔎 Tracer subagent, including the *hidden* bug a human would miss (the `PENDING` rename) | Core | P3-2 + P3-3 | `impact.json`, video |
| F8 | **Document understanding**: the Tracer reads the upstream team's RFC `.docx` and quotes its rollout and migration guidance in the companion PR | Core | P3-2 + P3-3 | PR body "Migration notes" |

### Generation: the fix
| # | Feature | Status | Built in | Shown in the demo |
|---|---|---|---|---|
| F9 | **Tolerant-reader REST adapter** (`OrderView`) that accepts v1 and v2 payloads | Core | 🛠️ Transformer in P3-3 | diff in the companion PR |
| F10 | **Consumer-compat gRPC client**: vendored v2 proto with the removed fields re-declared as deprecated, and regenerated stubs. One client reads both server versions | Core | same | diff + V3/V4 |
| F11 | **Version-aware SQL**: the report picks the v1 or v2 query from `alembic_version` | Core | same | diff + V3/V4 |
| F12 | **Mocks and fixtures updated**: v2 fixture twins, tests parametrised over v1 and v2 | Core | same | V2 check |
| F13 | **Minimal diff, public API unchanged**, enforced by rules + the V6 scope check | Core | same | V6 |

### Verification: proving it
| # | Feature | Status | Built in | Shown in the demo |
|---|---|---|---|---|
| F14 | **Docker mock containers**: Postgres + upstream container (REST + gRPC) + **Prism contract mock** + consumer test runner, run once per contract version | Core | frozen compose + P4-1 | S5, `VERIFICATION.md` |
| F15 | **Backward and forward compatibility proof**: the same integration tests must pass against v1 (V3) **and** v2 (V4) | Core | P2-1 tests + P4-1 | before/after table |
| F16 | **Business-value assertions**, so silent breaks fail: amount 1999, unpaid gets 409, revenue rows | Core | template tests | V4 red before, green after |
| F17 | **Six deterministic checks V1–V6**; the model never overrides a failing check | Core | P4-1 | verification table |
| F18 | **✅ Verifier subagent**: verdict + concrete fix instructions; max 1 automatic fix loop | Core | P3-2 + P3-3 | `verdict.json` |

### Delivery: human-gated
| # | Feature | Status | Built in | Shown in the demo |
|---|---|---|---|---|
| F19 | **Human approval gate**: approve / show diff / request changes / abort | Core | skill S7 | video |
| F20 | **Draft companion PR** with a full body: drift table, impact, verification, migration notes, rollout plan, evidence | Core | P3-1 report + `open_companion_pr.sh` | companion PR page |
| F21 | **Upstream ↔ companion linking**: SyncSnitch comments on PR #1 with the companion PR link | Core | `open_companion_pr.sh` | PR #1 |
| F22 | **Companion-PR CI**: `contract-verify` re-runs the containers in GitHub Actions | Core | frozen workflows | green check |

### Automation and safety
| # | Feature | Status | Built in | Shown in the demo |
|---|---|---|---|---|
| F23 | **Automatic drift comment** on any upstream PR that touches contracts or migrations (0 coins) | Core | frozen workflows + P3-1 | PR #1 comment |
| F24 | **Write-guard hook**: blocks writes to the upstream repo and to secrets during a run | Core | P3-2 (hooks) | screenshot of a blocked write |
| F25 | **Evidence logger hook**: per-device JSONL of every Bob tool call | Core | P3-2 (hooks) | `bob_sessions/raw/` |
| F26 | **Idempotent demo reset** (`reset_demo.sh`, dry run by default) | Core | frozen script | — |

### Demo website (Vercel)
| # | Feature | Status | Built in | Shown in the demo |
|---|---|---|---|---|
| F27 | **Run replay dashboard**: S1–S9 timeline, drift by surface, Mermaid impact map, diff2html diff, V1–V6 table, links | Core | P4-2 | website |
| F28 | **Live contract matrix**: billing before/after × orders v1/v2, real REST calls in-process | Core | P4-3 | website |
| F29 | **Try-it sandbox**: 4 prebaked contract changes, live detect + trace in under 1 s | Core (first to cut in lean mode) | P4-3 | website |
| F30 | **Health monitoring**: cron smoke test that opens an issue if the demo URL breaks | Core | frozen workflow + P4-3 | — |

### Stretch
| # | Feature | Status | Built in | Shown in the demo |
|---|---|---|---|---|
| F31 | **GitHub MCP path** for PR creation (disabled by default to save tokens) | Stretch | P3-2 | optional in the recorded run |
| F32 | **Headless runs**: Bob Shell `bob -p "/syncsnitch …"` in CI, with a GitHub Environment approval as the gate | Stretch / roadmap | — | roadmap slide |
| F33 | **Fan-out to N consumers**; TypeScript/Java tracers; Avro/GraphQL; cleanup PR after rollout | Roadmap | — | roadmap slide |

---

## 2. IBM Bob 2.0 features used, and where the evidence is

| Bob feature | How SyncSnitch uses it | Where | Evidence in `bob_sessions/` |
|---|---|---|---|
| **Advanced / Code mode (agent)** | builds every service, the engine, the verifier and the site from spec-exact prompts | P1-1 … P4-3 | `exports/P*-*.md` |
| **Ask mode** (read-only) | cross-repo blast-radius analysis: loud vs silent | P2-2 | `exports/P2-2-*.md` |
| **Custom modes** | 🕵️ SyncSnitch, 🔎 Tracer, 🛠️ Transformer, ✅ Verifier | P3-2 | `screenshots/P3-2-1-modes.png` |
| **Subagents** (isolated contexts, parallel `explore`) | the three SyncSnitch subagents; the Tracer fans out explorers | P3-3 | `exports/P3-3-hero-run.md` |
| **Workflows** (deterministic + AI steps + human gate) | the S0–S9 skill: 5 deterministic steps cost 0 tokens | P3-2, P3-3 | same |
| **Parallel tool calling** | Tracer file reads; batched file writes in every build prompt | all | exports |
| **Document understanding** (.docx) | the Tracer reads RFC-042 `orders-v2-change-proposal.docx` | P3-3 (S3) | hero export |
| **Skills + slash commands** | `.bob/skills/syncsnitch-workflow`, `/syncsnitch`, `/evidence` | P3-2 | mode/command screenshots |
| **Rules** | guardrails + tolerant-reader rules | P3-2 | — |
| **Lifecycle hooks** | PreToolUse write-guard, PostToolUse/Stop evidence logger | P3-2 | `raw/*.jsonl` |
| **MCP** (optional) | GitHub server for PRs, off by default | P3-2 | — |
| **Multi-root workspace** | Bob sees all three repos at once | setup | — |
| **Bobalytics** | coin ledger: the whole project within 40 Bobcoins | all | `screenshots/bobalytics-*.png` |

---

## 3. Explicit non-goals (so nobody builds them)
- Auto-merging anything. SyncSnitch only opens **draft** PRs.
- More than one consumer service in the demo (fan-out is roadmap).
- Non-Python consumers, GraphQL or Avro (roadmap).
- Running Bob unattended in CI (stretch F32; it costs coins per PR).
- watsonx.ai in the product. It's optional for copywriting only, if the rules allow.

---

## 4. Judging criteria map
| Criterion | Where SyncSnitch scores |
|---|---|
| **Meaningful use of IBM Bob** (mandatory) | 12+ Bob features, each with an export or screenshot (§2); Bob built all product code; subagents + workflow + human gate in the hero run |
| **Originality** | Detection tools exist. **Autonomous, verified, cross-repo companion PRs** don't. Includes the consumer-compat proto trick and the loud-vs-silent analysis |
| **Business value** | Prevents production incidents from contract drift (including the silent ones); removes cross-team coordination toil; cost-aware design (deterministic steps, 40-coin budget) |
| **Presentation** | Live website (replay, matrix, try-it), a 3–4 min video of the real hero run, a clean repo with ARCHITECTURE/WORKFLOW/FEATURES docs |
