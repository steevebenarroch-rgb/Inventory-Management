import os
import io
import json
from datetime import datetime, timezone, timedelta
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    send_file,
)
from werkzeug.utils import secure_filename
import pandas as pd
from models import db, Category, Supplier, Product, InventoryItem, Transaction, ImportLog

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "pharmacy-inventory-secret-key-2024")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'pharmacy.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

db.init_app(app)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def seed_demo_data():
    if Category.query.count() > 0:
        return

    categories = [
        Category(name="Analgesics"),
        Category(name="Antibiotics"),
        Category(name="Cardiovascular"),
        Category(name="Diabetes"),
        Category(name="Respiratory"),
        Category(name="Vitamins & Supplements"),
        Category(name="OTC"),
    ]
    db.session.add_all(categories)

    suppliers = [
        Supplier(name="PharmaCo Distributors", contact="John Smith", phone="555-0101", email="orders@pharmaco.com"),
        Supplier(name="MedSupply Inc.", contact="Jane Doe", phone="555-0202", email="sales@medsupply.com"),
        Supplier(name="Generic Pharma Ltd.", contact="Bob Johnson", phone="555-0303", email="info@genericpharma.com"),
    ]
    db.session.add_all(suppliers)
    db.session.flush()

    cat = {c.name: c for c in categories}
    sup = {s.name: s for s in suppliers}

    products = [
        Product(name="Amoxicillin 500mg Capsules", ndc="00093-3160-01", generic_name="Amoxicillin",
                category=cat["Antibiotics"], supplier=sup["PharmaCo Distributors"],
                unit="capsule", reorder_point=50, unit_cost=0.25),
        Product(name="Metformin 500mg Tablets", ndc="00093-1048-01", generic_name="Metformin HCl",
                category=cat["Diabetes"], supplier=sup["PharmaCo Distributors"],
                unit="tablet", reorder_point=100, unit_cost=0.10),
        Product(name="Lisinopril 10mg Tablets", ndc="00071-0207-23", generic_name="Lisinopril",
                category=cat["Cardiovascular"], supplier=sup["MedSupply Inc."],
                unit="tablet", reorder_point=50, unit_cost=0.15),
        Product(name="Atorvastatin 20mg Tablets", ndc="00071-0156-23", generic_name="Atorvastatin Calcium",
                category=cat["Cardiovascular"], supplier=sup["MedSupply Inc."],
                unit="tablet", reorder_point=50, unit_cost=0.30),
        Product(name="Albuterol Inhaler 90mcg", ndc="00173-0682-20", generic_name="Albuterol Sulfate",
                category=cat["Respiratory"], supplier=sup["Generic Pharma Ltd."],
                unit="inhaler", reorder_point=10, unit_cost=8.50),
        Product(name="Ibuprofen 200mg Tablets", ndc="00904-5616-51", generic_name="Ibuprofen",
                category=cat["Analgesics"], supplier=sup["Generic Pharma Ltd."],
                unit="tablet", reorder_point=100, unit_cost=0.05),
        Product(name="Acetaminophen 500mg Tablets", ndc="00450-0449-71", generic_name="Acetaminophen",
                category=cat["Analgesics"], supplier=sup["Generic Pharma Ltd."],
                unit="tablet", reorder_point=100, unit_cost=0.04),
        Product(name="Vitamin D3 1000 IU", ndc="00904-5728-60", generic_name="Cholecalciferol",
                category=cat["Vitamins & Supplements"], supplier=sup["MedSupply Inc."],
                unit="softgel", reorder_point=30, unit_cost=0.08),
        Product(name="Cetirizine 10mg Tablets", ndc="00573-0149-10", generic_name="Cetirizine HCl",
                category=cat["OTC"], supplier=sup["Generic Pharma Ltd."],
                unit="tablet", reorder_point=50, unit_cost=0.12),
        Product(name="Omeprazole 20mg Capsules", ndc="00378-3280-01", generic_name="Omeprazole",
                category=cat["OTC"], supplier=sup["PharmaCo Distributors"],
                unit="capsule", reorder_point=40, unit_cost=0.20),
    ]
    db.session.add_all(products)
    db.session.flush()

    today = datetime.now(timezone.utc).date()
    inventory_items = [
        InventoryItem(product=products[0], lot_number="LOT-2024-001", quantity=200,
                      expiry_date=today + timedelta(days=365), location="A-1-1"),
        InventoryItem(product=products[1], lot_number="LOT-2024-002", quantity=8,  # low stock
                      expiry_date=today + timedelta(days=180), location="B-2-1"),
        InventoryItem(product=products[2], lot_number="LOT-2024-003", quantity=150,
                      expiry_date=today + timedelta(days=25), location="C-1-2"),  # expiring soon
        InventoryItem(product=products[3], lot_number="LOT-2024-004", quantity=75,
                      expiry_date=today + timedelta(days=400), location="C-2-1"),
        InventoryItem(product=products[4], lot_number="LOT-2024-005", quantity=5,  # low stock
                      expiry_date=today + timedelta(days=500), location="D-1-1"),
        InventoryItem(product=products[5], lot_number="LOT-2024-006", quantity=500,
                      expiry_date=today + timedelta(days=730), location="E-1-1"),
        InventoryItem(product=products[6], lot_number="LOT-2024-007", quantity=350,
                      expiry_date=today + timedelta(days=600), location="E-2-1"),
        InventoryItem(product=products[7], lot_number="LOT-2024-008", quantity=90,
                      expiry_date=today + timedelta(days=365), location="F-1-1"),
        InventoryItem(product=products[8], lot_number="LOT-2024-009", quantity=40,
                      expiry_date=today + timedelta(days=15), location="G-1-1"),  # expiring very soon
        InventoryItem(product=products[9], lot_number="LOT-2024-010", quantity=120,
                      expiry_date=today + timedelta(days=300), location="G-2-1"),
    ]
    db.session.add_all(inventory_items)

    transactions = [
        Transaction(product=products[0], transaction_type="received", quantity=200,
                    lot_number="LOT-2024-001", reference="PO-001", performed_by="Admin"),
        Transaction(product=products[1], transaction_type="received", quantity=100,
                    lot_number="LOT-2024-002", reference="PO-002", performed_by="Admin"),
        Transaction(product=products[1], transaction_type="dispensed", quantity=92,
                    lot_number="LOT-2024-002", reference="RX-1045", performed_by="Pharmacist"),
        Transaction(product=products[2], transaction_type="received", quantity=150,
                    lot_number="LOT-2024-003", reference="PO-003", performed_by="Admin"),
        Transaction(product=products[4], transaction_type="received", quantity=20,
                    lot_number="LOT-2024-005", reference="PO-004", performed_by="Admin"),
        Transaction(product=products[4], transaction_type="dispensed", quantity=15,
                    lot_number="LOT-2024-005", reference="RX-1046", performed_by="Pharmacist"),
    ]
    db.session.add_all(transactions)
    db.session.commit()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    today = datetime.now(timezone.utc).date()
    expiry_warning_days = 30

    total_products = Product.query.filter_by(is_active=True).count()
    total_categories = Category.query.count()

    active_products = Product.query.filter_by(is_active=True).all()
    low_stock_items = [p for p in active_products if p.is_low_stock]

    expiring_soon = (
        InventoryItem.query
        .filter(
            InventoryItem.expiry_date != None,
            InventoryItem.expiry_date <= today + timedelta(days=expiry_warning_days),
            InventoryItem.expiry_date >= today,
            InventoryItem.quantity > 0,
        )
        .order_by(InventoryItem.expiry_date)
        .all()
    )

    expired_items = (
        InventoryItem.query
        .filter(
            InventoryItem.expiry_date != None,
            InventoryItem.expiry_date < today,
            InventoryItem.quantity > 0,
        )
        .all()
    )

    recent_transactions = (
        Transaction.query
        .order_by(Transaction.created_at.desc())
        .limit(10)
        .all()
    )

    total_inventory_value = sum(
        item.quantity * (item.product.unit_cost or 0)
        for item in InventoryItem.query.all()
    )

    return render_template(
        "dashboard.html",
        total_products=total_products,
        total_categories=total_categories,
        low_stock_count=len(low_stock_items),
        low_stock_items=low_stock_items,
        expiring_soon=expiring_soon,
        expired_items=expired_items,
        recent_transactions=recent_transactions,
        total_inventory_value=total_inventory_value,
        now=datetime.now(timezone.utc),
    )


# ── Products ──────────────────────────────────────────────────────────────────

@app.route("/products")
def products():
    search = request.args.get("search", "")
    category_id = request.args.get("category_id", "")
    supplier_id = request.args.get("supplier_id", "")

    query = Product.query.filter_by(is_active=True)
    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f"%{search}%"),
                Product.generic_name.ilike(f"%{search}%"),
                Product.ndc.ilike(f"%{search}%"),
            )
        )
    if category_id:
        query = query.filter_by(category_id=category_id)
    if supplier_id:
        query = query.filter_by(supplier_id=supplier_id)

    products_list = query.order_by(Product.name).all()
    categories = Category.query.order_by(Category.name).all()
    suppliers = Supplier.query.order_by(Supplier.name).all()

    return render_template(
        "products.html",
        products=products_list,
        categories=categories,
        suppliers=suppliers,
        search=search,
        selected_category=category_id,
        selected_supplier=supplier_id,
    )


@app.route("/products/new", methods=["GET", "POST"])
def product_new():
    if request.method == "POST":
        product = Product(
            name=request.form["name"],
            ndc=request.form.get("ndc") or None,
            generic_name=request.form.get("generic_name"),
            category_id=request.form.get("category_id") or None,
            supplier_id=request.form.get("supplier_id") or None,
            unit=request.form.get("unit", "unit"),
            reorder_point=int(request.form.get("reorder_point", 10)),
            unit_cost=float(request.form.get("unit_cost", 0)),
            description=request.form.get("description"),
        )
        db.session.add(product)
        db.session.commit()
        flash(f"Product '{product.name}' added successfully.", "success")
        return redirect(url_for("products"))

    categories = Category.query.order_by(Category.name).all()
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template("product_form.html", product=None, categories=categories, suppliers=suppliers)


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == "POST":
        product.name = request.form["name"]
        product.ndc = request.form.get("ndc") or None
        product.generic_name = request.form.get("generic_name")
        product.category_id = request.form.get("category_id") or None
        product.supplier_id = request.form.get("supplier_id") or None
        product.unit = request.form.get("unit", "unit")
        product.reorder_point = int(request.form.get("reorder_point", 10))
        product.unit_cost = float(request.form.get("unit_cost", 0))
        product.description = request.form.get("description")
        db.session.commit()
        flash(f"Product '{product.name}' updated.", "success")
        return redirect(url_for("products"))

    categories = Category.query.order_by(Category.name).all()
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template("product_form.html", product=product, categories=categories, suppliers=suppliers)


@app.route("/products/<int:product_id>/delete", methods=["POST"])
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = False
    db.session.commit()
    flash(f"Product '{product.name}' removed.", "info")
    return redirect(url_for("products"))


# ── Inventory ─────────────────────────────────────────────────────────────────

@app.route("/inventory")
def inventory():
    search = request.args.get("search", "")
    category_id = request.args.get("category_id", "")
    show_expired = request.args.get("show_expired", "")
    show_low = request.args.get("show_low", "")

    today = datetime.now(timezone.utc).date()
    query = InventoryItem.query.join(Product).filter(Product.is_active == True)

    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f"%{search}%"),
                InventoryItem.lot_number.ilike(f"%{search}%"),
                InventoryItem.location.ilike(f"%{search}%"),
            )
        )
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if show_expired:
        query = query.filter(InventoryItem.expiry_date < today)
    if show_low:
        # handled in Python after query
        pass

    items = query.order_by(Product.name, InventoryItem.expiry_date).all()

    if show_low:
        low_product_ids = {p.id for p in Product.query.all() if p.is_low_stock}
        items = [i for i in items if i.product_id in low_product_ids]

    categories = Category.query.order_by(Category.name).all()

    return render_template(
        "inventory.html",
        items=items,
        categories=categories,
        search=search,
        selected_category=category_id,
        show_expired=show_expired,
        show_low=show_low,
        today=today,
    )


@app.route("/inventory/adjust", methods=["GET", "POST"])
def inventory_adjust():
    if request.method == "POST":
        product_id = int(request.form["product_id"])
        transaction_type = request.form["transaction_type"]
        quantity = int(request.form["quantity"])
        lot_number = request.form.get("lot_number")
        expiry_date_str = request.form.get("expiry_date")
        location = request.form.get("location")
        reference = request.form.get("reference")
        notes = request.form.get("notes")
        performed_by = request.form.get("performed_by", "Staff")

        expiry_date = None
        if expiry_date_str:
            from dateutil.parser import parse as parse_date
            expiry_date = parse_date(expiry_date_str).date()

        product = Product.query.get_or_404(product_id)

        if transaction_type == "received":
            item = InventoryItem(
                product_id=product_id,
                lot_number=lot_number,
                quantity=quantity,
                expiry_date=expiry_date,
                location=location,
            )
            db.session.add(item)
        elif transaction_type in ("dispensed", "expired", "adjusted"):
            # Deduct from inventory (FIFO by expiry)
            remaining = quantity
            items = (
                InventoryItem.query
                .filter_by(product_id=product_id)
                .filter(InventoryItem.quantity > 0)
                .order_by(InventoryItem.expiry_date.asc().nullslast())
                .all()
            )
            for inv_item in items:
                if remaining <= 0:
                    break
                deduct = min(inv_item.quantity, remaining)
                inv_item.quantity -= deduct
                remaining -= deduct
            if remaining > 0:
                flash(f"Warning: only {quantity - remaining} units were available.", "warning")

        txn = Transaction(
            product_id=product_id,
            transaction_type=transaction_type,
            quantity=quantity,
            lot_number=lot_number,
            reference=reference,
            notes=notes,
            performed_by=performed_by,
        )
        db.session.add(txn)
        db.session.commit()
        flash("Inventory updated successfully.", "success")
        return redirect(url_for("inventory"))

    products_list = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return render_template("inventory_adjust.html", products=products_list)


# ── Import ─────────────────────────────────────────────────────────────────────

EXPECTED_COLUMNS = {
    "dispensed": ["ndc", "quantity"],
    "received": ["ndc", "quantity", "lot_number", "expiry_date"],
    "adjustment": ["ndc", "quantity", "adjustment_type"],
}

COLUMN_ALIASES = {
    "drug_code": "ndc",
    "national_drug_code": "ndc",
    "drug ndc": "ndc",
    "qty": "quantity",
    "qty_dispensed": "quantity",
    "qty_received": "quantity",
    "lot": "lot_number",
    "lot #": "lot_number",
    "lot#": "lot_number",
    "exp_date": "expiry_date",
    "expiration": "expiry_date",
    "expiration_date": "expiry_date",
    "exp": "expiry_date",
    "type": "adjustment_type",
}


def normalize_columns(df):
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df.rename(columns=COLUMN_ALIASES, inplace=True)
    return df


@app.route("/import", methods=["GET", "POST"])
def import_data():
    logs = ImportLog.query.order_by(ImportLog.imported_at.desc()).limit(20).all()

    if request.method == "POST":
        import_type = request.form.get("import_type")
        file = request.files.get("file")

        if not file or file.filename == "":
            flash("No file selected.", "danger")
            return redirect(url_for("import_data"))

        if not allowed_file(file.filename):
            flash("Invalid file type. Please upload a CSV or Excel file.", "danger")
            return redirect(url_for("import_data"))

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        log = ImportLog(filename=filename, import_type=import_type)
        db.session.add(log)
        db.session.flush()

        errors = []
        imported = 0

        try:
            if filename.endswith(".csv"):
                df = pd.read_csv(filepath)
            else:
                df = pd.read_excel(filepath)

            df = normalize_columns(df)
            log.records_total = len(df)

            required = EXPECTED_COLUMNS.get(import_type, ["ndc", "quantity"])
            missing_cols = [c for c in required if c not in df.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {', '.join(missing_cols)}")

            today = datetime.now(timezone.utc).date()

            for idx, row in df.iterrows():
                try:
                    ndc = str(row.get("ndc", "")).strip()
                    quantity = int(row.get("quantity", 0))
                    if not ndc or quantity <= 0:
                        errors.append(f"Row {idx+2}: invalid NDC or quantity")
                        continue

                    product = Product.query.filter_by(ndc=ndc).first()
                    if not product:
                        # Try fuzzy match on name if ndc column contains name
                        product = Product.query.filter(Product.name.ilike(f"%{ndc}%")).first()
                    if not product:
                        errors.append(f"Row {idx+2}: product not found for NDC/name '{ndc}'")
                        continue

                    txn_type = import_type if import_type != "adjustment" else str(row.get("adjustment_type", "adjusted")).lower()

                    lot_number = str(row.get("lot_number", "")).strip() or None
                    expiry_date = None
                    if "expiry_date" in row and pd.notna(row["expiry_date"]):
                        from dateutil.parser import parse as parse_date
                        try:
                            expiry_date = parse_date(str(row["expiry_date"])).date()
                        except Exception:
                            pass

                    if txn_type == "received":
                        item = InventoryItem(
                            product_id=product.id,
                            lot_number=lot_number,
                            quantity=quantity,
                            expiry_date=expiry_date,
                            received_date=today,
                        )
                        db.session.add(item)
                    else:
                        remaining = quantity
                        inv_items = (
                            InventoryItem.query
                            .filter_by(product_id=product.id)
                            .filter(InventoryItem.quantity > 0)
                            .order_by(InventoryItem.expiry_date.asc().nullslast())
                            .all()
                        )
                        for inv_item in inv_items:
                            if remaining <= 0:
                                break
                            deduct = min(inv_item.quantity, remaining)
                            inv_item.quantity -= deduct
                            remaining -= deduct

                    txn = Transaction(
                        product_id=product.id,
                        transaction_type=txn_type,
                        quantity=quantity,
                        lot_number=lot_number,
                        reference=f"Import #{log.id}",
                        notes=f"Imported from {filename}",
                    )
                    db.session.add(txn)
                    imported += 1

                except Exception as row_err:
                    errors.append(f"Row {idx+2}: {str(row_err)}")

        except Exception as e:
            log.status = "failed"
            log.error_details = str(e)
            db.session.commit()
            flash(f"Import failed: {e}", "danger")
            return redirect(url_for("import_data"))

        log.records_imported = imported
        log.records_failed = len(errors)
        log.status = "success" if not errors else ("partial" if imported > 0 else "failed")
        log.error_details = "\n".join(errors) if errors else None
        db.session.commit()

        flash(
            f"Import complete: {imported} records imported, {len(errors)} failed.",
            "success" if not errors else "warning",
        )
        return redirect(url_for("import_data"))

    return render_template("import.html", logs=logs)


@app.route("/import/template/<import_type>")
def download_template(import_type):
    templates = {
        "dispensed": pd.DataFrame(columns=["ndc", "quantity", "lot_number", "reference"]),
        "received": pd.DataFrame(columns=["ndc", "quantity", "lot_number", "expiry_date", "location"]),
        "adjustment": pd.DataFrame(columns=["ndc", "quantity", "adjustment_type", "notes"]),
    }
    df = templates.get(import_type, templates["dispensed"])
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"template_{import_type}.csv",
    )


# ── Transactions ───────────────────────────────────────────────────────────────

@app.route("/transactions")
def transactions():
    search = request.args.get("search", "")
    txn_type = request.args.get("type", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = Transaction.query.join(Product)
    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f"%{search}%"),
                Transaction.reference.ilike(f"%{search}%"),
                Transaction.lot_number.ilike(f"%{search}%"),
            )
        )
    if txn_type:
        query = query.filter(Transaction.transaction_type == txn_type)
    if date_from:
        query = query.filter(Transaction.created_at >= date_from)
    if date_to:
        query = query.filter(Transaction.created_at <= date_to + " 23:59:59")

    txns = query.order_by(Transaction.created_at.desc()).limit(200).all()
    return render_template("transactions.html", transactions=txns,
                           search=search, selected_type=txn_type,
                           date_from=date_from, date_to=date_to)


# ── Reports ────────────────────────────────────────────────────────────────────

@app.route("/reports")
def reports():
    today = datetime.now(timezone.utc).date()
    expiry_warning_days = 30

    active_products = Product.query.filter_by(is_active=True).all()
    low_stock_items = [p for p in active_products if p.is_low_stock]

    expiring_soon = (
        InventoryItem.query
        .filter(
            InventoryItem.expiry_date != None,
            InventoryItem.expiry_date <= today + timedelta(days=expiry_warning_days),
            InventoryItem.expiry_date >= today,
            InventoryItem.quantity > 0,
        )
        .order_by(InventoryItem.expiry_date)
        .all()
    )

    expired_items = (
        InventoryItem.query
        .filter(
            InventoryItem.expiry_date != None,
            InventoryItem.expiry_date < today,
            InventoryItem.quantity > 0,
        )
        .all()
    )

    inventory_value_by_category = {}
    for product in active_products:
        cat_name = product.category.name if product.category else "Uncategorized"
        value = product.total_stock * (product.unit_cost or 0)
        inventory_value_by_category[cat_name] = inventory_value_by_category.get(cat_name, 0) + value

    return render_template(
        "reports.html",
        low_stock_items=low_stock_items,
        expiring_soon=expiring_soon,
        expired_items=expired_items,
        inventory_value_by_category=inventory_value_by_category,
        today=today,
    )


@app.route("/reports/export/<report_type>")
def export_report(report_type):
    today = datetime.now(timezone.utc).date()

    if report_type == "low_stock":
        active_products = Product.query.filter_by(is_active=True).all()
        data = [
            {
                "Product": p.name,
                "NDC": p.ndc,
                "Category": p.category.name if p.category else "",
                "Current Stock": p.total_stock,
                "Reorder Point": p.reorder_point,
                "Unit": p.unit,
                "Supplier": p.supplier.name if p.supplier else "",
            }
            for p in active_products if p.is_low_stock
        ]
    elif report_type == "expiring":
        items = (
            InventoryItem.query
            .filter(
                InventoryItem.expiry_date != None,
                InventoryItem.expiry_date <= today + timedelta(days=90),
                InventoryItem.quantity > 0,
            )
            .order_by(InventoryItem.expiry_date)
            .all()
        )
        data = [
            {
                "Product": i.product.name if i.product else "",
                "Lot Number": i.lot_number,
                "Quantity": i.quantity,
                "Expiry Date": i.expiry_date.isoformat() if i.expiry_date else "",
                "Days Until Expiry": i.days_until_expiry,
                "Location": i.location,
            }
            for i in items
        ]
    elif report_type == "inventory":
        items = InventoryItem.query.join(Product).filter(Product.is_active == True).all()
        data = [
            {
                "Product": i.product.name if i.product else "",
                "NDC": i.product.ndc if i.product else "",
                "Category": i.product.category.name if i.product and i.product.category else "",
                "Lot Number": i.lot_number,
                "Quantity": i.quantity,
                "Unit": i.product.unit if i.product else "",
                "Expiry Date": i.expiry_date.isoformat() if i.expiry_date else "",
                "Location": i.location,
            }
            for i in items
        ]
    else:
        flash("Unknown report type.", "danger")
        return redirect(url_for("reports"))

    df = pd.DataFrame(data)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"report_{report_type}_{today.isoformat()}.csv",
    )


# ── Suppliers & Categories (simple CRUD via AJAX) ─────────────────────────────

@app.route("/api/categories", methods=["GET", "POST"])
def api_categories():
    if request.method == "POST":
        data = request.get_json()
        cat = Category(name=data["name"])
        db.session.add(cat)
        db.session.commit()
        return jsonify(cat.to_dict()), 201
    return jsonify([c.to_dict() for c in Category.query.order_by(Category.name).all()])


@app.route("/api/suppliers", methods=["GET", "POST"])
def api_suppliers():
    if request.method == "POST":
        data = request.get_json()
        sup = Supplier(
            name=data["name"],
            contact=data.get("contact"),
            phone=data.get("phone"),
            email=data.get("email"),
        )
        db.session.add(sup)
        db.session.commit()
        return jsonify(sup.to_dict()), 201
    return jsonify([s.to_dict() for s in Supplier.query.order_by(Supplier.name).all()])


@app.route("/suppliers")
def suppliers():
    all_suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template("suppliers.html", suppliers=all_suppliers)


@app.route("/suppliers/new", methods=["GET", "POST"])
def supplier_new():
    if request.method == "POST":
        sup = Supplier(
            name=request.form["name"],
            contact=request.form.get("contact"),
            phone=request.form.get("phone"),
            email=request.form.get("email"),
        )
        db.session.add(sup)
        db.session.commit()
        flash(f"Supplier '{sup.name}' added.", "success")
        return redirect(url_for("suppliers"))
    return render_template("supplier_form.html", supplier=None)


@app.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
def supplier_edit(supplier_id):
    sup = Supplier.query.get_or_404(supplier_id)
    if request.method == "POST":
        sup.name = request.form["name"]
        sup.contact = request.form.get("contact")
        sup.phone = request.form.get("phone")
        sup.email = request.form.get("email")
        db.session.commit()
        flash(f"Supplier '{sup.name}' updated.", "success")
        return redirect(url_for("suppliers"))
    return render_template("supplier_form.html", supplier=sup)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_demo_data()
    app.run(debug=True, host="0.0.0.0", port=5000)
