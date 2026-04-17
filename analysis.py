"""
Inventory Intelligence Engine
------------------------------
Classifies products by movement velocity and generates actionable recommendations.

Movement classes (configurable via AppSetting):
  fast      >= fast_mover_monthly (default 30 units/mo)  → target 3-4 weeks stock
  moderate  >= moderate_mover_monthly (default 10)        → target 4-6 weeks stock
  slow      >= 1 unit/mo                                  → target 6-8 weeks stock
  non-mover 0 dispenses in non_mover_days (default 90d)   → flag for action

Action codes (sorted by urgency):
  ORDER_URGENT       < 14 days of supply
  ORDER_SOON         below target, >= 14 days
  MAINTAIN           within target band (80%–150%)
  REDUCE_ORDERS      overstocked (150%–300% of target)
  RETURN_OR_DISPOSE  severely overstocked (>300%) or non-mover with stock
  DISCONTINUE        non-mover with zero adjusted stock
"""

from datetime import datetime, timezone, timedelta
from models import db, Product, StockSnapshot, DispensingRecord, ExpiredReturn, AppSetting


# ── Settings helpers ──────────────────────────────────────────────────────────

DEFAULTS = {
    "analysis_period_days": 90,
    "fast_mover_monthly": 30,
    "moderate_mover_monthly": 10,
    "fast_target_days": 28,
    "moderate_target_days": 42,
    "slow_target_days": 56,
    "non_mover_days": 90,
}


def get_setting(key):
    row = AppSetting.query.filter_by(key=key).first()
    default = DEFAULTS[key]
    return type(default)(row.value) if row else default


def get_all_settings():
    return {k: get_setting(k) for k in DEFAULTS}


def seed_settings():
    labels = {
        "analysis_period_days": "Days of dispensing history to analyse (e.g. 90)",
        "fast_mover_monthly": "Fast mover threshold — units/month (e.g. 30)",
        "moderate_mover_monthly": "Moderate mover threshold — units/month (e.g. 10)",
        "fast_target_days": "Fast mover target stock — days of supply (e.g. 28)",
        "moderate_target_days": "Moderate mover target stock — days of supply (e.g. 42)",
        "slow_target_days": "Slow mover target stock — days of supply (e.g. 56)",
        "non_mover_days": "Non-mover window — no dispenses in this many days (e.g. 90)",
    }
    for key, default in DEFAULTS.items():
        if not AppSetting.query.filter_by(key=key).first():
            db.session.add(AppSetting(key=key, value=str(default), description=labels[key]))
    db.session.commit()


# ── Data status ───────────────────────────────────────────────────────────────

def get_data_status():
    """Return info about what data is currently loaded."""
    from sqlalchemy import func

    latest_snap = (
        StockSnapshot.query
        .order_by(StockSnapshot.snapshot_date.desc())
        .first()
    )
    earliest_disp = (
        db.session.query(func.min(DispensingRecord.dispense_date)).scalar()
    )
    latest_disp = (
        db.session.query(func.max(DispensingRecord.dispense_date)).scalar()
    )
    total_products_with_data = (
        db.session.query(func.count(func.distinct(DispensingRecord.product_id))).scalar()
    )

    return {
        "snapshot_date": latest_snap.snapshot_date if latest_snap else None,
        "dispense_from": earliest_disp,
        "dispense_to": latest_disp,
        "dispense_days": (latest_disp - earliest_disp).days + 1 if earliest_disp and latest_disp else 0,
        "products_with_dispense_data": total_products_with_data or 0,
        "has_stock_data": latest_snap is not None,
        "has_dispense_data": earliest_disp is not None,
    }


# ── Core analysis ─────────────────────────────────────────────────────────────

ACTION_PRIORITY = {
    "ORDER_URGENT": 1,
    "RETURN_OR_DISPOSE": 2,
    "ORDER_SOON": 3,
    "REDUCE_ORDERS": 4,
    "MAINTAIN": 5,
    "DISCONTINUE": 6,
}

ACTION_LABELS = {
    "ORDER_URGENT": "Order Urgently",
    "ORDER_SOON": "Order Soon",
    "MAINTAIN": "Maintain",
    "REDUCE_ORDERS": "Reduce Orders",
    "RETURN_OR_DISPOSE": "Return / Dispose",
    "DISCONTINUE": "Discontinue",
}

CLASS_LABELS = {
    "fast": "Fast Mover",
    "moderate": "Moderate",
    "slow": "Slow Mover",
    "non-mover": "Non-Mover",
}


def run_analysis():
    """
    Run the full inventory intelligence analysis.
    Returns a list of result dicts sorted by (priority, product_name).
    """
    s = get_all_settings()
    analysis_days = s["analysis_period_days"]
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=analysis_days)

    # Use the actual date range of loaded dispensing data if shorter
    from sqlalchemy import func
    earliest = db.session.query(func.min(DispensingRecord.dispense_date)).scalar()
    latest = db.session.query(func.max(DispensingRecord.dispense_date)).scalar()
    if earliest and latest:
        available_days = (latest - earliest).days + 1
        if available_days < analysis_days:
            analysis_days = available_days
            cutoff = earliest

    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    results = []

    for product in products:
        # ── Stock ────────────────────────────────────────────────────────────
        latest_snap = (
            StockSnapshot.query
            .filter_by(product_id=product.id)
            .order_by(StockSnapshot.snapshot_date.desc())
            .first()
        )
        ems_stock = latest_snap.quantity if latest_snap else 0
        snapshot_date = latest_snap.snapshot_date if latest_snap else None

        # Expired/returned stock not yet credited in EMS
        uncredited = (
            db.session.query(func.sum(ExpiredReturn.quantity))
            .filter(
                ExpiredReturn.product_id == product.id,
                ExpiredReturn.credited_in_ems == False,
            )
            .scalar()
        ) or 0
        adjusted_stock = max(0, ems_stock - uncredited)

        # ── Dispensing velocity ──────────────────────────────────────────────
        total_dispensed = (
            db.session.query(func.sum(DispensingRecord.quantity_dispensed))
            .filter(
                DispensingRecord.product_id == product.id,
                DispensingRecord.dispense_date >= cutoff,
            )
            .scalar()
        ) or 0

        last_record = (
            DispensingRecord.query
            .filter_by(product_id=product.id)
            .order_by(DispensingRecord.dispense_date.desc())
            .first()
        )
        days_since_last = (
            (datetime.now(timezone.utc).date() - last_record.dispense_date).days
            if last_record else None
        )

        avg_daily = total_dispensed / analysis_days if analysis_days > 0 else 0
        avg_monthly = avg_daily * 30

        # Skip products with absolutely no data
        if ems_stock == 0 and total_dispensed == 0 and uncredited == 0:
            continue

        # ── Movement classification ──────────────────────────────────────────
        is_non_mover = (
            total_dispensed == 0
            or (days_since_last is not None and days_since_last >= s["non_mover_days"])
        )

        if is_non_mover:
            movement_class = "non-mover"
            target_days = 0
        elif avg_monthly >= s["fast_mover_monthly"]:
            movement_class = "fast"
            target_days = s["fast_target_days"]
        elif avg_monthly >= s["moderate_mover_monthly"]:
            movement_class = "moderate"
            target_days = s["moderate_target_days"]
        else:
            movement_class = "slow"
            target_days = s["slow_target_days"]

        # ── Days of supply ───────────────────────────────────────────────────
        if avg_daily > 0:
            days_of_supply = adjusted_stock / avg_daily
        elif adjusted_stock > 0:
            days_of_supply = 9999  # stock with zero velocity = infinite oversupply
        else:
            days_of_supply = 0

        # ── Recommendation ───────────────────────────────────────────────────
        if movement_class == "non-mover":
            if adjusted_stock > 0:
                action = "RETURN_OR_DISPOSE"
                since_str = f"{days_since_last}d" if days_since_last else f"{s['non_mover_days']}+d"
                detail = (
                    f"No movement in {since_str}. "
                    f"{adjusted_stock} {product.unit}(s) on hand — "
                    "consider returning to supplier or flagging for disposal."
                )
            else:
                action = "DISCONTINUE"
                detail = "No movement and no stock. Consider removing from active formulary."

        elif days_of_supply >= 9999:
            excess = adjusted_stock
            action = "RETURN_OR_DISPOSE"
            detail = (
                f"Stock present but no recent dispensing. "
                f"Return or dispose of ~{excess} {product.unit}(s)."
            )

        elif days_of_supply > target_days * 3:
            excess = int(adjusted_stock - target_days * avg_daily)
            action = "RETURN_OR_DISPOSE"
            detail = (
                f"{int(days_of_supply)}d supply on hand vs {target_days}d target. "
                f"Severely overstocked — consider returning ~{excess} {product.unit}(s) to supplier."
            )

        elif days_of_supply > target_days * 1.5:
            excess = int(adjusted_stock - target_days * avg_daily)
            skip_orders = max(1, int((days_of_supply - target_days) / 30))
            action = "REDUCE_ORDERS"
            detail = (
                f"{int(days_of_supply)}d supply on hand (target {target_days}d). "
                f"Skip or reduce next {skip_orders} order(s). Excess: ~{excess} {product.unit}(s)."
            )

        elif days_of_supply >= target_days * 0.8:
            action = "MAINTAIN"
            detail = (
                f"Healthy stock level — {int(days_of_supply)}d supply "
                f"(target {target_days}d, avg {avg_monthly:.0f}/mo)."
            )

        elif days_of_supply >= 14:
            order_qty = max(0, int((target_days - days_of_supply) * avg_daily))
            action = "ORDER_SOON"
            detail = (
                f"{int(days_of_supply)}d supply remaining (target {target_days}d). "
                f"Plan to order ~{order_qty} {product.unit}(s) at next opportunity."
            )

        else:
            order_qty = max(0, int((target_days - days_of_supply) * avg_daily))
            action = "ORDER_URGENT"
            detail = (
                f"Only {int(days_of_supply)}d supply left — critically low. "
                f"Order ~{order_qty} {product.unit}(s) immediately."
            )

        results.append({
            "product": product,
            "ems_stock": ems_stock,
            "snapshot_date": snapshot_date,
            "uncredited_returns": uncredited,
            "adjusted_stock": adjusted_stock,
            "total_dispensed": int(total_dispensed),
            "analysis_days": analysis_days,
            "avg_monthly": round(avg_monthly, 1),
            "avg_daily": round(avg_daily, 3),
            "movement_class": movement_class,
            "days_of_supply": None if days_of_supply >= 9999 else round(days_of_supply, 0),
            "target_days": target_days,
            "action": action,
            "action_label": ACTION_LABELS[action],
            "detail": detail,
            "priority": ACTION_PRIORITY[action],
            "days_since_last": days_since_last,
        })

    results.sort(key=lambda r: (r["priority"], r["product"].name))
    return results


def summarise(results):
    """Return high-level counts used by the dashboard."""
    counts = {a: 0 for a in ACTION_PRIORITY}
    for r in results:
        counts[r["action"]] += 1

    non_movers = [r for r in results if r["movement_class"] == "non-mover"]
    dead_stock_units = sum(r["adjusted_stock"] for r in non_movers)

    overstocked = [r for r in results if r["action"] in ("RETURN_OR_DISPOSE", "REDUCE_ORDERS")]
    excess_units = sum(
        max(0, r["adjusted_stock"] - (r["target_days"] * r["avg_daily"]))
        for r in overstocked
        if r["avg_daily"] > 0
    )

    return {
        "action_counts": counts,
        "non_mover_count": len(non_movers),
        "dead_stock_units": int(dead_stock_units),
        "overstocked_count": len(overstocked),
        "excess_units": int(excess_units),
        "urgent_count": counts["ORDER_URGENT"],
        "total_analysed": len(results),
    }
