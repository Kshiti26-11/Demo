# WORK.md — the SyncSnitch prompt book

> **4 people · 1 shared IBM Bob account · 40 Bobcoins in total · every prompt is paste-ready and self-contained.**
> Each person pastes **only their own prompts**, in the order below, into **their own** Bob on **their own** device.
> Nobody edits a file that belongs to someone else, so nobody ever gets a merge conflict.

- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- End-to-end workflow and timeline: [WORKFLOW.md](WORKFLOW.md)
- Feature list: [FEATURES.md](FEATURES.md)

---

## 0. Read me first (2 minutes, 0 coins)

**What we are building.** SyncSnitch is an autonomous, human-gated contract-drift agent.
1. An upstream team opens a PR that changes a contract: REST payload (OpenAPI), gRPC (protobuf) or a DB migration.
2. SyncSnitch detects the drift and traces every usage in the downstream repo.
3. Bob's 3 subagents generate a backward-compatible adapter in that repo.
4. SyncSnitch proves the adapter with Docker mock containers against the old **and** new contract.
5. After a human approves, it opens a **draft companion PR** in the downstream repo.

**The demo repos:**
- `orders-service`, upstream, owned by Person 1
- `billing-service`, downstream, owned by Person 2
- this repo (`kshiti26-11/demo`), the SyncSnitch agent itself, owned by Persons 3 and 4

**Rules of this book:**
1. **Run prompts in the order of §2.** Within a person, strictly in order. Different people run in parallel.
2. **One prompt = one new Bob task** (click "New task" first). A fresh context costs fewer coins.
3. **Paste the whole prompt block** unchanged (use the copy button on the grey block).
4. **Mode:** use **Advanced** unless the prompt header says otherwise. Keep **all MCP servers disabled**. Don't run `/init`.
5. **After each prompt:** export the task and commit the evidence (snippet under each prompt). This is a hackathon requirement.
6. **Budget:** if a prompt blows past its budget, stop and tell Person 3. The coin ledger is in §6.
7. **Never** edit `pyproject.toml`, `uv.lock`, `.github/`, `templates/`, `contracts/reference/`, `verify/` or `scripts/*.sh` in this repo. They're frozen, validated scaffolding.

**Who is who:**

| Person | Owns | Prompts |
|---|---|---|
| **Person 1**, Upstream | the whole `orders-service` repo | P1-1, P1-2 |
| **Person 2**, Downstream | the whole `billing-service` repo | P2-1, P2-2 |
| **Person 3**, Agent + Bob lead | engine + Bob layer in this repo; runs the hero demo | P3-1, P3-2, H-1, P3-3, (P3-4) |
| **Person 4**, Verify + CI + site | verifier + demo website in this repo; deploys | P4-1, P4-2, P4-3, H-2 |

---

## 1. Setup (humans only, 0 coins) — finish before any prompt

### 1.1 Account owner of `kshiti26-11` (one person, ~5 min)
1. Merge the PR that added this file (`branch2` → `main`). **All prompts read files from `main`.**
2. `kshiti26-11/demo` → Settings → General → **Change visibility → Public**. Cross-repo GitHub Actions and the submission both need it. **Do not rename the repo**, because the workflows reference `kshiti26-11/demo`.
3. Create two **empty, public** repos with no README, .gitignore or license: `kshiti26-11/orders-service` and `kshiti26-11/billing-service`.
4. On all 3 repos: Settings → Collaborators → add the other 3 teammates with **Write** access.

### 1.2 Everyone: tools (~10 min)
- **OS:** macOS or Linux. On Windows, use **WSL2 (Ubuntu)** for everything, or set Bob's terminal to **Git Bash**. Every command here is bash.
- **git**: set your identity with `git config --global user.name "…"` and `git config --global user.email "…"`.
- **uv**: `curl -LsSf https://astral.sh/uv/install.sh | sh`, then `uv python install 3.12`.
- **Docker Desktop**, running. **Required for Persons 3 and 4**, recommended for 1 and 2.
- **GitHub CLI**, then `gh auth login`. **Required for Persons 1 and 3.**

### 1.3 Everyone: exact folder layout (the prompts depend on it)
```bash
mkdir -p ~/hack && cd ~/hack
git clone https://github.com/kshiti26-11/demo.git syncsnitch     # folder name MUST be "syncsnitch"
git clone https://github.com/kshiti26-11/orders-service.git       # "empty repository" warning is fine
git clone https://github.com/kshiti26-11/billing-service.git      # "empty repository" warning is fine
cd ~/hack/syncsnitch && uv sync --frozen
```

### 1.4 Everyone: Bob settings (same shared account on every device)
- Sign in to IBM Bob with the team account.
- Settings → task history retention = **keep all**. We need the exports.
- Auto-approve: reads and writes inside the workspace, plus commands (`uv`, `git`, `cp`, `mkdir`, `docker`, `gh`). This avoids stalls; approvals are free but slow.
- **File → Open Workspace from File → `~/hack/syncsnitch/syncsnitch.code-workspace`**. That's a multi-root workspace with all 3 repos.
- All MCP servers **off**, since each enabled server costs tokens on every request.

### 1.5 Person 3: coin ledger baseline
Open **Bobalytics** and take a screenshot → `~/hack/syncsnitch/bob_sessions/screenshots/bobalytics-0-start.png`. Then start the ledger in §6.

### 1.6 Person 2: rules check (step 0, ~10 min)
Read the lablab IBM Bob 2.0 hackathon rules and submission page. Post three answers in the team chat:
- (a) Are AI tools other than Bob allowed for docs and media?
- (b) What's the video length limit?
- (c) What are the exact submission fields?

---

## 2. Order of prompts (the whole project, in order)

| Round | ID | Who | Start when… | What Bob builds | Budget |
|---|---|---|---|---|---|
| 1 | **P1-1** | 1 | setup done | orders-service v1: REST + gRPC + DB, Docker image, tests, CI | 3 |
| 1 | **P2-1** | 2 | setup done | billing-service v1 consumer: 3 endpoints, gRPC stubs, SQL report, tests, CI | 4 |
| 1 | **P3-1** | 3 | setup done | SyncSnitch engine: `detect` (REST, gRPC, DB), `trace`, `report`, `run-artifact` + tests | 5 |
| 1 | **P4-1** | 4 | setup done | `syncsnitch verify`: git worktrees, checks V1–V6, Docker mock containers, JUnit parsing + tests | 4 |
| 2 | **P1-2** | 1 | P1-1 pushed | branch `feat/orders-v2` (breaking v2 on all 3 surfaces) + **PR #1** (never merge it) | 2 |
| 2 | **P2-2** | 2 | P2-1 pushed | *(Ask mode, optional)* Bob explains, across repos, what breaks and why: loud vs silent | 1 |
| 2 | **P3-2** | 3 | P3-1 pushed | install the Bob layer: 4 custom modes, the S0–S9 workflow skill, `/syncsnitch`, rules, hooks | 1 |
| 2 | **P4-2** | 4 | P4-1 pushed | demo website: run-replay dashboard (FastAPI + Jinja2), Vercel-ready + tests | 3 |
| 3 | **H-1** | 3 | P1-2, P2-1, P3-1, P4-1 pushed | *(human, 0 coins)* deterministic dry run: proves v1 ✅ / v2 ❌ before any fix | 0 |
| 3 | **P4-3** | 4 | P1-2, P2-1, P3-1, P4-2 pushed | live contract matrix + try-it sandbox + vendoring + Vercel deploy + smoke test | 3 |
| 4 | **P3-3** | 3 | everything above ✅ | **hero run** (screen-record it): `/syncsnitch <PR #1>` → verified **draft** companion PR | 6 |
| 5 | **H-2** | 4 | P3-3 done | *(human, 0 coins)* re-vendor "after" code, redeploy, smoke test | 0 |
| 6 | **F-n** | anyone | a check fails | fix-prompt template (§4), only when needed | reserve |
| 7 | **P3-4** | 3 | the end | *(optional)* final README + `bob_sessions` index; skip if coins are short | (2) |
| | | | | **planned 32 + reserve 8** | **40** |

**Calibration:** when Round 1 is done, Person 3 checks Bobalytics.
- **Under 20 coins spent:** carry on.
- **Over 20:** switch to **lean mode** (§5).

---

## 3. The prompts

### P1-1 · Person 1 · orders-service v1 (REST + gRPC + DB)
| Start when | Mode | Budget | You'll see at the end |
|---|---|---|---|
| Setup done | Advanced, new task | ≈3 coins | `N passed`, image `orders-service:v1` built, commit pushed to `main` |

````text
[SyncSnitch P1-1 · Person 1 · budget ≈3 Bobcoins]

CONTEXT
SyncSnitch is a contract-drift agent. You are building the UPSTREAM service "orders-service". It owns the Orders
contract on 3 surfaces: REST (OpenAPI), gRPC (protobuf) and DB (Alembic migrations). This prompt builds contract
v1 on branch main. (A later prompt, P1-2, makes the breaking v2 on another branch.)
Folders: ~/hack/syncsnitch = main repo, READ-ONLY for you (you only copy from it).
         ~/hack/orders-service = YOUR repo (empty clone of https://github.com/kshiti26-11/orders-service).

RULES (the whole team shares 40 Bobcoins - follow strictly)
1. Do not explore or search. Open only files named here. Never open files under ~/hack/syncsnitch.
2. Copy files with the cp commands below; never retype them.
3. Create several files per turn. Never print file contents back to me.
4. Run the ACCEPTANCE commands once at the end. If something fails, fix it at most 2 times, then STOP and report.
5. Final reply: at most 10 lines (what you built, test result, commit SHA).
6. Inside the package orders_service/ use RELATIVE imports only (for example: from .db import make_engine).
   rest.py, and everything it imports, must NEVER import grpc or orders_service.gen.

STEP 1 - copy templates and frozen contracts (run exactly):
cd ~/hack/orders-service
git symbolic-ref HEAD refs/heads/main
cp -r ../syncsnitch/templates/orders-service/. .
mkdir -p contracts migrations/versions orders_service tests
cp ../syncsnitch/contracts/reference/v1/openapi.yaml contracts/openapi.yaml
cp ../syncsnitch/contracts/reference/v1/orders.proto contracts/orders.proto
cp ../syncsnitch/contracts/reference/migrations/0001_create_orders.py migrations/versions/
cp ../syncsnitch/contracts/reference/seed.json orders_service/seed.json
uv sync
(The templates gave you pyproject.toml, alembic.ini, migrations/env.py, scripts/gen_proto.py, docker/entrypoint.sh,
Dockerfile, .dockerignore, .gitignore, .bobignore and .github/workflows/{ci,syncsnitch}.yml. Do not edit them.)

STEP 2 - create the package orders_service/ :
- __init__.py: empty.
- config.py: database_url() -> env DATABASE_URL, default "sqlite:///./orders.db"; grpc_port() -> int(env GRPC_PORT, default 50051).
- db.py: make_engine(url): if url starts with "sqlite" and contains ":memory:" use
  create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool), otherwise create_engine(url).
  make_sessionmaker(engine) -> sessionmaker(bind=engine, expire_on_commit=False).
- models.py: SQLAlchemy 2 "class Base(DeclarativeBase)" and "class Order(Base)", __tablename__ = "orders", columns
  exactly as migration 0001: order_id String(32) primary key, customer_name String(200), total_price Numeric(10, 2),
  status String(32), created_at DateTime(timezone=True).
- seed.py: seed(session): delete all orders, then insert the 4 rows from seed.json (same folder) with
  customer_name, total_price = Decimal(amount_minor) / 100, status = status_v1, created_at = the ISO time ("...Z") as
  UTC; commit. Under if __name__ == "__main__": seed the database at config.database_url().
- schemas.py: helper utc(dt) (naive -> replace(tzinfo=UTC), aware -> astimezone(UTC)). Pydantic model OrderOut:
  order_id: str, customer_name: str, total_price: float, status: str, created_at: datetime; classmethod
  from_row(row) with total_price=float(row.total_price) and created_at=utc(row.created_at).
  The JSON must look exactly like:
  {"order_id":"o-1001","customer_name":"Ada Lovelace","total_price":19.99,"status":"PAID","created_at":"2026-09-01T10:00:00Z"}
- rest.py: def create_app(database_url: str | None = None, *, init_schema: bool = False, seed: bool = False) -> FastAPI
  engine = make_engine(database_url or config.database_url()); if init_schema: Base.metadata.create_all(engine);
  Session = make_sessionmaker(engine); if seed: call seed() once; app = FastAPI(title="orders-service", version="1.0.0");
  keep Session on app.state. Routes (plain def, not async):
    GET /health -> {"status": "ok"}
    GET /orders -> list[OrderOut] sorted by order_id
    GET /orders/{order_id} -> OrderOut, or HTTP 404 with {"detail": "order not found"}
  No module-level app object (uvicorn starts it with --factory). No startup/lifespan events.
- grpc_server.py: import stubs with "from .gen import orders_pb2, orders_pb2_grpc".
  class OrderLookup(orders_pb2_grpc.OrderLookupServicer) with GetOrderSummary(request, context): load the row; if it is
  missing: context.abort(grpc.StatusCode.NOT_FOUND, "order not found"); otherwise return orders_pb2.OrderSummary(
  order_id=..., customer_name=..., total_price=float(row.total_price),
  status=orders_pb2.OrderStatus.Value("ORDER_STATUS_" + row.status)).
  def serve(port: int | None = None, db_url: str | None = None) -> grpc.Server: grpc.server(ThreadPoolExecutor(max_workers=8)),
  add_insecure_port(f"0.0.0.0:{port or grpc_port()}"), start(), return the server.
  Under if __name__ == "__main__": serve().wait_for_termination()  (the container runs: python -m orders_service.grpc_server;
  docker/entrypoint.sh also runs alembic upgrade head, python -m orders_service.seed and
  uvicorn orders_service.rest:create_app --factory --host 0.0.0.0 --port 8000).

STEP 3 - generate the gRPC stubs and the runtime requirements (run exactly):
uv run python scripts/gen_proto.py
uv export --no-dev --no-hashes -o requirements.txt

STEP 4 - tests/ (pytest; create an empty tests/__init__.py):
- test_rest.py: client = TestClient(create_app("sqlite+pysqlite:///:memory:", init_schema=True, seed=True)). Assert:
  /health == {"status": "ok"}; /orders ids == ["o-1001","o-1002","o-1003","o-1004"]; /orders/o-1001 equals the
  "paid" example value of GET /orders/{order_id} in contracts/openapi.yaml; /orders/o-1002 has status "PENDING";
  /orders/o-9999 -> 404; every order from /orders validates against the spec. Validate like this:
    spec = yaml.safe_load(open("contracts/openapi.yaml"))
    registry = Registry().with_resource("urn:spec", Resource.from_contents(spec, default_specification=DRAFT202012))
    Draft202012Validator({"$ref": "urn:spec#/components/schemas/Order"}, registry=registry).validate(order)
  (imports: from jsonschema import Draft202012Validator; from referencing import Registry, Resource;
   from referencing.jsonschema import DRAFT202012)
- test_grpc.py: url = f"sqlite:///{tmp_path}/o.db"; create_app(url, init_schema=True, seed=True); server = serve(port=<a free
  port>, db_url=url); GetOrderSummary(order_id="o-1001") -> total_price 19.99, customer_name "Ada Lovelace",
  status ORDER_STATUS_PAID; "o-9999" -> grpc.StatusCode.NOT_FOUND; finally server.stop(None).
- test_migrations.py: monkeypatch env DATABASE_URL = f"sqlite:///{tmp_path}/m.db";
  alembic.command.upgrade(alembic.config.Config("alembic.ini"), "head"); the columns of table "orders" ==
  {"order_id", "customer_name", "total_price", "status", "created_at"}.

STEP 5 - README.md (at most 15 lines): what the service is; the 3 contract files; tests: uv run pytest -q;
local run: uv run alembic upgrade head && uv run python -m orders_service.seed &&
uv run uvicorn orders_service.rest:create_app --factory --port 8000

ACCEPTANCE (run once):
uv run pytest -q                      -> expect all passed (at least 8 tests)
docker build -t orders-service:v1 .   -> only if Docker is running; otherwise say "docker skipped"

COMMIT & PUSH (run exactly):
git add .gitignore .dockerignore .bobignore pyproject.toml uv.lock requirements.txt alembic.ini Dockerfile README.md contracts migrations orders_service scripts docker tests .github
git commit -m "feat: orders-service v1 (REST + gRPC + DB contract)" -m "Bob-Session: P1-1"
git push -u origin main
````

**Evidence (after the task, 0 coins):** Bob → History → **Export** this task → save as `~/hack/syncsnitch/bob_sessions/exports/P1-1-orders-v1.md`. Add 1–2 screenshots as `bob_sessions/screenshots/P1-1-<n>-<what>.png`. Then run:
```bash
cd ~/hack/syncsnitch && git add bob_sessions && git commit -m "evidence: P1-1" && git pull --rebase origin main && git push origin main
```

### P1-2 · Person 1 · the breaking change: branch `feat/orders-v2` + PR #1
| Start when | Mode | Budget | You'll see at the end |
|---|---|---|---|
| P1-1 pushed | Advanced, new task | ≈2 coins | tests pass on the branch; **PR #1 URL** (`…/orders-service/pull/1`). **Never merge PR #1**: it's the demo trigger |

````text
[SyncSnitch P1-2 · Person 1 · budget ≈2 Bobcoins]

CONTEXT
orders-service v1 is on main (from prompt P1-1). Now create the BREAKING contract v2 on branch feat/orders-v2 and open
PR #1. v2 changes all 3 surfaces: money becomes minor units (total{amount_minor,currency}), customer becomes an object
(customer{customer_id,display_name}), status PENDING is renamed AWAITING_PAYMENT, optional shipping_eta is added, and DB
migration 0002 changes the table. PR #1 must NEVER be merged - it is the SyncSnitch demo trigger.
Work only in ~/hack/orders-service. ~/hack/syncsnitch is read-only (copy from it only).

RULES: same as before - no exploring, cp instead of retyping, several files per turn, never print file contents,
run ACCEPTANCE once (max 2 fix attempts, then STOP and report), final reply at most 10 lines, relative imports only,
rest.py must never import grpc or orders_service.gen.

STEP 1 - branch + frozen v2 contracts (run exactly):
cd ~/hack/orders-service && git checkout main && git pull --ff-only && git checkout -b feat/orders-v2
cp ../syncsnitch/contracts/reference/v2/openapi.yaml contracts/openapi.yaml
cp ../syncsnitch/contracts/reference/v2/orders.proto contracts/orders.proto
cp ../syncsnitch/contracts/reference/migrations/0002_money_customer_status.py migrations/versions/
mkdir -p docs
cp ../syncsnitch/contracts/reference/orders-v2-change-proposal.docx ../syncsnitch/contracts/reference/orders-v2-change-proposal.md docs/
uv run python scripts/gen_proto.py

STEP 2 - update ONLY these files to v2:
- orders_service/models.py: Order columns = migration head: order_id String(32) PK, customer_id String(32),
  customer_display_name String(200), total_minor BigInteger, currency String(3), status String(32),
  created_at DateTime(timezone=True), shipping_eta DateTime(timezone=True) nullable.
- orders_service/seed.py: insert customer_id, customer_display_name = customer_name, total_minor = amount_minor,
  currency, status = status_v2, created_at, shipping_eta (None when null, else parsed as UTC).
- orders_service/schemas.py: CustomerOut{customer_id: str, display_name: str}; MoneyOut{amount_minor: int, currency: str};
  OrderOut{order_id: str, customer: CustomerOut, total: MoneyOut, status: str, created_at: datetime,
  shipping_eta: datetime | None = None}; from_row builds the nested objects; datetimes UTC-aware via utc().
- orders_service/rest.py: same routes; add response_model_exclude_none=True to GET /orders and GET /orders/{order_id}
  (shipping_eta is omitted when null); FastAPI version "2.0.0".
- orders_service/grpc_server.py: return orders_pb2.OrderSummary(order_id=..., status=OrderStatus.Value("ORDER_STATUS_" + row.status),
  customer=orders_pb2.Customer(customer_id=..., display_name=row.customer_display_name),
  total=orders_pb2.Money(amount_minor=row.total_minor, currency=row.currency),
  shipping_eta=row.shipping_eta formatted "%Y-%m-%dT%H:%M:%SZ" in UTC, or "" when null).
- tests: test_rest.py -> /orders/o-1001 equals the v2 "paid" example; /orders/o-1002 status "AWAITING_PAYMENT";
  /orders/o-1003 has shipping_eta "2026-09-05T12:00:00Z"; spec validation as before (now against the v2 contract).
  test_grpc.py -> total.amount_minor 1999, total.currency "USD", customer.display_name "Ada Lovelace", status ORDER_STATUS_PAID.
  test_migrations.py -> upgrade to "0001"; insert two v1 rows with sqlalchemy.text() and plain values:
  ("o-1001", "Ada Lovelace", 19.99, "PAID", "2026-09-01 10:00:00") and ("o-1002", "Alan Turing", 5.0, "PENDING",
  "2026-09-02 11:00:00"); upgrade to "head"; assert o-1001: total_minor 1999, currency "USD", customer_id "c-1001",
  customer_display_name "Ada Lovelace"; o-1002: status "AWAITING_PAYMENT"; downgrade to "0001"; assert o-1001
  total_price == 19.99 (as float) and o-1002 status "PENDING".

ACCEPTANCE (run once):
uv run pytest -q   -> expect all passed

COMMIT, PUSH, OPEN PR #1 (run exactly):
git add contracts migrations orders_service tests docs
git commit -m "feat!: Orders API v2 - money in minor units, structured customer, PENDING renamed AWAITING_PAYMENT" -m "Implements RFC-042 (docs/orders-v2-change-proposal.docx). Breaking for REST, gRPC and DB consumers." -m "Bob-Session: P1-2"
git push -u origin feat/orders-v2
gh pr create --repo kshiti26-11/orders-service --base main --head feat/orders-v2 --title "feat!: Orders API v2 (money in minor units, customer object, AWAITING_PAYMENT)" --body "Implements RFC-042 (docs/orders-v2-change-proposal.docx). Breaking change for REST, gRPC and DB consumers. DO NOT MERGE - SyncSnitch demo trigger."
Print the PR URL. If gh is not available, tell me to open the PR in the browser with the same title and body.
````

**Evidence:** export this task → `bob_sessions/exports/P1-2-orders-v2-pr.md`. Screenshot the PR page → `bob_sessions/screenshots/P1-2-1-pr1.png`. Then run the same `git add bob_sessions …` snippet as in P1-1.
**Tell the team:** post the PR URL in the chat. Expect `https://github.com/kshiti26-11/orders-service/pull/1`. The automatic **SyncSnitch comment** on PR #1 comes from the `syncsnitch` check, which needs Person 3's engine (P3-1). If the check ran before P3-1 was pushed and failed, open PR #1 → Checks → **Re-run all jobs** once P3-1 is on `main`.
**After that, Person 1 is free:** you're on media duty (§7).

### P2-1 · Person 2 · billing-service v1 (the consumer that will break)
| Start when | Mode | Budget | You'll see at the end |
|---|---|---|---|
| Setup done | Advanced, new task | ≈4 coins | `N passed, 1 skipped` (the integration-test module skips locally), commit pushed to `main` |

````text
[SyncSnitch P2-1 · Person 2 · budget ≈4 Bobcoins]

CONTEXT
SyncSnitch is a contract-drift agent. You are building the DOWNSTREAM service "billing-service". It consumes the Orders
contract v1 from orders-service on 3 surfaces: REST (GET /orders/{order_id}), gRPC (orders.OrderLookup/GetOrderSummary)
and SQL (a revenue report reading the orders table). Later the upstream ships a breaking v2; this service must break
exactly as described below so the demo can show SyncSnitch fixing it.
Folders: ~/hack/syncsnitch = main repo, READ-ONLY for you (copy from it only).
         ~/hack/billing-service = YOUR repo (empty clone of https://github.com/kshiti26-11/billing-service).

RULES (the whole team shares 40 Bobcoins - follow strictly)
1. Do not explore or search. Open only files named here. Never open files under ~/hack/syncsnitch.
2. Copy files with the cp commands below; never retype them.
3. Create several files per turn. Never print file contents back to me.
4. Run the ACCEPTANCE commands once at the end. If something fails, fix it at most 2 times, then STOP and report.
5. Final reply: at most 10 lines (what you built, test result, commit SHA).
6. Inside the package billing/ use RELATIVE imports only. Only billing/clients/orders_grpc.py may import grpc or
   billing.clients.gen, and only INSIDE its function (lazy import). No other module imports grpc or the stubs.

STEP 1 - copy templates and the vendored v1 client contract (run exactly):
cd ~/hack/billing-service
git symbolic-ref HEAD refs/heads/main
cp -r ../syncsnitch/templates/billing-service/. .
mkdir -p contracts/upstream billing/clients billing/models billing/services billing/reports tests/unit tests/fixtures
cp ../syncsnitch/contracts/reference/v1/orders.proto contracts/upstream/orders.proto
cp ../syncsnitch/contracts/reference/v1/openapi.yaml contracts/upstream/openapi.yaml
uv sync
uv run python scripts/regen_stubs.py
uv run python -c "import json,yaml; s=yaml.safe_load(open('contracts/upstream/openapi.yaml')); ex=s['paths']['/orders/{order_id}']['get']['responses']['200']['content']['application/json']['examples']; [json.dump(ex[k]['value'], open(f'tests/fixtures/order_v1_{k}.json','w'), indent=2) for k in ('paid','unpaid')]"
(The templates gave you pyproject.toml, Dockerfile, .dockerignore, .gitignore, .bobignore, scripts/regen_stubs.py,
tests/integration/{__init__,test_contract}.py and .github/workflows/{ci,contract-verify}.yml. Do not edit them.)

STEP 2 - create the package billing/ (every folder gets an empty __init__.py; billing/clients/gen already exists):
- config.py: orders_rest_url() -> env ORDERS_REST_URL (default "http://localhost:8000"); orders_grpc_addr() -> env
  ORDERS_GRPC_ADDR (default "localhost:50051"); reports_db_url() -> env REPORTS_DB_URL (default "sqlite:///./orders_replica.db").
- clients/orders_rest.py: class OrderNotFound(Exception); class OrdersRestClient(base_url: str,
  transport: httpx.AsyncBaseTransport | None = None) with async get_order(order_id, headers: dict | None = None) -> dict:
  use "async with httpx.AsyncClient(base_url=..., transport=self.transport, timeout=10)", GET /orders/{order_id};
  404 -> raise OrderNotFound; other errors -> raise_for_status(); return r.json().
- clients/orders_grpc.py: class OrderNotFound(Exception); def get_order_summary(addr: str, order_id: str): import grpc and
  "from .gen import orders_pb2, orders_pb2_grpc" INSIDE the function; with grpc.insecure_channel(addr): call
  OrderLookupStub.GetOrderSummary(GetOrderSummaryRequest(order_id=...), timeout=10); NOT_FOUND -> raise OrderNotFound.
- models/order.py: Pydantic OrderDTO: order_id: str, customer_name: str, total_price: float, status: str, created_at: datetime.
- services/invoice.py: TAX_RATE = Decimal("0.0825"); NOT_PAYABLE = {"PENDING", "CANCELLED"};
  build_invoice(order: OrderDTO) -> dict | None: return None if order.status in NOT_PAYABLE; subtotal = round-half-up of
  Decimal(str(order.total_price)) * 100; tax = round-half-up of subtotal * TAX_RATE; return {"order_id", "customer"
  (= customer_name), "subtotal_minor", "tax_minor", "total_minor" (= subtotal + tax), "currency": "USD"}.
  For o-1001 (19.99) this is exactly: subtotal_minor 1999, tax_minor 165, total_minor 2164.
- services/payments.py (must NOT import the stubs): PAID_STATES = {"ORDER_STATUS_PAID", "ORDER_STATUS_SHIPPED"};
  status_from_summary(summary) -> {"order_id", "paid": status name in PAID_STATES, "amount_minor": round-half-up of
  Decimal(str(summary.total_price)) * 100, "currency": "USD"}; get the status name with
  type(summary).DESCRIPTOR.fields_by_name["status"].enum_type.values_by_number[summary.status].name
- reports/revenue.sql (exactly):
  SELECT date(created_at) AS day, SUM(total_price) AS revenue FROM orders WHERE status IN ('PAID', 'SHIPPED') GROUP BY day ORDER BY day
- reports/revenue.py: run_revenue_report(db_url) -> list[dict]: create_engine(db_url), run the SQL file (text()),
  dispose the engine; return [{"day": str(row.day)[:10], "revenue_minor": round-half-up of Decimal(str(row.revenue)) * 100}].
- contract_entrypoints.py: invoice_from_order_payload(payload: dict) -> dict | None =
  build_invoice(OrderDTO.model_validate(payload)). (SyncSnitch and the demo site call this function.)
- api.py: def create_app(orders_rest_url=None, orders_rest_transport=None, orders_grpc_addr=None, reports_db_url=None) -> FastAPI
  (each None falls back to config.*). FastAPI(title="billing-service", version="1.0.0"). Routes:
    GET  /health -> {"status": "ok"}
    POST /invoices/{order_id} (async def, status_code=201) -> payload = await rest client get_order(order_id);
         OrderNotFound -> 404 {"detail": "order not found"}; invoice = invoice_from_order_payload(payload);
         None -> JSONResponse(409, {"detail": "order not payable"}); else return the invoice.
    GET  /payments/{order_id}/status (plain def) -> status_from_summary(orders_grpc.get_order_summary(addr, order_id));
         OrderNotFound -> 404.
    GET  /reports/revenue (plain def) -> run_revenue_report(db_url).
  No module-level app, no startup events. Do not catch other exceptions (a contract break must surface as HTTP 500).

STEP 3 - unit tests (tests/__init__.py and tests/unit/__init__.py empty):
- tests/unit/test_invoice.py: invoice_from_order_payload(order_v1_paid.json) == {"order_id": "o-1001", "customer":
  "Ada Lovelace", "subtotal_minor": 1999, "tax_minor": 165, "total_minor": 2164, "currency": "USD"};
  order_v1_unpaid.json -> None; the paid payload with status "CANCELLED" -> None.
- tests/unit/test_api.py: an httpx.MockTransport that serves tests/fixtures/order_v1_paid.json for /orders/o-1001,
  order_v1_unpaid.json for /orders/o-1002 and 404 for anything else; TestClient(create_app(orders_rest_url="http://orders",
  orders_rest_transport=transport)): POST /invoices/o-1001 -> 201 with the invoice above; o-1002 -> 409; o-9999 -> 404.
- tests/unit/test_payments.py: from billing.clients.gen import orders_pb2; OrderSummary(order_id="o-1001",
  customer_name="Ada Lovelace", total_price=19.99, status=orders_pb2.ORDER_STATUS_PAID) -> status_from_summary(...) ==
  {"order_id": "o-1001", "paid": True, "amount_minor": 1999, "currency": "USD"}.
- tests/unit/test_revenue.py: in a SQLite file under tmp_path create table orders(order_id, customer_name, total_price
  NUMERIC, status, created_at) with raw SQL and insert: (o-1001, 19.99, PAID, '2026-09-01 10:00:00'),
  (o-1002, 5.0, PENDING, '2026-09-02 11:00:00'), (o-1003, 120.5, SHIPPED, '2026-09-03 12:00:00'),
  (o-1004, 42.0, CANCELLED, '2026-09-04 13:00:00'); run_revenue_report(url) ==
  [{"day": "2026-09-01", "revenue_minor": 1999}, {"day": "2026-09-03", "revenue_minor": 12050}].

STEP 4 - exports + README (run exactly, then write README.md with at most 15 lines: what it is, the 3 endpoints, the 3
contract dependencies, uv run pytest -q, the Dockerfile runs the integration tests used by SyncSnitch):
uv export --no-dev --no-hashes -o requirements.txt
uv export --no-hashes -o requirements-dev.txt

ACCEPTANCE (run once):
uv run pytest -q                              -> expect all unit tests passed and "1 skipped" (the integration module)
docker build -t billing-service:tests .       -> only if Docker is running; otherwise say "docker skipped"

COMMIT & PUSH (run exactly):
git add .gitignore .dockerignore .bobignore pyproject.toml uv.lock requirements.txt requirements-dev.txt Dockerfile README.md contracts billing scripts tests .github
git commit -m "feat: billing-service v1 consumer (REST + gRPC + SQL)" -m "Bob-Session: P2-1"
git push -u origin main
````

**Evidence:** export → `bob_sessions/exports/P2-1-billing-v1.md`, 1–2 screenshots → `bob_sessions/screenshots/P2-1-*.png`, then run the `git add bob_sessions …` snippet.

### P2-2 · Person 2 · *(optional)* Ask mode: Bob explains the cross-repo blast radius
| Start when | Mode | Budget | Why |
|---|---|---|---|
| P2-1 pushed | **Ask** (read-only), new task | ≈1 coin | Judges value Bob's contextual reasoning across repos. This export is the "Bob understood the system" evidence. **Skip it in lean mode.** |

````text
[SyncSnitch P2-2 · Person 2 · Ask mode · budget ≈1 Bobcoin]
Read ONLY these files (do not search):
@syncsnitch/contracts/reference/v1/openapi.yaml @syncsnitch/contracts/reference/v2/openapi.yaml
@syncsnitch/contracts/reference/v1/orders.proto @syncsnitch/contracts/reference/v2/orders.proto
@syncsnitch/contracts/reference/migrations/0002_money_customer_status.py
@billing-service/billing/models/order.py @billing-service/billing/services/invoice.py
@billing-service/billing/services/payments.py @billing-service/billing/reports/revenue.sql
Question: if orders-service ships this v2 contract, what breaks in billing-service? For each billing endpoint
(POST /invoices/{order_id}, GET /payments/{order_id}/status, GET /reports/revenue) give: which contract surface
(REST, gRPC, DB), the exact file:line, and whether the failure is LOUD (exception/HTTP 500) or SILENT (wrong data, no
error), with one sentence why. Finish with the one bug a human fixing only the loud errors would still miss.
Answer in at most 15 lines.
````

**Expected answer:**
- **Invoices:** REST, loud. `OrderDTO` loses `customer_name` and `total_price`.
- **Hidden:** `PENDING` is renamed, so unpaid orders would get invoiced (silent).
- **Payments:** gRPC, silent. Old stubs read `total_price` as `0.0`.
- **Revenue:** DB, loud. The `total_price` column is dropped.

**Evidence:** export → `bob_sessions/exports/P2-2-ask-blast-radius.md` and screenshot the answer. **After that, Person 2 is on media and submission duty (§7).**

### P3-1 · Person 3 · the SyncSnitch engine (detect · trace · report · run-artifact)
| Start when | Mode | Budget | You'll see at the end |
|---|---|---|---|
| Setup done | Advanced, new task | ≈5 coins | `tests/engine` all passed; `uv run syncsnitch detect --help` works; commit pushed |

````text
[SyncSnitch P3-1 · Person 3 · budget ≈5 Bobcoins]

CONTEXT
SyncSnitch is a contract-drift agent. You are building its deterministic ENGINE - the parts that cost 0 tokens at run
time: detect (REST/OpenAPI, gRPC/protobuf and DB/Alembic drift), trace (every consumer usage + the endpoint it breaks),
report (PR body / CI comment) and run-artifact (JSON for the demo website). Person 4 builds "syncsnitch verify" in
syncsnitch/verify/ at the same time - do NOT create that folder. Repo: ~/hack/syncsnitch (work here).

RULES (the whole team shares 40 Bobcoins - follow strictly)
1. Do not explore or search. The only existing files you may open are pyproject.toml and contracts/reference/*.
2. Never edit pyproject.toml, uv.lock, syncsnitch/__init__.py, .github/, templates/, contracts/, verify/, scripts/, web/.
   All dependencies are already declared (pyyaml, jsonschema, protobuf, grpcio-tools, jinja2; dev: pytest). If you
   believe one is missing, STOP and report.
3. Create several files per turn; never print file contents back. Final reply at most 10 lines.
4. Run ACCEPTANCE once at the end; fix at most 2 times, then STOP and report.
5. Inside syncsnitch/ use RELATIVE imports only (the demo site loads this package under another name). Import
   grpc_tools only inside compile_proto. No __init__.py files under tests/; test file names must be unique.

FILES TO CREATE (only these)
syncsnitch/cli.py, syncsnitch/gitutil.py, syncsnitch/detect/{__init__,openapi,proto,migrations}.py,
syncsnitch/trace/{__init__,python_ast,files}.py, syncsnitch/report/__init__.py,
syncsnitch/report/templates/{pr_body.md.j2,comment.md.j2}, syncsnitch/runs/__init__.py,
tests/engine/{test_detect,test_trace,test_cli}.py

DATA SHAPES (use exactly)
Change = {"id", "surface": "rest"|"grpc"|"db", "kind", "location", "old", "new", "breaking": bool, "note"}
  with id = f"{surface}:{location}:{kind}" and "old" = the old identifier/value consumers may still use.
drift.json = {"run_id", "upstream": {"repo", "base", "head", "base_sha", "head_sha"}, "changes": [Change],
  "summary": {"total", "breaking", "by_surface": {"rest", "grpc", "db"}}}
Hit = {"file" (relative to the consumer root), "line", "token", "change_ids": [...], "usage_kind", "symbol",
  "endpoints": [...], "in_tests": bool}
candidates.json = {"run_id", "consumer" (absolute path), "hits": [Hit], "summary": {"hits", "files", "endpoints": [...]}}

DETECT
- detect/openapi.py: diff_openapi(old_text, new_text) -> list[Change]. Compare components.schemas (resolve local "#/"
  $refs). schema_added (breaking False) / schema_removed (True). Enums: enum_value_removed (True, location
  "<Schema>.<value>", old=value) / enum_value_added (False, note "consumers with exhaustive status handling may
  break"). Object properties: property_removed (True, location "<Schema>.<prop>", old=prop), property_added (False,
  note "required" or "optional"), type_changed (True) when the type or the $ref target differs.
- detect/proto.py: compile_proto(text) -> bytes: write it to a temp dir as orders.proto and run
  grpc_tools.protoc.main(["grpc_tools.protoc", "-I<tmp>", "-I<grpc_tools package dir>/_proto", "--include_imports",
  "--descriptor_set_out=<tmp>/out.binpb", "<tmp>/orders.proto"]); return the bytes.
  diff_descriptor_sets(old: bytes, new: bytes) -> list[Change]: parse with
  google.protobuf.descriptor_pb2.FileDescriptorSet.FromString (NEVER add them to a descriptor pool). Messages by
  "<package>.<Message>": message_added (False) / message_removed (True). Fields by NUMBER: field_removed (True,
  location "<pkg>.<Msg>.<number>", old = old field name), field_added (False), field_renamed (True),
  field_type_changed (True). Enum values by number (location "<pkg>.<Enum>.<number>"): enum_value_removed (True),
  enum_value_added (False), enum_value_renamed (True, old = old value name, note "wire-compatible, source-breaking").
  diff_proto_texts(old_text, new_text) = diff_descriptor_sets(compile_proto(old_text), compile_proto(new_text)).
- detect/migrations.py: diff_migrations(files: list[tuple[str, str]]) -> list[Change], ast on each file's upgrade()
  only. Handle op.add_column / op.drop_column / op.alter_column(table, ...) and batch_op.* inside
  "with op.batch_alter_table('<table>') as batch_op:". column_added (False, location "<table>.<col>"),
  column_dropped (True, old=col), column_renamed via new_column_name= (True, old=col, new=new name).
  op.execute("UPDATE t SET c = 'NEW' WHERE c = 'OLD'") -> value_renamed (True, location "t.c.OLD", old "OLD",
  new "NEW"); any other op.execute -> data_update (False, location "<file>:<line>").
- gitutil.py: run(args, cwd) -> str (subprocess.run, check=True, text=True, capture_output=True);
  resolve_ref(repo, ref) -> sha (try "git rev-parse --verify <ref>^{commit}", then "origin/<ref>");
  show_file(repo, sha, path) -> str | None; added_files(repo, base_sha, head_sha, pathspec) -> list[str]
  (git diff --name-only --diff-filter=A); new_run_id() -> "r-" + UTC time "%Y%m%d-%H%M%S".
- detect/__init__.py: run_detect(upstream: Path, base, head, run_id, runs_dir: Path) -> dict. Upstream files:
  contracts/openapi.yaml and contracts/orders.proto read at both refs (skip a surface if missing at either ref) and the
  migrations/versions/*.py files ADDED between base and head. Write <runs_dir>/<run_id>/drift.json and return it.

TRACE
- trace/__init__.py: trace_consumer(changes: list[dict], consumer: Path) -> list[Hit] and run_trace(run_id, consumer,
  runs_dir) (reads drift.json, writes candidates.json, returns it). Tokens = the "old" value of every BREAKING change
  (token -> list of change ids). Skip folders .venv, .git, __pycache__, gen, node_modules, .pytest_cache. Scan files
  concurrently with a ThreadPoolExecutor; sort hits by (file, line).
- trace/python_ast.py, for every *.py: Subscript with a string-constant token -> "subscript"; .get("<token>") ->
  "get_call"; Attribute named token -> "attribute"; AnnAssign target named token -> "model_field"; keyword argument
  named token -> "keyword"; string constant equal to token -> "literal"; a longer string containing the token as a
  whole word -> "embedded_text". symbol = innermost enclosing function/class name; for module-level hits inside
  "NAME = ..." use NAME. Endpoints: routes = functions decorated with @<x>.get/post/put/patch/delete("<path>") ->
  "METHOD /path"; build a reference graph (for every function/class: all Name ids and Attribute attrs used inside it);
  endpoints(symbol) = routes reachable by walking "who references this symbol" up to 3 hops.
  in_tests = path starts with "tests/".
- trace/files.py: *.sql -> "sql_column" (whole-word match per line; endpoints = endpoints of every function in any .py
  file that mentions the sql file name); *.proto -> "proto_field"; *.json under tests/ -> "fixture" (line contains
  "\"<token>\""). Do NOT scan *.yaml.

REPORT (jinja2 templates in syncsnitch/report/templates/)
- report/__init__.py: render(run_dir: Path, fmt: "pr"|"comment", upstream_pr_url: str | None) -> str. Loads
  drift.json plus, when present, candidates.json, impact.json, verification.json, verdict.json. Writes pr_body.md or
  comment.md into run_dir and returns the text.
- pr_body.md.j2 sections: "## Why this PR exists" (upstream PR link + counts) · "## Contract drift" (table: surface |
  kind | location | old -> new | breaking) · "## Impact" (impact.json endpoints, else candidates) · "## Verification"
  (table: check | name | result | details from verification.json) · "## Migration notes" (impact.json
  migration_notes) · "## Rollout plan" (1. merge this tolerant reader 2. deploy upstream v2 3. remove the v1 paths in a
  cleanup PR) · "## Evidence" (run id, "Built with IBM Bob - see bob_sessions/ in kshiti26-11/demo").
- comment.md.j2 (CI comment on the upstream PR): first line "<!-- syncsnitch -->", heading "### SyncSnitch found
  contract drift", counts by surface, the breaking-changes table, affected consumer files and endpoints, and the line
  "Run /syncsnitch <PR URL> in IBM Bob to generate a verified companion PR."

RUN ARTIFACT
- runs/__init__.py: write_run_artifact(run_id, runs_dir, consumer: Path, branch, base_branch="main",
  upstream_pr_url=None, companion_pr_url=None, bob_export=None, out_dir=Path("web/runs")) -> Path, writing
  <out_dir>/<run_id>.json = {"run_id", "created_at", "upstream_pr_url", "companion_pr_url", "branch", "drift",
  "candidates", "impact", "verification", "verdict" (each json or null), "diff" (git -C consumer diff
  <base_branch>...<branch>, max 200 KB), "diffstat", "steps": [{"id": "S1".."S9", "name", "type":
  "deterministic"|"ai"|"human", "status": "done"|"skipped"}], "bob_session_export"}.

CLI - syncsnitch/cli.py: def main(argv: list[str] | None = None) -> int (argparse). The console script "syncsnitch"
is already declared. Defaults: --runs-dir .syncsnitch/runs; --run-id = gitutil.new_run_id().
  syncsnitch detect --upstream DIR --base REF --head REF [--run-id ID] [--runs-dir DIR]
      -> writes drift.json; prints "RUN_ID=<id>" and one line per breaking change; exit 0
  syncsnitch trace --run-id ID --consumer DIR [--runs-dir DIR] -> writes candidates.json; prints hits per file
  syncsnitch report --run-id ID --format pr|comment [--upstream-pr-url URL] [--runs-dir DIR] -> prints the markdown
  syncsnitch run-artifact --run-id ID --consumer DIR --branch BR [--base-branch main] [--upstream-pr-url URL]
      [--companion-pr-url URL] [--bob-export PATH] [--runs-dir DIR] [--out-dir web/runs] -> prints the file path
  syncsnitch verify ... -> import syncsnitch.verify.cli lazily and return its main(remaining argv); on ImportError print
      "syncsnitch verify is not built yet (Person 4 builds syncsnitch/verify/)" and return 2.

TESTS (tests/engine/, no network, no Docker)
- test_detect.py (inputs from contracts/reference/):
  REST v1->v2 == exactly these (kind, location): (schema_added, Customer), (schema_added, Money),
  (property_removed, Order.customer_name), (property_removed, Order.total_price), (property_added, Order.customer),
  (property_added, Order.shipping_eta), (property_added, Order.total), (enum_value_removed, OrderStatus.PENDING),
  (enum_value_added, OrderStatus.AWAITING_PAYMENT) - exactly 3 breaking.
  gRPC v1->v2 == exactly: (message_added, orders.Customer), (message_added, orders.Money),
  (field_removed, orders.OrderSummary.2), (field_removed, orders.OrderSummary.3), (field_added, orders.OrderSummary.5),
  (field_added, orders.OrderSummary.6), (field_added, orders.OrderSummary.7), (enum_value_renamed, orders.OrderStatus.1)
  - exactly 3 breaking, with olds customer_name, total_price, ORDER_STATUS_PENDING.
  DB (0002 file) contains column_added for orders.total_minor, orders.currency, orders.customer_id, orders.shipping_eta;
  (column_renamed, orders.customer_name); (column_dropped, orders.total_price); (value_renamed, orders.status.PENDING);
  and 2 data_update entries - exactly 3 breaking.
- test_trace.py: write a mini consumer into tmp_path and trace it with the REST+DB changes of the reference contracts:
    api.py: from fastapi import FastAPI; from entry import invoice_from_order_payload; from payments import
      status_from_summary; from revenue import run_revenue_report; def create_app(): app = FastAPI();
      @app.post("/invoices/{order_id}") async def create_invoice(order_id): return invoice_from_order_payload({});
      @app.get("/payments/{order_id}/status") def payment_status(order_id): return status_from_summary(None);
      @app.get("/reports/revenue") def revenue(): return run_revenue_report("x"); return app
    models.py: from pydantic import BaseModel; class OrderDTO(BaseModel): customer_name: str; total_price: float
    invoice.py: NOT_PAYABLE = {"PENDING", "CANCELLED"}; def build_invoice(order): return None if order.status in
      NOT_PAYABLE else order.total_price
    entry.py: from invoice import build_invoice; from models import OrderDTO; def invoice_from_order_payload(p):
      return build_invoice(OrderDTO.model_validate(p))
    payments.py: def status_from_summary(s): return s.total_price
    revenue.sql: SELECT SUM(total_price) FROM orders
    revenue.py: SQL_FILE = "revenue.sql"; def run_revenue_report(url): return SQL_FILE
  Expect: "PENDING" in invoice.py -> endpoints ["POST /invoices/{order_id}"]; total_price in payments.py ->
  ["GET /payments/{order_id}/status"]; revenue.sql total_price -> ["GET /reports/revenue"]; the OrderDTO fields in
  models.py -> ["POST /invoices/{order_id}"]. (The files are only parsed, never imported.)
- test_cli.py: in tmp_path create a git repo "up" (git init -b main; commit with
  git -c user.name=test -c user.email=test@example.com commit ... because CI has no git identity): commit
  contracts/openapi.yaml, contracts/orders.proto (v1 reference files) and migrations/versions/0001_create_orders.py on main; then branch feat/v2 committing the v2 files and
  migrations/versions/0002_money_customer_status.py. main(["detect", "--upstream", up, "--base", "main", "--head",
  "feat/v2", "--run-id", "t1", "--runs-dir", runs]) == 0 and drift.json summary.breaking == 9 (3 per surface); then
  trace the mini consumer and main(["report", "--run-id", "t1", "--format", "pr", "--runs-dir", runs]) == 0 and
  pr_body.md contains "## Contract drift".

ACCEPTANCE (run once):
uv sync --frozen && uv run pytest -q tests/engine    -> all passed
uv run syncsnitch detect --help                      -> shows usage

COMMIT & PUSH (run exactly):
git add syncsnitch/cli.py syncsnitch/gitutil.py syncsnitch/detect syncsnitch/trace syncsnitch/report syncsnitch/runs tests/engine
git commit -m "feat(engine): detect (REST/gRPC/DB), trace, report, run-artifact" -m "Bob-Session: P3-1"
git pull --rebase origin main && git push origin main
````

**Evidence:** export → `bob_sessions/exports/P3-1-engine.md` plus 1 screenshot, then run the `git add bob_sessions …` snippet.

### P3-2 · Person 3 · install the Bob layer (modes · subagents · workflow skill · hooks)
| Start when | Mode | Budget | You'll see at the end |
|---|---|---|---|
| P3-1 pushed | Advanced, new task | ≈1 coin | 4 SyncSnitch modes in the mode picker; `/syncsnitch` in the slash-command list |

````text
[SyncSnitch P3-2 · Person 3 · budget ≈1 Bobcoin]

CONTEXT
Install the SyncSnitch Bob layer into ~/hack/syncsnitch: 4 custom modes (🕵️ SyncSnitch orchestrator, 🔎 Schema Diff &
AST Tracer, 🛠️ Downstream Code Transformer, ✅ Contract Verifier), the S0-S9 workflow skill, the /syncsnitch and
/evidence commands, rules, lifecycle hooks (scripts/bob_hooks/guard.py and logger.py already exist) and an optional,
disabled GitHub MCP server. All files are prepared in templates/bob/.bob/ and syntax-checked. Your job: install them and
check them against YOUR OWN documented configuration schema, adapting only keys/format that differ.

RULES: do not explore; open only the files named here; keep every text as written; final reply at most 6 lines.

STEP 1 (run exactly):
cd ~/hack/syncsnitch && cp -r templates/bob/.bob .

STEP 2 - check against your documented schema and fix ONLY what differs:
- .bob/custom_modes.yaml (fields used: customModes[].slug, name, description, roleDefinition, whenToUse,
  customInstructions, groups, allowedSubagents). If allowedSubagents may list mode slugs in your version, add
  syncsnitch-tracer, syncsnitch-transformer and syncsnitch-verifier to the "syncsnitch" mode; otherwise keep "explore".
- .bob/skills/syncsnitch-workflow/SKILL.md (frontmatter: name, description).
- .bob/commands/syncsnitch.md and .bob/commands/evidence.md (frontmatter: description, argument-hint; args $1 $2).
- .bob/settings.json (lifecycle hooks: PreToolUse -> guard.py on file-writing tools, PostToolUse and Stop -> logger.py).
  If your version does not read hooks from .bob/settings.json, delete that file and say so.
- .bob/mcp.json (GitHub MCP server, "disabled": true - leave it disabled).

STEP 3 - reply with: the 4 mode names as shown in the mode picker, whether /syncsnitch is listed as a slash command,
whether hooks are active, and every key you changed.

COMMIT & PUSH (run exactly):
git add .bob
git commit -m "feat(bob): SyncSnitch modes, workflow skill, commands, rules, hooks" -m "Bob-Session: P3-2"
git pull --rebase origin main && git push origin main
````

**Then (human):** reload the Bob window (Command Palette → "Reload Window"). Open the mode picker and **screenshot** the 4 SyncSnitch modes → `bob_sessions/screenshots/P3-2-1-modes.png`. Export the task → `bob_sessions/exports/P3-2-bob-layer.md`, then run the evidence snippet.

### H-1 · Person 3 · deterministic dry run (human, **0 coins**)
**Start when** P1-2, P2-1, P3-1 and P4-1 are pushed. This proves the break **before** any fix and gives the "before" screenshot for the video.
```bash
cd ~/hack/syncsnitch && git pull --rebase origin main && uv sync --frozen
git -C ../orders-service fetch origin && git -C ../billing-service pull --ff-only
uv run syncsnitch detect --upstream ../orders-service --base main --head feat/orders-v2 --run-id dry-1
uv run syncsnitch trace  --run-id dry-1 --consumer ../billing-service
uv run syncsnitch verify --run-id dry-1 --upstream ../orders-service --base main --head feat/orders-v2 --consumer ../billing-service
cat .syncsnitch/runs/dry-1/VERIFICATION.md
```
**Expected results:**
- **detect:** 9 breaking changes, 3 each for REST, gRPC and DB.
- **trace:** hits in `billing/models/order.py`, `billing/services/invoice.py` (including the silent `"PENDING"`), `billing/services/payments.py`, `billing/reports/revenue.sql` and `contracts/upstream/orders.proto`.
- **verify** exits 1, which is correct before the fix:

  | Check | Result | Why |
  |---|---|---|
  | V1 | ✅ | |
  | V2 | ❌ | no v2 fixtures yet |
  | V3 | ✅ | v1: 5/5 passed |
  | V4 | ❌ | v2: 0/5 passed |
  | V5 | ❌ | |
  | V6 | ✅ | |

The first container run downloads images and takes about 3–6 minutes. Screenshot `VERIFICATION.md` → `bob_sessions/screenshots/H-1-before.png`.
**If anything differs**, compare with ARCHITECTURE.md §6, then use a fix prompt (§4) for the owner of the failing part.

### P4-1 · Person 4 · `syncsnitch verify` (Subagent 3's deterministic judge: mock containers)
| Start when | Mode | Budget | You'll see at the end |
|---|---|---|---|
| Setup done | Advanced, new task | ≈4 coins | `tests/verify` all passed (no Docker needed for the tests); commit pushed |

````text
[SyncSnitch P4-1 · Person 4 · budget ≈4 Bobcoins]

CONTEXT
SyncSnitch's Subagent 3 (Contract Verifier) bases its verdict on a DETERMINISTIC command that you build now:
"syncsnitch verify". It proves the consumer (billing-service) works against the upstream contract v1 (backward
compatibility) and v2 (the change) by running the consumer's integration tests inside Docker mock containers, plus
fast pre-checks. The compose topology already exists and is validated: verify/docker-compose.yml (services orders-db,
orders-upstream, orders-rest-mock (Prism), billing-contract-tests; env UPSTREAM_DIR, CONSUMER_DIR, RESULTS_DIR,
CONTRACT_VERSION; the test container writes /results/junit-<CONTRACT_VERSION>.xml and exits 0 only when all tests
pass). Person 3 builds the rest of the syncsnitch package in parallel; its CLI calls your
syncsnitch.verify.cli.main(argv). Repo: ~/hack/syncsnitch.

RULES
1. Do not explore or search. The only existing file you may open is verify/docker-compose.yml.
2. Create ONLY syncsnitch/verify/ (new) and tests/verify/ (new, no __init__.py; unique test file names starting with
   test_verify_). Never edit pyproject.toml, uv.lock, syncsnitch/__init__.py or anything else. Available libraries:
   pyyaml, jsonschema (+ referencing), pytest; stdlib for the rest (subprocess, xml.etree, argparse, json, shutil).
3. RELATIVE imports inside syncsnitch/verify/. Several files per turn; never print file contents. Final reply at most 10 lines.
4. Run ACCEPTANCE once; fix at most 2 times, then STOP and report.

BUILD syncsnitch/verify/
- __init__.py (empty). runner.py: class Runner with run(args: list[str], cwd=None, env=None, timeout=900) ->
  tuple[int, str] (returncode, stdout+stderr). EVERY subprocess call goes through a Runner so tests can inject a fake.
- cli.py: def main(argv: list[str] | None = None, runner: Runner | None = None) -> int, argparse prog "syncsnitch verify":
  --run-id (required) --upstream DIR --base REF --head REF --consumer DIR [--consumer-base main]
  [--runs-dir .syncsnitch/runs] [--compose-file verify/docker-compose.yml] [--versions v1,v2] [--no-containers]
- Refs: resolve(repo, ref) -> sha: "git -C <repo> rev-parse --verify <ref>^{commit}", else "origin/<ref>".
- Worktrees: <runs_dir>/<run_id>/upstream-v1 at the base sha and upstream-v2 at the head sha via
  "git -C <upstream> worktree add --detach <abs path> <sha>". ALWAYS remove them at the end with
  "git -C <upstream> worktree remove --force <path>" (try/finally, also on errors).
- Checks, each {"id", "name", "status": "pass"|"fail"|"skip", "details"}:
  V1 "consumer unit tests": "uv run pytest -q" with cwd=<consumer>; pass iff exit 0 (details: last 15 output lines).
  V2 "v2 fixtures match the new contract": every <consumer>/tests/fixtures/*v2*.json validates against
     components.schemas.Order of <upstream-v2>/contracts/openapi.yaml, using
     Draft202012Validator({"$ref": "urn:spec#/components/schemas/Order"}, registry=Registry().with_resource("urn:spec",
     Resource.from_contents(spec, default_specification=DRAFT202012))); no such files -> fail, "no v2 fixtures found".
  V3 "consumer vs upstream v1 (backward compatible)" and V4 "consumer vs upstream v2 (new contract)": for each version:
     RESULTS_DIR = abs(<runs_dir>/<run_id>/results) (create it); project = "ss-" + run_id + "-" + version, lowercased,
     only [a-z0-9-]; run "docker compose -f <compose-file> -p <project> up --build --abort-on-container-exit
     --exit-code-from billing-contract-tests" with env = os.environ + {UPSTREAM_DIR: abs(<upstream-vN worktree>),
     CONSUMER_DIR: abs(<consumer>), RESULTS_DIR, CONTRACT_VERSION: version}; then ALWAYS
     "docker compose -f <compose-file> -p <project> down -v --remove-orphans" (same env). Parse
     RESULTS_DIR/junit-<version>.xml with xml.etree: pass iff exit code 0 AND tests >= 1 AND failures + errors == 0;
     details "<passed>/<total> passed" + the names of failing test cases.
  V5 "Prism contract examples": pass iff test case "test_rest_contract_examples_parse" passed in BOTH junit files.
  V6 "diff scope": "git -C <consumer> diff --name-only <consumer-base>...HEAD" (resolve consumer-base like refs); pass
     iff every path starts with billing/, contracts/upstream/, tests/ or scripts/, or equals README.md or
     .syncsnitch.json, and no file under tests/ was deleted (--diff-filter=D); no changes -> pass ("no changes").
  --no-containers -> V3, V4, V5 = "skip".
- Output in <runs_dir>/<run_id>/: verification.json = {"run_id", "consumer_sha", "upstream": {"base_sha", "head_sha"},
  "checks": [...], "summary": {"passed", "failed", "skipped", "verdict": "green"|"red"}} (green iff no check failed)
  and VERIFICATION.md = a markdown table "| Check | Name | Result | Details |" with ✅ / ❌ / ⏭️. Print the table.
  Exit code 0 when green, 1 when red, 2 on usage errors.

TESTS (tests/verify/, no Docker, no network)
A FakeRunner returns canned (code, output) by matching the command; for "compose up" calls it writes a canned junit file
into RESULTS_DIR. Use real tiny git repos in tmp_path for the upstream (contracts/openapi.yaml = the v1 reference file
on main, the v2 reference file on branch feat/v2) and the consumer (a tests/fixtures/order_v2_paid.json copied from the
v2 "paid" example) so refs and worktrees run for real. Commit with git -c user.name=test -c user.email=test@example.com
(CI has no git identity) and create repos with git init -b main. Cases: (1) everything passes -> exit 0 and 6 checks pass;
(2) the v2 junit has 5 failures -> V4 and V5 fail, verdict red, exit 1; (3) no v2 fixture -> V2 fails;
(4) --no-containers -> V3-V5 skip; (5) worktrees are removed even when the compose call raises.

ACCEPTANCE (run once):
uv sync --frozen && uv run pytest -q tests/verify     -> all passed
uv run python -c "from syncsnitch.verify.cli import main; raise SystemExit(main(['--help']))"   -> prints usage

COMMIT & PUSH (run exactly):
git add syncsnitch/verify tests/verify
git commit -m "feat(verify): mock-container contract verification (V1-V6)" -m "Bob-Session: P4-1"
git pull --rebase origin main && git push origin main
````

**Evidence:** export → `bob_sessions/exports/P4-1-verify.md` plus 1 screenshot, then run the evidence snippet.

### P4-2 · Person 4 · demo website: skeleton + run-replay dashboard
| Start when | Mode | Budget | You'll see at the end |
|---|---|---|---|
| P4-1 pushed | Advanced, new task | ≈3 coins | `tests/website` all passed; the site runs locally with the sample run |

````text
[SyncSnitch P4-2 · Person 4 · budget ≈3 Bobcoins]

CONTEXT
The public demo website for judges (Vercel, Root Directory = web/). This prompt builds the skeleton and the RUN REPLAY
dashboard; prompt P4-3 adds the live contract matrix and the try-it sandbox. Already present, do not edit:
web/vercel.json, web/requirements.txt, web/.python-version and web/api/index.py (it puts web/ on sys.path and imports
"webapp.main:app"). A run artifact is web/runs/<run_id>.json with keys run_id, created_at, upstream_pr_url,
companion_pr_url, branch, drift {changes[], summary}, candidates {hits[], summary}, impact, verification {checks[],
summary}, verdict, diff, diffstat, steps [{id, name, type, status}], bob_session_export - any key may be null.
Repo: ~/hack/syncsnitch.

RULES
1. Do not explore or search; the only existing file you may open is web/api/index.py.
2. Create ONLY web/webapp/, web/templates/, web/static/, web/runs/_sample.json and tests/website/ (no __init__.py;
   test files named test_site_*.py). Never touch other paths, pyproject.toml or uv.lock.
3. Relative imports inside web/webapp/. Several files per turn; never print file contents. Final reply at most 10 lines.
4. Run ACCEPTANCE once; fix at most 2 times, then STOP and report.

BUILD
- web/webapp/__init__.py (empty) and web/webapp/main.py: app = FastAPI(title="SyncSnitch demo"); Jinja2Templates for
  web/templates and StaticFiles at /static for web/static (paths computed from __file__). Use the current Starlette
  signature templates.TemplateResponse(request, "<page>.html", {...}). Routes:
    GET /  -> home: the pitch in 3 lines ("An upstream team changed a contract. SyncSnitch found every downstream break,
              generated a backward-compatible fix, proved it in containers and opened a draft PR after a human
              approved."), the S1-S9 pipeline as pure HTML/CSS, buttons to /runs, /matrix and /try.
    GET /runs -> runs from web/runs/*.json, newest first; files starting with "_" are listed only when there is no
              other run (labelled "sample").
    GET /runs/{run_id} -> header with links (upstream PR, companion PR, bob_sessions export); S1-S9 timeline with
              badges deterministic / AI / human; drift table grouped by surface (REST, gRPC, DB) with breaking rows
              highlighted; impact map as a Mermaid "graph LR" (change -> file -> endpoint) using
              https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js ; the diff rendered with diff2html
              (https://cdn.jsdelivr.net/npm/diff2html/bundles/js/diff2html-ui.min.js and
              https://cdn.jsdelivr.net/npm/diff2html/bundles/css/diff2html.min.css); the verification table V1-V6 with
              ✅/❌/⏭️. Unknown run -> the 404 page.
    GET /api/runs, GET /api/runs/{run_id} -> the JSON.  GET /health -> {"status": "ok"}.
    GET /matrix and GET /try -> a simple "coming in P4-3" page (P4-3 replaces them).
- web/templates/: base.html (nav: Home, Runs, Matrix, Try it, GitHub https://github.com/kshiti26-11/demo; footer
  "Built with IBM Bob · evidence in bob_sessions/"), home.html, runs.html, run_detail.html, not_found.html,
  coming_soon.html. Clean, readable, mobile-friendly, light/dark via prefers-color-scheme, no build step, no JS framework.
- web/static/style.css.
- web/runs/_sample.json: a realistic sample (run_id "_sample") with the 9 breaking changes of the Orders v2 demo
  (REST property_removed Order.customer_name and Order.total_price, enum_value_removed OrderStatus.PENDING; gRPC
  field_removed orders.OrderSummary.2 and .3, enum_value_renamed orders.OrderStatus.1; DB column_renamed
  orders.customer_name, column_dropped orders.total_price, value_renamed orders.status.PENDING), 3 impacted endpoints
  (POST /invoices/{order_id} loud, GET /payments/{order_id}/status silent, GET /reports/revenue loud), a short unified
  diff, verification V1-V6 all pass, steps S1-S9 done.
- tests/website/test_site_replay.py (insert web/ into sys.path, then TestClient(app)): / -> 200; /runs -> 200 and
  contains "sample"; /runs/_sample -> 200 and contains "V4" and "POST /invoices/{order_id}"; /runs/nope -> 404;
  /api/runs/_sample -> run_id "_sample"; /health -> ok.

ACCEPTANCE (run once):
uv sync --frozen && uv run pytest -q tests/website    -> all passed

COMMIT & PUSH (run exactly):
git add web/webapp web/templates web/static web/runs/_sample.json tests/website
git commit -m "feat(web): demo site skeleton + run replay dashboard" -m "Bob-Session: P4-2"
git pull --rebase origin main && git push origin main
````

**Local preview (human, optional):** `cd ~/hack/syncsnitch/web && uv run --project .. uvicorn webapp.main:app --port 8080`, then open http://localhost:8080. **Evidence:** export → `bob_sessions/exports/P4-2-site-replay.md`, then screenshot the run page.

### P4-3 · Person 4 · live contract matrix + try-it sandbox + Vercel deploy
| Start when | Mode | Budget | You'll see at the end |
|---|---|---|---|
| P1-2, P2-1, P3-1, P4-2 pushed | Advanced, new task | ≈3 coins | `tests/website` all passed; the Vercel steps printed for you |

````text
[SyncSnitch P4-3 · Person 4 · budget ≈3 Bobcoins]

CONTEXT
Add the LIVE CONTRACT MATRIX and the TRY-IT SANDBOX to the demo site and prepare the Vercel deploy. Vendoring is done by
the existing, validated script scripts/vendor_demo_code.sh (do not edit it). It creates:
  web/_vendor/orders_v1/orders_service/    (orders-service at main = contract v1)
  web/_vendor/orders_v2/orders_service/    (orders-service at feat/orders-v2 = contract v2)
  web/_vendor/billing_before/billing/      (billing-service at main = before SyncSnitch)
  web/_vendor/billing_after/billing/       (billing-service after the companion PR; until then = main)
  web/_vendor/syncsnitch_engine/syncsnitch/  and web/_vendor/PINS.json
These packages use relative imports only. orders_service.rest.create_app(database_url, *, init_schema, seed) builds
the orders REST app; billing.api.create_app(orders_rest_url=..., orders_rest_transport=...) builds billing, whose REST
client accepts an httpx transport. The site must NEVER import grpc or any orders_pb2 module (two proto versions in one
process would clash). Repo: ~/hack/syncsnitch.

RULES: do not explore; the only existing files you may open are web/webapp/main.py and web/templates/base.html.
Create/modify ONLY web/** (never web/vercel.json, web/requirements.txt, web/api/index.py), tests/website/
(test_site_*.py) and the new scripts/build_tryit_scenarios.py and scripts/smoke_demo_url.py. Several files per turn;
never print file contents; run ACCEPTANCE once (max 2 fixes, then STOP); final reply at most 10 lines.

STEP 1 - vendor (run exactly):
cd ~/hack/syncsnitch && git -C ../orders-service fetch origin && git -C ../billing-service fetch origin
bash scripts/vendor_demo_code.sh main feat/orders-v2 main main

STEP 2 - web/webapp/vendor.py: load(alias, package_dir) with importlib.util.spec_from_file_location(alias,
<dir>/__init__.py, submodule_search_locations=[<dir>]), module_from_spec, sys.modules[alias] = module, exec_module;
aliases orders_v1, orders_v2, billing_before, billing_after, syncsnitch_engine -> the web/_vendor/ folders above.
Load lazily and cache.

STEP 3 - live contract matrix, web/webapp/matrix.py: orders apps = <alias>.rest.create_app("sqlite+pysqlite:///:memory:",
init_schema=True, seed=True) for v1 and v2 (build once). For billing in (before, after) x orders in (v1, v2) x order in
(o-1001 paid, o-1002 unpaid): billing app = <alias>.api.create_app(orders_rest_url="http://orders",
orders_rest_transport=httpx.ASGITransport(app=orders_app)); POST /invoices/{order} through
httpx.AsyncClient(transport=httpx.ASGITransport(app=billing_app, raise_app_exceptions=False), base_url="http://billing").
Cell = {status_code, body (first 200 chars), verdict}; verdict "ok" when (o-1001 -> 201 with total_minor 2164) or
(o-1002 -> 409), else "broken". Expected: before x v1 ok/ok, before x v2 broken/broken (HTTP 500); after = before until
the companion PR exists. Add GET /matrix (2x2 grid, green/red cells, the text "live REST calls, in-process") and
GET /api/matrix (JSON). Under the grid, "gRPC and DB (from the latest recorded container run)": the V3/V4 details of the
newest web/runs/*.json that has verification, if any.

STEP 4 - try-it sandbox: scripts/build_tryit_scenarios.py (run it once) creates web/scenarios/<name>/ for 4 scenarios
from contracts/reference/: rest_field_rename (v1 openapi vs v1 with customer_name renamed customer_full_name),
rest_enum_rename (v1 vs v1 with PENDING renamed AWAITING_PAYMENT), grpc_fields_removed (v1 vs v2 orders.proto, saved as
old.binpb / new.binpb via syncsnitch.detect.proto.compile_proto), db_column_changes (the 0002 migration file).
web/webapp/tryit.py: run(scenario) -> {"changes": [...], "hits": [...]} using the VENDORED engine
(syncsnitch_engine.detect.openapi.diff_openapi / .proto.diff_descriptor_sets / .migrations.diff_migrations, then
syncsnitch_engine.trace.trace_consumer(changes, web/_vendor/billing_before)). GET /try (4 scenario buttons, fetch
POST /api/try {"scenario": name}, render the changes and hits tables).

STEP 5 - scripts/smoke_demo_url.py <base_url> (httpx only, runnable with: uv run --no-project --with httpx python
scripts/smoke_demo_url.py <url>): check /health, /, /runs, /matrix, /api/matrix (before x v2 must be "broken"),
POST /api/try for all 4 scenarios (each returns at least 1 change). Print a table; exit 1 on any failure.

STEP 6 - tests/website/test_site_matrix.py and test_site_try.py: /api/matrix before x v1 ok and before x v2 broken;
/api/try returns changes for every scenario; afterwards "grpc" not in sys.modules and no module name ends with
"orders_pb2".

ACCEPTANCE (run once):
uv sync --frozen && uv run pytest -q tests/website    -> all passed

COMMIT & PUSH (run exactly):
git add web scripts/build_tryit_scenarios.py scripts/smoke_demo_url.py tests/website
git commit -m "feat(web): live contract matrix, try-it sandbox, vendored demo code" -m "Bob-Session: P4-3"
git pull --rebase origin main && git push origin main

Finally print these manual Vercel steps for me (do not run them): vercel.com -> Add New Project -> import
kshiti26-11/demo -> Root Directory "web" -> Framework preset "Other" -> Deploy. Then GitHub kshiti26-11/demo ->
Settings -> Secrets and variables -> Actions -> Variables -> New variable DEMO_URL = <production URL>. Then run
uv run --no-project --with httpx python scripts/smoke_demo_url.py <production URL>
````

**Then (human, 0 coins):** do the Vercel steps. Make sure the production URL is **public**: Settings → Deployment Protection → off for production. Run the smoke test and screenshot the matrix → `bob_sessions/screenshots/P4-3-1-matrix.png`. Export → `bob_sessions/exports/P4-3-site-matrix-tryit.md`.

### P3-3 · Person 3 · 🎬 THE HERO RUN (record your screen)
| Start when | Mode | Budget | You'll see at the end |
|---|---|---|---|
| All prompts above done and H-1 as expected | the command switches to 🕵️ SyncSnitch; new task | ≈6 coins | a **draft** companion PR in billing-service, linked from PR #1; its `contract-verify` check goes green |

**Checklist before you paste (human, 0 coins):**
```bash
cd ~/hack/syncsnitch && git pull --rebase origin main && uv sync --frozen
git -C ../orders-service fetch origin && git -C ../billing-service checkout main && git -C ../billing-service pull --ff-only
docker info >/dev/null && echo "docker OK"; gh auth status
bash scripts/reset_demo.sh            # dry run: shows what a reset would do (use --apply only for a re-run)
```
Then: start screen recording (for the video), open a **new task**, and paste:

````text
/syncsnitch https://github.com/kshiti26-11/orders-service/pull/1 ../billing-service
````

**What happens:**

| Step | What it does | Type | Coins |
|---|---|---|---|
| S0–S2 | Prepare, detect drift, trace the consumer | deterministic | 0 |
| S3 | 🔎 Tracer reads the change-proposal `.docx` and writes `impact.json` | subagent | spends coins |
| S4 | 🛠️ Transformer writes the tolerant reader on branch `syncsnitch/orders-service-pr1` | subagent | spends coins |
| S5 | Mock containers run v1 and v2, about 3–6 minutes | deterministic | 0 |
| S6 | ✅ Verifier returns a verdict | subagent | spends coins |
| **S7** | **Bob asks you** | human | 0 |
| S8 | Draft PR opens and PR #1 gets a link | deterministic | 0 |
| S9 | Run artifact is written | deterministic | 0 |

At **S7**, click **"Show full diff"** first (good for the video), then **"Approve & open draft PR"**.

**After the run (human, 0 coins):**
1. Open the companion PR URL. The `contract-verify` check runs the same containers in GitHub Actions and should go green (screenshot it).
2. Commit the run artifact so the website shows it:
   ```bash
   cd ~/hack/syncsnitch && git add web/runs/r-*.json && git commit -m "run: hero run artifact" -m "Bob-Session: P3-3" && git pull --rebase origin main && git push origin main
   ```
3. **Evidence (the most important one):**
   - Export → `bob_sessions/exports/P3-3-hero-run.md`.
   - Screenshots `P3-3-<n>-….png`: the mode picker, the subagents working, the verification table, the approval question, the draft PR, the green check, and Bobalytics.
   - Run the evidence snippet.
4. **If S5/S6 goes red twice:** stop. Show VERIFICATION.md to the team and use a fix prompt (§4) or the reserve. **Never fake a green run.**

### H-2 · Person 4 · show the "after" code on the website (human, 0 coins)
**Start when** P3-3 has opened the companion PR.
```bash
cd ~/hack/syncsnitch && git pull --rebase origin main && git -C ../billing-service fetch origin
bash scripts/vendor_demo_code.sh main feat/orders-v2 main syncsnitch/orders-service-pr1
git add web/_vendor && git commit -m "chore(web): vendor billing after SyncSnitch" && git pull --rebase origin main && git push origin main
# after Vercel redeploys (about 1 min):
uv run --no-project --with httpx python scripts/smoke_demo_url.py https://<your-project>.vercel.app
```
**Expected matrix:** before×v1 ✅, before×v2 ❌ (500), after×v1 ✅, **after×v2 ✅**. Screenshot → `bob_sessions/screenshots/H-2-matrix-after.png`.

### P3-4 · Person 3 · *(optional, 2 coins from the reserve)* final README + evidence index
**Skip this if the coins are short.** Humans can write the README from ARCHITECTURE.md instead.

````text
[SyncSnitch P3-4 · Person 3 · budget ≈2 Bobcoins]
Replace ~/hack/syncsnitch/README.md and fill the "Index" table at the end of bob_sessions/README.md. You may open only:
the first 80 lines of ARCHITECTURE.md, the top-level keys of the newest web/runs/r-*.json, and the file LISTS of
bob_sessions/exports/ and bob_sessions/screenshots/ (ls only - never open those files).
README sections: one-line pitch; 30-second overview; demo links (website <DEMO_URL>, video <VIDEO_URL>, upstream PR
https://github.com/kshiti26-11/orders-service/pull/1, companion PR <COMPANION_PR_URL>); the Mermaid architecture diagram
copied from ARCHITECTURE.md; "How IBM Bob is used" table (feature -> where -> evidence file in bob_sessions/);
quickstart (folder layout, uv sync --frozen, /syncsnitch <PR URL>); repo map; credits ("Planning docs, reference
contracts and scaffolding were prepared with Claude Code; all product code was built with IBM Bob from WORK.md").
Index table: one row per export file: Step | Person | What Bob built | Export | Screenshots.
Final reply at most 5 lines. Then run exactly:
git add README.md bob_sessions/README.md && git commit -m "docs: final README and bob_sessions index" -m "Bob-Session: P3-4" && git pull --rebase origin main && git push origin main
````

---

## 4. Fix-prompt template (F-n), only when a check fails
Use it for **one** failure at a time. Paste at most 30 lines of the error. Budget ≈1 coin per fix. Put the fix number in the ledger.

````text
[SyncSnitch F-<n> · Person <N> · budget ≈1 Bobcoin]
I am Person <N> in WORK.md. Fix ONLY this failure, touching only files that my prompt <P?-?> created:
<paste at most 30 lines of the failing output>
Rules: do not explore; open only the files named in the error; make the smallest possible fix; run
<the ACCEPTANCE command of my prompt> once; at most 2 attempts, then STOP and report; final reply at most 5 lines.
Then run exactly: git add <the files you changed> && git commit -m "fix: <what>" -m "Bob-Session: F-<n>" && git pull --rebase && git push
````

**Common failures and who fixes them:**

| Symptom | Likely owner | Hint |
|---|---|---|
| `ImportError … orders_pb2` or `No module named 'app'` | 1 or 2 | the imports inside the package must be relative; rerun `scripts/gen_proto.py` / `regen_stubs.py` |
| `docker compose` build is slow or sends a huge context | 1 or 2 | the `.dockerignore` from the template must be committed |
| V2 fails after the hero run | 3 (Transformer rules) | the v2 fixture names must contain `v2`: `tests/fixtures/order_v2_*.json` |
| V6 fails | 3 | the Transformer edited a file outside `billing/`, `contracts/upstream/`, `tests/`, `scripts/` |
| Prism container exits immediately | 4 | the compose file must keep `--multiprocess=false` (it's in the frozen file) |
| Vercel 500 on `/matrix` | 4 | some module imported `grpc`/`orders_pb2`; REST modules must not import them |

---

## 5. Lean mode: when Bobalytics shows overspend
Apply these from the top down until the remaining plan fits the coins left:

| # | Cut | Saves | Instead |
|---|---|---|---|
| 1 | P2-2 (Ask-mode analysis) | ~1 | show the H-1 dry run in the video instead |
| 2 | P3-4 (final README by Bob) | ~2 | humans write the README from ARCHITECTURE.md |
| 3 | Try-it sandbox in P4-3 | ~1 | delete STEP 4 from the P4-3 prompt before pasting |
| 4 | S6 fix loop | ~2 | if the Verifier is red, fix by hand with F-n |
| 5 | A second hero run | ~6 | **record the first hero run**; reuse it for the video |
| never | S0–S9, H-1, `bob_sessions`, the draft companion PR, the video | | these are the submission |

---

## 6. Coin ledger (Person 3 updates it after every round from Bobalytics)

| Prompt | Budget | Actual | Running total | Notes |
|---|---|---|---|---|
| P1-1 | 3 | | | |
| P2-1 | 4 | | | |
| P3-1 | 5 | | | |
| P4-1 | 4 | | | **Round 1 total ≤ 20?** otherwise go lean (§5) |
| P1-2 | 2 | | | |
| P2-2 | 1 | | | optional |
| P3-2 | 1 | | | |
| P4-2 | 3 | | | |
| P4-3 | 3 | | | |
| P3-3 | 6 | | | hero run |
| F-… | ≤ 8 | | | reserve |
| **Total** | **40** | | | |

---

## 7. Who may touch what (this is why there are no merge conflicts)

| Path | Owner | Notes |
|---|---|---|
| `kshiti26-11/orders-service` (whole repo) | **Person 1** | branch `main` (v1) + branch `feat/orders-v2` (PR #1) |
| `kshiti26-11/billing-service` (whole repo) | **Person 2** | SyncSnitch's Transformer writes only on branches `syncsnitch/*` |
| `syncsnitch/{cli.py,gitutil.py,detect,trace,report,runs}`, `tests/engine/`, `.bob/`, `web/runs/r-*.json`, final `README.md` | **Person 3** | |
| `syncsnitch/verify/`, `tests/verify/`, `tests/website/`, `web/**` (except `web/runs/r-*.json`), `scripts/build_tryit_scenarios.py`, `scripts/smoke_demo_url.py` | **Person 4** | |
| `bob_sessions/exports/P<N>-*`, `bob_sessions/screenshots/P<N>-*` | each person, own prefix | `bob_sessions/raw/` files are per-device (hook logger) |
| `pyproject.toml`, `uv.lock`, `.gitignore`, `.bobignore`, `syncsnitch/__init__.py`, `syncsnitch.code-workspace`, `contracts/reference/`, `templates/`, `verify/docker-compose.yml`, `.github/workflows/`, `scripts/*.sh`, `scripts/bob_hooks/` | **frozen**, nobody | validated scaffolding. A change here needs the whole team's OK |

**Every push:** `git pull --rebase origin main` first. If a rebase ever conflicts, run `git rebase --abort` and tell the team; don't resolve it blindly. Never `git add -A` in this repo, and never force-push.

---

## 8. Non-Bob tasks (0 coins): media and submission
These don't need Bob. If the rules check (§1.6) allows it, other tools can help: watsonx.ai Granite for copy, or Claude for the script, deck outline and QA.

| Task | Owner | When (see WORKFLOW.md) | Output |
|---|---|---|---|
| Video script + shot list (3–4 min, or the rule limit) | Person 1 | after P1-2 | `docs/video-script.md` (optional) |
| Screen recording of the hero run + the website | Persons 3 and 4 | P3-3, H-2 | raw footage |
| Video edit (hook → break → SyncSnitch in Bob → approval → draft PR → green matrix → value) | Person 4 | after H-2 | video link |
| Slide deck (9 slides) + cover image (16:9) | Person 2 | after P2-2 | PDF + PNG |
| LICENSE (GitHub → Add file → choose a license template, e.g. Apache-2.0) | Person 3 | any time | `LICENSE` |
| `bob_sessions` completeness check (every prompt exported? hero screenshots?) | Person 2 | before submission | checklist ✅ |
| lablab submission (title, descriptions, tags, cover, video, deck, repo `kshiti26-11/demo`, demo URL) | Person 4 + Person 1 reads it back | at T+42 | submitted ✅ |

