"""CLI end to end: detect -> trace -> report -> run-artifact in real temporary git repos (no network)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from syncsnitch.cli import main

_REFS = Path(__file__).resolve().parent.parent.parent / "contracts" / "reference"

MINI_CONSUMER = {
    "api.py": (
        "from fastapi import FastAPI\n"
        "from entry import invoice_from_order_payload\n"
        "from payments import status_from_summary\n"
        "from revenue import run_revenue_report\n\n"
        "def create_app():\n"
        "    app = FastAPI()\n\n"
        "    @app.post(\"/invoices/{order_id}\")\n"
        "    async def create_invoice(order_id):\n"
        "        return invoice_from_order_payload({})\n\n"
        "    @app.get(\"/payments/{order_id}/status\")\n"
        "    def payment_status(order_id):\n"
        "        return status_from_summary(None)\n\n"
        "    @app.get(\"/reports/revenue\")\n"
        "    def revenue():\n"
        "        return run_revenue_report(\"x\")\n\n"
        "    return app\n"
    ),
    "models.py": "from pydantic import BaseModel\n\nclass OrderDTO(BaseModel):\n    customer_name: str\n    total_price: float\n",
    "invoice.py": (
        "NOT_PAYABLE = {\"PENDING\", \"CANCELLED\"}\n\n"
        "def build_invoice(order):\n"
        "    return None if order.status in NOT_PAYABLE else order.total_price\n"
    ),
    "entry.py": (
        "from invoice import build_invoice\nfrom models import OrderDTO\n\n"
        "def invoice_from_order_payload(p):\n    return build_invoice(OrderDTO.model_validate(p))\n"
    ),
    "payments.py": "def status_from_summary(s):\n    return s.total_price\n",
    "revenue.sql": "SELECT SUM(total_price) FROM orders\n",
    "revenue.py": "SQL_FILE = \"revenue.sql\"\n\ndef run_revenue_report(url):\n    return SQL_FILE\n",
}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def make_upstream(root: Path, sub: str = "") -> Path:
    """Orders upstream: contract v1 on main, v2 (+ migration 0002) on feat/v2. ``sub`` = monorepo sub-folder."""
    root.mkdir(parents=True)
    git(root, "init", "-b", "main")
    svc = root / sub
    (svc / "contracts").mkdir(parents=True)
    (svc / "migrations" / "versions").mkdir(parents=True)
    shutil.copy(_REFS / "v1" / "openapi.yaml", svc / "contracts" / "openapi.yaml")
    shutil.copy(_REFS / "v1" / "orders.proto", svc / "contracts" / "orders.proto")
    shutil.copy(_REFS / "migrations" / "0001_create_orders.py", svc / "migrations" / "versions")
    git(root, "add", ".")
    git(root, "commit", "-m", "v1")
    git(root, "checkout", "-b", "feat/v2")
    shutil.copy(_REFS / "v2" / "openapi.yaml", svc / "contracts" / "openapi.yaml")
    shutil.copy(_REFS / "v2" / "orders.proto", svc / "contracts" / "orders.proto")
    shutil.copy(_REFS / "migrations" / "0002_money_customer_status.py", svc / "migrations" / "versions")
    git(root, "add", ".")
    git(root, "commit", "-m", "v2")
    git(root, "checkout", "main")
    return svc


def make_consumer(root: Path) -> Path:
    root.mkdir(parents=True)
    for name, text in MINI_CONSUMER.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def test_detect_trace_report(tmp_path, capsys):
    up = make_upstream(tmp_path / "up")
    consumer = make_consumer(tmp_path / "consumer")
    runs = tmp_path / "runs"

    assert main(["detect", "--upstream", str(up), "--base", "main", "--head", "feat/v2",
                 "--run-id", "t1", "--runs-dir", str(runs)]) == 0
    assert "RUN_ID=t1" in capsys.readouterr().out
    drift = json.loads((runs / "t1" / "drift.json").read_text())
    assert drift["summary"]["breaking"] == 9
    assert {s: sum(c["breaking"] for c in drift["changes"] if c["surface"] == s) for s in ("rest", "grpc", "db")} == {
        "rest": 3, "grpc": 3, "db": 3}

    assert main(["trace", "--run-id", "t1", "--consumer", str(consumer), "--runs-dir", str(runs)]) == 0
    hits = json.loads((runs / "t1" / "candidates.json").read_text())["hits"]

    def endpoints(file: str, token: str) -> list[str]:
        return sorted({e for h in hits if h["file"] == file and h["token"] == token for e in h["endpoints"]})

    assert endpoints("invoice.py", "PENDING") == ["POST /invoices/{order_id}"]
    assert endpoints("payments.py", "total_price") == ["GET /payments/{order_id}/status"]
    assert endpoints("revenue.sql", "total_price") == ["GET /reports/revenue"]
    assert endpoints("models.py", "customer_name") == ["POST /invoices/{order_id}"]
    assert endpoints("models.py", "total_price") == ["POST /invoices/{order_id}"]
    assert len({(h["file"], h["line"], h["token"], h["usage_kind"]) for h in hits}) == len(hits), "duplicate hits"

    assert main(["report", "--run-id", "t1", "--format", "pr", "--runs-dir", str(runs)]) == 0
    body = (runs / "t1" / "pr_body.md").read_text()
    assert "## Contract drift" in body and "## Rollout plan" in body

    assert main(["report", "--run-id", "t1", "--format", "comment", "--runs-dir", str(runs)]) == 0
    assert (runs / "t1" / "comment.md").read_text().startswith("<!-- syncsnitch -->")


def test_detect_in_a_monorepo_subfolder(tmp_path):
    """kshiti26-11/demo layout: the upstream is orders-service/ inside a bigger repo."""
    mono = tmp_path / "mono"
    make_upstream(mono, sub="orders-service")
    (mono / "billing-service").mkdir()
    runs = tmp_path / "runs"
    assert main(["detect", "--upstream", str(mono / "orders-service"), "--base", "main", "--head", "feat/v2",
                 "--run-id", "m1", "--runs-dir", str(runs)]) == 0
    assert json.loads((runs / "m1" / "drift.json").read_text())["summary"]["breaking"] == 9


def test_run_artifact(tmp_path):
    up = make_upstream(tmp_path / "up")
    consumer = make_consumer(tmp_path / "consumer")
    git(consumer, "init", "-b", "main")
    git(consumer, "add", ".")
    git(consumer, "commit", "-m", "consumer v1")
    git(consumer, "checkout", "-b", "syncsnitch/orders-service-pr1")
    (consumer / "payments.py").write_text("def status_from_summary(s):\n    return s.total.amount_minor\n")
    git(consumer, "commit", "-am", "tolerant reader")

    runs, out = tmp_path / "runs", tmp_path / "web-runs"
    assert main(["detect", "--upstream", str(up), "--base", "main", "--head", "feat/v2",
                 "--run-id", "t2", "--runs-dir", str(runs)]) == 0
    assert main(["run-artifact", "--run-id", "t2", "--consumer", str(consumer),
                 "--branch", "syncsnitch/orders-service-pr1", "--runs-dir", str(runs), "--out-dir", str(out)]) == 0
    art = json.loads((out / "t2.json").read_text())
    assert art["drift"]["summary"]["breaking"] == 9
    assert "amount_minor" in art["diff"]
    assert [s["id"] for s in art["steps"]] == [f"S{i}" for i in range(1, 10)]
    assert {s["id"]: s["status"] for s in art["steps"]}["S4"] == "done"


def test_verify_is_delegated(capsys):
    assert main(["verify", "--help"]) == 0
    assert "--no-containers" in capsys.readouterr().out
    assert main(["verify"]) == 2  # missing required arguments


@pytest.mark.parametrize("cmd", ["detect", "trace", "report", "run-artifact"])
def test_help(cmd):
    with pytest.raises(SystemExit) as exc:
        main([cmd, "--help"])
    assert exc.value.code == 0
