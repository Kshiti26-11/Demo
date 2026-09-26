# SyncSnitch

**An autonomous, human-gated contract-drift agent built with IBM Bob 2.0.**
When an upstream PR changes a REST payload, a gRPC definition or a database migration, SyncSnitch:
- finds every downstream usage it breaks, loud or silent;
- has Bob's subagents write a backward-compatible adapter in the consumer;
- proves it with Docker mock containers against the old **and** new contract;
- opens a **draft companion PR** after a human approves.

*IBM Bob 2.0 Hackathon (lablab.ai), track: Release, Deployment & Application Maintenance. Formerly "SchemaShift".*

## Try it: paste a GitHub link, press "Run 3 Agents"
On the home page paste a repo link (or a `/tree/<branch>`, `/pull/<n>` or `/compare/<a>...<b>` link) and press Enter.
The live run page `/live/<run_id>` opens: the **SyncSnitch Multi-Agent Orchestrator** with the 3 subagent cards, a Bobcoin
meter and the **Live Agent Log Stream**. Nothing more to paste anywhere: the site is the orchestrator.

| Step | Who | What |
|---|---|---|
| S0–S2 | site (0 Bobcoins) | find the upstream (`contracts/openapi.yaml` / `*.proto`) and the consumer, detect the drift, trace every usage |
| prepare | site | clone the repo into `.syncsnitch/work/<run_id>`, branch `syncsnitch/<run_id>`, copy the upstream change proposal |
| S3 | **agent** Tracer | → `impact.json`, every broken endpoint, loud vs silent |
| S4 | **agent** Transformer | → tolerant-reader commits on the branch, unit tests green |
| S5 | site (0 Bobcoins) | `syncsnitch verify`: unit tests, v2 fixtures, Docker mock containers vs v1 and v2 (when Docker runs), diff scope |
| S6 | **agent** Verifier | → `verdict.json`; if red, one automatic fix round (S4 → S5 → S6) |
| S7 | **you** | Approve or Reject on the run page (a failing check always means red; nothing is published from red) |
| S8–S9 | site (0 Bobcoins) | push the branch, open a **DRAFT** companion PR, write `web/runs/<run_id>.json` (replay page) |

The three agents are the custom modes in `.bob/custom_modes.yaml` (role, instructions and `.bob/rules*`), run on one of two
engines; their live output is the log stream:
- **IBM Bob**: `bob run --mode <agent>` (headless IBM Bob Shell). Budget per run in Bobcoins (`SYNCSNITCH_BOB_BUDGET`, default 5).
- **Gemini** (free tier: Google AI Studio key, OpenAI-compatible endpoint, `SYNCSNITCH_GEMINI_MODEL`, default
  `gemini-3.8-flash`; free-tier prompts may be used by Google), **Grok** (xAI Responses API, `SYNCSNITCH_GROK_MODEL`,
  default `grok-4.7`) or **Claude** (Anthropic Messages API, `SYNCSNITCH_CLAUDE_MODEL`, default `claude-opus-5-5`):
  the same definitions through `web/webapp/llm_agent.py` with
  sandboxed tools (read anywhere in the workspace except `.env`/`.git`; the Tracer writes only `impact.json`, the Verifier
  only `verdict.json`, the Transformer only the consumer folder; commands: `uv run pytest`, `regen_stubs.py`, git; API keys
  never reach the commands). Budget per run in tokens (`SYNCSNITCH_TOKEN_BUDGET`, default 3,000,000).

`SYNCSNITCH_AGENT_BACKEND=bob|gemini|grok|claude` picks the engine (the setup scripts set it; `auto` = the first of
IBM Bob, Gemini, Grok, Claude that is set up).
The page names the engine that ran each agent, and commits carry its trailer. A stopped run can be resumed.

**One-time setup** (the page shows what is missing, with the command), then start the site:
```bash
bash scripts/gemini_setup.sh   # Gemini (free tier): saves your Google AI Studio key in .env.local (hidden, gitignored)
bash scripts/grok_setup.sh     # or Grok: the same with an xAI API key
bash scripts/claude_setup.sh   # or Claude: the same with an Anthropic API key
bash scripts/bob_setup.sh      # or IBM Bob: installs Bob Shell, saves your Bob API key, license
bash scripts/run_site.sh       # http://localhost:8000
```
Docker Desktop running = V3–V5 run in mock containers; without it they are reported as skipped, never as passed.
On Vercel the page runs S1–S2 only (a serverless function cannot host a Bob session) and points to the local runner.
The Repo Analyzer (`/analyze`) shows the full S1–S2 tables and lets you pick upstream/consumer/base/head by hand. The old
manual path still works too: `/syncsnitch <link>` in a Bob IDE task (shown on the page when this machine is not set up).

## Start here
| Doc | For |
|---|---|
| **[WORK.md](WORK.md)** | **the team's prompt book**: setup, then paste-ready IBM Bob prompts per person, in order (40 Bobcoins total) |
| [WORKFLOW.md](WORKFLOW.md) | what happens end to end, the 48-hour timeline, the demo-day flow, troubleshooting |
| [ARCHITECTURE.md](ARCHITECTURE.md) | components, contracts v1→v2, the break matrix, containers, CI, website, validation |
| [FEATURES.md](FEATURES.md) | every feature, the Bob 2.0 features used and where, non-goals, judging map |

## Layout
The demo services live in this repo (a monorepo) as well as in the planned separate repos:

| Path / repo | Role |
|---|---|
| `kshiti26-11/demo` (this repo, cloned locally as `syncsnitch/`) | the SyncSnitch agent: engine, verifier, Bob layer, CI, demo website, `bob_sessions/` |
| `orders-service/` (planned: `kshiti26-11/orders-service`) | upstream demo service (contract owner); v1 = commit `15f95af`, v2 = branch `feat/orders-v2` |
| `billing-service/` (planned: `kshiti26-11/billing-service`) | downstream demo service (contract consumer) |

Every `syncsnitch` command accepts either a repository root or a monorepo sub-folder, e.g. the H-1 dry run here:
```bash
uv run syncsnitch detect --upstream orders-service --base 15f95af --head feat/orders-v2 --run-id dry-1
uv run syncsnitch trace  --run-id dry-1 --consumer billing-service
uv run syncsnitch verify --run-id dry-1 --upstream orders-service --base 15f95af --head feat/orders-v2 --consumer billing-service --consumer-base branch1
```

## What's in this repo
- `syncsnitch/`: the deterministic engine (`detect`, `trace`, `report`, `run-artifact`, `verify`).
- `.bob/`: the Bob layer (4 modes, the S0–S9 skill, `/syncsnitch`, rules, hooks).
- `web/`: the demo website (run replay, live contract matrix, try-it sandbox, paste-a-repo analysis).
- `contracts/reference/`: the frozen, validated v1/v2 contracts (OpenAPI, protobuf, Alembic, seed, RFC `.docx`).
- `templates/`: validated boilerplate for the service repos and the Bob layer.
- `verify/`, `.github/workflows/`, `scripts/`: container topology, CI and helper scripts, linted with `actionlint` and `shellcheck`.
- `pyproject.toml` + `uv.lock`: shared, frozen dependencies. Run `uv sync --frozen`.
- `bob_sessions/`: IBM Bob evidence (exported task histories and screenshots).

## Provenance
The planning docs, reference contracts and shared scaffolding were prepared with Claude Code. The product code was built by
**IBM Bob** from the prompts in WORK.md, and every Bob task is exported to `bob_sessions/`. The 2026-09-26 integration fixes
(CLI flags, monorepo support, endpoint tracing, report/run-artifact, website status display), the paste-a-repo
analysis page and the local agent runner (`web/webapp/agents.py`, `web/webapp/llm_agent.py`) were written with
Claude Code. The three agents run on IBM Bob or, when chosen, on Gemini, Grok or Claude; every run records which
engine it used.
