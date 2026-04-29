"""Browser UI pages: main data/WIP page and scheduler page."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data:; "
    "connect-src 'self';"
)
_HEADERS = {"Content-Security-Policy": _CSP, "X-Content-Type-Options": "nosniff"}

_SHARED_STYLE = """
    body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 1100px; }
    nav { margin-bottom: 1.5rem; }
    nav a { margin-right: 1rem; font-weight: bold; text-decoration: none; color: #1565c0; }
    nav a.active { color: #222; border-bottom: 2px solid #222; padding-bottom: 2px; }
    fieldset { margin-bottom: 1rem; }
    label { display: inline-block; min-width: 160px; }
    button { margin-top: .5rem; margin-right: .5rem; cursor: pointer; }
    pre { background: #111; color: #0f0; padding: .75rem; border-radius: 6px;
          white-space: pre-wrap; font-size: .85rem; }
    .row { margin: .4rem 0; }
    .small { color: #666; font-size: .9rem; }
"""

_SHARED_JS = """
const out = document.getElementById('out');

function log(data) {
  out.textContent = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
}
function logError(context, err) {
  log({ error: context, message: err && err.message ? err.message : String(err) });
}
window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason && event.reason.message ? event.reason.message : String(event.reason);
  log({ error: 'Unhandled promise rejection', message: reason });
});

async function parseResponse(resp) {
  const ct = resp.headers.get('content-type') || '';
  const payload = ct.includes('application/json') ? await resp.json() : await resp.text();
  return { ok: resp.ok, status: resp.status, payload };
}
async function safeRequest(url, options) {
  let resp;
  try { resp = await fetch(url, options); }
  catch (err) { throw new Error('Network error: ' + (err.message || err)); }
  const parsed = await parseResponse(resp);
  if (!parsed.ok) throw new Error('HTTP ' + parsed.status + ': ' + JSON.stringify(parsed.payload));
  return parsed.payload;
}
"""


# ── Main page: seed helpers, CSV uploads, WIP ─────────────────────────────

@router.get("/", include_in_schema=False)
@router.get("/ui", include_in_schema=False)
def upload_ui() -> HTMLResponse:
    return HTMLResponse(content=_MAIN_HTML, headers=_HEADERS)


_MAIN_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Contractor Ops</title>
  <style>
""" + _SHARED_STYLE + """
    #wipChart { border: 1px solid #ddd; border-radius: 6px; width: 100%; max-width: 940px; }
  </style>
</head>
<body>
  <noscript><p style="color:red;font-weight:bold">JavaScript is required.</p></noscript>
  <nav>
    <a href="/" class="active">Data &amp; WIP</a>
    <a href="/scheduler">Scheduler</a>
  </nav>
  <h1>Contractor Ops</h1>

  <fieldset>
    <legend>Demo data</legend>
    <button onclick="seed(true)">Seed demo data (reset)</button>
    <button onclick="clearDemo()">Clear all data</button>
  </fieldset>

  <fieldset>
    <legend>Upload CSVs</legend>
    <div class="row">
      <label>ADP CSV</label>
      <input type="file" id="adp" accept=".csv" />
      <button onclick="upload('adp')">Upload ADP</button>
    </div>
    <div class="row">
      <label>QBO CSV</label>
      <input type="file" id="qbo" accept=".csv" />
      <button onclick="upload('qbo')">Upload QBO</button>
    </div>
    <div class="row">
      <label>Budgets CSV</label>
      <input type="file" id="budgets" accept=".csv" />
      <button onclick="upload('budgets')">Upload Budgets</button>
    </div>
  </fieldset>

  <fieldset>
    <legend>WIP Report</legend>
    <div class="row">
      <label>As-of date (optional)</label>
      <input type="date" id="wipAsOf" />
      <button onclick="loadWip()">Load WIP</button>
      <button onclick="downloadWipCsv()">Download CSV</button>
    </div>
    <p class="small">Green = over-billed, red = under-billed.</p>
    <canvas id="wipChart" width="940" height="300"></canvas>
  </fieldset>

  <h3>Response log</h3>
  <pre id="out">Ready.</pre>

<script>
""" + _SHARED_JS + """

async function seed(reset) {
  try {
    log(await safeRequest('/seed/demo?reset=' + (reset ? 'true' : 'false'), { method: 'POST' }));
  } catch (err) { logError('seed failed', err); }
}

async function clearDemo() {
  if (!window.confirm('Remove all table rows?')) return;
  try {
    log(await safeRequest('/seed/demo', { method: 'DELETE' }));
  } catch (err) { logError('clear failed', err); }
}

async function upload(kind) {
  try {
    const fi = document.getElementById(kind);
    if (!fi.files.length) { log('Choose a file first.'); return; }
    const fd = new FormData();
    fd.append('file', fi.files[0]);
    log(await safeRequest('/ingest/' + kind, { method: 'POST', body: fd }));
  } catch (err) { logError('upload failed', err); }
}

let latestWipRows = [];

async function loadWip() {
  try {
    const asOf = document.getElementById('wipAsOf').value;
    const url = asOf ? '/wip?as_of=' + encodeURIComponent(asOf) : '/wip';
    const body = await safeRequest(url, { method: 'GET' });
    latestWipRows = Array.isArray(body) ? body : [];
    drawWipChart(latestWipRows);
    log(latestWipRows);
  } catch (err) { logError('load WIP failed', err); }
}

function drawWipChart(rows) {
  const canvas = document.getElementById('wipChart');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!rows.length) {
    ctx.fillStyle = '#666'; ctx.font = '16px sans-serif';
    ctx.fillText('No WIP data.', 16, 30); return;
  }
  const values = rows.map(r => Number(r.over_under_billing || 0));
  const maxAbs = Math.max(1, ...values.map(v => Math.abs(v)));
  const left = 150, right = canvas.width - 20, width = right - left;
  const barH = Math.max(16, Math.floor((canvas.height - 20) / rows.length) - 6);
  const zeroX = left + width / 2;
  ctx.strokeStyle = '#999'; ctx.beginPath();
  ctx.moveTo(zeroX, 8); ctx.lineTo(zeroX, canvas.height - 8); ctx.stroke();
  rows.forEach((row, i) => {
    const y = 10 + i * (barH + 6), value = Number(row.over_under_billing || 0);
    const barW = Math.round((Math.abs(value) / maxAbs) * ((width / 2) - 8));
    const x = value >= 0 ? zeroX : zeroX - barW;
    ctx.fillStyle = value >= 0 ? '#2e7d32' : '#c62828';
    ctx.fillRect(x, y, Math.max(1, barW), barH);
    ctx.fillStyle = '#222'; ctx.font = '12px sans-serif';
    const label = row.job_name || '';
    ctx.fillText(label.length > 22 ? label.slice(0, 22) + '...' : label, 8, y + barH - 4);
    ctx.fillText(value.toFixed(2), value >= 0 ? x + barW + 6 : x - 70, y + barH - 4);
  });
}

function downloadWipCsv() {
  if (!latestWipRows.length) { log('Load WIP first.'); return; }
  const headers = ['job_id','job_name','customer_name','contract_value','actual_total_cost',
    'budget_total_cost','pct_complete','earned_revenue','billed_to_date',
    'over_under_billing','status','flags'];
  const esc = v => {
    if (v == null) return '';
    const t = Array.isArray(v) ? v.join('|') : String(v);
    return /[",\\n]/.test(t) ? '"' + t.split('"').join('""') + '"' : t;
  };
  const lines = [headers.join(',')];
  for (const row of latestWipRows) lines.push(headers.map(h => esc(row[h])).join(','));
  const blob = new Blob([lines.join('\\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'wip_report.csv';
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
</script>
</body>
</html>
"""


# ── Scheduler page ─────────────────────────────────────────────────────────

@router.get("/scheduler", include_in_schema=False)
def scheduler_ui() -> HTMLResponse:
    return HTMLResponse(content=_SCHEDULER_HTML, headers=_HEADERS)


_SCHEDULER_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Crew Scheduler</title>
  <link href="https://cdn.jsdelivr.net/npm/vis-timeline@7.7.3/styles/vis-timeline-graph2d.min.css" rel="stylesheet" />
  <style>
""" + _SHARED_STYLE + """
    #scheduleTimeline { border: 1px solid #ddd; border-radius: 6px; height: 480px; margin-top: .5rem; }
    table { width: 100%; border-collapse: collapse; font-size: .9rem; margin-top: .75rem; }
    th, td { border: 1px solid #ddd; padding: .35rem .6rem; text-align: left; }
    th { background: #f5f5f5; }
    .pct-ok   { color: #2e7d32; font-weight: bold; }
    .pct-low  { color: #1565c0; }
    .pct-over { color: #c62828; font-weight: bold; }
    .gap-under { color: #c62828; font-weight: bold; }
    .gap-ok    { color: #2e7d32; }
  </style>
</head>
<body>
  <noscript><p style="color:red;font-weight:bold">JavaScript is required.</p></noscript>
  <nav>
    <a href="/">Data &amp; WIP</a>
    <a href="/scheduler" class="active">Scheduler</a>
  </nav>
  <h1>Crew Scheduler</h1>

  <fieldset>
    <legend>Import Workbook</legend>
    <p class="small">Upload the crew scheduling .xlsx (sheets: <strong>Employee Contact Information</strong>, <strong>Man Day Count</strong>, plus monthly sheets named January–December).</p>
    <div class="row">
      <input type="file" id="scheduleFile" accept=".xlsx,.xlsm" />
      <button onclick="importSchedule()">Import</button>
    </div>
  </fieldset>

  <fieldset>
    <legend>View Schedule</legend>
    <div class="row">
      <label>Month</label>
      <input type="month" id="scheduleMonth" />
      <button onclick="loadSchedule()">Load</button>
    </div>
    <div id="scheduleTimeline"></div>

    <h4 style="margin-top:1.25rem">Utilization</h4>
    <table id="utilizationTable">
      <thead><tr><th>Name</th><th>Crew Type</th><th>Available Days</th><th>Assigned Days</th><th>Utilization %</th></tr></thead>
      <tbody></tbody>
    </table>

    <h4 style="margin-top:1.25rem">Coverage (demand vs assigned)</h4>
    <table id="coverageTable">
      <thead><tr><th>Job</th><th>Crew Type</th><th>Needed</th><th>Assigned</th><th>Gap</th></tr></thead>
      <tbody></tbody>
    </table>
  </fieldset>

  <h3>Response log</h3>
  <pre id="out">Ready.</pre>

<script src="https://cdn.jsdelivr.net/npm/vis-timeline@7.7.3/standalone/umd/vis-timeline-graph2d.min.js"></script>
<script>
""" + _SHARED_JS + """

async function importSchedule() {
  try {
    const fi = document.getElementById('scheduleFile');
    if (!fi.files.length) { log('Choose a .xlsx file first.'); return; }
    const fd = new FormData();
    fd.append('file', fi.files[0]);
    log(await safeRequest('/schedule/import', { method: 'POST', body: fd }));
  } catch (err) { logError('import failed', err); }
}

let scheduleTimeline = null;
const JOB_COLORS = ['#1565c0','#2e7d32','#6a1b9a','#e65100','#00695c',
  '#ad1457','#4527a0','#558b2f','#0277bd','#827717','#4e342e','#37474f'];
const jobColorMap = {};
let colorIdx = 0;
function jobColor(name) {
  if (!name) return '#9e9e9e';
  if (!jobColorMap[name]) { jobColorMap[name] = JOB_COLORS[colorIdx++ % JOB_COLORS.length]; }
  return jobColorMap[name];
}

async function loadSchedule() {
  try {
    const month = document.getElementById('scheduleMonth').value || new Date().toISOString().slice(0, 7);
    const [assignments, utilization, coverage] = await Promise.all([
      safeRequest('/schedule/assignments?month=' + month),
      safeRequest('/schedule/utilization?month=' + month),
      safeRequest('/schedule/coverage?month=' + month),
    ]);
    renderTimeline(assignments, month);
    renderUtilization(utilization);
    renderCoverage(coverage);
    log({ month, assignments: assignments.length, crew: utilization.length });
  } catch (err) { logError('load schedule failed', err); }
}

function renderTimeline(assignments, month) {
  const empMap = {};
  assignments.forEach(a => {
    empMap[a.employee_id] = a.employee_name + (a.crew_type ? ' (' + a.crew_type + ')' : '');
  });
  const groups = new vis.DataSet(
    Object.entries(empMap).map(([id, content]) => ({ id, content }))
  );
  const items = new vis.DataSet(assignments.map((a, i) => {
    const d = new Date(a.work_date + 'T00:00:00');
    const end = new Date(d); end.setDate(end.getDate() + 1);
    const color = jobColor(a.job_name);
    return { id: i, group: a.employee_id, content: a.job_name || '?', start: d, end,
      style: 'background:' + color + ';border-color:' + color + ';color:#fff;font-size:.8rem;',
      title: (a.job_name || '?') + ' – ' + a.work_date };
  }));
  const [y, m] = month.split('-').map(Number);
  const start = new Date(y, m - 1, 1), end = new Date(y, m, 1);
  const opts = { start, end, min: start, max: end, stack: false,
    orientation: 'top', moveable: false, zoomable: false };
  if (scheduleTimeline) {
    scheduleTimeline.setGroups(groups);
    scheduleTimeline.setItems(items);
    scheduleTimeline.setWindow(start, end, { animation: false });
  } else {
    scheduleTimeline = new vis.Timeline(document.getElementById('scheduleTimeline'), items, groups, opts);
  }
}

function renderUtilization(rows) {
  const tbody = document.querySelector('#utilizationTable tbody');
  tbody.innerHTML = '';
  rows.forEach(r => {
    const pct = r.utilization_pct;
    const cls = pct > 100 ? 'pct-over' : pct >= 80 ? 'pct-ok' : 'pct-low';
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>' + r.employee_name + '</td><td>' + (r.crew_type || '') + '</td><td>'
      + r.available_days + '</td><td>' + r.assigned_days + '</td><td class="' + cls + '">' + pct + '%</td>';
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
    tr.innerHTML = '<td>' + r.job_name + '</td><td>' + (r.crew_type || 'any') + '</td><td>'
      + r.man_days_needed + '</td><td>' + r.man_days_assigned + '</td><td class="' + cls + '">'
      + (gap >= 0 ? '+' : '') + gap + '</td>';
    tbody.appendChild(tr);
  });
}
</script>
</body>
</html>
"""
