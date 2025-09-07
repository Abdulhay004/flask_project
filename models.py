from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from datetime import datetime


db = SQLAlchemy()

class Branch(db.Model):
    __tablename__ = "branches"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    address = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Filial -> mahsulotlar (relationship)
    products = db.relationship("Product", backref="branch", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Branch {self.name}>"


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)

    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)

    # Uch tilda nom va tavsif
    name_uz = db.Column(db.String(200))
    name_ru = db.Column(db.String(200))
    name_en = db.Column(db.String(200))

    description_uz = db.Column(db.Text, nullable=True)
    description_ru = db.Column(db.Text, nullable=True)
    description_en = db.Column(db.Text, nullable=True)

    # Kimlar uchun
    for_whom_uz = db.Column(db.Text, nullable=True)
    for_whom_ru = db.Column(db.Text, nullable=True)
    for_whom_en = db.Column(db.Text, nullable=True)

    # Tarkibiy qismi
    components_uz = db.Column(db.Text, nullable=True)
    components_ru = db.Column(db.Text, nullable=True)
    components_en = db.Column(db.Text, nullable=True)

    # Ishlab chiqaruvchi
    company_uz = db.Column(db.String(200), nullable=True)
    company_ru = db.Column(db.String(200), nullable=True)
    company_en = db.Column(db.String(200), nullable=True)

    # Foydalanish tartibi
    usage_uz = db.Column(db.Text, nullable=True)
    usage_ru = db.Column(db.Text, nullable=True)
    usage_en = db.Column(db.Text, nullable=True)

    # Foydalanish mumkin bo'lmagan holatlar
    not_usage_uz = db.Column(db.Text, nullable=True)
    not_usage_ru = db.Column(db.Text, nullable=True)
    not_usage_en = db.Column(db.Text, nullable=True)

    # Saqlash shartlari
    storage_uz = db.Column(db.Text, nullable=True)
    storage_ru = db.Column(db.Text, nullable=True)
    storage_en = db.Column(db.Text, nullable=True)

    # Yaroqlilik muddati
    expiry_uz = db.Column(db.String(100), nullable=True)
    expiry_ru = db.Column(db.String(100), nullable=True)
    expiry_en = db.Column(db.String(100), nullable=True)

    # Sertifikat va standartlar
    certificate_uz = db.Column(db.Text, nullable=True)
    certificate_ru = db.Column(db.Text, nullable=True)
    certificate_en = db.Column(db.Text, nullable=True)

    # Aksiya va bonuslar
    promotion_uz = db.Column(db.Text, nullable=True)
    promotion_ru = db.Column(db.Text, nullable=True)
    promotion_en = db.Column(db.Text, nullable=True)

    # Xulosa
    conclusion_uz = db.Column(db.Text, nullable=True)
    conclusion_ru = db.Column(db.Text, nullable=True)
    conclusion_en = db.Column(db.Text, nullable=True)

    # Country (3 ta til uchun alohida maydonlar)
    country_uz = db.Column(db.String(120), nullable=True)
    country_ru = db.Column(db.String(120), nullable=True)
    country_en = db.Column(db.String(120), nullable=True)

    # Location (3 ta til uchun alohida maydonlar)
    location_uz = db.Column(db.String(120), nullable=True)
    location_ru = db.Column(db.String(120), nullable=True)
    location_en = db.Column(db.String(120), nullable=True)

    image = db.Column(db.String(255), nullable=True) # filename
    qr_code = db.Column(db.String(255)) # filename (e.g. "12.png")

    last_scanned_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    views = db.Column(db.Integer, default=0)

class LanguageView(db.Model):
    __tablename__ = "language_views"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    lang = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship("Product", backref="lang_views")