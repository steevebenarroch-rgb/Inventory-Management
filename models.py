from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    products = db.relationship("Product", backref="category", lazy=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class Supplier(db.Model):
    __tablename__ = "suppliers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    contact = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(150))
    products = db.relationship("Product", backref="supplier", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "contact": self.contact,
            "phone": self.phone,
            "email": self.email,
        }


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    ndc = db.Column(db.String(50), unique=True)  # National Drug Code
    generic_name = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    unit = db.Column(db.String(50), default="unit")  # tablet, vial, bottle, etc.
    reorder_point = db.Column(db.Integer, default=10)
    unit_cost = db.Column(db.Float, default=0.0)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    inventory_items = db.relationship("InventoryItem", backref="product", lazy=True)
    transactions = db.relationship("Transaction", backref="product", lazy=True)

    @property
    def total_stock(self):
        return sum(
            item.quantity
            for item in self.inventory_items
            if item.quantity is not None
        )

    @property
    def is_low_stock(self):
        return self.total_stock <= self.reorder_point

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "ndc": self.ndc,
            "generic_name": self.generic_name,
            "category": self.category.name if self.category else None,
            "supplier": self.supplier.name if self.supplier else None,
            "unit": self.unit,
            "reorder_point": self.reorder_point,
            "unit_cost": self.unit_cost,
            "total_stock": self.total_stock,
            "is_low_stock": self.is_low_stock,
        }


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    lot_number = db.Column(db.String(100))
    quantity = db.Column(db.Integer, default=0, nullable=False)
    expiry_date = db.Column(db.Date)
    location = db.Column(db.String(100))  # shelf/bin location
    received_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    notes = db.Column(db.Text)

    @property
    def is_expired(self):
        if self.expiry_date:
            return self.expiry_date < datetime.now(timezone.utc).date()
        return False

    @property
    def days_until_expiry(self):
        if self.expiry_date:
            delta = self.expiry_date - datetime.now(timezone.utc).date()
            return delta.days
        return None

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else None,
            "lot_number": self.lot_number,
            "quantity": self.quantity,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "location": self.location,
            "received_date": self.received_date.isoformat() if self.received_date else None,
            "days_until_expiry": self.days_until_expiry,
            "is_expired": self.is_expired,
        }


class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # received, dispensed, adjusted, expired, returned
    quantity = db.Column(db.Integer, nullable=False)
    lot_number = db.Column(db.String(100))
    reference = db.Column(db.String(200))  # PO number, prescription #, etc.
    notes = db.Column(db.Text)
    performed_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else None,
            "transaction_type": self.transaction_type,
            "quantity": self.quantity,
            "lot_number": self.lot_number,
            "reference": self.reference,
            "notes": self.notes,
            "performed_by": self.performed_by,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
        }


class ImportLog(db.Model):
    __tablename__ = "import_logs"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    import_type = db.Column(db.String(50))  # dispensed, received, adjustment
    records_total = db.Column(db.Integer, default=0)
    records_imported = db.Column(db.Integer, default=0)
    records_failed = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="pending")  # pending, success, partial, failed
    error_details = db.Column(db.Text)
    imported_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "import_type": self.import_type,
            "records_total": self.records_total,
            "records_imported": self.records_imported,
            "records_failed": self.records_failed,
            "status": self.status,
            "error_details": self.error_details,
            "imported_at": self.imported_at.strftime("%Y-%m-%d %H:%M") if self.imported_at else None,
        }
