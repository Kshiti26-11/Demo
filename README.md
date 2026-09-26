<<<<<<< HEAD
# SyncSnitch

**An autonomous, human-gated contract-drift agent built with IBM Bob 2.0.**
When an upstream PR changes a REST payload, a gRPC definition or a database migration, SyncSnitch:
- finds every downstream usage it breaks, loud or silent;
- has Bob's subagents write a backward-compatible adapter in the consumer;
- proves it with Docker mock containers against the old **and** new contract;
- opens a **draft companion PR** after a human approves.

*IBM Bob 2.0 Hackathon (lablab.ai), track: Release, Deployment & Application Maintenance. Formerly "SchemaShift".*

## Start here
| Doc | For |
|---|---|
| **[WORK.md](WORK.md)** | **the team's prompt book**: setup, then paste-ready IBM Bob prompts per person, in order (40 Bobcoins total) |
| [WORKFLOW.md](WORKFLOW.md) | what happens end to end, the 48-hour timeline, the demo-day flow, troubleshooting |
| [ARCHITECTURE.md](ARCHITECTURE.md) | components, contracts v1→v2, the break matrix, containers, CI, website, validation |
| [FEATURES.md](FEATURES.md) | every feature, the Bob 2.0 features used and where, non-goals, judging map |

## Repos
| Repo | Role |
|---|---|
| `kshiti26-11/demo` (this repo, cloned locally as `syncsnitch/`) | the SyncSnitch agent: engine, verifier, Bob layer, CI, demo website, `bob_sessions/` |
| `kshiti26-11/orders-service` | upstream demo service (contract owner) |
| `kshiti26-11/billing-service` | downstream demo service (contract consumer) |

## What's in this repo right now
- `contracts/reference/`: the frozen, validated v1/v2 contracts (OpenAPI, protobuf, Alembic, seed, RFC `.docx`).
- `templates/`: validated boilerplate for the service repos and the Bob layer.
- `verify/`, `.github/workflows/`, `scripts/`: the frozen container topology, CI and helper scripts. All are linted with `actionlint` and `shellcheck`.
- `pyproject.toml` + `uv.lock`: shared, frozen dependencies. Run `uv sync --frozen`.
- `bob_sessions/`: IBM Bob evidence (exported task histories and screenshots).

The engine, verifier, Bob modes and website get built by the team with IBM Bob, following WORK.md.
