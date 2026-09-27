"""API models as the SyncSnitch agent engine, instead of IBM Bob Shell: Gemini (Google), Groq, Grok (xAI) or Claude.

The same three agents with the same definitions: the role and instructions of each custom mode in
.bob/custom_modes.yaml plus the rules in .bob/rules/ and .bob/rules-<mode>/, run through the provider's API with a
few sandboxed tools. The runner (agents.py) calls run() for S3, S4 and S6 exactly as it calls `bob run`.

  gemini  Google, OpenAI-compatible chat  POST https://generativelanguage.googleapis.com/v1beta/openai/chat/completions
          (GEMINI_API_KEY, SYNCSNITCH_GEMINI_MODEL; has a free tier, whose content Google may use to improve products)
  groq    GroqCloud, OpenAI-compatible chat  POST https://api.groq.com/openai/v1/chat/completions
          (GROQ_API_KEY, SYNCSNITCH_GROQ_MODEL; free tier, fast open-weight models)
  grok    xAI Responses API     POST https://api.x.ai/v1/responses   (XAI_API_KEY, SYNCSNITCH_GROK_MODEL)
  claude  Anthropic Messages    POST https://api.anthropic.com/v1/messages (ANTHROPIC_API_KEY, SYNCSNITCH_CLAUDE_MODEL)

Sandbox: files are read only inside the workspace (never .env files or .git); the Tracer may write only impact.json,
the Verifier only verdict.json, the Transformer only files inside the consumer folder. The Transformer's `run` tool
accepts `uv run pytest`, `uv run python scripts/regen_stubs.py` and git (writes only inside the consumer), chained
with `&&` and `cd`, and nothing else (no pipes, redirects or other programs).

Keys and models live in .env.local (scripts/gemini_setup.sh, groq_setup.sh, grok_setup.sh, claude_setup.sh). The API
address can only be changed with SYNCSNITCH_GEMINI_BASE_URL / SYNCSNITCH_GROQ_BASE_URL / SYNCSNITCH_XAI_BASE_URL /
SYNCSNITCH_ANTHROPIC_BASE_URL; generic *_BASE_URL variables of the surrounding shell are deliberately ignored.
"""
from __future__ import annotations

import html
import json
import os
import re
import shlex
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml

from . import live

REPO_ROOT = live.REPO_ROOT
PROVIDERS = {
    "gemini": {"label": "Gemini", "vendor": "Google", "key": "GEMINI_API_KEY", "model_env": "SYNCSNITCH_GEMINI_MODEL",
               "default_model": "gemini-3.8-flash", "base_env": "SYNCSNITCH_GEMINI_BASE_URL",
               "base": "https://generativelanguage.googleapis.com", "path": "/v1beta/openai/chat/completions",
               "setup": "bash scripts/gemini_setup.sh", "console": "https://aistudio.google.com/apikey"},
    "groq": {"label": "Groq", "vendor": "Groq", "key": "GROQ_API_KEY", "model_env": "SYNCSNITCH_GROQ_MODEL",
             "default_model": "llama-3.1-8b-instant", "base_env": "SYNCSNITCH_GROQ_BASE_URL",
             "base": "https://api.groq.com", "path": "/openai/v1/chat/completions",
             "setup": "bash scripts/groq_setup.sh", "console": "https://console.groq.com/keys"},
    "grok": {"label": "Grok", "vendor": "xAI", "key": "XAI_API_KEY", "model_env": "SYNCSNITCH_GROK_MODEL",
             "default_model": "grok-4.7", "base_env": "SYNCSNITCH_XAI_BASE_URL", "base": "https://api.x.ai",
             "path": "/v1/responses", "setup": "bash scripts/grok_setup.sh", "console": "https://console.x.ai"},
    "claude": {"label": "Claude", "vendor": "Anthropic", "key": "ANTHROPIC_API_KEY",
               "model_env": "SYNCSNITCH_CLAUDE_MODEL", "default_model": "claude-opus-5-5", "base_env": "SYNCSNITCH_ANTHROPIC_BASE_URL",
               "base": "https://api.anthropic.com", "path": "/v1/messages", "setup": "bash scripts/claude_setup.sh",
               "console": "https://console.anthropic.com"},
}
ANTHROPIC_VERSION = "2023-06-01"
MAX_OUTPUT_TOKENS = 16000
MAX_TURNS = {"tracer": 30, "transformer": 60, "verifier": 12}
MODES = {"tracer": "syncsnitch-tracer", "transformer": "syncsnitch-transformer", "verifier": "syncsnitch-verifier"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}
SECRET_ENV = ("ANTHROPIC", "XAI", "OPENAI", "GEMINI", "GOOGLE_API", "GROQ", "BOB_", "GITHUB_TOKEN", "GH_TOKEN", "CLAUDE")
GIT_READ = {"status", "diff", "log", "show", "ls-files", "rev-parse", "blame"}
GIT_WRITE = {"add", "commit", "rm", "mv", "restore", "checkout"}
UV_FLAGS = {"--frozen", "--quiet", "-q", "--offline"}
COMMAND_TIMEOUT = 600


def model_of(provider: str, env: dict) -> str:
    p = PROVIDERS[provider]
    return env.get(p["model_env"]) or p["default_model"]


def api_url(provider: str) -> str:
    p = PROVIDERS[provider]
    return (os.environ.get(p["base_env"]) or p["base"]).rstrip("/") + p["path"]


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(300.0, connect=20.0))


@dataclass
class Result:
    """What one agent session left behind (same fields the runner reads from a Bob session)."""
    cost: int = 0  # tokens processed: input (cached or not) + output
    task_id: str | None = None
    errors: list[str] = field(default_factory=list)
    result: str = ""
    turns: int = 0


# ---------------------------------------------------------------------------
# The agent definitions (shared with IBM Bob)
# ---------------------------------------------------------------------------

def system_prompt(agent: str, provider: str, model: str) -> str:
    modes = yaml.safe_load((REPO_ROOT / ".bob" / "custom_modes.yaml").read_text(encoding="utf-8"))["customModes"]
    mode = next(m for m in modes if m["slug"] == MODES[agent])
    parts = [mode["roleDefinition"].strip(), mode.get("customInstructions", "").strip()]
    for folder in (REPO_ROOT / ".bob" / "rules", REPO_ROOT / ".bob" / f"rules-{MODES[agent]}"):
        for rule in (sorted(folder.glob("*.md")) if folder.is_dir() else []):
            parts.append(rule.read_text(encoding="utf-8").strip())
    p = PROVIDERS[provider]
    vendor = f"{p['vendor']} " if p["vendor"] != p["label"] else ""  # avoid "Groq Groq"
    parts.append(
        f"You are running as {model} ({vendor}{p['label']}) through the SyncSnitch website, not inside IBM "
        "Bob. Work only through the tools you are given. Paths are relative to the workspace root (the SyncSnitch "
        "repo). Do the one step you are asked for, never ask questions, keep replies short. If a rule mentions a "
        "Bob-Session commit trailer, use the trailer given in the task instead.")
    return "\n\n".join(p for p in parts if p)


def _tool(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": props, "required": required}}


def tool_specs(provider: str, names: list[str]) -> list[dict]:
    """The tool definitions in the provider's format (Anthropic: input_schema; xAI Responses: flat functions)."""
    if provider == "claude":
        return [TOOLS[n] for n in names]
    if provider in ("gemini", "groq"):  # OpenAI chat-completions shape
        return [{"type": "function", "function": {"name": TOOLS[n]["name"], "description": TOOLS[n]["description"],
                                                  "parameters": TOOLS[n]["input_schema"]}} for n in names]
    return [{"type": "function", "name": TOOLS[n]["name"], "description": TOOLS[n]["description"],
             "parameters": TOOLS[n]["input_schema"]} for n in names]


_PATH = {"type": "string", "description": "path relative to the workspace root"}
TOOLS = {
    "read_file": _tool("read_file", "Read a text file with line numbers (a .docx file is returned as plain text).",
                       {"path": _PATH, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, ["path"]),
    "list_dir": _tool("list_dir", "List a directory (non-recursive).", {"path": _PATH}, ["path"]),
    "search": _tool("search", "Search files under a directory for a regular expression; returns file:line: text.",
                    {"pattern": {"type": "string"}, "path": _PATH}, ["pattern", "path"]),
    "write_file": _tool("write_file", "Create or overwrite a file with the given content.",
                        {"path": _PATH, "content": {"type": "string"}}, ["path", "content"]),
    "edit_file": _tool("edit_file", "Replace one exact, unique occurrence of old_text with new_text in a file.",
                       {"path": _PATH, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
                       ["path", "old_text", "new_text"]),
    "run": _tool("run", "Run a command in the consumer folder. Allowed: `uv run pytest ...`, "
                        "`uv run python scripts/regen_stubs.py`, and git (status, diff, log, show, ls-files, add, "
                        "commit, rm, mv, restore); `git -C <upstream> show <ref>:<path>` reads the upstream. Chain "
                        "with && and cd. No pipes or redirects.", {"command": {"type": "string"}}, ["command"]),
}
AGENT_TOOLS = {"tracer": ["read_file", "list_dir", "search", "write_file"],
               "transformer": ["read_file", "list_dir", "search", "write_file", "edit_file", "run"],
               "verifier": ["read_file", "list_dir", "search", "write_file"]}


# ---------------------------------------------------------------------------
# Sandboxed tools
# ---------------------------------------------------------------------------

class ToolError(Exception):
    pass


def _within(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def _secret(p: Path) -> bool:
    name = p.name.lower()
    return name.startswith(".env") or any(m in name for m in ("secret", "id_rsa", ".pem"))


def docx_text(data: bytes) -> str:
    import io  # noqa: PLC0415

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


class Sandbox:
    def __init__(self, ctx: dict, agent: str):
        self.agent = agent
        self.run_dir = Path(ctx["run_dir"]).resolve()
        self.cons = Path(ctx["cons_path"]).resolve()
        self.up = Path(ctx["up_path"]).resolve() if ctx.get("up") else None
        self.read_roots = [REPO_ROOT.resolve(), Path(ctx["work"]).resolve(), self.run_dir]
        self.write_files = {"tracer": [self.run_dir / "impact.json"],
                            "verifier": [self.run_dir / "verdict.json"]}.get(agent, [])

    def path(self, raw: str) -> Path:
        p = Path(str(raw).strip())
        return (p if p.is_absolute() else REPO_ROOT / p).resolve()

    def _dir(self, raw: str, cwd: Path) -> Path:
        """A directory argument: relative to the current directory if it exists there, else to the workspace root."""
        p = Path(raw)
        if p.is_absolute():
            return p.resolve()
        here = (cwd / p).resolve()
        return here if here.exists() else (REPO_ROOT / p).resolve()

    def readable(self, raw: str) -> Path:
        p = self.path(raw)
        if not any(_within(p, r) for r in self.read_roots) or _secret(p) or ".git" in p.parts:
            raise ToolError(f"{raw}: outside what this agent may read")
        return p

    def writable(self, raw: str) -> Path:
        p = self.path(raw)
        ok = p in self.write_files or (self.agent == "transformer" and _within(p, self.cons)
                                       and not (self.up and _within(p, self.up)))
        if not ok or _secret(p) or ".git" in p.parts:
            allowed = ", ".join(str(f) for f in self.write_files) or f"files inside {self.cons}"
            raise ToolError(f"{raw}: this agent may only write {allowed}")
        return p

    # --- tools ---
    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
        p = self.readable(path)
        if not p.is_file():
            raise ToolError(f"{path}: no such file")
        data = p.read_bytes()
        text = docx_text(data) if p.suffix.lower() == ".docx" else data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        start = max(1, int(start_line or 1))
        end = min(len(lines), int(end_line or start + 1999))
        body = "\n".join(f"{i:5}  {lines[i - 1]}" for i in range(start, end + 1))
        more = f"\n... ({len(lines) - end} more lines; use start_line)" if end < len(lines) else ""
        return (body + more)[:120_000] or "(empty file)"

    def list_dir(self, path: str) -> str:
        p = self.readable(path)
        if not p.is_dir():
            raise ToolError(f"{path}: not a directory")
        rows = [f"{c.name}/" if c.is_dir() else c.name for c in sorted(p.iterdir())
                if c.name not in SKIP_DIRS and not _secret(c)]
        return "\n".join(rows[:500]) or "(empty)"

    def search(self, pattern: str, path: str) -> str:
        root = self.readable(path)
        try:
            rx = re.compile(pattern)
        except re.error as e:
            raise ToolError(f"bad regular expression: {e}") from e
        hits = []
        files = [root] if root.is_file() else (f for f in root.rglob("*") if f.is_file())
        for f in files:
            if SKIP_DIRS & set(f.parts) or _secret(f) or f.stat().st_size > 1_000_000:
                continue
            try:
                for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{f.relative_to(REPO_ROOT) if _within(f, REPO_ROOT) else f}:{n}: {line[:200]}")
                        if len(hits) >= 200:
                            return "\n".join(hits) + "\n... (first 200 matches)"
            except (UnicodeDecodeError, OSError):
                continue
        return "\n".join(hits) or "no matches"

    def write_file(self, path: str, content: str) -> str:
        p = self.writable(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"wrote {path} ({len(content.splitlines())} lines)"

    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        p = self.writable(path)
        if not p.is_file():
            raise ToolError(f"{path}: no such file")
        text = p.read_text(encoding="utf-8")
        count = text.count(old_text) if old_text else 0
        if count != 1:
            raise ToolError(f"old_text found {count} times in {path}: it must match exactly once")
        p.write_text(text.replace(old_text, new_text), encoding="utf-8")
        return f"edited {path}"

    def run(self, command: str) -> str:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        try:
            tokens = list(lex)
        except ValueError as e:
            raise ToolError(f"cannot parse the command: {e}") from e
        segments, current = [], []
        for tok in tokens:
            if tok == "&&":
                segments.append(current)
                current = []
            elif set(tok) <= set(";|&<>()") and tok:
                raise ToolError(f"`{tok}` is not allowed: only && chaining, no pipes, redirects or subshells")
            else:
                current.append(tok)
        segments.append(current)
        cwd, outputs = self.cons, []
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(SECRET_ENV)}
        for seg in segments:
            if not seg:
                raise ToolError("empty command")
            if seg[0] == "cd":
                target = self._dir(seg[1], cwd) if len(seg) == 2 else None
                if target is None or not _within(target, self.cons) or not target.is_dir():
                    raise ToolError(f"cd is allowed only into the consumer folder {self.cons}")
                cwd = target
                continue
            seg = self._check(seg, cwd)
            try:
                out = subprocess.run(seg, cwd=str(cwd), capture_output=True, text=True, timeout=COMMAND_TIMEOUT,
                                     env=env, stdin=subprocess.DEVNULL)
                text, code = (out.stdout or "") + (out.stderr or ""), out.returncode
            except subprocess.TimeoutExpired:
                text, code = f"timed out after {COMMAND_TIMEOUT} s", 124
            except OSError as e:
                text, code = str(e), 127
            outputs.append(f"$ {shlex.join(seg)}\n{text[-12_000:]}\n(exit {code})")
            if code != 0:
                break
        return "\n".join(outputs)

    def _check(self, seg: list[str], cwd: Path) -> list[str]:
        """Allow-list one command; returns it with any `git -C <dir>` made absolute."""
        if seg[0] == "uv" and len(seg) >= 3 and seg[1] == "run":
            rest = seg[2:]
            while rest and rest[0] in UV_FLAGS:
                rest = rest[1:]
            if rest[:1] == ["pytest"] or rest[:3] == ["python", "-m", "pytest"] \
                    or rest == ["python", "scripts/regen_stubs.py"]:
                return seg
        if seg[0] == "git" and len(seg) >= 2:
            args, where = seg[1:], cwd
            if args[0] == "-C" and len(args) >= 3:
                where = self._dir(args[1], cwd)
                seg = ["git", "-C", str(where), *args[2:]]
                args = args[2:]
            if not any(_within(where, r) for r in self.read_roots):
                raise ToolError("git -C must point inside the workspace")
            if args and args[0] in GIT_READ:
                return seg
            if args and args[0] in GIT_WRITE:
                if not _within(where, self.cons) or (self.up and _within(where, self.up)):
                    raise ToolError("git may change files only inside the consumer folder")
                return seg
        raise ToolError("allowed: `uv run pytest ...`, `uv run python scripts/regen_stubs.py`, and git "
                        "(status, diff, log, show, ls-files, add, commit, rm, mv, restore)")




# ---------------------------------------------------------------------------
# Talking to the providers
# ---------------------------------------------------------------------------

def _post(client: httpx.Client, provider: str, key: str, body: dict) -> dict:
    p = PROVIDERS[provider]
    headers = ({"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION} if provider == "claude"
               else {"authorization": f"Bearer {key}"})  # xAI, and the OpenAI-compatible endpoints (Gemini, Groq)
    headers["content-type"] = "application/json"
    attempts = 8
    for attempt in range(attempts):
        try:
            r = client.post(api_url(provider), headers=headers, json=body)
        except httpx.HTTPError as e:
            if attempt == attempts - 1:
                raise ToolError(f"cannot reach the {p['label']} API: {e}") from e
            time.sleep(min(30, 2 ** attempt))
            continue
        if r.status_code == 200:
            return r.json()
        daily = "per day" in r.text.lower() or "perday" in r.text.lower()  # a daily quota will not come back soon
        if r.status_code in (429, 500, 502, 503, 504, 529) and attempt < attempts - 1 and not daily:
            wait = r.headers.get("retry-after") or _retry_delay(r.text) or 2 ** (attempt + 1)
            time.sleep(min(60.0, float(wait)))
            continue
        detail = _error_text(r)
        text = str(detail).lower()
        hint = (" (the daily quota is used up: resume the run after it resets, or pick another model with "
                f"{p['setup']})" if r.status_code == 429 and daily
                else f" (add credits in {p['console']})" if any(w in text for w in ("credit", "billing", "balance"))
                else f" (check {p['key']} in .env.local)" if r.status_code in (401, 403) else "")
        raise ToolError(f"{p['label']} API {r.status_code}: {str(detail)[:700]}{hint}")
    raise ToolError(f"{p['label']} API: too many retries")


def _error_text(r: httpx.Response) -> str:
    """The error message, whatever the shape: {"error": {...}}, [{"error": {...}}] (Google), or plain text."""
    try:
        data = r.json()
    except ValueError:
        return r.text
    if isinstance(data, list) and data:
        data = data[0]
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)
    return str(err or data or r.text)


def _retry_delay(text: str) -> float | None:
    """Google puts the wait in the error body ("retryDelay": "17s")."""
    m = re.search(r'retry[_ ]?delay"?\s*[:=]\s*"?(\d+(?:\.\d+)?)s', text, re.IGNORECASE)
    return float(m.group(1)) if m else None


@dataclass
class Turn:
    texts: list[str]
    calls: list[tuple[str, str, object]]  # (call id, tool name, arguments: dict, or the raw string if not JSON)
    tokens: int
    response_id: str | None
    truncated: bool = False
    refused: bool = False


class _Anthropic:
    """Messages API: the whole conversation is sent every turn, with cache breakpoints."""

    def __init__(self, client, key, model, system, tools, prompt):
        self.client, self.key, self.model, self.tools = client, key, model, tools
        self.system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        self.messages: list[dict] = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]

    def step(self, results: list[tuple[str, str, bool]] | None, note: str | None) -> Turn:
        if results:
            self.messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": cid, "content": out, **({"is_error": True} if err else {})}
                for cid, out, err in results]})
        elif note:
            self.messages.append({"role": "user", "content": [{"type": "text", "text": note}]})
        for msg in self.messages:  # one breakpoint, on the newest user turn
            if msg["role"] == "user" and isinstance(msg["content"], list):
                for block in msg["content"]:
                    block.pop("cache_control", None)
        self.messages[-1]["content"][-1]["cache_control"] = {"type": "ephemeral"}
        resp = _post(self.client, "claude", self.key, {"model": self.model, "max_tokens": MAX_OUTPUT_TOKENS,
                                                        "system": self.system, "tools": self.tools,
                                                        "messages": self.messages})
        content = resp.get("content") or []
        self.messages.append({"role": "assistant", "content": content})
        usage = resp.get("usage") or {}
        tokens = sum(int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                                       "cache_read_input_tokens"))
        return Turn(texts=[b["text"] for b in content if b.get("type") == "text" and b.get("text", "").strip()],
                    calls=[(b.get("id"), b.get("name"), b.get("input") or {}) for b in content
                           if b.get("type") == "tool_use"],
                    tokens=tokens, response_id=resp.get("id"), truncated=resp.get("stop_reason") == "max_tokens",
                    refused=resp.get("stop_reason") == "refusal")


class _XAI:
    """xAI Responses API: the server keeps the conversation (previous_response_id); each turn sends only what is new."""

    def __init__(self, client, key, model, system, tools, prompt):
        self.client, self.key, self.model, self.system, self.tools = client, key, model, system, tools
        self.prompt, self.previous = prompt, None

    def step(self, results: list[tuple[str, str, bool]] | None, note: str | None) -> Turn:
        body = {"model": self.model, "instructions": self.system, "tools": self.tools, "store": True,
                "max_output_tokens": MAX_OUTPUT_TOKENS}
        if self.previous is None:
            body["input"] = [{"role": "user", "content": self.prompt}]
        else:
            body["previous_response_id"] = self.previous
            body["input"] = ([{"type": "function_call_output", "call_id": cid,
                               "output": ("ERROR: " + out) if err else out} for cid, out, err in results]
                             if results else [{"role": "user", "content": note or "Continue."}])
        resp = _post(self.client, "grok", self.key, body)
        self.previous = resp.get("id")
        texts, calls = [], []
        for item in resp.get("output") or []:
            if item.get("type") == "message":
                for part in item.get("content") or []:
                    if part.get("type") in ("output_text", "text") and str(part.get("text", "")).strip():
                        texts.append(part["text"])
                    elif part.get("type") == "refusal":
                        texts.append(str(part.get("refusal") or "refused"))
            elif item.get("type") == "function_call":
                raw = item.get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except ValueError:
                    args = raw  # reported back to the model as a tool error
                calls.append((item.get("call_id") or item.get("id"), item.get("name"), args))
        usage = resp.get("usage") or {}
        tokens = int(usage.get("total_tokens") or (int(usage.get("input_tokens") or 0)
                                                   + int(usage.get("output_tokens") or 0)))
        return Turn(texts=texts, calls=calls, tokens=tokens, response_id=resp.get("id"),
                    truncated=resp.get("status") == "incomplete" and not calls)


class _OpenAIChat:
    """OpenAI-compatible chat completions (Gemini, Groq): the whole conversation every turn. Assistant messages are
    sent back exactly as received, so provider extras (e.g. Gemini's thought signatures) survive."""

    def __init__(self, client, key, model, system, tools, prompt, provider):
        self.client, self.key, self.model, self.tools, self.provider = client, key, model, tools, provider
        self.messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        self.n = 0

    def step(self, results: list[tuple[str, str, bool]] | None, note: str | None) -> Turn:
        if results:
            self.messages += [{"role": "tool", "tool_call_id": cid, "content": ("ERROR: " + out) if err else out}
                              for cid, out, err in results]
        elif note:
            self.messages.append({"role": "user", "content": note})
        resp = _post(self.client, self.provider, self.key, {"model": self.model, "messages": self.messages,
                                                           "tools": self.tools, "tool_choice": "auto",
                                                           "max_tokens": MAX_OUTPUT_TOKENS})
        choice = (resp.get("choices") or [{}])[0]
        msg = dict(choice.get("message") or {"role": "assistant", "content": ""})
        msg.setdefault("role", "assistant")
        calls = []
        for call in msg.get("tool_calls") or []:
            if not call.get("id"):
                self.n += 1
                call["id"] = f"call_{self.n}"  # tool results must name the call they answer
            fn = call.get("function") or {}
            raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
            except ValueError:
                args = raw
            calls.append((call["id"], fn.get("name"), args))
        self.messages.append(msg)
        content = msg.get("content")
        texts = [content] if isinstance(content, str) and content.strip() else \
            [c.get("text", "") for c in content or [] if isinstance(c, dict) and str(c.get("text", "")).strip()] \
            if isinstance(content, list) else []
        usage = resp.get("usage") or {}
        tokens = int(usage.get("total_tokens") or (int(usage.get("prompt_tokens") or 0)
                                                   + int(usage.get("completion_tokens") or 0)))
        return Turn(texts=texts, calls=calls, tokens=tokens, response_id=resp.get("id"),
                    truncated=choice.get("finish_reason") == "length" and not calls)


# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------

def run(provider: str, ctx: dict, agent: str, prompt: str, cap_tokens: int, env: dict, say, describe,
        on_usage) -> Result:
    """One agent session: loop until the model ends its turn, the turn limit or the token cap."""
    p = PROVIDERS[provider]
    key, model = env.get(p["key"]), model_of(provider, env)
    res = Result()
    if not key:
        res.errors.append(f"{p['key']} is not set ({p['setup']})")
        say(res.errors[-1], "error")
        return res
    box = Sandbox(ctx, agent)
    started, tool_calls = time.monotonic(), 0
    with _client() as client:
        sys_prompt, specs = system_prompt(agent, provider, model), tool_specs(provider, AGENT_TOOLS[agent])
        if provider == "claude":
            session = _Anthropic(client, key, model, sys_prompt, specs, prompt)
        elif provider == "grok":
            session = _XAI(client, key, model, sys_prompt, specs, prompt)
        else:  # OpenAI-compatible chat completions: gemini, groq
            session = _OpenAIChat(client, key, model, sys_prompt, specs, prompt, provider)
        results, note = None, None
        while True:
            if res.turns >= MAX_TURNS[agent]:
                res.errors.append(f"no result after {MAX_TURNS[agent]} turns")
                say(f"Stopped after {MAX_TURNS[agent]} turns", "error")
                break
            try:
                turn = session.step(results, note)
            except ToolError as e:
                res.errors.append(str(e))
                say(str(e), "error")
                break
            res.turns += 1
            res.task_id = res.task_id or turn.response_id
            res.cost += turn.tokens
            on_usage(res.cost)
            for text in turn.texts:
                res.result = text.strip()
                for line in text.splitlines():
                    say(line)
            results, note = [], None
            for call_id, name, args in turn.calls:
                tool_calls += 1
                say(describe(name, args if isinstance(args, dict) else {}))
                try:
                    if name not in AGENT_TOOLS[agent]:
                        raise ToolError(f"{name} is not available to this agent")
                    if not isinstance(args, dict):
                        raise ToolError("the arguments are not a JSON object")
                    output, is_error = getattr(box, name)(**args), False
                except ToolError as e:
                    output, is_error = str(e), True
                    say(f"{name} refused: {e}", "warn")
                except (TypeError, OSError, ValueError) as e:
                    output, is_error = f"{type(e).__name__}: {e}", True
                    say(f"{name} failed: {e}", "warn")
                results.append((call_id, output, is_error))
            if not results:
                results = None
                if turn.truncated:
                    note = "Your reply hit the output limit. Continue; write big files in smaller edit_file steps."
                else:
                    if turn.refused:
                        res.errors.append(f"{p['label']} declined this step")
                    break
            if res.cost > cap_tokens:
                res.errors.append(f"token cap reached ({res.cost:,} of {cap_tokens:,} tokens)")
                say(f"Stopped: the token cap for this agent is reached ({res.cost:,} of {cap_tokens:,})", "error")
                break
    secs = int(time.monotonic() - started)
    say(f"{p['label']} session finished: {tool_calls} tool calls · {res.turns} turns · {res.cost:,} tokens · "
        f"{secs // 60}m {secs % 60:02d}s · {model}", "ok" if not res.errors else "warn")
    return res


def ping(provider: str, env: dict) -> str:
    """A one-line request to check the key and the model (used by the setup scripts)."""
    p = PROVIDERS[provider]
    model = model_of(provider, env)
    if not env.get(p["key"]):
        raise ToolError(f"no {p['key']} in .env.local ({p['setup']})")
    ask = "Reply with the single word OK."
    with _client() as client:
        if provider == "claude":
            resp = _post(client, provider, env[p["key"]], {"model": model, "max_tokens": 16,
                                                           "messages": [{"role": "user", "content": ask}]})
            text = "".join(b.get("text", "") for b in resp.get("content") or [] if b.get("type") == "text")
        elif provider == "grok":  # xAI Responses API
            resp = _post(client, provider, env[p["key"]], {"model": model, "input": [{"role": "user", "content": ask}],
                                                           "max_output_tokens": 512, "store": False})
            text = "".join(part.get("text", "") for item in resp.get("output") or [] if item.get("type") == "message"
                           for part in item.get("content") or [])
        else:  # OpenAI-compatible chat completions: gemini, groq
            resp = _post(client, provider, env[p["key"]], {"model": model, "max_tokens": 512,
                                                           "messages": [{"role": "user", "content": ask}]})
            text = str(((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    return f"{model}: {text.strip() or '(no text)'}"


if __name__ == "__main__":  # python -m web.webapp.llm_agent grok|claude  (checks the key in .env.local)
    from . import agents  # noqa: PLC0415

    which = sys.argv[1] if len(sys.argv) > 1 else "gemini"
    try:
        print(ping(which, agents.local_env()))
    except ToolError as e:
        print(f"FAILED: {e}")
        raise SystemExit(1) from e
