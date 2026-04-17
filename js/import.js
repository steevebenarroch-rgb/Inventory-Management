// ── File parsing ──────────────────────────────────────────────────────────────
function parseFile(file, callback) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (ext === 'csv') {
    Papa.parse(file, { header:true, skipEmptyLines:true,
      complete: r => callback(r.data, null),
      error:    e => callback(null, e.message) });
  } else if (ext === 'xlsx' || ext === 'xls') {
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const wb = XLSX.read(e.target.result, { type:'array' });
        callback(XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval:'' }), null);
      } catch(err) { callback(null, err.message); }
    };
    reader.readAsArrayBuffer(file);
  } else {
    callback(null, 'Unsupported file type. Please use CSV or Excel (.xlsx).');
  }
}

function normaliseRow(raw, aliases) {
  const out = {};
  for (const [k, v] of Object.entries(raw)) {
    const key = k.trim().toLowerCase().replace(/\s+/g, '_');
    out[aliases[key] || key] = typeof v === 'string' ? v.trim() : v;
  }
  return out;
}

function resolveOrCreateProduct(row) {
  const products = DB.get('products', []);
  const ndc  = (row.ndc  || '').toString().trim();
  const name = (row.name || '').toString().trim();
  let product = null;
  if (ndc)  product = products.find(p => p.ndc === ndc);
  if (!product && name) product = products.find(p => p.name.toLowerCase() === name.toLowerCase());
  if (!product && (ndc || name)) {
    product = {
      id:       Date.now().toString() + '_' + Math.random().toString(36).slice(2),
      name:     name || ndc,
      ndc:      ndc  || null,
      category: (row.category || '').toString().trim() || null,
      unit:     (row.unit || 'unit').toString().trim() || 'unit',
      active:   true,
    };
    products.push(product);
    DB.set('products', products);
  }
  return product;
}

// ── Import: stock snapshot ────────────────────────────────────────────────────
function importStock(rawData, snapDate, filename) {
  const errors = [];
  let ok = 0;
  const existing = DB.get('stock', []).filter(s => s.snapshotDate !== snapDate);
  const newSnaps = [];
  for (const [i, raw] of rawData.entries()) {
    const row = normaliseRow(raw, STOCK_ALIASES);
    const qty = parseInt(row.quantity);
    if (isNaN(qty) || qty < 0) { errors.push(`Row ${i+2}: invalid quantity`); continue; }
    const product = resolveOrCreateProduct(row);
    if (!product) { errors.push(`Row ${i+2}: cannot identify product (need ndc or name column)`); continue; }
    newSnaps.push({ productId: product.id, quantity: qty, snapshotDate: snapDate });
    ok++;
  }
  DB.set('stock', [...existing, ...newSnaps]);
  logBatch(filename, 'stock_snapshot', rawData.length, ok, errors, snapDate, null, null);
  toast(`Stock import: ${ok} records loaded${errors.length?' ('+errors.length+' skipped)':''}.`, errors.length?'warning':'success');
  renderImport();
}

// ── Import: dispensing history ────────────────────────────────────────────────
function importDispenses(rawData, periodStart, periodEnd, filename) {
  const errors = [];
  let ok = 0;
  const fallbackDate = periodEnd;
  const hasDateCol = rawData.length > 0 &&
    Object.keys(normaliseRow(rawData[0], DISPENSE_ALIASES)).includes('date');
  const newRecords = [];
  for (const [i, raw] of rawData.entries()) {
    const row = normaliseRow(raw, DISPENSE_ALIASES);
    const qty = parseInt(row.quantity);
    if (isNaN(qty) || qty <= 0) continue;
    let dispDate = fallbackDate;
    if (hasDateCol && row.date) {
      const parsed = new Date(row.date);
      if (!isNaN(parsed)) dispDate = parsed.toISOString().split('T')[0];
    }
    const product = resolveOrCreateProduct(row);
    if (!product) { errors.push(`Row ${i+2}: cannot identify product`); continue; }
    newRecords.push({ productId: product.id, quantity: qty, date: dispDate });
    ok++;
  }
  DB.set('dispenses', [...DB.get('dispenses', []), ...newRecords]);
  logBatch(filename, 'dispensing_history', rawData.length, ok, errors, null, periodStart, periodEnd);
  toast(`Dispensing import: ${ok} records loaded${errors.length?' ('+errors.length+' skipped)':''}.`, errors.length?'warning':'success');
  renderImport();
}

function logBatch(filename, type, total, ok, errors, snapDate, periodStart, periodEnd) {
  const batches = DB.get('importBatches', []);
  batches.push({
    id: Date.now().toString(),
    filename, type, total, ok, failed: errors.length,
    status: errors.length === 0 ? 'success' : ok > 0 ? 'partial' : 'failed',
    errors: errors.length ? errors.slice(0,30).join('\n') : null,
    date:   snapDate,
    period: periodStart && periodEnd ? `${periodStart} – ${periodEnd}` : null,
    importedAt: new Date().toLocaleString(),
  });
  DB.set('importBatches', batches);
}

// ── Import page ───────────────────────────────────────────────────────────────
function renderImport() {
  const batches = DB.get('importBatches', []).slice().reverse().slice(0, 20);
  const today   = new Date().toISOString().split('T')[0];

  const batchRows = batches.map(b => `<tr>
    <td class="fw-semibold small">${b.filename}</td>
    <td>${b.type==='stock_snapshot'
      ?'<span class="badge bg-success-subtle text-success border border-success-subtle">Stock Snapshot</span>'
      :'<span class="badge bg-info-subtle text-info border border-info-subtle">Dispensing History</span>'}</td>
    <td class="text-muted small">${b.period||b.date||'—'}</td>
    <td class="text-center">${b.total}</td>
    <td class="text-center text-success fw-bold">${b.ok}</td>
    <td class="text-center text-danger">${b.failed}</td>
    <td>${b.status==='success'?'<span class="badge bg-success">Success</span>':b.status==='partial'?'<span class="badge bg-warning text-dark">Partial</span>':'<span class="badge bg-danger">Failed</span>'}</td>
    <td class="text-muted small">${b.importedAt||''}</td>
    <td>
      ${b.errors?`<button class="btn btn-sm btn-outline-danger py-0 px-1 me-1" onclick="showErrors('${b.id}')"><i class="bi bi-exclamation-circle"></i></button>`:''}
      <button class="btn btn-sm btn-outline-danger py-0 px-1" onclick="deleteImport('${b.id}')"><i class="bi bi-trash"></i></button>
    </td></tr>`).join('');

  document.getElementById('main').innerHTML = `
    ${dataBanner()}
    <div class="mb-4">
      <h2 class="fw-bold mb-0"><i class="bi bi-cloud-upload me-2 text-primary"></i>Import from EMS</h2>
      <p class="text-muted mt-1">Upload CSV or Excel exports. Two imports needed for full analysis. Requires internet for Bootstrap/PapaParse/SheetJS.</p>
    </div>
    <div class="row g-4">
      <div class="col-lg-6">
        <div class="card border-0 shadow-sm h-100">
          <div class="card-header border-0 pt-3">
            <h6 class="fw-bold mb-0"><i class="bi bi-box-seam me-2 text-success"></i>1. Current Stock Snapshot</h6>
            <small class="text-muted">Export current on-hand quantities from your EMS.</small>
          </div>
          <div class="card-body">
            <form id="stockForm">
              <div class="mb-3"><label class="form-label small fw-semibold">File (CSV or Excel) *</label>
                <input type="file" id="stockFile" class="form-control form-control-sm" accept=".csv,.xlsx,.xls" required></div>
              <div class="mb-3"><label class="form-label small fw-semibold">Snapshot Date</label>
                <input type="date" id="snapDate" class="form-control form-control-sm" value="${today}"></div>
              <button type="submit" class="btn btn-success btn-sm w-100"><i class="bi bi-upload me-1"></i>Upload Stock Snapshot</button>
            </form>
            <hr class="my-3">
            <p class="small text-muted mb-2"><strong>Required:</strong> <code>quantity</code> + <code>ndc</code> or <code>name</code><br><strong>Optional:</strong> category, unit</p>
            <button class="btn btn-outline-secondary btn-sm" onclick="dlTemplate('stock')"><i class="bi bi-download me-1"></i>Download Template</button>
          </div>
        </div>
      </div>
      <div class="col-lg-6">
        <div class="card border-0 shadow-sm h-100">
          <div class="card-header border-0 pt-3">
            <h6 class="fw-bold mb-0"><i class="bi bi-calendar-range me-2 text-info"></i>2. Dispensing History</h6>
            <small class="text-muted">Export dispensing records for the last 90 days.</small>
          </div>
          <div class="card-body">
            <form id="dispenseForm">
              <div class="mb-3"><label class="form-label small fw-semibold">File (CSV or Excel) *</label>
                <input type="file" id="dispFile" class="form-control form-control-sm" accept=".csv,.xlsx,.xls" required></div>
              <div class="row">
                <div class="col-6 mb-3"><label class="form-label small fw-semibold">Period Start *</label>
                  <input type="date" id="pStart" class="form-control form-control-sm" required></div>
                <div class="col-6 mb-3"><label class="form-label small fw-semibold">Period End *</label>
                  <input type="date" id="pEnd" class="form-control form-control-sm" value="${today}" required></div>
              </div>
              <div class="alert alert-info small py-2 mb-3"><i class="bi bi-lightbulb me-1"></i>If your file has a <code>date</code> column per row those dates are used. Otherwise the period end date is used for all rows.</div>
              <button type="submit" class="btn btn-info btn-sm w-100 text-white"><i class="bi bi-upload me-1"></i>Upload Dispensing History</button>
            </form>
            <hr class="my-3">
            <p class="small text-muted mb-2"><strong>Required:</strong> <code>quantity</code> + <code>ndc</code> or <code>name</code><br><strong>Optional:</strong> <code>date</code> (fill_date, dispense_date, rx_date…)</p>
            <div class="d-flex gap-2">
              <button class="btn btn-outline-secondary btn-sm" onclick="dlTemplate('disp_summary')"><i class="bi bi-download me-1"></i>Summary Template</button>
              <button class="btn btn-outline-secondary btn-sm" onclick="dlTemplate('disp_daily')"><i class="bi bi-download me-1"></i>Daily Template</button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="card border-0 shadow-sm mt-4">
      <div class="card-header border-0 pt-3"><h6 class="fw-bold mb-0"><i class="bi bi-info-circle me-2 text-secondary"></i>Supported Column Aliases</h6></div>
      <div class="card-body">
        <div class="row"><div class="col-md-6">
          <table class="table table-sm table-bordered small mb-0"><thead class="table-light"><tr><th>Column</th><th>Also recognised as</th></tr></thead><tbody>
            <tr><td><code>ndc</code></td><td>drug_code, drug_ndc, national_drug_code</td></tr>
            <tr><td><code>name</code></td><td>drug_name, product_name, medication, description</td></tr>
            <tr><td><code>quantity</code></td><td>on_hand, qty_on_hand, qty, stock (for snapshot)<br>qty_dispensed, total_dispensed (for dispensing)</td></tr>
          </tbody></table>
        </div><div class="col-md-6 mt-3 mt-md-0">
          <table class="table table-sm table-bordered small mb-0"><thead class="table-light"><tr><th>Column</th><th>Also recognised as</th></tr></thead><tbody>
            <tr><td><code>date</code></td><td>dispense_date, fill_date, transaction_date, rx_date</td></tr>
            <tr><td><code>category</code></td><td>drug_category, drug_class</td></tr>
            <tr><td><code>unit</code></td><td>uom, unit_of_measure</td></tr>
          </tbody></table>
        </div></div>
      </div>
    </div>
    <div class="card border-0 shadow-sm mt-4">
      <div class="card-header border-0 pt-3"><h6 class="fw-bold mb-0"><i class="bi bi-clock-history me-2 text-secondary"></i>Import History</h6></div>
      <div class="card-body p-0"><div class="table-responsive">
        <table class="table table-hover align-middle mb-0 small">
          <thead class="table-light"><tr><th>File</th><th>Type</th><th>Period/Date</th><th class="text-center">Records</th><th class="text-center">OK</th><th class="text-center">Failed</th><th>Status</th><th>Imported</th><th></th></tr></thead>
          <tbody>${batchRows||'<tr><td colspan="9" class="text-center text-muted py-4">No imports yet.</td></tr>'}</tbody>
        </table></div></div></div>`;

  document.getElementById('stockForm')?.addEventListener('submit', e => {
    e.preventDefault();
    const file = document.getElementById('stockFile').files[0];
    const date = document.getElementById('snapDate').value || todayStr();
    if (!file) return;
    parseFile(file, (data, err) => err ? toast(err, 'danger') : importStock(data, date, file.name));
  });

  document.getElementById('dispenseForm')?.addEventListener('submit', e => {
    e.preventDefault();
    const file   = document.getElementById('dispFile').files[0];
    const pStart = document.getElementById('pStart').value;
    const pEnd   = document.getElementById('pEnd').value;
    if (!file || !pStart || !pEnd) { toast('Please fill all required fields.', 'danger'); return; }
    parseFile(file, (data, err) => err ? toast(err, 'danger') : importDispenses(data, pStart, pEnd, file.name));
  });
}

function showErrors(id) {
  const b = DB.get('importBatches', []).find(b => b.id === id);
  if (b?.errors) alert('Import errors:\n\n' + b.errors);
}

function deleteImport(id) {
  if (!confirm('Delete this import record? The data it loaded will NOT be removed.')) return;
  DB.set('importBatches', DB.get('importBatches', []).filter(b => b.id !== id));
  toast('Record deleted.', 'info');
  renderImport();
}

function dlTemplate(type) {
  const csvs = {
    stock:        'ndc,name,quantity,category,unit\n00093-3160-01,Amoxicillin 500mg,150,Antibiotics,capsule',
    disp_summary: 'ndc,name,quantity\n00093-3160-01,Amoxicillin 500mg,420',
    disp_daily:   'ndc,name,quantity,date\n00093-3160-01,Amoxicillin 500mg,14,2026-04-01\n00093-3160-01,Amoxicillin 500mg,12,2026-04-02',
  };
  const names = { stock:'template_stock_snapshot.csv', disp_summary:'template_dispensing_summary.csv', disp_daily:'template_dispensing_daily.csv' };
  const a = Object.assign(document.createElement('a'),
    { href: URL.createObjectURL(new Blob([csvs[type]], { type:'text/csv' })), download: names[type] });
  a.click();
}

// ── Settings ──────────────────────────────────────────────────────────────────
function renderSettings() {
  const s = getSettings();
  const field = (key, label, hint, min, max) =>
    `<div class="mb-3"><label class="form-label small fw-semibold">${label}</label>
     <input type="number" name="${key}" class="form-control" value="${s[key]}" min="${min}" max="${max}">
     <div class="form-text">${hint}</div></div>`;

  document.getElementById('main').innerHTML = `
    ${dataBanner()}
    <div class="mb-4">
      <h2 class="fw-bold mb-0"><i class="bi bi-sliders me-2 text-primary"></i>Analysis Settings</h2>
      <p class="text-muted mt-1">Tune thresholds used to classify products and generate recommendations.</p>
    </div>
    <div class="row justify-content-center"><div class="col-lg-8">
      <form id="settingsForm">
        <div class="card border-0 shadow-sm mb-4">
          <div class="card-header border-0 pt-3"><h6 class="fw-bold mb-0"><i class="bi bi-calendar-range me-2 text-info"></i>Analysis Period</h6></div>
          <div class="card-body"><div class="row">
            <div class="col-md-6">${field('analysis_period_days','Days of history to analyse','How many days of dispensing history to use.',7,365)}</div>
            <div class="col-md-6">${field('non_mover_days','Non-mover window (days)','No dispenses in this many days = non-mover.',7,365)}</div>
          </div></div>
        </div>
        <div class="card border-0 shadow-sm mb-4">
          <div class="card-header border-0 pt-3"><h6 class="fw-bold mb-0"><i class="bi bi-speedometer me-2 text-primary"></i>Movement Thresholds (units/month)</h6></div>
          <div class="card-body"><div class="row">
            <div class="col-md-6">${field('fast_mover_monthly','<span class="badge bg-primary me-1">Fast</span> Minimum units/month','Products dispensing ≥ this per month are fast movers.',1,9999)}</div>
            <div class="col-md-6">${field('moderate_mover_monthly','<span class="badge bg-info text-dark me-1">Moderate</span> Minimum units/month','Between moderate and fast = moderate mover.',1,9999)}</div>
          </div></div>
        </div>
        <div class="card border-0 shadow-sm mb-4">
          <div class="card-header border-0 pt-3"><h6 class="fw-bold mb-0"><i class="bi bi-bullseye me-2 text-success"></i>Target Stock Levels (days of supply)</h6></div>
          <div class="card-body"><div class="row">
            <div class="col-md-4">${field('fast_target_days','<span class="badge bg-primary me-1">Fast</span> Target Days','e.g. 28 days (4 weeks)',7,180)}</div>
            <div class="col-md-4">${field('moderate_target_days','<span class="badge bg-info text-dark me-1">Moderate</span> Target Days','e.g. 42 days (6 weeks)',7,180)}</div>
            <div class="col-md-4">${field('slow_target_days','<span class="badge bg-secondary me-1">Slow</span> Target Days','e.g. 56 days (8 weeks)',7,365)}</div>
          </div></div>
        </div>
        <div class="d-flex gap-2">
          <button type="submit" class="btn btn-primary px-4"><i class="bi bi-check-circle me-1"></i>Save Settings</button>
          <button type="button" class="btn btn-outline-danger" onclick="resetSettings()">Reset to Defaults</button>
        </div>
      </form>
    </div></div>`;

  document.getElementById('settingsForm')?.addEventListener('submit', e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const saved = {};
    for (const [k, v] of fd.entries()) saved[k] = parseFloat(v);
    DB.set('settings', saved);
    toast('Settings saved.');
  });
}

function resetSettings() {
  if (!confirm('Reset all settings to defaults?')) return;
  DB.set('settings', {});
  renderSettings();
  toast('Settings reset to defaults.');
}

// ── Router + init ─────────────────────────────────────────────────────────────
const PAGES = {
  dashboard: renderDashboard,
  analysis:  renderAnalysis,
  overstock: renderOverstock,
  reorder:   renderReorder,
  returns:   renderReturns,
  import:    renderImport,
  settings:  renderSettings,
};

function nav(page) {
  document.querySelectorAll('#nav-links .nav-link').forEach(el =>
    el.classList.toggle('active', el.dataset.page === page));
  window.location.hash = page;
  (PAGES[page] || renderDashboard)();
}

document.getElementById('nav-links').addEventListener('click', e => {
  const link = e.target.closest('[data-page]');
  if (link) { e.preventDefault(); nav(link.dataset.page); }
});

nav(PAGES[window.location.hash.slice(1)] ? window.location.hash.slice(1) : 'dashboard');
