import os
import io
from datetime import datetime, timezone, date as date_type
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify, send_file,
)
from werkzeug.utils import secure_filename
import pandas as pd
from dateutil.parser import parse as parse_date

from models import db, Product, ImportBatch, StockSnapshot, DispensingRecord, ExpiredReturn, AppSetting
from analysis import run_analysis, summarise, get_data_status, seed_settings, get_all_settings, DEFAULTS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "pharmaintel-secret-2024")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'pharmaintel.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

db.init_app(app)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Column name normalisation
STOCK_ALIASES = {
    "drug_code": "ndc", "drug_ndc": "ndc", "national_drug_code": "ndc",
    "drug_name": "name", "product_name": "name", "medication": "name",
    "description": "name", "item_description": "name", "item_name": "name",
    "on_hand": "quantity", "on_hand_qty": "quantity", "qty_on_hand": "quantity",
    "quantity_on_hand": "quantity", "qty": "quantity", "stock": "quantity",
    "current_stock": "quantity",
    "drug_category": "category", "drug_class": "category",
    "uom": "unit", "unit_of_measure": "unit",
}

DISPENSE_ALIASES = {
    "drug_code": "ndc", "drug_ndc": "ndc", "national_drug_code": "ndc",
    "drug_name": "name", "product_name": "name", "medication": "name",
    "description": "name", "item_description": "name", "item_name": "name",
    "qty": "quantity", "qty_dispensed": "quantity", "dispensed_qty": "quantity",
    "total_dispensed": "quantity", "units_dispensed": "quantity",
    "dispense_date": "date", "transaction_date": "date", "fill_date": "date",
    "service_date": "date", "rx_date": "date",
}


def normalise_df(df, aliases):
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df.rename(columns=aliases, inplace=True)
    return df


def resolve_product(row, create_if_missing=True):
    """Find or create a Product from a DataFrame row."""
    ndc = str(row.get("ndc", "")).strip() if "ndc" in row.index else ""
    name = str(row.get("name", "")).strip() if "name" in row.index else ""

    product = None
    if ndc:
        product = Product.query.filter_by(ndc=ndc).first()
    if not product and name:
        product = Product.query.filter(Product.name.ilike(name)).first()
    if not product and name and create_if_missing:
        product = Product(
            name=name or ndc,
            ndc=ndc or None,
            category=str(row.get("category", "")).strip() or None,
            unit=str(row.get("unit", "unit")).strip() or "unit",
        )
        db.session.add(product)
        db.session.flush()
    return product


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    status = get_data_status()
    if not status["has_stock_data"] and not status["has_dispense_data"]:
        return render_template("onboarding.html", status=status)

    results = run_analysis()
    summary = summarise(results)
    priority_items = [r for r in results if r["priority"] <= 3][:20]

    return render_template(
        "dashboard.html",
        summary=summary,
        priority_items=priority_items,
        status=status,
    )


# ── Movement Analysis ─────────────────────────────────────────────────────────

@app.route("/analysis")
def analysis():
    filter_class = request.args.get("class", "")
    filter_action = request.args.get("action", "")

    status = get_data_status()
    results = run_analysis()

    if filter_class:
        results = [r for r in results if r["movement_class"] == filter_class]
    if filter_action:
        results = [r for r in results if r["action"] == filter_action]

    return render_template(
        "analysis.html",
        results=results,
        status=status,
        filter_class=filter_class,
        filter_action=filter_action,
    )


# ── Overstock / Dead Stock ────────────────────────────────────────────────────

@app.route("/overstock")
def overstock():
    status = get_data_status()
    results = run_analysis()
    items = [r for r in results if r["action"] in ("RETURN_OR_DISPOSE", "REDUCE_ORDERS", "DISCONTINUE")]
    return render_template("overstock.html", items=items, status=status)


# ── Reorder ───────────────────────────────────────────────────────────────────

@app.route("/reorder")
def reorder():
    status = get_data_status()
    results = run_analysis()
    items = [r for r in results if r["action"] in ("ORDER_URGENT", "ORDER_SOON")]
    return render_template("reorder.html", items=items, status=status)


# ── Expired / Returns Log ─────────────────────────────────────────────────────

@app.route("/returns", methods=["GET", "POST"])
def returns_log():
    if request.method == "POST":
        product_id = request.form.get("product_id")
        quantity = request.form.get("quantity")
        event_date_str = request.form.get("event_date")
        event_type = request.form.get("event_type")
        lot_number = request.form.get("lot_number", "").strip() or None
        notes = request.form.get("notes", "").strip() or None

        if not product_id or not quantity or not event_date_str:
            flash("Product, quantity and date are required.", "danger")
        else:
            try:
                event_date = parse_date(event_date_str).date()
                entry = ExpiredReturn(
                    product_id=int(product_id),
                    quantity=int(quantity),
                    event_date=event_date,
                    event_type=event_type,
                    lot_number=lot_number,
                    notes=notes,
                    credited_in_ems=False,
                )
                db.session.add(entry)
                db.session.commit()
                flash("Entry logged. This quantity will be subtracted from your adjusted stock.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error: {e}", "danger")
        return redirect(url_for("returns_log"))

    entries = (
        ExpiredReturn.query
        .join(Product)
        .order_by(ExpiredReturn.event_date.desc())
        .all()
    )
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    status = get_data_status()
    today = datetime.now(timezone.utc).date().isoformat()
    return render_template("returns_log.html", entries=entries, products=products,
                           status=status, today=today)


@app.route("/returns/<int:entry_id>/mark-credited", methods=["POST"])
def mark_credited(entry_id):
    entry = ExpiredReturn.query.get_or_404(entry_id)
    entry.credited_in_ems = True
    db.session.commit()
    flash("Marked as credited in EMS. It will no longer reduce your adjusted stock.", "success")
    return redirect(url_for("returns_log"))


@app.route("/returns/<int:entry_id>/delete", methods=["POST"])
def delete_return(entry_id):
    entry = ExpiredReturn.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    flash("Entry deleted.", "info")
    return redirect(url_for("returns_log"))


# ── Import ─────────────────────────────────────────────────────────────────────

@app.route("/import", methods=["GET", "POST"])
def import_data():
    batches = ImportBatch.query.order_by(ImportBatch.imported_at.desc()).limit(20).all()

    if request.method == "POST":
        import_type = request.form.get("import_type")
        file = request.files.get("file")

        if not file or not file.filename:
            flash("No file selected.", "danger")
            return redirect(url_for("import_data"))
        if not allowed_file(file.filename):
            flash("Only CSV and Excel files are accepted.", "danger")
            return redirect(url_for("import_data"))

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        batch = ImportBatch(filename=filename, import_type=import_type)
        db.session.add(batch)
        db.session.flush()

        try:
            df = pd.read_csv(filepath) if filename.lower().endswith(".csv") else pd.read_excel(filepath)
        except Exception as e:
            batch.status = "failed"
            batch.error_details = str(e)
            db.session.commit()
            flash(f"Could not read file: {e}", "danger")
            return redirect(url_for("import_data"))

        batch.records_total = len(df)
        errors = []
        ok = 0

        if import_type == "stock_snapshot":
            df = normalise_df(df, STOCK_ALIASES)
            snap_date_str = request.form.get("snapshot_date", "")
            try:
                snap_date = parse_date(snap_date_str).date() if snap_date_str else datetime.now(timezone.utc).date()
            except Exception:
                snap_date = datetime.now(timezone.utc).date()

            batch.snapshot_date = snap_date

            if "quantity" not in df.columns:
                batch.status = "failed"
                batch.error_details = "Missing 'quantity' column (also tried: on_hand, qty, stock, quantity_on_hand)"
                db.session.commit()
                flash("Import failed: no quantity column found.", "danger")
                return redirect(url_for("import_data"))

            # Delete previous snapshot records for this date to allow re-import
            existing_ids = [
                s.id for s in StockSnapshot.query.filter_by(snapshot_date=snap_date).all()
            ]
            if existing_ids:
                StockSnapshot.query.filter(StockSnapshot.id.in_(existing_ids)).delete(synchronize_session=False)

            for idx, row in df.iterrows():
                try:
                    qty = int(float(row["quantity"])) if pd.notna(row.get("quantity")) else 0
                    if qty < 0:
                        qty = 0
                    product = resolve_product(row)
                    if not product:
                        errors.append(f"Row {idx+2}: cannot identify product (no ndc or name)")
                        continue
                    db.session.add(StockSnapshot(
                        product_id=product.id,
                        quantity=qty,
                        snapshot_date=snap_date,
                        import_batch_id=batch.id,
                    ))
                    ok += 1
                except Exception as e:
                    errors.append(f"Row {idx+2}: {e}")

        elif import_type == "dispensing_history":
            df = normalise_df(df, DISPENSE_ALIASES)

            period_start_str = request.form.get("period_start", "")
            period_end_str = request.form.get("period_end", "")
            try:
                period_start = parse_date(period_start_str).date() if period_start_str else None
                period_end = parse_date(period_end_str).date() if period_end_str else datetime.now(timezone.utc).date()
            except Exception:
                period_start = None
                period_end = datetime.now(timezone.utc).date()

            # Use midpoint of period as fallback date when no date column
            fallback_date = period_end or datetime.now(timezone.utc).date()
            has_date_col = "date" in df.columns

            if "quantity" not in df.columns:
                batch.status = "failed"
                batch.error_details = "Missing quantity column (also tried: qty, qty_dispensed, total_dispensed)"
                db.session.commit()
                flash("Import failed: no quantity column found.", "danger")
                return redirect(url_for("import_data"))

            batch.period_start = period_start
            batch.period_end = period_end

            for idx, row in df.iterrows():
                try:
                    qty = int(float(row["quantity"])) if pd.notna(row.get("quantity")) else 0
                    if qty <= 0:
                        continue

                    if has_date_col and pd.notna(row.get("date")):
                        try:
                            disp_date = parse_date(str(row["date"])).date()
                        except Exception:
                            disp_date = fallback_date
                    else:
                        disp_date = fallback_date

                    product = resolve_product(row)
                    if not product:
                        errors.append(f"Row {idx+2}: cannot identify product")
                        continue

                    db.session.add(DispensingRecord(
                        product_id=product.id,
                        quantity_dispensed=qty,
                        dispense_date=disp_date,
                        import_batch_id=batch.id,
                    ))
                    ok += 1
                except Exception as e:
                    errors.append(f"Row {idx+2}: {e}")

        else:
            flash("Unknown import type.", "danger")
            return redirect(url_for("import_data"))

        batch.records_ok = ok
        batch.records_failed = len(errors)
        batch.status = "success" if not errors else ("partial" if ok > 0 else "failed")
        batch.error_details = "\n".join(errors[:50]) if errors else None
        db.session.commit()

        flash(
            f"Import complete: {ok} records loaded, {len(errors)} skipped.",
            "success" if not errors else "warning",
        )
        return redirect(url_for("import_data"))

    return render_template("import.html", batches=batches)


@app.route("/import/<int:batch_id>/delete", methods=["POST"])
def delete_import(batch_id):
    batch = ImportBatch.query.get_or_404(batch_id)
    # Remove associated records
    if batch.import_type == "stock_snapshot":
        StockSnapshot.query.filter_by(import_batch_id=batch_id).delete()
    elif batch.import_type == "dispensing_history":
        DispensingRecord.query.filter_by(import_batch_id=batch_id).delete()
    db.session.delete(batch)
    db.session.commit()
    flash("Import batch and its data deleted.", "info")
    return redirect(url_for("import_data"))


@app.route("/import/template/<template_type>")
def download_template(template_type):
    templates = {
        "stock_snapshot": pd.DataFrame(columns=["ndc", "name", "quantity", "category", "unit"]),
        "dispensing_history_summary": pd.DataFrame(columns=["ndc", "name", "quantity"]),
        "dispensing_history_daily": pd.DataFrame(columns=["ndc", "name", "quantity", "date"]),
    }
    df = templates.get(template_type, templates["stock_snapshot"])
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(buf, mimetype="text/csv", as_attachment=True,
                     download_name=f"template_{template_type}.csv")


# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        for key in DEFAULTS:
            val = request.form.get(key, "").strip()
            if val:
                row = AppSetting.query.filter_by(key=key).first()
                if row:
                    row.value = val
                else:
                    db.session.add(AppSetting(key=key, value=val))
        db.session.commit()
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))

    current = get_all_settings()
    descriptions = {
        row.key: row.description
        for row in AppSetting.query.all()
    }
    status = get_data_status()
    return render_template("settings.html", settings=current, descriptions=descriptions, status=status)


# ── Export ────────────────────────────────────────────────────────────────────

@app.route("/export/<export_type>")
def export_csv(export_type):
    results = run_analysis()
    today = datetime.now(timezone.utc).date().isoformat()

    filters = {
        "all": results,
        "overstock": [r for r in results if r["action"] in ("RETURN_OR_DISPOSE", "REDUCE_ORDERS", "DISCONTINUE")],
        "reorder": [r for r in results if r["action"] in ("ORDER_URGENT", "ORDER_SOON")],
        "non_movers": [r for r in results if r["movement_class"] == "non-mover"],
    }
    data = filters.get(export_type, results)

    rows = [
        {
            "Product": r["product"].name,
            "NDC": r["product"].ndc or "",
            "Category": r["product"].category or "",
            "EMS Stock": r["ems_stock"],
            "Uncredited Returns": r["uncredited_returns"],
            "Adjusted Stock": r["adjusted_stock"],
            "Avg Dispensed/Month": r["avg_monthly"],
            "Days of Supply": r["days_of_supply"],
            "Target Days": r["target_days"],
            "Movement Class": r["movement_class"],
            "Recommended Action": r["action_label"],
            "Detail": r["detail"],
        }
        for r in data
    ]

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(buf, mimetype="text/csv", as_attachment=True,
                     download_name=f"pharmaintel_{export_type}_{today}.csv")


# ── Products (view/edit) ──────────────────────────────────────────────────────

@app.route("/products")
def products():
    all_products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return render_template("products.html", products=all_products)


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == "POST":
        product.name = request.form["name"]
        product.ndc = request.form.get("ndc") or None
        product.generic_name = request.form.get("generic_name") or None
        product.category = request.form.get("category") or None
        product.unit = request.form.get("unit", "unit")
        db.session.commit()
        flash(f"'{product.name}' updated.", "success")
        return redirect(url_for("products"))
    return render_template("product_edit.html", product=product)


@app.route("/products/<int:product_id>/deactivate", methods=["POST"])
def product_deactivate(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = False
    db.session.commit()
    flash(f"'{product.name}' removed from analysis.", "info")
    return redirect(url_for("products"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_settings()
    app.run(debug=True, host="0.0.0.0", port=5000)
