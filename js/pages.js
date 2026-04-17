// ── Overstock / Dead Stock ────────────────────────────────────────────────────
function renderOverstock() {
  const results      = runAnalysis();
  const disposeItems = results.filter(r => r.action === 'RETURN_OR_DISPOSE');
  const reduceItems  = results.filter(r => r.action === 'REDUCE_ORDERS');
  const discItems    = results.filter(r => r.action === 'DISCONTINUE');

  const disposeRows = disposeItems.map(r => `<tr>
    <td><div class="fw-semibold small">${r.product.name}</div>
        <div class="text-muted" style="font-size:.72rem">${r.product.category||''}</div></td>
    <td class="text-center fw-bold">${r.adjustedStock} ${r.product.unit||'unit'}(s)
        ${r.uncredited>0?`<div class="text-danger" style="font-size:.7rem">EMS: ${r.emsStock} (−${r.uncredited} uncredited)</div>`:''}</td>
    <td class="text-center small">${r.avgMonthly}</td>
    <td class="text-center">${r.daysOfSupply===null?'<span class="badge bg-danger">∞</span>':`<span class="badge bg-danger">${r.daysOfSupply}d</span>`}</td>
    <td class="text-center small text-muted">${r.daysSinceLast!=null?r.daysSinceLast+'d ago':'Never'}</td>
    <td class="small">${r.detail}</td></tr>`).join('');

  const reduceRows = reduceItems.map(r => `<tr>
    <td><div class="fw-semibold small">${r.product.name}</div></td>
    <td>${classBadge(r.movementClass)}</td>
    <td class="text-center fw-bold">${r.adjustedStock} ${r.product.unit||'unit'}(s)</td>
    <td class="text-center small">${r.avgMonthly}/mo</td>
    <td class="text-center"><span class="badge bg-warning text-dark">${r.daysOfSupply}d</span></td>
    <td class="text-center small text-muted">${r.targetDays}d</td>
    <td class="small">${r.detail}</td></tr>`).join('');

  const discRows = discItems.map(r => `<tr>
    <td><div class="fw-semibold small">${r.product.name}</div></td>
    <td class="text-center text-muted small">${r.daysSinceLast!=null?r.daysSinceLast+'d ago':'Never in data'}</td>
    <td class="small">${r.detail}</td></tr>`).join('');

  const sec = (headerHtml, border, colsHtml, rowsHtml) => rowsHtml ? `
    <div class="card border-0 shadow-sm border-start ${border} mb-4">
      <div class="card-header border-0 pt-3">${headerHtml}</div>
      <div class="card-body p-0"><div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
          <thead class="table-light"><tr>${colsHtml}</tr></thead>
          <tbody>${rowsHtml}</tbody>
        </table></div></div></div>` : '';

  document.getElementById('main').innerHTML = `
    ${dataBanner()}
    <div class="d-flex justify-content-between align-items-center mb-4">
      <div><h2 class="fw-bold mb-0"><i class="bi bi-box-arrow-left me-2 text-warning"></i>Dead Stock &amp; Overstock</h2>
        <p class="text-muted small mt-1 mb-0">Items with too much stock, no movement, or ready for return/disposal.</p></div>
      <button class="btn btn-sm btn-outline-secondary" onclick="exportOverstock()"><i class="bi bi-download me-1"></i>Export CSV</button>
    </div>
    ${sec(
      `<h6 class="fw-bold text-danger mb-0"><i class="bi bi-arrow-90deg-left me-2"></i>Return to Supplier / Dispose <span class="badge bg-danger ms-2">${disposeItems.length}</span></h6>
       <small class="text-muted">Severely overstocked or no movement. Consider returning for credit or disposing.</small>`,
      'border-danger border-4',
      '<th>Product</th><th class="text-center">Adjusted Stock</th><th class="text-center">Avg/mo</th><th class="text-center">Days Supply</th><th class="text-center">Last Moved</th><th>Recommendation</th>',
      disposeRows)}
    ${sec(
      `<h6 class="fw-bold text-warning mb-0"><i class="bi bi-arrow-down-circle me-2"></i>Reduce Next Orders <span class="badge bg-warning text-dark ms-2">${reduceItems.length}</span></h6>
       <small class="text-muted">Overstocked relative to dispensing rate. Skip or reduce upcoming orders.</small>`,
      'border-warning border-4',
      '<th>Product</th><th>Class</th><th class="text-center">Adjusted Stock</th><th class="text-center">Avg/mo</th><th class="text-center">Days Supply</th><th class="text-center">Target</th><th>Recommendation</th>',
      reduceRows)}
    ${sec(
      `<h6 class="fw-bold text-secondary mb-0"><i class="bi bi-x-circle me-2"></i>Consider Removing from Formulary <span class="badge bg-secondary ms-2">${discItems.length}</span></h6>
       <small class="text-muted">No movement and no stock. These items may no longer be needed.</small>`,
      'border-secondary border-4',
      '<th>Product</th><th class="text-center">Last Dispensed</th><th>Recommendation</th>',
      discRows)}
    ${!disposeItems.length && !reduceItems.length && !discItems.length
      ? `<div class="card border-0 shadow-sm"><div class="card-body text-center py-5 text-muted">
           <i class="bi bi-check-circle fs-2 text-success"></i><p class="mt-2">No overstock or dead stock detected.</p></div></div>` : ''}`;
}

// ── Reorder ───────────────────────────────────────────────────────────────────
function renderReorder() {
  const results     = runAnalysis();
  const urgentItems = results.filter(r => r.action === 'ORDER_URGENT');
  const soonItems   = results.filter(r => r.action === 'ORDER_SOON');

  const mkRows = (items, badgeCls) => items.map(r => `<tr class="${badgeCls==='bg-danger'?'row-urgent':'row-order-soon'}">
    <td><div class="fw-semibold">${r.product.name}</div>
        <div class="text-muted small">${r.product.category||''}</div></td>
    <td>${classBadge(r.movementClass)}</td>
    <td class="text-center fw-bold">${r.adjustedStock} ${r.product.unit||'unit'}(s)</td>
    <td class="text-center small">${r.avgMonthly}/mo</td>
    <td class="text-center"><span class="badge ${badgeCls}">${r.daysOfSupply??0}d</span></td>
    <td class="text-center small text-muted">${r.targetDays}d</td>
    <td class="small fw-semibold">${r.detail}</td></tr>`).join('');

  const sec = (headerHtml, border, rows) => rows ? `
    <div class="card border-0 shadow-sm border-start ${border} mb-4">
      <div class="card-header border-0 pt-3">${headerHtml}</div>
      <div class="card-body p-0"><div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
          <thead class="table-light"><tr><th>Product</th><th>Class</th><th class="text-center">Adjusted Stock</th><th class="text-center">Avg/mo</th><th class="text-center">Days Supply</th><th class="text-center">Target</th><th>Suggested Order</th></tr></thead>
          <tbody>${rows}</tbody></table></div></div></div>` : '';

  document.getElementById('main').innerHTML = `
    ${dataBanner()}
    <div class="d-flex justify-content-between align-items-center mb-4">
      <div><h2 class="fw-bold mb-0"><i class="bi bi-cart-plus me-2 text-primary"></i>Reorder Suggestions</h2>
        <p class="text-muted small mt-1 mb-0">Items below target stock level based on dispensing velocity.</p></div>
      <button class="btn btn-sm btn-outline-secondary" onclick="exportReorder()"><i class="bi bi-download me-1"></i>Export CSV</button>
    </div>
    ${sec(`<h6 class="fw-bold text-danger mb-0"><i class="bi bi-exclamation-octagon me-2"></i>Order Immediately <span class="badge bg-danger ms-2">${urgentItems.length}</span></h6>
           <small class="text-muted">Less than 14 days of supply. Order now to avoid stockout.</small>`,
      'border-danger border-4', mkRows(urgentItems,'bg-danger'))}
    ${sec(`<h6 class="fw-bold text-primary mb-0"><i class="bi bi-cart-plus me-2"></i>Order at Next Opportunity <span class="badge bg-primary ms-2">${soonItems.length}</span></h6>
           <small class="text-muted">14+ days remaining but below target. Plan next order.</small>`,
      'border-primary border-4', mkRows(soonItems,'bg-primary'))}
    ${!urgentItems.length && !soonItems.length
      ? `<div class="card border-0 shadow-sm"><div class="card-body text-center py-5 text-muted">
           <i class="bi bi-check-circle fs-2 text-success"></i><p class="mt-2">All items are at or above target stock levels.</p></div></div>` : ''}`;
}

// ── Expired / Returns Log ─────────────────────────────────────────────────────
function renderReturns() {
  const products = DB.get('products', []).filter(p => p.active !== false);
  const entries  = DB.get('returns', []).slice().reverse();
  const today    = new Date().toISOString().split('T')[0];

  const rows = entries.map(e => {
    const p = products.find(p => p.id == e.productId);
    return `<tr class="${e.credited?'table-secondary':''}">
      <td class="small fw-semibold">${p?.name||'Unknown'}</td>
      <td>${e.type==='expired_destroyed'?'<span class="badge bg-danger">Expired</span>':'<span class="badge bg-warning text-dark">Returned</span>'}</td>
      <td class="text-center fw-bold">${e.quantity}</td>
      <td class="small text-muted">${e.lot||'—'}</td>
      <td class="small text-muted">${e.date}</td>
      <td>${e.credited
        ?'<span class="badge bg-success-subtle text-success border border-success-subtle"><i class="bi bi-check me-1"></i>Credited</span>'
        :'<span class="badge bg-danger-subtle text-danger border border-danger-subtle"><i class="bi bi-x me-1"></i>Not credited</span>'}</td>
      <td>
        ${!e.credited?`<button class="btn btn-sm btn-outline-success py-0 px-1 me-1" onclick="markCredited('${e.id}')"><i class="bi bi-check-circle"></i></button>`:''}
        <button class="btn btn-sm btn-outline-danger py-0 px-1" onclick="deleteReturn('${e.id}')"><i class="bi bi-trash"></i></button>
      </td></tr>`;
  }).join('');

  document.getElementById('main').innerHTML = `
    ${dataBanner()}
    <div class="mb-4">
      <h2 class="fw-bold mb-0"><i class="bi bi-arrow-counterclockwise me-2 text-primary"></i>Expired &amp; Returned Stock Log</h2>
      <p class="text-muted mt-1">Log meds destroyed (expired) or returned to supplier — not yet credited in EMS. PharmIntel subtracts these from your adjusted stock.</p>
    </div>
    <div class="row g-4">
      <div class="col-lg-4">
        <div class="card border-0 shadow-sm">
          <div class="card-header border-0 pt-3"><h6 class="fw-bold mb-0"><i class="bi bi-plus-circle me-2 text-success"></i>Log an Entry</h6></div>
          <div class="card-body">
            <form id="returnForm">
              <div class="mb-3"><label class="form-label small fw-semibold">Product *</label>
                <select name="productId" class="form-select form-select-sm" required>
                  <option value="">— Select —</option>
                  ${products.map(p=>`<option value="${p.id}">${p.name}</option>`).join('')}
                </select></div>
              <div class="mb-3"><label class="form-label small fw-semibold">Event Type *</label>
                <select name="type" class="form-select form-select-sm">
                  <option value="expired_destroyed">Expired &amp; Destroyed</option>
                  <option value="returned_credit">Returned for Credit</option>
                </select></div>
              <div class="row">
                <div class="col-6 mb-3"><label class="form-label small fw-semibold">Quantity *</label>
                  <input type="number" name="quantity" class="form-control form-control-sm" min="1" required></div>
                <div class="col-6 mb-3"><label class="form-label small fw-semibold">Date *</label>
                  <input type="date" name="date" class="form-control form-control-sm" value="${today}" required></div>
              </div>
              <div class="mb-3"><label class="form-label small fw-semibold">Lot #</label>
                <input type="text" name="lot" class="form-control form-control-sm" placeholder="Optional"></div>
              <div class="mb-3"><label class="form-label small fw-semibold">Notes</label>
                <textarea name="notes" class="form-control form-control-sm" rows="2"></textarea></div>
              <button type="submit" class="btn btn-primary btn-sm w-100"><i class="bi bi-plus-circle me-1"></i>Log Entry</button>
            </form>
          </div>
        </div>
        <div class="alert alert-info small mt-3">
          <i class="bi bi-info-circle me-1"></i><strong>Mark as credited</strong> once your EMS reflects the deduction, so PharmIntel stops subtracting it.
        </div>
      </div>
      <div class="col-lg-8">
        <div class="card border-0 shadow-sm">
          <div class="card-header border-0 pt-3 d-flex justify-content-between">
            <h6 class="fw-bold mb-0">Log History</h6>
            <span class="badge bg-secondary">${entries.length} entries</span>
          </div>
          <div class="card-body p-0"><div class="table-responsive">
            <table class="table table-hover align-middle mb-0">
              <thead class="table-light"><tr><th>Product</th><th>Type</th><th class="text-center">Qty</th><th>Lot</th><th>Date</th><th>EMS Status</th><th>Actions</th></tr></thead>
              <tbody>${rows||'<tr><td colspan="7" class="text-center text-muted py-4">No entries yet.</td></tr>'}</tbody>
            </table></div></div></div>
      </div>
    </div>`;

  document.getElementById('returnForm')?.addEventListener('submit', e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const entry = {
      id: Date.now() + '_' + Math.random().toString(36).slice(2),
      productId: fd.get('productId'),
      type:      fd.get('type'),
      quantity:  parseInt(fd.get('quantity')),
      date:      fd.get('date'),
      lot:       fd.get('lot') || null,
      notes:     fd.get('notes') || null,
      credited:  false,
    };
    const all = DB.get('returns', []);
    all.push(entry);
    DB.set('returns', all);
    toast('Entry logged. Adjusted stock updated.');
    renderReturns();
  });
}

function markCredited(id) {
  const all = DB.get('returns', []);
  const r = all.find(r => r.id === id);
  if (r) { r.credited = true; DB.set('returns', all); toast('Marked as credited in EMS.'); renderReturns(); }
}

function deleteReturn(id) {
  if (!confirm('Delete this entry?')) return;
  DB.set('returns', DB.get('returns', []).filter(r => r.id !== id));
  toast('Entry deleted.', 'info');
  renderReturns();
}

// ── Onboarding ────────────────────────────────────────────────────────────────
function renderOnboarding() {
  document.getElementById('main').innerHTML = `
    <div class="d-flex align-items-center justify-content-center" style="min-height:80vh;">
      <div class="text-center" style="max-width:520px;">
        <i class="bi bi-graph-up-arrow text-primary" style="font-size:3.5rem;"></i>
        <h2 class="fw-bold mt-3 mb-2">Welcome to PharmIntel</h2>
        <p class="text-muted mb-4">Identify dead stock, slow movers, and get ordering recommendations from your dispensing data. Export two reports from your EMS to get started.</p>
        <div class="row g-3 mb-4 text-start">
          ${[['1','bg-primary','Export current stock','From your EMS, export on-hand quantities for all active medications.'],
             ['2','bg-info','Export dispensing history','Export dispensing records for the last 90 days (or available period).'],
             ['3','bg-success','Upload both files','Use the Import page. Column names are auto-detected from most EMS formats.'],
             ['4','bg-warning text-dark','Review your analysis','See non-movers, overstock, and exact ordering recommendations per product.'],
          ].map(([n,cls,t,d])=>`<div class="col-6"><div class="card border-0 shadow-sm h-100 p-3">
            <div class="mb-2"><span class="badge ${cls}">${n}</span></div>
            <h6 class="fw-bold">${t}</h6><p class="small text-muted mb-0">${d}</p>
          </div></div>`).join('')}
        </div>
        <button class="btn btn-primary btn-lg px-5" onclick="nav('import')">
          <i class="bi bi-cloud-upload me-2"></i>Get Started — Import EMS Data
        </button>
      </div>
    </div>`;
}
