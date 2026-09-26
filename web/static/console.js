/* SyncSnitch console: launcher + live multi-agent orchestrator.
 * Everything shown comes from /api/live/<run> (the real run: S1-S2 on this site, then IBM Bob's events, files and
 * commits). The timing below only paces how real updates are revealed (typing, staggered checks). */
(() => {
  const boot = JSON.parse(document.getElementById('boot').textContent);
  const bootBob = Boolean(boot.bob);
  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const form = $('launcher'), input = $('link'), btn = $('launch-btn'), err = $('launch-error'), consoleEl = $('console');

  const AGENT = {site: 'SyncSnitch', engine: 'Engine', tracer: 'Tracer', transformer: 'Transformer',
                 verifier: 'Verifier', human: 'Human Gate', bob: 'IBM Bob'};
  const MODES = {tracer: 'syncsnitch-tracer', transformer: 'syncsnitch-transformer', verifier: 'syncsnitch-verifier'};
  const DONE = ['complete', 'failed', 'no_drift', 'aborted'];
  const PHASES = {
    tracing: ['TRACING', 'run'], waiting_bob: ['WAITING FOR IBM BOB', 'wait'], active: ['AGENTS ACTIVE', 'run'],
    approval: ['S7 AWAITING APPROVAL', 'human'], publishing: ['OPENING DRAFT PR', 'run'], complete: ['COMPLETE', 'ok'],
    failed: ['FAILED', 'bad'], aborted: ['REJECTED', 'bad'], no_drift: ['NO BREAKING CHANGES', 'ok'],
    blocked: ['SETUP NEEDED', 'wait'], interrupted: ['INTERRUPTED', 'bad'], red_gate: ['VERDICT RED · GATE CLOSED', 'bad'],
  };
  const CHECK = {pass: ['PASS ✅', 'ok'], fail: ['FAIL ✖', 'bad'], skip: ['SKIPPED', 'wait'], waiting: ['WAITING', 'idle']};

  let runId = null, query = '', generation = 0, finished = false, instant = false;
  let seenEvents = new Set(), checkState = {}, typingQueue = [], typing = false, prDone = false, diffLoadedFor = null;
  let gateBusy = false;

  /* ---------- launcher ---------- */
  function setBusy(busy) {
    btn.disabled = busy;
    btn.classList.toggle('is-busy', busy);
    btn.querySelector('.btn-label').textContent = busy ? 'Launching…' : 'Run 3 Agents';
  }
  async function launch() {
    err.hidden = true;
    setBusy(true);
    try {
      const res = await fetch('/api/launch', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                              body: JSON.stringify({link: input.value})});
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      history.pushState({run: data.run_id}, '', data.url);
      start(data.run_id, data.url.split('?')[1] || '', true);
    } catch (e) {
      err.textContent = 'Could not launch: ' + e.message;
      err.hidden = false;
    } finally {
      setBusy(false);
    }
  }
  form.addEventListener('submit', (e) => { e.preventDefault(); launch(); });  // Enter in the input submits too
  document.querySelectorAll('.chip[data-link]').forEach((chip) => chip.addEventListener('click', () => {
    input.value = chip.dataset.link;
    input.focus();
  }));

  /* ---------- console lifecycle ---------- */
  function clearConsole() {
    seenEvents = new Set(); checkState = {}; typingQueue = []; prDone = false; diffLoadedFor = null; finished = false;
    $('log').replaceChildren();
    $('diff-box').hidden = true; $('diff-box').replaceChildren(); $('diff-btn').setAttribute('aria-expanded', 'false');
    $('diff-btn').disabled = true;
    ['setup', 'run-error-box', 'resume-btn', 'gate', 'celebrate', 'actions-btn', 'analyze-link', 'coins']
      .forEach((id) => { $(id).hidden = true; });
    $('actions-note').textContent = ''; $('start-note').textContent = ''; gateBusy = false;
    document.querySelectorAll('[data-f="bob"]').forEach((el, i) => { el.textContent = 'agent ' + Object.values(MODES)[i]; });
    for (const id of ['agent-tracer', 'agent-transformer', 'agent-verifier']) setPill(id, 'queued');
    document.querySelectorAll('#checks li').forEach((li) => setCheck(li, 'waiting', ''));
    document.querySelectorAll('[data-f]').forEach((el) => {
      if (el.dataset.f === 'bob') return;
      if (el.tagName === 'UL') el.replaceChildren(); else if (el.dataset.f === 'flag') el.hidden = true; else el.textContent = '–';
    });
    setPhase('tracing');
  }
  function start(id, q, fresh) {
    generation += 1;
    clearConsole();
    runId = id; query = q; instant = !fresh;
    $('run-badge').textContent = 'RUN: ' + id;
    consoleEl.classList.add('is-open');
    consoleEl.removeAttribute('aria-hidden');
    consoleEl.inert = false;
    if (fresh) setTimeout(() => consoleEl.scrollIntoView({behavior: 'smooth', block: 'start'}), 120);
    poll(generation);
  }
  function reset(push) {
    generation += 1;  // stops the poll loop of the previous run
    runId = null;
    consoleEl.classList.remove('is-open');
    consoleEl.setAttribute('aria-hidden', 'true');
    consoleEl.inert = true;
    if (push) history.pushState({}, '', '/');
    const gen = generation;
    setTimeout(() => { if (gen === generation) clearConsole(); }, 400);  // not if a new run started meanwhile
    input.focus();
  }
  $('reset-btn').addEventListener('click', () => reset(true));
  window.addEventListener('popstate', () => {
    if (location.pathname === '/') reset(false); else location.reload();
  });

  async function poll(gen) {
    if (gen !== generation) return;
    try {
      const res = await fetch(`/api/live/${encodeURIComponent(runId)}?${query}`, {cache: 'no-store'});
      if (res.ok) await render(await res.json(), gen);
      else if (res.status === 404 || res.status === 400) {
        $('run-error').textContent = 'This run is not known here (it may have been cleared).';
        $('run-error').hidden = false;
        finished = true;
      }
    } catch (e) { /* network hiccup: keep polling */ }
    if (gen === generation) {
      instant = false;
      if (!finished) setTimeout(() => poll(gen), 1500); else setStream(false);
    }
  }

  /* ---------- rendering ---------- */
  function setPhase(phase) {
    const [label, cls] = PHASES[phase] || [String(phase).toUpperCase(), 'wait'];
    $('phase').textContent = label;
    $('phase').className = 'phase phase-' + cls;
    $('live-dot').className = 'live-dot' + (['complete', 'no_drift'].includes(phase) ? ' is-done'
      : ['failed', 'aborted', 'interrupted'].includes(phase) ? ' is-bad' : '');
  }
  function setStream(on, label) {
    const el = $('stream-state');
    el.classList.toggle('is-ended', !on);
    el.querySelector('span').textContent = label || (on ? 'STREAMING' : 'ENDED');
  }
  function setPill(cardId, status, verdict) {
    const card = $(cardId);
    const map = {
      queued: ['QUEUED', 'idle'], waiting: ['QUEUED', 'idle'], waiting_bob: ['AWAITING BOB', 'wait'],
      running: [cardId === 'agent-verifier' ? 'VERIFYING' : 'RUNNING', 'pulse'], failed: ['FAILED', 'bad'],
      stopped: ['STOPPED', 'bad'],
      done: cardId === 'agent-verifier' ? (verdict === 'green' ? ['PASS ✅', 'ok'] : verdict === 'red' ? ['FAIL ✖', 'bad'] : ['DONE', 'ok'])
                                        : ['DONE ✅', 'ok'],
    };
    const [label, cls] = map[status] || [status, 'idle'];
    card.dataset.status = status === 'waiting' ? 'queued' : status;
    const pill = card.querySelector('[data-pill]');
    pill.textContent = label;
    pill.className = 'pill pill-' + cls;
  }
  function setCheck(li, status, details) {
    const [label, cls] = CHECK[status] || CHECK.waiting;
    const pill = li.querySelector('.pill');
    pill.textContent = label;
    pill.className = 'pill pill-' + cls + (status !== 'waiting' ? ' pop' : '');
    li.querySelector('.check-detail').textContent = details ? ' · ' + details : '';
    li.dataset.status = status;
  }
  const f = (card, name) => $(card).querySelector(`[data-f="${name}"]`);

  async function render(s, gen) {
    setPhase(s.phase === 'approval' && s.verifier.verdict === 'red' ? 'red_gate' : s.phase);
    $('target').textContent = s.spec.link || s.spec.repo || '';
    $('consumer').textContent = s.spec.consumer === '' ? '(repo root)' : (s.spec.consumer || '…');
    const r = s.runner;
    const error = s.spec.error ? 'Stopped: ' + s.spec.error : (r && r.error ? r.error : '');
    $('run-error').textContent = error;
    $('run-error-box').hidden = !error;
    $('resume-btn').hidden = !(r && r.can_start && ['failed', 'interrupted'].includes(s.phase));
    if (s.phase === 'interrupted' && !error) {
      $('run-error').textContent = 'The server restarted while the agents were working. Resume continues from the last finished step.';
      $('run-error-box').hidden = false;
    }
    if (s.spec.bob_command) $('bob-cmd').textContent = s.spec.bob_command;
    renderSetup(s);
    renderCoins(s);

    // Subagent 1
    const t = s.tracer;
    setPill('agent-tracer', t.status);
    if (t.breaking != null) {
      const bs = t.by_surface || {};
      f('agent-tracer', 'breaking').textContent = `${t.breaking} breaking`;
      f('agent-tracer', 'surfaces').textContent = `${bs.rest || 0} REST · ${bs.grpc || 0} gRPC · ${bs.db || 0} DB`;
      f('agent-tracer', 'usages').textContent = t.hits != null ? `${t.hits} references · ${t.files} files` : '–';
      f('agent-tracer', 'endpoints').textContent = `${t.endpoints.length} endpoint${t.endpoints.length === 1 ? '' : 's'}`;
      const eps = f('agent-tracer', 'eplist');
      if (eps.childElementCount !== t.endpoints.length) {
        eps.replaceChildren(...t.endpoints.map((ep) => {
          const li = document.createElement('li');
          const fail = (t.failures || {})[ep];
          li.textContent = ep;
          if (fail) { const b = document.createElement('b'); b.className = 'ep-' + fail.toLowerCase(); b.textContent = fail.toUpperCase(); li.append(' ', b); }
          return li;
        }));
      } else if (t.classified) {
        [...eps.children].forEach((li, i) => {
          const ep = t.endpoints[i], fail = (t.failures || {})[ep];
          if (fail && !li.querySelector('b')) { const b = document.createElement('b'); b.className = 'ep-' + fail.toLowerCase(); b.textContent = fail.toUpperCase(); li.append(' ', b); }
        });
      }
      const flag = f('agent-tracer', 'flag');
      flag.hidden = false;
      flag.className = 'callout' + (t.classified ? ' callout-warn' : '');
      flag.textContent = t.classified
        ? `⚠️ Flagged: ${t.loud} loud break${t.loud === 1 ? '' : 's'} + ${t.silent} silent` + (t.silent_why ? ` — ${t.silent_why}` : '')
        : 'Loud / silent classification (S3) is done by the Tracer agent';
    }

    // Subagent 2
    const x = s.transformer;
    setPill('agent-transformer', x.status);
    f('agent-transformer', 'branch').textContent = x.status === 'waiting' ? '–' : x.branch;
    f('agent-transformer', 'files').textContent = x.files != null
      ? `${x.files} file${x.files === 1 ? '' : 's'}` + (x.uncommitted ? ` · ${x.uncommitted} uncommitted` : '')
      : (x.uncommitted ? `${x.uncommitted} being edited` : '–');
    f('agent-transformer', 'diffstat').textContent = (x.insertions || x.deletions) ? `+${x.insertions} / −${x.deletions} lines` : '–';
    const st = Object.fromEntries(s.verifier.checks.map((c) => [c.id, c.status]));
    const compat = f('agent-transformer', 'compat');
    if (['V1', 'V2', 'V3', 'V4', 'V5', 'V6'].some((id) => st[id] === 'fail')) { compat.textContent = 'not proven ✖'; compat.className = 'v-red'; }
    else if (st.V3 === 'pass' && st.V4 === 'pass') { compat.textContent = 'v1 + v2 ✓ (mock containers)'; compat.className = 'v-green'; }
    else if (st.V1 === 'pass' && st.V2 === 'pass') { compat.textContent = 'v1 + v2 per unit tests (containers skipped)'; compat.className = ''; }
    else { compat.textContent = '–'; compat.className = ''; }
    $('diff-btn').disabled = !s.diff_available;
    if (!$('diff-box').hidden && s.diff_key && s.diff_key !== diffLoadedFor) loadDiff(s.diff_key);

    // Subagent 3 (checks flip one by one, 250 ms apart)
    const v = s.verifier;
    setPill('agent-verifier', v.status, v.verdict);
    for (const c of v.checks) {
      if (gen !== generation) return;
      const key = c.status + '|' + c.details;
      if (checkState[c.id] === key) continue;
      const changed = checkState[c.id] !== undefined || c.status !== 'waiting';
      checkState[c.id] = key;
      setCheck(document.querySelector(`#checks li[data-check="${c.id}"]`), c.status, c.details);
      if (changed && !instant) await sleep(250);
    }
    const skipped = v.checks.filter((c) => c.status === 'skip').length;
    f('agent-verifier', 'verdict').textContent = v.verdict === 'green' ? (skipped ? `GREEN (${skipped} skipped)` : 'GREEN (PASS)')
      : v.verdict === 'red' ? 'RED (FAIL)' : v.status === 'running' ? 'Evaluating…' : '–';
    f('agent-verifier', 'verdict').className = v.verdict === 'green' ? 'v-green' : v.verdict === 'red' ? 'v-red' : '';

    // Log stream
    for (const e of s.events) {
      if (seenEvents.has(e.key)) continue;
      seenEvents.add(e.key);
      if (instant) appendLine(e, true); else typingQueue.push(e);
    }
    if (!typing && typingQueue.length) typeQueue(gen);

    renderGate(s);
    if (s.spec.analyze_url) { $('analyze-link').href = s.spec.analyze_url; $('analyze-link').hidden = false; }
    const runnerOn = Boolean(s.runner && s.runner.state !== 'blocked');  // the runner does S5 itself
    $('actions-btn').hidden = runnerOn || !(s.spec.base_sha && !DONE.includes(s.phase) && !s.actions);
    if (s.actions) $('actions-note').textContent = `GitHub Actions: ${s.actions.status}${s.actions.conclusion ? ' · ' + s.actions.conclusion : ''}`;
    finished = DONE.includes(s.phase) && !(r && r.can_start);
    if (s.phase === 'approval') setStream(false, 'AWAITING HUMAN');
    else if (s.phase === 'blocked') setStream(false, 'SETUP NEEDED');
    else setStream(!DONE.includes(s.phase));
  }

  function renderSetup(s) {
    const r = s.runner;
    const show = s.phase === 'blocked' || s.phase === 'waiting_bob';
    $('setup').hidden = !show;
    if (!show) return;
    const list = $('setup-list');
    const problems = (r && r.problems) || [];
    const key = problems.map((p) => p.id).join(',');
    if (list.dataset.key !== key) {
      list.dataset.key = key;
      list.replaceChildren(...problems.map((p) => {
        const li = document.createElement('li');
        const text = document.createElement('span'); text.textContent = p.text;
        li.append(text);
        if (p.fix) {
          const pre = document.createElement('pre'); pre.textContent = p.fix;
          const b = document.createElement('button'); b.type = 'button'; b.className = 'btn btn-ghost btn-sm'; b.textContent = 'Copy';
          b.addEventListener('click', (e) => copyText(pre, e.target));
          const row = document.createElement('div'); row.className = 'fix-row'; row.append(pre, b);
          li.append(row);
        }
        return li;
      }));
    }
    $('start-btn').disabled = !(r && r.can_start);
    $('start-btn').hidden = Boolean(r && r.problems.some((p) => p.id === 'vercel'));
    if (!problems.length && !(r && r.can_start)) $('start-note').textContent = 'Checking this machine…';
  }

  const tokens = (n) => n >= 1e6 ? (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + 'M' : n >= 1000 ? Math.round(n / 1000) + 'k' : String(Math.round(n));
  function renderCoins(s) {
    const r = s.runner;
    $('coins').hidden = !(r && r.budget && r.backend && r.state !== 'blocked');
    if (!r || !r.backend) return;
    const tok = r.unit === 'tokens';
    const amount = (n) => tok ? tokens(n || 0) : Number(n || 0).toFixed(2);
    $('coins-icon').textContent = tok ? '🔢' : '🪙';
    $('coins-spent').textContent = amount(r.spent);
    $('coins-budget').textContent = r.budget ? amount(r.budget) : '–';
    $('coins-unit').textContent = r.unit;
    $('coins-engine').textContent = ` · ${r.label}` + (r.model ? ` (${r.model})` : '');
    for (const [agent, mode] of Object.entries(MODES)) {
      const el = f('agent-' + agent, 'bob');
      const cost = (r.spent_by || {})[agent];
      const task = (r.tasks || {})[agent];
      el.textContent = `${r.label} · ${tok ? 'agent' : 'mode'} ${mode}` + (cost != null ? ` · ${tok ? tokens(cost) + ' tokens' : '🪙 ' + cost.toFixed(2)}` : '')
        + (task ? ` · ${String(task).slice(0, tok ? 12 : 8)}` : '');
    }
  }

  function renderGate(s) {
    const v = s.verifier, gate = $('gate');
    const show = Boolean(v.verdict) || ['approval', 'publishing', 'complete'].includes(s.phase);
    if (!show) { gate.hidden = true; return; }
    gate.hidden = false;
    const byId = Object.fromEntries(v.checks.map((c) => [c.id, c.status]));
    const containers = byId.V3 === 'pass' && byId.V4 === 'pass';
    const skipped = v.checks.filter((c) => c.status === 'skip').length;
    if (s.phase === 'aborted') {
      gate.className = 'gate gate-blocked';
      $('gate-title').textContent = '🛡️ S7 Human Approval Gate — REJECTED';
      $('gate-desc').textContent = 'The human rejected this run: nothing was pushed and no PR was opened.';
    } else if (v.verdict === 'green') {
      gate.className = 'gate gate-open';
      $('gate-title').textContent = '🛡️ S7 Human Approval Gate Unlocked — '
        + (skipped ? `GREEN · ${skipped} of 6 checks skipped` : 'VERIFIED PASS');
      const ids = (st) => v.checks.filter((c) => c.status === st).map((c) => c.id).join(', ');
      $('gate-desc').textContent = (containers ? 'Contract verified against both Upstream v1 & v2 in mock containers. ' : '')
        + `Passed: ${ids('pass') || 'none'}.` + (skipped ? ` Skipped: ${ids('skip')}.` : '')
        + ' Review the tolerant-reader diff and approve the companion draft PR.';
    } else if (v.verdict === 'red') {
      gate.className = 'gate gate-blocked';
      $('gate-title').textContent = '🛡️ S7 Human Approval Gate — BLOCKED (verification RED)';
      $('gate-desc').textContent = 'The Verifier routed fixes back to the Transformer. Nothing is opened until the checks are green.';
    } else {
      gate.className = 'gate gate-open';
      $('gate-title').textContent = '🛡️ S7 Human Approval Gate';
      $('gate-desc').textContent = 'Waiting for the human decision in IBM Bob.';
    }
    const r = s.runner, runnerGate = Boolean(r && r.state !== 'blocked');
    if (runnerGate && v.verdict === 'red') {
      $('gate-desc').textContent = 'The Verifier found failing checks' + (r.state === 'approval' ? ' after the automatic fix round' : '')
        + '. Nothing can be published from a red run: reject it, or fix the branch and start a new run.';
    }
    $('gate-note').textContent = s.companion_pr_url || v.verdict === 'red' || s.phase === 'aborted' ? ''
      : s.phase === 'publishing' ? `Approved. Pushing ${s.transformer.branch} and opening a DRAFT companion PR…`
      : runnerGate ? `SyncSnitch never opens a PR without you: Approve pushes ${s.transformer.branch} and opens a DRAFT PR (never merged).`
      : 'The approval question is waiting in your IBM Bob task: SyncSnitch never opens a PR without you.';
    const approve = $('approve-btn'), reject = $('reject-btn');
    approve.hidden = Boolean(s.companion_pr_url) || v.verdict === 'red' || s.phase === 'aborted';
    approve.disabled = gateBusy || (runnerGate ? !r.can_approve : !bootBob);
    approve.dataset.mode = runnerGate ? 'runner' : 'bob';
    reject.hidden = !(runnerGate && r.can_reject);
    reject.disabled = gateBusy;
    const replay = $('replay-btn');
    if (s.replay_url) { replay.href = s.replay_url; replay.removeAttribute('aria-disabled'); }
    if (s.companion_pr_url && !prDone) {
      prDone = true;
      const c = $('celebrate');
      const m = s.companion_pr_url.match(/github\.com\/([^/]+\/[^/]+)\/pull\/(\d+)/);
      const a = document.createElement('a');
      a.href = s.companion_pr_url; a.target = '_blank'; a.rel = 'noreferrer';
      a.textContent = m ? `${m[1]}#${m[2]}` : s.companion_pr_url;
      c.replaceChildren('🎉 Companion Draft PR opened: ', a);
      c.hidden = false;
      c.classList.add('burst');
    }
  }

  /* ---------- terminal ---------- */
  function lineParts(e) {
    const li = document.createElement('li');
    li.className = `lv-${e.level} ag-${e.agent}`;
    const ts = document.createElement('span'); ts.className = 'ts';
    ts.textContent = `[${new Date(e.ts).toLocaleTimeString([], {hour12: false})}]`;
    const who = document.createElement('span'); who.className = 'who';
    const engine = {bob: 'IBM Bob', claude: 'Claude', grok: 'Grok', gemini: 'Gemini', groq: 'Groq'}[e.src];
    who.textContent = engine ? `[${engine} › ${AGENT[e.agent] || e.agent}]` : `[${AGENT[e.agent] || e.agent}]`;
    if (engine) li.classList.add('src-bob', 'src-' + e.src);
    const msg = document.createElement('span'); msg.className = 'msg';
    li.append(ts, who, msg);
    return [li, msg, (e.level === 'error' ? '✖ ' : e.level === 'warn' ? '⚠ ' : '') + e.msg];
  }
  function stickToBottom(fn) {
    const log = $('log');
    const stick = log.scrollTop + log.clientHeight >= log.scrollHeight - 40;
    fn();
    if (stick) log.scrollTop = log.scrollHeight;
  }
  function appendLine(e) {
    const [li, msg, text] = lineParts(e);
    msg.textContent = text;
    stickToBottom(() => $('log').append(li));
  }
  async function typeQueue(gen) {
    typing = true;
    while (typingQueue.length && gen === generation) {
      const e = typingQueue.shift();
      const [li, msg, text] = lineParts(e);
      li.classList.add('typing');
      stickToBottom(() => $('log').append(li));
      const fast = typingQueue.length > 8;  // catch up when many events arrive at once
      const step = fast ? text.length : Math.max(1, Math.ceil(text.length / 45));
      for (let i = step; ; i += step) {
        msg.textContent = text.slice(0, Math.min(i, text.length));
        stickToBottom(() => {});
        if (i >= text.length) break;
        await sleep(12);
      }
      li.classList.remove('typing');
      if (!fast) await sleep(200);
    }
    typing = false;
  }

  /* ---------- patch diff ---------- */
  async function loadDiff(key) {
    diffLoadedFor = key;
    const box = $('diff-box');
    try {
      const res = await fetch(`/api/live/${encodeURIComponent(runId)}/diff?${query}`, {cache: 'no-store'});
      const data = await res.json();
      box.replaceChildren(...(data.diff || 'No patch yet.').split('\n').map((line) => {
        const span = document.createElement('span');
        span.className = line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff ') || line.startsWith('index ') ? 'd-file'
          : line.startsWith('@@') ? 'd-hunk' : line.startsWith('+') ? 'd-add' : line.startsWith('-') ? 'd-del' : '';
        span.textContent = line || '\u00a0';
        return span;
      }));
    } catch (e) { box.textContent = 'Could not load the patch.'; }
  }
  $('diff-btn').addEventListener('click', () => {
    const box = $('diff-box'), open = box.hidden;
    box.hidden = !open;
    $('diff-btn').setAttribute('aria-expanded', String(open));
    if (open) loadDiff('now');
  });

  /* ---------- hand-off helpers ---------- */
  async function copyText(pre, button) {
    try { await navigator.clipboard.writeText(pre.textContent); button.textContent = 'Copied ✓'; return; } catch { /* fall back */ }
    const range = document.createRange(); range.selectNodeContents(pre);
    const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
    let ok = false; try { ok = document.execCommand('copy'); } catch { ok = false; }
    button.textContent = ok ? 'Copied ✓' : 'Selected: press ⌘C';
  }
  $('copy-btn').addEventListener('click', (e) => copyText($('bob-cmd'), e.target));
  async function openBob() {
    const res = await fetch('/api/open-bob', {method: 'POST'});
    const note = $('gate').hidden ? $('start-note') : $('gate-note');
    note.textContent = res.ok ? 'IBM Bob is in front: answer the question in your SyncSnitch task.' : 'Open IBM Bob yourself: ' + (await res.json()).detail;
  }
  document.querySelectorAll('[data-open-bob]').forEach((b) => b.addEventListener('click', openBob));

  async function post(action) {
    const res = await fetch(`/api/live/${encodeURIComponent(runId)}/${action}`, {method: 'POST'});
    let data = {};
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) throw new Error(data.detail || res.statusText);
    return data;
  }
  async function startAgents(button, note) {
    button.disabled = true;
    note.textContent = 'Starting the IBM Bob agents…';
    try {
      await post('agents');
      note.textContent = '';
      finished = false; poll(generation);
    } catch (e) { note.textContent = 'Could not start: ' + e.message; button.disabled = false; }
  }
  $('start-btn').addEventListener('click', () => startAgents($('start-btn'), $('start-note')));
  $('resume-btn').addEventListener('click', () => startAgents($('resume-btn'), $('run-error')));
  $('approve-btn').addEventListener('click', async () => {
    if ($('approve-btn').dataset.mode !== 'runner') { openBob(); return; }
    gateBusy = true; $('approve-btn').disabled = true; $('reject-btn').disabled = true;
    $('gate-note').textContent = 'Approved. Pushing the branch and opening a DRAFT companion PR…';
    try { await post('approve'); } catch (e) { $('gate-note').textContent = 'Could not approve: ' + e.message; }
    gateBusy = false;
  });
  $('reject-btn').addEventListener('click', async () => {
    if (!window.confirm('Reject this run? Nothing will be pushed and no PR will be opened.')) return;
    gateBusy = true;
    try { await post('reject'); } catch (e) { $('gate-note').textContent = 'Could not reject: ' + e.message; }
    gateBusy = false;
  });
  $('actions-btn').addEventListener('click', async () => {
    $('actions-btn').disabled = true;
    const res = await fetch(`/api/live/${encodeURIComponent(runId)}/verify`, {method: 'POST'});
    const data = await res.json();
    $('actions-note').textContent = res.ok ? 'Started in GitHub Actions (first container build takes 3–6 min)…' : 'Could not start: ' + data.detail;
    if (!res.ok) $('actions-btn').disabled = false;
  });

  if (boot.run) start(boot.run, boot.query, false);
})();
