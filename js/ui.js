// ── UI helpers ────────────────────────────────────────────────────────────────
function classBadge(cls) {
  const map = { fast:'bg-primary', moderate:'bg-info text-dark', slow:'bg-secondary', 'non-mover':'bg-danger' };
  const lbl = { fast:'Fast', moderate:'Moderate', slow:'Slow Mover', 'non-mover':'Non-Mover' };
  return `<span class="badge ${map[cls]}">${lbl[cls]}</span>`;
}

function actionBadge(action) {
  const map = { ORDER_URGENT:'bg-danger', ORDER_SOON:'bg-primary', MAINTAIN:'bg-success',
    REDUCE_ORDERS:'bg-warning text-dark', RETURN_OR_DISPOSE:'bg-danger', DISCONTINUE:'bg-dark' };
  const lbl = { ORDER_URGENT:'Order Urgently', ORDER_SOON:'Order Soon', MAINTAIN:'Maintain',
    REDUCE_ORDERS:'Reduce Orders', RETURN_OR_DISPOSE:'Return / Dispose', DISCONTINUE:'Discontinue' };
  return `<span class="badge ${map[action]}">${lbl[action]}</span>`;
}

function fmtDate(d) {
  if (!d) return null;
  return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' });
}

function dataBanner() {
  const st = getDataStatus();
  const snap = st.snapshotDate
    ? `<span class="badge bg-success-subtle text-success border border-success-subtle"><i class="bi bi-box-seam me-1"></i>Stock: ${fmtDate(st.snapshotDate)}</span>`
    : `<span class="badge bg-warning-subtle text-warning border border-warning-subtle"><i class="bi bi-exclamation-triangle me-1"></i>No stock snapshot</span>`;
  const disp = st.dispenseFrom
    ? `<span class="badge bg-info-subtle text-info border border-info-subtle"><i class="bi bi-calendar-range me-1"></i>Dispensing: ${fmtDate(st.dispenseFrom)} – ${fmtDate(st.dispenseTo)} (${st.dispenseDays}d)</span>`
    : `<span class="badge bg-warning-subtle text-warning border border-warning-subtle"><i class="bi bi-exclamation-triangle me-1"></i>No dispensing data</span>`;
  const btn = (!st.hasStock || !st.hasDispenses)
    ? `<a href="#" onclick="nav('import');return false;" class="btn btn-sm btn-warning py-0 ms-auto"><i class="bi bi-cloud-upload me-1"></i>Import EMS data</a>` : '';
  return `<div class="data-banner mb-3 d-flex flex-wrap gap-2 align-items-center">
    <span class="small text-muted"><i class="bi bi-database me-1"></i>Data:</span>${snap}${disp}${btn}</div>`;
}

function toast(msg, type = 'success') {
  const id = 'toast_' + Date.now();
  const div = document.createElement('div');
  div.innerHTML = `<div id="${id}" class="alert alert-${type} alert-dismissible fade show position-fixed bottom-0 end-0 m-3" style="z-index:9999;max-width:420px;">${msg}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>`;
  document.body.appendChild(div.firstChild);
  setTimeout(() => document.getElementById(id)?.remove(), 5000);
}

// ── Export helpers ────────────────────────────────────────────────────────────
function todayStr() { return new Date().toISOString().split('T')[0]; }

function toRows(results) {
  return results.map(r => ({
    Product: r.product.name, NDC: r.product.ndc || '', Category: r.product.category || '',
    'EMS Stock': r.emsStock, 'Uncredited Returns': r.uncredited, 'Adjusted Stock': r.adjustedStock,
    'Avg/Month': r.avgMonthly, 'Days of Supply': r.daysOfSupply, 'Target Days': r.targetDays,
    'Movement Class': r.movementClass, Action: r.action, Detail: r.detail,
  }));
}

function dlCSV(rows, filename) {
  const csv = Papa.unparse(rows);
  const a = Object.assign(document.createElement('a'),
    { href: URL.createObjectURL(new Blob([csv], { type:'text/csv' })), download: filename });
  a.click();
}

function exportAll()      { dlCSV(toRows(runAnalysis()), `pharmaintel_analysis_${todayStr()}.csv`); }
function exportOverstock() {
  dlCSV(toRows(runAnalysis().filter(r => ['RETURN_OR_DISPOSE','REDUCE_ORDERS','DISCONTINUE'].includes(r.action))),
    `pharmaintel_overstock_${todayStr()}.csv`);
}
function exportReorder()  {
  dlCSV(toRows(runAnalysis().filter(r => ['ORDER_URGENT','ORDER_SOON'].includes(r.action))),
    `pharmaintel_reorder_${todayStr()}.csv`);
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
function renderDashboard() {
  const st = getDataStatus();
  if (!st.hasStock && !st.hasDispenses) { renderOnboarding(); return; }
  const results = runAnalysis();
  const sum = summarise(results);
  const priority = results.filter(r => r.priority <= 3).slice(0, 20);

  const kpi = (icon, cls, val, lbl, border) =>
    `<div class="col-sm-6 col-xl-3"><div class="card border-0 shadow-sm h-100 ${border}">
      <div class="card-body d-flex align-items-center gap-3">
        <div class="rounded-3 p-3 bg-${cls}-subtle"><i class="bi ${icon} fs-3 text-${cls}"></i></div>
        <div><div class="fs-2 fw-bold text-${cls}">${val}</div><div class="text-muted small">${lbl}</div></div>
      </div></div></div>`;

  const actionBar = [
    ['ORDER_URGENT','Order Urgent','danger','reorder'],
    ['ORDER_SOON','Order Soon','primary','reorder'],
    ['MAINTAIN','Maintain','success','analysis'],
    ['REDUCE_ORDERS','Reduce Orders','warning','overstock'],
    ['RETURN_OR_DISPOSE','Return/Dispose','danger','overstock'],
    ['DISCONTINUE','Discontinue','secondary','overstock'],
  ].map(([a,l,c,pg]) =>
    `<div class="col border-start"><a href="#" onclick="nav('${pg}');return false;" class="text-decoration-none">
      <div class="fw-bold text-${c} fs-4">${sum.counts[a]}</div>
      <div class="small text-muted">${l}</div></a></div>`).join('');

  const rows = priority.map(r => {
    const rowCls = r.action==='ORDER_URGENT'?'row-urgent':
      ['RETURN_OR_DISPOSE','DISCONTINUE'].includes(r.action)?'row-dispose':
      r.action==='REDUCE_ORDERS'?'row-reduce':r.action==='ORDER_SOON'?'row-order-soon':'';
    return `<tr class="${rowCls}">
      <td><div class="fw-semibold small">${r.product.name}</div>${r.product.ndc?`<div class="text-muted" style="font-size:.72rem">${r.product.ndc}</div>`:''}</td>
      <td>${classBadge(r.movementClass)}</td>
      <td class="text-center small">${r.emsStock}${r.uncredited>0?`<div class="text-danger" style="font-size:.7rem">−${r.uncredited} uncredited</div>`:''}</td>
      <td class="text-center fw-bold small">${r.adjustedStock}</td>
      <td class="text-center small">${r.avgMonthly}</td>
      <td class="text-center small fw-bold">${r.daysOfSupply===null?'<span class="text-danger">∞</span>':r.daysOfSupply+'d'}</td>
      <td>${actionBadge(r.action)}</td>
      <td class="small text-muted detail-cell">${r.detail}</td></tr>`;
  }).join('') || '<tr><td colspan="8" class="text-center text-muted py-4">No priority actions — stock is well managed.</td></tr>';

  document.getElementById('main').innerHTML = `
    ${dataBanner()}
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h2 class="fw-bold mb-0"><i class="bi bi-speedometer2 me-2 text-primary"></i>Dashboard</h2>
      <button class="btn btn-sm btn-outline-secondary" onclick="exportAll()"><i class="bi bi-download me-1"></i>Export Full Analysis</button>
    </div>
    <div class="row g-3 mb-4">
      ${kpi('bi-exclamation-octagon','danger',sum.urgentCount,'Urgent Reorders','border-start border-danger border-4')}
      ${kpi('bi-hourglass-bottom','warning',sum.nonMoverCount,'Non-Movers','border-start border-warning border-4')}
      ${kpi('bi-box-arrow-left','info',sum.overstockedCount,'Overstocked Items','border-start border-info border-4')}
      ${kpi('bi-boxes','secondary',sum.total,'Products Analysed','')}
    </div>
    <div class="card border-0 shadow-sm mb-4"><div class="card-body py-3">
      <div class="row g-2 text-center">${actionBar}</div></div></div>
    <div class="card border-0 shadow-sm">
      <div class="card-header border-0 d-flex justify-content-between pt-3">
        <h6 class="fw-bold mb-0"><i class="bi bi-list-task me-2 text-danger"></i>Priority Actions</h6>
        <a href="#" onclick="nav('analysis');return false;" class="btn btn-sm btn-outline-secondary">View All →</a>
      </div>
      <div class="card-body p-0"><div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
          <thead class="table-light"><tr><th>Product</th><th>Class</th><th class="text-center">EMS Stock</th><th class="text-center">Adjusted</th><th class="text-center">Avg/mo</th><th class="text-center">Days Supply</th><th>Action</th><th>Detail</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div></div></div>`;
}

// ── Movement Analysis ─────────────────────────────────────────────────────────
function renderAnalysis() {
  const results = runAnalysis();
  document.getElementById('main').innerHTML = `
    ${dataBanner()}
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h2 class="fw-bold mb-0"><i class="bi bi-bar-chart-line me-2 text-primary"></i>Movement Analysis</h2>
      <button class="btn btn-sm btn-outline-secondary" onclick="exportAll()"><i class="bi bi-download me-1"></i>Export CSV</button>
    </div>
    <div class="card border-0 shadow-sm mb-3"><div class="card-body py-2 d-flex flex-wrap gap-2 align-items-end">
      <div><label class="form-label small fw-semibold mb-1">Class</label>
        <select id="fClass" class="form-select form-select-sm" onchange="filterAnalysis()">
          <option value="">All Classes</option>
          <option value="fast">Fast Mover</option><option value="moderate">Moderate</option>
          <option value="slow">Slow Mover</option><option value="non-mover">Non-Mover</option>
        </select></div>
      <div><label class="form-label small fw-semibold mb-1">Action</label>
        <select id="fAction" class="form-select form-select-sm" onchange="filterAnalysis()">
          <option value="">All Actions</option>
          <option value="ORDER_URGENT">Order Urgently</option><option value="ORDER_SOON">Order Soon</option>
          <option value="MAINTAIN">Maintain</option><option value="REDUCE_ORDERS">Reduce Orders</option>
          <option value="RETURN_OR_DISPOSE">Return / Dispose</option><option value="DISCONTINUE">Discontinue</option>
        </select></div>
      <div><label class="form-label small fw-semibold mb-1">Search</label>
        <input type="text" id="fSearch" class="form-control form-control-sm" placeholder="Product name…" oninput="filterAnalysis()" style="max-width:200px;"></div>
    </div></div>
    <div class="card border-0 shadow-sm"><div class="card-body p-0"><div class="table-responsive">
      <table class="table table-hover align-middle mb-0">
        <thead class="table-light"><tr>
          <th>Product</th><th>Category</th><th class="text-center">EMS</th>
          <th class="text-center">Uncredited</th><th class="text-center">Adjusted</th>
          <th class="text-center">Dispensed</th><th class="text-center">Avg/mo</th>
          <th class="text-center">Days Supply</th><th class="text-center">Target</th>
          <th>Class</th><th>Action</th><th>Detail</th>
        </tr></thead>
        <tbody id="analysisBody">${buildAnalysisRows(results)}</tbody>
      </table></div>
      <div id="analysisCount" class="px-3 py-2 border-top text-muted small">${results.length} product(s)</div>
    </div></div>`;
}

function buildAnalysisRows(results) {
  if (!results.length) return '<tr><td colspan="12" class="text-center text-muted py-5"><i class="bi bi-inbox fs-2"></i><p class="mt-2">No data. <a href="#" onclick="nav(\'import\');return false;">Import EMS data</a> to begin.</p></td></tr>';
  return results.map(r => {
    const rowCls = r.action==='ORDER_URGENT'?'row-urgent':
      ['RETURN_OR_DISPOSE','DISCONTINUE'].includes(r.action)?'row-dispose':
      r.action==='REDUCE_ORDERS'?'row-reduce':r.action==='ORDER_SOON'?'row-order-soon':'';
    return `<tr class="${rowCls}">
      <td><div class="fw-semibold small">${r.product.name}</div>${r.product.ndc?`<div class="text-muted" style="font-size:.72rem">${r.product.ndc}</div>`:''}</td>
      <td class="small text-muted">${r.product.category||'—'}</td>
      <td class="text-center small">${r.emsStock}</td>
      <td class="text-center small ${r.uncredited>0?'text-danger fw-semibold':''}">${r.uncredited||'—'}</td>
      <td class="text-center fw-bold small">${r.adjustedStock}</td>
      <td class="text-center small">${r.totalDispensed}</td>
      <td class="text-center small">${r.avgMonthly}</td>
      <td class="text-center small fw-bold">${r.daysOfSupply===null?'<span class="text-danger">∞</span>':r.daysOfSupply+'d'}</td>
      <td class="text-center small text-muted">${r.targetDays||'—'}</td>
      <td>${classBadge(r.movementClass)}</td>
      <td>${actionBadge(r.action)}</td>
      <td class="small text-muted detail-cell">${r.detail}</td></tr>`;
  }).join('');
}

function filterAnalysis() {
  const cls    = document.getElementById('fClass')?.value || '';
  const action = document.getElementById('fAction')?.value || '';
  const search = (document.getElementById('fSearch')?.value || '').toLowerCase();
  let results  = runAnalysis();
  if (cls)    results = results.filter(r => r.movementClass === cls);
  if (action) results = results.filter(r => r.action === action);
  if (search) results = results.filter(r =>
    r.product.name.toLowerCase().includes(search) ||
    (r.product.ndc||'').toLowerCase().includes(search) ||
    (r.product.category||'').toLowerCase().includes(search));
  const body = document.getElementById('analysisBody');
  const count = document.getElementById('analysisCount');
  if (body)  body.innerHTML  = buildAnalysisRows(results);
  if (count) count.textContent = `${results.length} product(s)`;
}
