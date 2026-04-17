'use strict';

// ── Constants ─────────────────────────────────────────────────────────────────
const DEFAULTS = {
  analysis_period_days: 90,
  fast_mover_monthly: 30,
  moderate_mover_monthly: 10,
  fast_target_days: 28,
  moderate_target_days: 42,
  slow_target_days: 56,
  non_mover_days: 90,
};

const STOCK_ALIASES = {
  drug_code:'ndc', drug_ndc:'ndc', national_drug_code:'ndc',
  drug_name:'name', product_name:'name', medication:'name',
  description:'name', item_description:'name', item_name:'name',
  on_hand:'quantity', on_hand_qty:'quantity', qty_on_hand:'quantity',
  quantity_on_hand:'quantity', qty:'quantity', stock:'quantity', current_stock:'quantity',
  drug_category:'category', drug_class:'category',
  uom:'unit', unit_of_measure:'unit',
};

const DISPENSE_ALIASES = {
  drug_code:'ndc', drug_ndc:'ndc', national_drug_code:'ndc',
  drug_name:'name', product_name:'name', medication:'name',
  description:'name', item_description:'name', item_name:'name',
  qty:'quantity', qty_dispensed:'quantity', dispensed_qty:'quantity',
  total_dispensed:'quantity', units_dispensed:'quantity',
  dispense_date:'date', transaction_date:'date', fill_date:'date',
  service_date:'date', rx_date:'date',
};

// ── Storage ───────────────────────────────────────────────────────────────────
const DB = {
  get: (key, def = null) => {
    try { const v = localStorage.getItem('pi_' + key); return v !== null ? JSON.parse(v) : def; }
    catch { return def; }
  },
  set: (key, val) => localStorage.setItem('pi_' + key, JSON.stringify(val)),
};

function getSettings() { return { ...DEFAULTS, ...DB.get('settings', {}) }; }

// ── Data status ───────────────────────────────────────────────────────────────
function getDataStatus() {
  const stock = DB.get('stock', []);
  const dispenses = DB.get('dispenses', []);
  const snapDates = stock.map(s => s.snapshotDate).filter(Boolean).sort();
  const dispDates = dispenses.map(d => d.date).filter(Boolean).sort();
  return {
    snapshotDate: snapDates.at(-1) || null,
    dispenseFrom: dispDates[0] || null,
    dispenseTo:   dispDates.at(-1) || null,
    dispenseDays: dispDates.length > 1
      ? Math.ceil((new Date(dispDates.at(-1)) - new Date(dispDates[0])) / 86400000) + 1
      : dispDates.length,
    hasStock:     stock.length > 0,
    hasDispenses: dispenses.length > 0,
  };
}

// ── Analysis engine ───────────────────────────────────────────────────────────
function runAnalysis() {
  const s = getSettings();
  const products  = DB.get('products', []).filter(p => p.active !== false);
  const stockAll  = DB.get('stock', []);
  const dispenses = DB.get('dispenses', []);
  const returns   = DB.get('returns', []);

  // Latest snapshot per product
  const stockMap = {};
  for (const snap of stockAll) {
    if (!stockMap[snap.productId] || snap.snapshotDate > stockMap[snap.productId].snapshotDate)
      stockMap[snap.productId] = snap;
  }

  // Uncredited returns per product
  const uncreditedMap = {};
  for (const r of returns.filter(r => !r.credited))
    uncreditedMap[r.productId] = (uncreditedMap[r.productId] || 0) + r.quantity;

  const today = new Date(); today.setHours(0,0,0,0);

  // Effective analysis period from actual data range
  const allDates  = dispenses.map(d => new Date(d.date)).filter(d => !isNaN(d));
  const earliest  = allDates.length ? new Date(Math.min(...allDates)) : null;
  const latest    = allDates.length ? new Date(Math.max(...allDates)) : null;
  let analysisDays = s.analysis_period_days;
  if (earliest && latest) {
    const avail = Math.ceil((latest - earliest) / 86400000) + 1;
    if (avail < analysisDays) analysisDays = avail;
  }
  const cutoff = earliest || new Date(today.getTime() - s.analysis_period_days * 86400000);

  const results = [];

  for (const product of products) {
    const snap         = stockMap[product.id];
    const emsStock     = snap ? snap.quantity : 0;
    const snapshotDate = snap ? snap.snapshotDate : null;
    const uncredited   = uncreditedMap[product.id] || 0;
    const adjustedStock = Math.max(0, emsStock - uncredited);

    const inPeriod      = dispenses.filter(d => d.productId == product.id && new Date(d.date) >= cutoff);
    const totalDispensed = inPeriod.reduce((s, d) => s + d.quantity, 0);

    const allForProduct = dispenses.filter(d => d.productId == product.id);
    const lastDate = allForProduct.length
      ? new Date(Math.max(...allForProduct.map(d => new Date(d.date)))) : null;
    const daysSinceLast = lastDate ? Math.floor((today - lastDate) / 86400000) : null;

    if (emsStock === 0 && totalDispensed === 0 && uncredited === 0) continue;

    const avgDaily   = analysisDays > 0 ? totalDispensed / analysisDays : 0;
    const avgMonthly = avgDaily * 30;

    const isNonMover = totalDispensed === 0
      || (daysSinceLast !== null && daysSinceLast >= s.non_mover_days);

    let movementClass, targetDays;
    if (isNonMover)                                { movementClass = 'non-mover'; targetDays = 0; }
    else if (avgMonthly >= s.fast_mover_monthly)   { movementClass = 'fast';      targetDays = s.fast_target_days; }
    else if (avgMonthly >= s.moderate_mover_monthly){ movementClass = 'moderate'; targetDays = s.moderate_target_days; }
    else                                           { movementClass = 'slow';      targetDays = s.slow_target_days; }

    let dos = avgDaily > 0 ? adjustedStock / avgDaily : (adjustedStock > 0 ? 9999 : 0);

    let action, detail, priority;
    const u = product.unit || 'unit';

    if (movementClass === 'non-mover') {
      if (adjustedStock > 0) {
        action = 'RETURN_OR_DISPOSE'; priority = 2;
        const since = daysSinceLast != null ? `${daysSinceLast}d` : `${s.non_mover_days}+d`;
        detail = `No movement in ${since}. ${adjustedStock} ${u}(s) on hand — consider returning to supplier or flagging for disposal.`;
      } else {
        action = 'DISCONTINUE'; priority = 6;
        detail = 'No movement and no stock. Consider removing from active formulary.';
      }
    } else if (dos >= 9999) {
      action = 'RETURN_OR_DISPOSE'; priority = 2;
      detail = `Stock present but no recent dispensing. Return or dispose of ~${adjustedStock} ${u}(s).`;
    } else if (dos > targetDays * 3) {
      const excess = Math.round(adjustedStock - targetDays * avgDaily);
      action = 'RETURN_OR_DISPOSE'; priority = 2;
      detail = `${Math.round(dos)}d supply vs ${targetDays}d target. Severely overstocked — consider returning ~${excess} ${u}(s).`;
    } else if (dos > targetDays * 1.5) {
      const excess = Math.round(adjustedStock - targetDays * avgDaily);
      const skip   = Math.max(1, Math.round((dos - targetDays) / 30));
      action = 'REDUCE_ORDERS'; priority = 4;
      detail = `${Math.round(dos)}d supply (target ${targetDays}d). Skip or reduce next ${skip} order(s). Excess: ~${excess} ${u}(s).`;
    } else if (dos >= targetDays * 0.8) {
      action = 'MAINTAIN'; priority = 5;
      detail = `Healthy stock — ${Math.round(dos)}d supply (target ${targetDays}d, avg ${avgMonthly.toFixed(1)}/mo).`;
    } else if (dos >= 14) {
      const qty = Math.max(0, Math.round((targetDays - dos) * avgDaily));
      action = 'ORDER_SOON'; priority = 3;
      detail = `${Math.round(dos)}d supply (target ${targetDays}d). Plan to order ~${qty} ${u}(s) at next opportunity.`;
    } else {
      const qty = Math.max(0, Math.round((targetDays - dos) * avgDaily));
      action = 'ORDER_URGENT'; priority = 1;
      detail = `Only ${Math.round(dos)}d supply left — critically low. Order ~${qty} ${u}(s) immediately.`;
    }

    results.push({
      product, emsStock, snapshotDate, uncredited, adjustedStock,
      totalDispensed, analysisDays,
      avgMonthly: Math.round(avgMonthly * 10) / 10,
      avgDaily:   Math.round(avgDaily * 1000) / 1000,
      movementClass,
      daysOfSupply: dos >= 9999 ? null : Math.round(dos),
      targetDays, action, detail, priority, daysSinceLast,
    });
  }

  results.sort((a, b) => a.priority - b.priority || a.product.name.localeCompare(b.product.name));
  return results;
}

function summarise(results) {
  const counts = { ORDER_URGENT:0, ORDER_SOON:0, MAINTAIN:0, REDUCE_ORDERS:0, RETURN_OR_DISPOSE:0, DISCONTINUE:0 };
  for (const r of results) counts[r.action]++;
  return {
    counts,
    nonMoverCount:    results.filter(r => r.movementClass === 'non-mover').length,
    overstockedCount: results.filter(r => ['RETURN_OR_DISPOSE','REDUCE_ORDERS'].includes(r.action)).length,
    urgentCount: counts.ORDER_URGENT,
    total: results.length,
  };
}
