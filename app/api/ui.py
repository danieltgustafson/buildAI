"""Tiny browser UI for auth + CSV uploads (POC convenience)."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self';"
)

_HEADERS = {"Content-Security-Policy": _CSP, "X-Content-Type-Options": "nosniff"}


@router.get("/", include_in_schema=False)
@router.get("/ui", include_in_schema=False)
def upload_ui() -> HTMLResponse:
    """Return a simple page for token login, seeding, and CSV uploads."""
    return HTMLResponse(content=_HTML, headers=_HEADERS)


_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Contractor Ops Upload UI</title>
  <link href="https://cdn.jsdelivr.net/npm/vis-timeline@7.7.3/styles/vis-timeline-graph2d.min.css" rel="stylesheet" />
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 1100px; }
    fieldset { margin-bottom: 1rem; }
    label { display: inline-block; min-width: 160px; }
    button { margin-top: .5rem; margin-right: .5rem; }
    pre { background: #111; color: #0f0; padding: .75rem; border-radius: 6px;
          white-space: pre-wrap; }
    .row { margin: .4rem 0; }
    .small { color: #666; font-size: .9rem; }
    #wipChart { border: 1px solid #ddd; border-radius: 6px; width: 100%; max-width: 940px; }
    #scheduleTimeline { border: 1px solid #ddd; border-radius: 6px; height: 420px; }
    #utilizationTable, #coverageTable { width: 100%; border-collapse: collapse; font-size: .9rem; margin-top: .75rem; }
    #utilizationTable th, #utilizationTable td,
    #coverageTable th, #coverageTable td { border: 1px solid #ddd; padding: .35rem .6rem; text-align: left; }
    #utilizationTable th, #coverageTable th { background: #f5f5f5; }
    .pct-ok { color: #2e7d32; font-weight: bold; }
    .pct-low { color: #1565c0; }
    .pct-over { color: #c62828; font-weight: bold; }
    .gap-under { color: #c62828; font-weight: bold; }
    .gap-ok { color: #2e7d32; }
  </style>
</head>
<body>
  <noscript><p style="color:red;font-weight:bold">⚠ JavaScript is blocked or disabled — buttons will not work.</p></noscript>
  <h1>Contractor Ops – Upload UI (POC)</h1>
  <p>Use this page to login, seed demo data, upload CSVs, and view a simple WIP chart/report.</p>

  <fieldset>
    <legend>1) Login (admin/admin or ops/ops)</legend>
    <div class="row"><label>Username</label><input id="username" value="admin" /></div>
    <div class="row"><label>Password</label>
      <input id="password" value="admin" type="password" /></div>
    <button onclick="login()">Get Token</button>
    <div class="row"><label>Token</label><input id="token" style="width: 75%" /></div>
  </fieldset>

  <fieldset>
    <legend>2) Demo data helpers (admin only)</legend>
    <button onclick="seed(true)">Seed demo data (reset=true)</button>
    <button onclick="clearDemo()">Clear all data (keep schema)</button>
  </fieldset>

  <fieldset>
    <legend>3) Upload CSVs</legend>
    <div class="row">
      <label>ADP CSV</label><input type="file" id="adp" accept=".csv" />
      <button onclick="upload('adp')">Upload ADP</button>
    </div>
    <div class="row">
      <label>QBO CSV</label><input type="file" id="qbo" accept=".csv" />
      <button onclick="upload('qbo')">Upload QBO</button>
    </div>
    <div class="row">
      <label>Budgets CSV</label><input type="file" id="budgets" accept=".csv" />
      <button onclick="upload('budgets')">Upload Budgets</button>
    </div>
  </fieldset>

  <fieldset>
    <legend>4) WIP Report</legend>
    <div class="row">
      <label>As-of date (optional)</label><input type="date" id="wipAsOf" />
      <button onclick="loadWip()">Load WIP</button>
      <button onclick="downloadWipCsv()">Download CSV</button>
    </div>
    <p class="small">Chart shows over/under billing per job. Green = over-billed, red = under-billed.</p>
    <canvas id="wipChart" width="940" height="300"></canvas>
  </fieldset>

  <fieldset>
    <legend>5) Schedule Import</legend>
    <p class="small">Upload your scheduling workbook (.xlsx). Expected sheets: <strong>Crew</strong> (Name + Level columns), <strong>Demand</strong> (Job Name + month columns with man-day counts), plus one sheet per month named like "Apr 2026" (columns = employee names, rows = day numbers, cells = job name).</p>
    <div class="row">
      <label>Schedule .xlsx</label>
      <input type="file" id="scheduleFile" accept=".xlsx,.xlsm" />
      <button onclick="importSchedule()">Import Workbook</button>
    </div>
  </fieldset>

  <fieldset>
    <legend>6) Schedule Visualization</legend>
    <div class="row">
      <label>Month</label>
      <input type="month" id="scheduleMonth" />
      <button onclick="loadSchedule()">Load Schedule</button>
    </div>
    <div id="scheduleTimeline"></div>
    <h4 style="margin-top:1rem">Utilization (assigned vs available weekdays)</h4>
    <table id="utilizationTable"><thead><tr><th>Name</th><th>Crew Type</th><th>Available Days</th><th>Assigned Days</th><th>Utilization %</th></tr></thead><tbody></tbody></table>
    <h4 style="margin-top:1rem">Coverage (demand vs assigned man-days)</h4>
    <table id="coverageTable"><thead><tr><th>Job</th><th>Crew Type</th><th>Needed</th><th>Assigned</th><th>Gap</th></tr></thead><tbody></tbody></table>
  </fieldset>

  <h3>Response log</h3>
  <pre id="out">Ready.</pre>

<script src="https://cdn.jsdelivr.net/npm/vis-timeline@7.7.3/standalone/umd/vis-timeline-graph2d.min.js"></script>
<script>
const out = document.getElementById('out');
let latestWipRows = [];

function log(data) {
  out.textContent = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
}

function logError(context, err) {
  const message = err && err.message ? err.message : String(err);
  log({ error: context, message });
}

window.addEventListener('error', (event) => {
  log({ error: 'Unhandled script error', message: event.message });
});

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason && event.reason.message ? event.reason.message : String(event.reason);
  log({ error: 'Unhandled promise rejection', message: reason });
});


async function parseResponse(resp) {
  const contentType = resp.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await resp.json()
    : await resp.text();
  return { ok: resp.ok, status: resp.status, payload };
}

async function safeRequest(url, options) {
  let resp;
  try {
    resp = await fetch(url, options);
  } catch (err) {
    throw new Error(`Network error calling ${url}: ${err && err.message ? err.message : String(err)}`);
  }

  const parsed = await parseResponse(resp);
  if (!parsed.ok) {
    throw new Error(`HTTP ${parsed.status} from ${url}: ${JSON.stringify(parsed.payload)}`);
  }
  return parsed.payload;
}

function authHeaders() {
  const token = document.getElementById('token').value.trim();
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

async function login() {
  try {
    const payload = {
      username: document.getElementById('username').value,
      password: document.getElementById('password').value,
    };
    const body = await safeRequest('/auth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (body.access_token) {
      document.getElementById('token').value = body.access_token;
    }
    log(body);
  } catch (err) {
    logError('login failed', err);
  }
}

async function seed(reset) {
  try {
    const body = await safeRequest(`/seed/demo?reset=${reset ? 'true' : 'false'}`, {
      method: 'POST',
      headers: authHeaders(),
    });
    log(body);
  } catch (err) {
    logError('seed failed', err);
  }
}

async function clearDemo() {
  const confirmed = window.confirm('This will remove all table rows. Continue?');
  if (!confirmed) return;
  try {
    const body = await safeRequest('/seed/demo', {
      method: 'DELETE',
      headers: authHeaders(),
    });
    log(body);
  } catch (err) {
    logError('clear demo failed', err);
  }
}

async function upload(kind) {
  try {
    const fileInput = document.getElementById(kind);
    if (!fileInput.files.length) {
      log(`Please choose a ${kind.toUpperCase()} CSV first.`);
      return;
    }

    const fd = new FormData();
    fd.append('file', fileInput.files[0]);

    const body = await safeRequest(`/ingest/${kind}`, {
      method: 'POST',
      headers: authHeaders(),
      body: fd,
    });
    log(body);
  } catch (err) {
    logError(`upload ${kind} failed`, err);
  }
}

function buildWipUrl() {
  const asOf = document.getElementById('wipAsOf').value;
  return asOf ? `/wip?as_of=${encodeURIComponent(asOf)}` : '/wip';
}

async function loadWip() {
  try {
    const body = await safeRequest(buildWipUrl(), {
      method: 'GET',
      headers: authHeaders(),
    });
    latestWipRows = Array.isArray(body) ? body : [];
    drawWipChart(latestWipRows);
    log(latestWipRows);
  } catch (err) {
    logError('load WIP failed', err);
  }
}

function drawWipChart(rows) {
  const canvas = document.getElementById('wipChart');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (!rows.length) {
    ctx.fillStyle = '#666';
    ctx.font = '16px sans-serif';
    ctx.fillText('No WIP rows to display.', 16, 30);
    return;
  }

  const values = rows.map(r => Number(r.over_under_billing || 0));
  const maxAbs = Math.max(1, ...values.map(v => Math.abs(v)));
  const left = 150;
  const right = canvas.width - 20;
  const width = right - left;
  const barHeight = Math.max(16, Math.floor((canvas.height - 20) / rows.length) - 6);
  const zeroX = left + width / 2;

  ctx.strokeStyle = '#999';
  ctx.beginPath();
  ctx.moveTo(zeroX, 8);
  ctx.lineTo(zeroX, canvas.height - 8);
  ctx.stroke();

  rows.forEach((row, i) => {
    const y = 10 + i * (barHeight + 6);
    const value = Number(row.over_under_billing || 0);
    const barW = Math.round((Math.abs(value) / maxAbs) * ((width / 2) - 8));
    const x = value >= 0 ? zeroX : zeroX - barW;

    ctx.fillStyle = value >= 0 ? '#2e7d32' : '#c62828';
    ctx.fillRect(x, y, Math.max(1, barW), barHeight);

    ctx.fillStyle = '#222';
    ctx.font = '12px sans-serif';
    const label = `${row.job_name}`;
    ctx.fillText(label.length > 22 ? `${label.slice(0, 22)}…` : label, 8, y + barHeight - 4);
    ctx.fillText(value.toFixed(2), value >= 0 ? x + barW + 6 : x - 70, y + barHeight - 4);
  });
}

function downloadWipCsv() {
  if (!latestWipRows.length) {
    log('No WIP data loaded yet. Click "Load WIP" first.');
    return;
  }

  const headers = [
    'job_id', 'job_name', 'customer_name', 'contract_value', 'actual_total_cost',
    'budget_total_cost', 'pct_complete', 'earned_revenue', 'billed_to_date',
    'over_under_billing', 'status', 'flags'
  ];

  const escapeCsv = (value) => {
    if (value === null || value === undefined) return '';
    const text = Array.isArray(value) ? value.join('|') : String(value);
    const escaped = text.split('"').join('""');
    return /[",\\n]/.test(text) ? `"${escaped}"` : text;
  };

  const lines = [headers.join(',')];
  for (const row of latestWipRows) {
    lines.push(headers.map(h => escapeCsv(row[h])).join(','));
  }

  const blob = new Blob([lines.join('\\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'wip_report.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// ── Schedule ──────────────────────────────────────────────────────────────

let scheduleTimeline = null;

const JOB_COLORS = [
  '#1565c0','#2e7d32','#6a1b9a','#e65100','#00695c',
  '#ad1457','#4527a0','#558b2f','#0277bd','#827717',
];
const jobColorMap = {};
let colorIdx = 0;

function jobColor(jobName) {
  if (!jobName) return '#9e9e9e';
  if (!jobColorMap[jobName]) {
    jobColorMap[jobName] = JOB_COLORS[colorIdx % JOB_COLORS.length];
    colorIdx++;
  }
  return jobColorMap[jobName];
}

async function importSchedule() {
  try {
    const fileInput = document.getElementById('scheduleFile');
    if (!fileInput.files.length) { log('Choose a .xlsx file first.'); return; }
    const fd = new FormData();
    fd.append('file', fileInput.files[0]);
    const body = await safeRequest('/schedule/import', {
      method: 'POST',
      headers: authHeaders(),
      body: fd,
    });
    log(body);
  } catch (err) {
    logError('schedule import failed', err);
  }
}

function scheduleMonthParam() {
  const v = document.getElementById('scheduleMonth').value;
  return v || new Date().toISOString().slice(0, 7);
}

async function loadSchedule() {
  try {
    const month = scheduleMonthParam();
    const [assignments, utilization, coverage] = await Promise.all([
      safeRequest('/schedule/assignments?month=' + month, { headers: authHeaders() }),
      safeRequest('/schedule/utilization?month=' + month, { headers: authHeaders() }),
      safeRequest('/schedule/coverage?month=' + month, { headers: authHeaders() }),
    ]);

    renderTimeline(assignments, month);
    renderUtilization(utilization);
    renderCoverage(coverage);
    log({ loaded: month, assignments: assignments.length });
  } catch (err) {
    logError('load schedule failed', err);
  }
}

function renderTimeline(assignments, month) {
  const container = document.getElementById('scheduleTimeline');

  // Groups = unique employees
  const empMap = {};
  assignments.forEach(a => {
    empMap[a.employee_id] = a.employee_name + (a.crew_type ? ' (' + a.crew_type + ')' : '');
  });
  const groups = new vis.DataSet(
    Object.entries(empMap).map(([id, name]) => ({ id, content: name }))
  );

  // Items = one block per assignment day
  const items = new vis.DataSet(
    assignments.map((a, i) => {
      const d = new Date(a.work_date + 'T00:00:00');
      const end = new Date(d); end.setDate(end.getDate() + 1);
      const color = jobColor(a.job_name);
      return {
        id: i,
        group: a.employee_id,
        content: a.job_name || '?',
        start: d,
        end: end,
        style: 'background:' + color + ';border-color:' + color + ';color:#fff;',
        title: (a.job_name || '?') + ' – ' + a.work_date,
      };
    })
  );

  // Set window to the selected month
  const [y, m] = month.split('-').map(Number);
  const windowStart = new Date(y, m - 1, 1);
  const windowEnd = new Date(y, m, 1);

  const options = {
    start: windowStart,
    end: windowEnd,
    min: windowStart,
    max: windowEnd,
    stack: false,
    orientation: 'top',
    moveable: false,
    zoomable: false,
  };

  if (scheduleTimeline) {
    scheduleTimeline.setGroups(groups);
    scheduleTimeline.setItems(items);
    scheduleTimeline.setWindow(windowStart, windowEnd, { animation: false });
  } else {
    scheduleTimeline = new vis.Timeline(container, items, groups, options);
  }
}

function renderUtilization(rows) {
  const tbody = document.querySelector('#utilizationTable tbody');
  tbody.innerHTML = '';
  rows.forEach(r => {
    const pct = r.utilization_pct;
    const cls = pct > 100 ? 'pct-over' : pct >= 80 ? 'pct-ok' : 'pct-low';
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + r.employee_name + '</td>' +
      '<td>' + (r.crew_type || '') + '</td>' +
      '<td>' + r.available_days + '</td>' +
      '<td>' + r.assigned_days + '</td>' +
      '<td class="' + cls + '">' + pct + '%</td>';
    tbody.appendChild(tr);
  });
}

function renderCoverage(rows) {
  const tbody = document.querySelector('#coverageTable tbody');
  tbody.innerHTML = '';
  rows.forEach(r => {
    const gap = r.gap;
    const cls = gap < 0 ? 'gap-under' : 'gap-ok';
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + r.job_name + '</td>' +
      '<td>' + (r.crew_type || 'any') + '</td>' +
      '<td>' + r.man_days_needed + '</td>' +
      '<td>' + r.man_days_assigned + '</td>' +
      '<td class="' + cls + '">' + (gap >= 0 ? '+' : '') + gap + '</td>';
    tbody.appendChild(tr);
  });
}


</script>
</body>
</html>
"""
