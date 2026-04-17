from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    ndc = db.Column(db.String(50), unique=True, index=True)
    generic_name = db.Column(db.String(200))
    category = db.Column(db.String(100))
    unit = db.Column(db.String(30), default="unit")
    is_active = db.Column(db.Boolean, default=True)

    snapshots = db.relationship("StockSnapshot", backref="product", lazy="dynamic")
    dispenses = db.relationship("DispensingRecord", backref="product", lazy="dynamic")
    returns = db.relationship("ExpiredReturn", backref="product", lazy="dynamic")

    def __repr__(self):
        return f"<Product {self.name}>"


class ImportBatch(db.Model):
    __tablename__ = "import_batches"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    import_type = db.Column(db.String(30), nullable=False)  # stock_snapshot | dispensing_history
    imported_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    records_total = db.Column(db.Integer, default=0)
    records_ok = db.Column(db.Integer, default=0)
    records_failed = db.Column(db.Integer, default=0)
    period_start = db.Column(db.Date)   # for dispensing imports
    period_end = db.Column(db.Date)     # for dispensing imports
    snapshot_date = db.Column(db.Date)  # for stock snapshot imports
    error_details = db.Column(db.Text)
    status = db.Column(db.String(20), default="pending")  # success | partial | failed


class StockSnapshot(db.Model):
    """One row per product per import — the on-hand quantity from the EMS."""
    __tablename__ = "stock_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    snapshot_date = db.Column(db.Date, nullable=False, index=True)
    import_batch_id = db.Column(db.Integer, db.ForeignKey("import_batches.id"))


class DispensingRecord(db.Model):
    """Dispensing data from EMS — one row per product per day (or per import period)."""
    __tablename__ = "dispensing_records"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    quantity_dispensed = db.Column(db.Integer, nullable=False)
    dispense_date = db.Column(db.Date, nullable=False, index=True)
    import_batch_id = db.Column(db.Integer, db.ForeignKey("import_batches.id"))


class ExpiredReturn(db.Model):
    """
    Medications removed from usable stock (expired & destroyed, or returned for credit)
    that the EMS hasn't yet credited back.  These inflate the EMS on-hand number.
    """
    __tablename__ = "expired_returns"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    event_type = db.Column(db.String(30), nullable=False)  # expired_destroyed | returned_credit
    lot_number = db.Column(db.String(100))
    notes = db.Column(db.Text)
    # Once the EMS has reflected this deduction, mark credited=True so we stop subtracting it
    credited_in_ems = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class AppSetting(db.Model):
    __tablename__ = "app_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(300))
