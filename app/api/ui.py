"""Tiny browser UI for auth + CSV uploads (POC convenience)."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def upload_ui() -> str:
    """Return a simple page for token login, seeding, and CSV uploads."""
    return """
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Contractor Ops Upload UI</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 860px; }
    fieldset { margin-bottom: 1rem; }
    label { display: inline-block; min-width: 130px; }
    button { margin-top: .5rem; }
    pre { background: #111; color: #0f0; padding: .75rem; border-radius: 6px;
          white-space: pre-wrap; }
    .row { margin: .4rem 0; }
  </style>
</head>
<body>
  <h1>Contractor Ops – Upload UI (POC)</h1>
  <p>Use this page to login, seed demo data, and upload CSVs without hand-calling API endpoints.</p>

  <fieldset>
    <legend>1) Login (admin/admin or ops/ops)</legend>
    <div class=\"row\"><label>Username</label><input id=\"username\" value=\"admin\" /></div>
    <div class=\"row\"><label>Password</label>
      <input id=\"password\" value=\"admin\" type=\"password\" /></div>
    <button onclick=\"login()\">Get Token</button>
    <div class=\"row\"><label>Token</label><input id=\"token\" style=\"width: 75%\" /></div>
  </fieldset>

  <fieldset>
    <legend>2) Demo data helpers (admin only)</legend>
    <button onclick=\"seed(true)\">Seed demo data (reset=true)</button>
    <button onclick=\"clearDemo()\">Clear all data (keep schema)</button>
  </fieldset>

  <fieldset>
    <legend>3) Upload CSVs</legend>
    <div class=\"row\">
      <label>ADP CSV</label><input type=\"file\" id=\"adp\" accept=\".csv\" />
      <button onclick=\"upload('adp')\">Upload ADP</button>
    </div>
    <div class=\"row\">
      <label>QBO CSV</label><input type=\"file\" id=\"qbo\" accept=\".csv\" />
      <button onclick=\"upload('qbo')\">Upload QBO</button>
    </div>
    <div class=\"row\">
      <label>Budgets CSV</label><input type=\"file\" id=\"budgets\" accept=\".csv\" />
      <button onclick=\"upload('budgets')\">Upload Budgets</button>
    </div>
  </fieldset>

  <h3>Response log</h3>
  <pre id=\"out\">Ready.</pre>

<script>
const out = document.getElementById('out');

function log(data) {
  out.textContent = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
}


async function parseResponse(resp) {
  const contentType = resp.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await resp.json()
    : await resp.text();
  return { ok: resp.ok, status: resp.status, payload };
}

function authHeaders() {
  const token = document.getElementById('token').value.trim();
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

async function login() {
  const payload = {
    username: document.getElementById('username').value,
    password: document.getElementById('password').value,
  };
  const resp = await fetch('/auth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const { ok, payload } = await parseResponse(resp);
  if (ok && payload.access_token) {
    document.getElementById('token').value = payload.access_token;
  }
  log(payload);
}

async function seed(reset) {
  const resp = await fetch(`/seed/demo?reset=${reset ? 'true' : 'false'}`, {
    method: 'POST',
    headers: authHeaders(),
  });
  const { payload } = await parseResponse(resp);
  log(payload);
}

async function clearDemo() {
  const confirmed = window.confirm('This will remove all table rows. Continue?');
  if (!confirmed) return;
  const resp = await fetch('/seed/demo', {
    method: 'DELETE',
    headers: authHeaders(),
  });
  const { payload } = await parseResponse(resp);
  log(payload);
}

async function upload(kind) {
  const fileInput = document.getElementById(kind);
  if (!fileInput.files.length) return log(`Please choose a ${kind.toUpperCase()} CSV first.`);

  const fd = new FormData();
  fd.append('file', fileInput.files[0]);

  const resp = await fetch(`/ingest/${kind}`, {
    method: 'POST',
    headers: authHeaders(),
    body: fd,
  });
  const { payload } = await parseResponse(resp);
  log(payload);
}
</script>
</body>
</html>
"""
