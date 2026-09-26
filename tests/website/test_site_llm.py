"""API models as the agent engine (Grok via the xAI Responses API, Claude via the Anthropic Messages API): the same
runner, the same agent definitions, instead of IBM Bob Shell. The APIs are faked (httpx MockTransport) by one scripted
model that plays each agent; git, the clone, the tools and their sandbox are real."""
import io
import json
import re
import sys
import zipfile

import httpx
import pytest

from web.webapp import agents, live, llm_agent
from tests.website.test_site_agents import RUN_ID, env, git, run_agents  # noqa: F401 - env is a fixture

USAGE = 1700  # tokens per fake response


def plan(agent: str, prompt: str, turn: int) -> tuple[list[tuple], bool]:
    """What the scripted model does: a list of ("text", str) / ("call", id, name, args), and whether it is done."""
    if agent == "tracer":
        run = re.search(r"Read (\S+?)/drift\.json", prompt).group(1)
        cons = re.search(r"Consumer: (\S+?)\.\n", prompt).group(1)
        if turn == 0:
            return [("text", "Reading the **drift** first."), ("call", "c1", "read_file", {"path": f"{run}/drift.json"}),
                    ("call", "c2", "read_file", {"path": f"{run}/change-proposal.md"})], False
        if turn == 1:
            impact = {"run_id": RUN_ID, "endpoints": [{"endpoint": "POST /invoices/{order_id}", "failure": "loud"},
                                                      {"endpoint": "GET /payments/{order_id}/status",
                                                       "failure": "silent"}]}
            return [("call", "c3", "write_file", {"path": f"{cons}/app.py", "content": "hacked"}),
                    ("call", "c4", "write_file", {"path": f"{run}/impact.json", "content": json.dumps(impact)})], False
        return [("text", "2 endpoints break: 1 loud, 1 silent.")], True
    if agent == "transformer":
        cons = re.search(r"cd (\S+) && uv run pytest", prompt).group(1)
        up = re.search(r"UPSTREAM=(\S+?),", prompt).group(1)
        commit = re.search(r"Commit on \S+: (cd .+)", prompt).group(1)
        if turn == 0:
            return [("call", "c5", "read_file", {"path": ".bob/rules-syncsnitch-transformer/tolerant-reader.md"}),
                    ("call", "c6", "edit_file", {"path": f"{cons}/app.py", "old_text": "NOT_PAYABLE = {'PENDING'}",
                                                 "new_text": "NOT_PAYABLE = {'PENDING', 'AWAITING_PAYMENT'}"}),
                    ("call", "c7", "write_file", {"path": f"{up}/contracts/openapi.yaml", "content": "broken"}),
                    ("call", "c8", "read_file", {"path": ".env.local"})], False
        if turn == 1:
            return [("call", "c9", "run", {"command": f"git -C {up} show HEAD:./contracts/openapi.yaml"}),
                    ("call", "c10", "run", {"command": "rm -rf /"}),
                    ("call", "c11", "run", {"command": f"git -C {up} commit -am x"}),
                    ("call", "c12", "run", {"command": commit})], False
        return [("text", "1 file changed, 1 insertion, 1 deletion")], True
    run = re.search(r"Read (\S+?)/verification\.json", prompt).group(1)
    if turn == 0:
        return [("call", "c13", "read_file", {"path": f"{run}/verification.json"})], False
    if turn == 1:
        verdict = {"run_id": RUN_ID, "verdict": "green", "reasons": ["executed checks passed; V3-V5 skipped"],
                   "fix_instructions": []}
        return [("call", "c14", "write_file", {"path": f"{run}/verdict.json", "content": json.dumps(verdict)})], False
    return [("text", "GREEN: executed checks passed")], True


def agent_of(system: str) -> str:
    return ("tracer" if "Schema Diff & AST Tracer" in system else
            "transformer" if "Downstream Code Transformer" in system else "verifier")


class FakeClaude:
    """Anthropic Messages API: the whole conversation arrives every turn."""
    provider = "claude"

    def __init__(self):
        self.requests: list[dict] = []

    def results(self) -> dict:
        return {b["tool_use_id"]: {"content": b["content"], "error": bool(b.get("is_error"))}
                for q in self.requests for m in q["body"]["messages"] if m["role"] == "user"
                for b in m["content"] if b.get("type") == "tool_result"}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"url": str(request.url), "headers": dict(request.headers), "body": body})
        agent = agent_of(body["system"][0]["text"])
        turn = sum(1 for m in body["messages"] if m["role"] == "assistant")
        items, done = plan(agent, body["messages"][0]["content"][0]["text"], turn)
        content = [{"type": "text", "text": i[1]} if i[0] == "text" else
                   {"type": "tool_use", "id": i[1], "name": i[2], "input": i[3]} for i in items]
        return httpx.Response(200, json={"id": f"msg_{agent}_{turn}", "type": "message", "role": "assistant",
                                         "content": content, "stop_reason": "end_turn" if done else "tool_use",
                                         "usage": {"input_tokens": 1000, "output_tokens": 200,
                                                   "cache_read_input_tokens": 500}})


class FakeGrok:
    """xAI Responses API: the server keeps the conversation; follow-ups carry previous_response_id."""
    provider = "grok"

    def __init__(self):
        self.requests: list[dict] = []
        self.threads: dict[str, tuple[str, str, int]] = {}  # response id -> (agent, prompt, turn)

    def results(self) -> dict:
        return {i["call_id"]: {"content": i["output"], "error": i["output"].startswith("ERROR: ")}
                for q in self.requests for i in q["body"]["input"] if i.get("type") == "function_call_output"}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"url": str(request.url), "headers": dict(request.headers), "body": body})
        if body.get("previous_response_id"):
            agent, prompt, turn = self.threads[body["previous_response_id"]]
            turn += 1
        else:
            agent, prompt, turn = agent_of(body["instructions"]), body["input"][0]["content"], 0
        items, done = plan(agent, prompt, turn)
        rid = f"resp_{agent}_{turn}_{len(self.requests)}"
        self.threads[rid] = (agent, prompt, turn)
        output = [{"type": "reasoning", "id": "rs_1", "summary": []}]
        output += [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": i[1]}]}
                   if i[0] == "text" else
                   {"type": "function_call", "id": f"fc_{i[1]}", "call_id": i[1], "name": i[2],
                    "arguments": json.dumps(i[3])} for i in items]
        return httpx.Response(200, json={"id": rid, "object": "response", "status": "completed", "output": output,
                                         "usage": {"input_tokens": 1500, "output_tokens": 200, "total_tokens": USAGE,
                                                   "input_tokens_details": {"cached_tokens": 500}}})


class FakeGemini:
    """OpenAI-compatible chat completions: the whole conversation arrives every turn; tool calls carry a thought
    signature that must come back unchanged."""
    provider = "gemini"

    def __init__(self):
        self.requests: list[dict] = []

    def results(self) -> dict:
        return {m["tool_call_id"]: {"content": m["content"], "error": m["content"].startswith("ERROR: ")}
                for q in self.requests for m in q["body"]["messages"] if m["role"] == "tool"}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"url": str(request.url), "headers": dict(request.headers), "body": body})
        msgs = body["messages"]
        agent, prompt = agent_of(msgs[0]["content"]), msgs[1]["content"]
        turn = sum(1 for m in msgs if m["role"] == "assistant")
        for m in msgs:  # every earlier assistant turn comes back with its signatures intact
            for call in m.get("tool_calls") or []:
                assert call["extra_content"] == {"google": {"thought_signature": f"sig-{call['id']}"}}
        items, done = plan(agent, prompt, turn)
        texts = [i[1] for i in items if i[0] == "text"]
        calls = [{"id": i[1], "type": "function", "function": {"name": i[2], "arguments": json.dumps(i[3])},
                  "extra_content": {"google": {"thought_signature": f"sig-{i[1]}"}}} for i in items if i[0] == "call"]
        message = {"role": "assistant", "content": "\n".join(texts) or None, **({"tool_calls": calls} if calls else {})}
        return httpx.Response(200, json={"id": f"chat_{agent}_{turn}", "object": "chat.completion",
                                         "choices": [{"index": 0, "message": message,
                                                      "finish_reason": "stop" if done else "tool_calls"}],
                                         "usage": {"prompt_tokens": 1500, "completion_tokens": 200,
                                                   "total_tokens": USAGE}})


@pytest.fixture(params=["gemini", "grok", "claude"])
def api(request, env, monkeypatch):  # noqa: F811 - the env fixture from test_site_agents
    provider = request.param
    monkeypatch.setenv("SYNCSNITCH_AGENT_BACKEND", provider)
    monkeypatch.setenv(llm_agent.PROVIDERS[provider]["key"], f"test-{provider}-key")
    for name in ("ANTHROPIC_BASE_URL", "XAI_BASE_URL", "OPENAI_BASE_URL"):  # the shell's own settings are ignored
        monkeypatch.setenv(name, "http://127.0.0.1:1/not-this")
    for name in ("SYNCSNITCH_ANTHROPIC_BASE_URL", "SYNCSNITCH_XAI_BASE_URL", "SYNCSNITCH_GEMINI_BASE_URL",
                 "SYNCSNITCH_TOKEN_BUDGET", "SYNCSNITCH_GROK_MODEL", "SYNCSNITCH_GEMINI_MODEL",
                 *(v["key"] for k, v in llm_agent.PROVIDERS.items() if k != provider)):
        monkeypatch.delenv(name, raising=False)
    fake = {"gemini": FakeGemini, "grok": FakeGrok, "claude": FakeClaude}[provider]()
    monkeypatch.setattr(llm_agent, "_client", lambda: httpx.Client(transport=httpx.MockTransport(fake)))
    return fake


def test_the_three_agents_run_on_an_api_model_with_the_same_definitions(env, api):  # noqa: F811
    provider = api.provider
    label, model = llm_agent.PROVIDERS[provider]["label"], llm_agent.PROVIDERS[provider]["default_model"]
    s = run_agents(env)
    assert (s["phase"], s["verifier"]["verdict"], s["transformer"]["commits"]) == ("approval", "green", 1)
    r = s["runner"]
    assert (r["backend"], r["label"], r["model"], r["unit"], r["budget"]) == (provider, label, model, "tokens",
                                                                              3_000_000.0)
    assert r["spent"] == 9 * USAGE and r["spent_by"] == {"tracer": 3 * USAGE, "transformer": 3 * USAGE,
                                                         "verifier": 3 * USAGE}
    reqs = api.requests
    assert {q["url"] for q in reqs} == {llm_agent.PROVIDERS[provider]["base"] + llm_agent.PROVIDERS[provider]["path"]}
    assert {q["body"]["model"] for q in reqs} == {model}

    # the sandbox said no, and the model saw why
    res = api.results()
    assert res["c3"]["error"] and "may only write" in res["c3"]["content"]
    assert res["c7"]["error"] and res["c8"]["error"] and res["c10"]["error"] and res["c11"]["error"]
    assert "version: 2" in res["c9"]["content"] and "(exit 0)" in res["c12"]["content"]
    assert "Roll out behind a flag" in res["c2"]["content"]
    assert (env["tmp"] / "work" / RUN_ID / "up" / "contracts" / "openapi.yaml").read_text() == "version: 2\n"

    log = git(env["tmp"] / "work" / RUN_ID, "log", "-1", "--format=%B")
    assert log.startswith("fix(contract): tolerant reader for the up contract change")
    assert f"SyncSnitch-Agent: {label} {model} ({RUN_ID})" in log and "Bob-Session" not in log
    lines = [e["msg"] for e in s["events"] if e.get("src") == provider]
    assert f"{label} ({model}) · agent syncsnitch-tracer · budget 900,000 tokens" in lines
    assert "Reading the drift first." in lines
    assert any(m.startswith("write_file refused:") for m in lines)
    assert any(m.startswith(f"{label} session finished: 4 tool calls · 3 turns · 5,100 tokens") for m in lines)
    assert any(m.startswith(f"S1-S2 done: starting the 3 agents on {label} ({model})")
               for m in (e["msg"] for e in s["events"]))


def test_grok_requests_use_the_responses_api(env, api):  # noqa: F811
    if api.provider != "grok":
        pytest.skip("xAI only")
    run_agents(env)
    first, follow = api.requests[0], api.requests[1]
    assert first["headers"]["authorization"] == "Bearer test-grok-key" and "x-api-key" not in first["headers"]
    assert first["body"]["store"] is True and first["body"]["input"][0]["role"] == "user"
    instructions = first["body"]["instructions"]
    assert "Schema Diff & AST Tracer" in instructions and "not inside IBM Bob" in instructions
    assert "xAI Grok" in instructions and "SyncSnitch guardrails" in instructions
    assert [t["name"] for t in first["body"]["tools"]] == ["read_file", "list_dir", "search", "write_file"]
    assert all(t["type"] == "function" and t["parameters"]["type"] == "object" for t in first["body"]["tools"])
    assert follow["body"]["previous_response_id"] == "resp_tracer_0_1"
    assert [i["type"] for i in follow["body"]["input"]] == ["function_call_output", "function_call_output"]
    transformer = next(q for q in api.requests if "Downstream Code Transformer" in q["body"].get("instructions", ""))
    assert "Tolerant-reader rules for the Downstream Code Transformer" in transformer["body"]["instructions"]
    assert [t["name"] for t in transformer["body"]["tools"]][-2:] == ["edit_file", "run"]


def test_gemini_requests_use_openai_compatible_chat(env, api):  # noqa: F811
    if api.provider != "gemini":
        pytest.skip("Gemini only")
    run_agents(env)  # FakeGemini itself asserts that every thought signature came back unchanged
    first, follow = api.requests[0], api.requests[1]
    assert first["headers"]["authorization"] == "Bearer test-gemini-key"
    assert first["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert [m["role"] for m in first["body"]["messages"]] == ["system", "user"]
    assert "Google Gemini" in first["body"]["messages"][0]["content"]
    assert all(t["type"] == "function" and t["function"]["parameters"]["type"] == "object"
               for t in first["body"]["tools"])
    assert [m["role"] for m in follow["body"]["messages"]] == ["system", "user", "assistant", "tool", "tool"]


def test_claude_requests_use_the_messages_api(env, api):  # noqa: F811
    if api.provider != "claude":
        pytest.skip("Anthropic only")
    run_agents(env)
    q = api.requests[0]
    assert q["headers"]["x-api-key"] == "test-claude-key" and q["headers"]["anthropic-version"] == "2023-06-01"
    assert q["body"]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert all(r["body"]["messages"][-1]["content"][-1].get("cache_control") for r in api.requests)


def test_a_rejected_key_stops_the_run_with_the_reason(env, api, monkeypatch):  # noqa: F811
    p = llm_agent.PROVIDERS[api.provider]
    monkeypatch.setattr(llm_agent, "_client", lambda: httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(401, json={"error": {"type": "authentication_error", "message": "invalid key"}}))))
    monkeypatch.setattr(llm_agent.time, "sleep", lambda s: None)
    s = run_agents(env)
    assert s["phase"] == "failed" and s["tracer"]["status"] == "failed"
    assert f"{p['label']} API 401: invalid key (check {p['key']} in .env.local)" in s["runner"]["error"]


def test_the_token_cap_stops_a_runaway_agent(env, api, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SYNCSNITCH_TOKEN_BUDGET", "100000")  # the Tracer may use 30,000 tokens
    monkeypatch.setattr(llm_agent, "MAX_TURNS", {**llm_agent.MAX_TURNS, "tracer": 40})
    real_plan = plan

    def forever(agent, prompt, turn):  # the Tracer never finishes
        return ([("call", f"x{turn}", "list_dir", {"path": "."})], False) if agent == "tracer" else \
            real_plan(agent, prompt, turn)
    monkeypatch.setattr(sys.modules[__name__], "plan", forever)
    s = run_agents(env)
    assert s["phase"] == "failed" and "token cap reached (30,600 of 30,000 tokens)" in s["runner"]["error"]
    assert s["runner"]["spent"] == 30_600


def test_a_budget_too_small_for_an_agent_is_refused_before_any_call(env, api, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SYNCSNITCH_TOKEN_BUDGET", "60000")
    s = run_agents(env)
    assert "token budget for this run is used up (0 of 60,000 spent)" in s["runner"]["error"]
    assert api.requests == []


def test_a_used_up_daily_quota_says_so_instead_of_retrying(env, api, monkeypatch):  # noqa: F811
    hits = []

    def quota(request):
        hits.append(1)
        return httpx.Response(429, json={"error": {"code": 429, "message": "Quota exceeded for metric: "
                                                   "generate_content_free_tier_requests, limit: 20, "
                                                   "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"}})
    monkeypatch.setattr(llm_agent, "_client", lambda: httpx.Client(transport=httpx.MockTransport(quota)))
    s = run_agents(env)
    assert len(hits) == 1 and "the daily quota is used up" in s["runner"]["error"]


def test_a_rate_limit_waits_and_retries(env, api, monkeypatch):  # noqa: F811
    slept, calls = [], {"n": 0}
    real = api

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited",
                                                       "details": [{"retryDelay": "7s"}]}})
        return real(request)
    monkeypatch.setattr(llm_agent.time, "sleep", slept.append)
    monkeypatch.setattr(llm_agent, "_client", lambda: httpx.Client(transport=httpx.MockTransport(flaky)))
    s = run_agents(env)
    assert s["phase"] == "approval" and slept[0] == 7.0


def test_engine_choice():
    assert agents.choose_backend({"XAI_API_KEY": "k", "SYNCSNITCH_AGENT_BACKEND": "grok"}) == ("grok", [])
    assert agents.choose_backend({"XAI_API_KEY": "k"})[0] in ("bob", "grok")  # auto: the first engine set up
    assert agents.choose_backend({"GEMINI_API_KEY": "k", "SYNCSNITCH_AGENT_BACKEND": "gemini"}) == ("gemini", [])
    assert agents.choose_backend({"XAI_API_KEY": "k", "ANTHROPIC_API_KEY": "k",
                                  "SYNCSNITCH_AGENT_BACKEND": "claude"}) == ("claude", [])
    missing = agents.choose_backend({"SYNCSNITCH_AGENT_BACKEND": "grok"})[1]
    assert missing[0]["fix"] == "bash scripts/grok_setup.sh"


def test_the_shell_s_base_urls_are_ignored(monkeypatch):
    for name in ("ANTHROPIC_BASE_URL", "XAI_BASE_URL", "OPENAI_BASE_URL", "GEMINI_BASE_URL"):
        monkeypatch.setenv(name, "http://proxy.example")
    for name in ("SYNCSNITCH_ANTHROPIC_BASE_URL", "SYNCSNITCH_XAI_BASE_URL", "SYNCSNITCH_GEMINI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert llm_agent.api_url("gemini") == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert llm_agent.api_url("grok") == "https://api.x.ai/v1/responses"
    assert llm_agent.api_url("claude") == "https://api.anthropic.com/v1/messages"
    monkeypatch.setenv("SYNCSNITCH_XAI_BASE_URL", "https://gateway.example/")
    assert llm_agent.api_url("grok") == "https://gateway.example/v1/responses"


def test_sandbox_rules(tmp_path):
    cons, up, run_dir = tmp_path / "work" / "cons", tmp_path / "work" / "up", tmp_path / "runs" / RUN_ID
    for d in (cons, up, run_dir):
        d.mkdir(parents=True)
    ctx = {"run_dir": run_dir, "cons_path": cons, "up_path": up, "up": "up", "work": tmp_path / "work"}
    box = llm_agent.Sandbox(ctx, "transformer")
    assert box._check(["uv", "run", "--frozen", "pytest", "-q"], cons)[:3] == ["uv", "run", "--frozen"]
    assert box._check(["git", "-C", str(up), "show", "HEAD:x"], cons)[2] == str(up.resolve())
    for bad in (["python", "-c", "1"], ["git", "-C", str(up), "commit"], ["git", "push"], ["uv", "pip", "install"],
                ["git", "-C", "/", "status"], ["git", "-c", "alias.e=!env", "e"]):
        with pytest.raises(llm_agent.ToolError):
            box._check(bad, cons)
    for command in ("git log | head", "git show x > f", "cd / && git status", "git status; ls", "echo $(id)"):
        with pytest.raises(llm_agent.ToolError):
            box.run(command)
    for path in (str(live.REPO_ROOT / ".env.local"), "/etc/hosts", str(live.REPO_ROOT / ".git" / "config")):
        with pytest.raises(llm_agent.ToolError):
            box.read_file(path)
    with pytest.raises(llm_agent.ToolError):
        llm_agent.Sandbox(ctx, "verifier").write_file(str(cons / "a.py"), "x")
    assert llm_agent.Sandbox(ctx, "verifier").write_file(str(run_dir / "verdict.json"), "{}").startswith("wrote")


def test_commands_never_see_api_keys(tmp_path, monkeypatch):
    for name in ("XAI_API_KEY", "ANTHROPIC_API_KEY", "BOB_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(name, "secret")
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw["env"])
        return type("P", (), {"stdout": "", "stderr": "", "returncode": 0})()
    monkeypatch.setattr(llm_agent.subprocess, "run", fake_run)
    ctx = {"run_dir": tmp_path, "cons_path": tmp_path, "up_path": tmp_path, "up": "", "work": tmp_path}
    llm_agent.Sandbox(ctx, "transformer").run("git status")
    assert seen and not any(k.startswith(("XAI", "ANTHROPIC", "BOB_", "GEMINI")) for k in seen)


def test_docx_proposals_are_read_as_text():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", '<w:document><w:body><w:p><w:r><w:t>Orders v2 &amp; rollout</w:t></w:r>'
                                         '</w:p><w:p><w:r><w:t>Dual-read for 2 weeks</w:t></w:r></w:p></w:body>'
                                         '</w:document>')
    assert llm_agent.docx_text(buf.getvalue()).splitlines() == ["Orders v2 & rollout", "Dual-read for 2 weeks"]
