import os
import time
import uuid
import qrcode
import boto3
import io
from PIL import Image
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, abort, flash, session, make_response, jsonify

from models import db, Product, Branch, LanguageView
from auth import auth_bp, admin_required
from sqlalchemy import func, extract

from datetime import datetime, timedelta
from collections import Counter

from translations import translations

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
# QR_DIR = os.path.join(BASE_DIR, 'static', 'qrcodes')
#
# os.makedirs(UPLOAD_DIR, exist_ok=True)
# os.makedirs(QR_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'secret')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///products.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
# app.config['QR_FOLDER'] = QR_DIR

# init db + blueprints
db.init_app(app)
app.register_blueprint(auth_bp)

from flask_migrate import Migrate
migrate = Migrate(app, db)

R2_BUCKET = os.getenv("R2_BUCKET")
R2_ENDPOINT = os.getenv("R2_ENDPOINT")  # masalan: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")

s3_client = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY
)

def upload_file_to_r2(file_obj, filename, folder="uploads"):
    """ Faylni Cloudflare R2 ga yuklash va public URL qaytarish """
    filename = secure_filename(filename)
    key = f"{folder}/{filename}"
    s3_client.upload_fileobj(
        file_obj,
        R2_BUCKET,
        key,
        ExtraArgs={"ACL": "public-read"}  # fayl public bo‘lsin
    )
    return f"{R2_ENDPOINT}/{R2_BUCKET}/{key}"


# -----------------------------
# Helpers
# -----------------------------
ALLOWED_EXT = {'.png', '.jpg', '.jpeg', '.webp'}

def _unique_filename(filename: str) -> str:
    name = secure_filename(filename)
    root, ext = os.path.splitext(name)
    ts = int(time.time() * 1000)
    return f"{root}_{ts}{ext.lower()}"


def _check_image_ext(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXT

def _generate_qr_for_product(branch_id: int, product_id: int) -> str:
    product_url = url_for('product_entry', branch_id=branch_id, product_id=product_id, _external=True)
    img = qrcode.make(product_url)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    qr_filename = f"{product_id}.png"
    return upload_file_to_r2(buffer, qr_filename, "qrcodes")

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or not _check_image_ext(file.filename):
        return "Noto‘g‘ri fayl", 400

    filename = _unique_filename(file.filename)
    url = upload_file_to_r2(file, filename, "products")

    # DB’da saqlash: product.image_url = url
    return {"url": url}


@app.route('/admin/branch/<int:branch_id>/stats')
@admin_required
def branch_stats(branch_id):
    branch = Branch.query.get_or_404(branch_id)
    products = Product.query.filter_by(branch_id=branch.id).all()
    product_ids = [p.id for p in products]

    # Umumiy skanlar
    total_scans = sum(p.views for p in products)

    # Foydalanuvchilar
    new_users = sum(1 for p in products if p.views == 1)
    repeat_users = sum(1 for p in products if p.views > 1)

    # ✅ Tillar bo‘yicha statistikalar (aniq)
    lang_stats = dict(
        db.session.query(LanguageView.lang, func.count(LanguageView.id))
        .filter(LanguageView.product_id.in_(product_ids))
        .group_by(LanguageView.lang)
        .all()
    )

    for l in ["uz", "ru", "en"]:
        lang_stats.setdefault(l, 0)

    # ✅ Oxirgi 7 kunlik skanlar
    today = datetime.utcnow().date()
    last_week = today - timedelta(days=7)
    daily = []
    for i in range(7):
        day = last_week + timedelta(days=i+1)
        count = LanguageView.query.filter(
            LanguageView.product_id.in_(product_ids),
            func.date(LanguageView.created_at) == day
        ).count()
        daily.append({"date": day.strftime("%Y-%m-%d"), "count": count})

    # ✅ Oxirgi 3 oylik skanlar.
    last_3_months = today - timedelta(days=90)
    monthly = (
        db.session.query(
            func.to_char(LanguageView.created_at, 'YYYY-MM'),  # ✅ PostgreSQL uchun
            func.count(LanguageView.id)
        )
        .filter(
            LanguageView.product_id.in_(product_ids),
            LanguageView.created_at >= last_3_months
        )
        .group_by(func.to_char(LanguageView.created_at, 'YYYY-MM'))
        .all()
    )
    monthly = [{"date": k, "count": v} for k, v in monthly]

    # Top 5 QR
    qr_counts = {p.id: p.views for p in products if p.views > 0}
    top_products = sorted(qr_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    top_qr = []
    for pid, views in top_products:
        product = next(p for p in products if p.id == pid)
        # Default nom (uz > ru > en)
        name = product.name_uz or product.name_ru or product.name_en or f"Product {pid}"
        top_qr.append((name, views))

    stats_data = {
        "total_scans": total_scans,
        "new_users": new_users,
        "repeat_users": repeat_users,
        "lang_stats": lang_stats,
        "daily": daily,
        "monthly": monthly,
        "top_qr": top_qr
    }

    return render_template("stats.html", stats_data=stats_data, total_scans=total_scans, branch_id=branch_id)

# -----------------------------
# Public routes (no auth)
# -----------------------------
@app.route('/')
def index():
    return redirect(url_for('auth.login'))

# --- Branch (filial) routes ---
@app.route("/branches")
def branch_list():
    branches = Branch.query.all()
    return render_template("branches.html", branches=branches)

@app.route("/branches/add", methods=["GET", "POST"])
def branch_add():
    if request.method == "POST":
        name = request.form.get("name")
        address = request.form.get("address")
        branch = Branch(name=name, address=address)
        db.session.add(branch)
        db.session.commit()
        flash("Filial qo‘shildi!", "success")
        return redirect(url_for("branch_list"))
    return render_template("branch_form.html")

@app.route("/branches/<int:branch_id>/dashboard")
def branch_dashboard(branch_id):
    branch = Branch.query.get_or_404(branch_id)
    products = Product.query.filter_by(branch_id=branch.id).all()
    return render_template("dashboard.html", branch=branch, products=products)

@app.route("/branches/delete/<int:branch_id>", methods=["POST"])
def branch_delete(branch_id):
    branch = Branch.query.get(branch_id)
    if not branch:
        flash("Filial topilmadi!", "danger")
        return redirect(url_for("branch_list"))

    try:
        db.session.delete(branch)
        db.session.commit()
        flash("Filial muvaffaqiyatli o‘chirildi ✅", "success")
    except Exception as e:
        db.session.rollback()
        flash("Xatolik yuz berdi: " + str(e), "danger")

    return redirect(url_for("branch_list"))




# Mahsulotni yuklash sahifasi (QR orqali kirganda)
@app.route('/branch/<int:branch_id>/product/<int:product_id>')
def product_entry(branch_id, product_id):
    product = Product.query.filter_by(id=product_id, branch_id=branch_id).first_or_404()
    return render_template("loading.html", product=product, branch_id=branch_id)


# Til tanlash sahifasi
@app.route('/branch/<int:branch_id>/select-language/<int:product_id>')
def select_language(branch_id, product_id):
    product = Product.query.filter_by(id=product_id, branch_id=branch_id).first_or_404()

    product.last_scanned_at = datetime.now()
    db.session.commit()

    return render_template('select_language.html', product=product, branch_id=branch_id)


# Mahsulot tafsilotlari (tanlangan til bilan)
@app.route("/branch/<int:branch_id>/product/<int:product_id>/<lang>")
def product_detail(branch_id, product_id, lang):
    product = Product.query.filter_by(id=product_id, branch_id=branch_id).first_or_404()

    if lang not in ["uz", "ru", "en"]:
        abort(400, "Noto‘g‘ri til tanlandi")

    # Foydalanuvchi identifikatori (cookie orqali)
    user_id = request.cookies.get("user_id")
    if not user_id:
        user_id = str(uuid.uuid4())

    viewed_key = f"viewed_{branch_id}_{product_id}_{user_id}"
    if not session.get(viewed_key):
        # Umumiy ko‘rishlarni oshirish
        product.views = (product.views or 0) + 1
        product.last_scanned_at = datetime.utcnow()

        # ✅ Til bo‘yicha ko‘rishni saqlash
        lang_view = LanguageView(product_id=product.id, lang=lang)
        db.session.add(lang_view)

        db.session.commit()
        session[viewed_key] = True

    resp = make_response(
        render_template("product_detail.html", product=product, lang=lang, branch_id=branch_id)
    )
    resp.set_cookie("user_id", user_id, max_age=60*60*24*365)  # 1 yil
    return resp


# -----------------------------
# Admin routes (CRUD)
# -----------------------------
@app.route('/dashboard')
@admin_required
def dashboard():
    # Hamma filiallar va mahsulotlar
    products = Product.query.order_by(Product.id.desc()).all()
    branches = Branch.query.all()
    return render_template('branches.html', products=products, branches=branches)


@app.route("/branches/<int:branch_id>/products/add", methods=["GET", "POST"])
@admin_required
def add_product(branch_id):
    branch = Branch.query.get_or_404(branch_id)
    if request.method == 'POST':
        file = request.files.get('image')
        if not file or file.filename.strip() == '':
            flash('Rasm yuklash majburiy', 'danger')
            return render_template('product_form.html', mode='add')

        if not _check_image_ext(file.filename):
            flash('Rasm turi noto‘g‘ri (png/jpg/jpeg/webp).', 'danger')
            return render_template('product_form.html', mode='add')

        filename = _unique_filename(file.filename)

        # 📌 Faylni R2 ga yuklash
        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
            aws_access_key_id=os.getenv("R2_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("R2_SECRET_KEY"),
        )

        s3.upload_fileobj(
            Fileobj=io.BytesIO(file.read()),   # faylni xotiradan yuklaydi
            Bucket=os.getenv("R2_BUCKET"),
            Key=f"uploads/{filename}",         # bucket ichida qayerga yoziladi
            ExtraArgs={"ContentType": file.content_type}
        )

        product = Product(
            branch_id=branch.id,

            name_uz=request.form.get('name_uz', ''),
            name_ru=request.form.get('name_ru', ''),
            name_en=request.form.get('name_en', ''),

            description_uz=request.form.get('description_uz', ''),
            description_ru=request.form.get('description_ru', ''),
            description_en=request.form.get('description_en', ''),

            for_whom_uz = request.form.get('for_whom_uz', ''),
            for_whom_ru = request.form.get('for_whom_ru', ''),
            for_whom_en = request.form.get('for_whom_en', ''),

            components_uz=request.form.get('components_uz', ''),
            components_ru=request.form.get('components_ru', ''),
            components_en=request.form.get('components_en', ''),

            company_uz=request.form.get('company_uz', ''),
            company_ru=request.form.get('company_ru', ''),
            company_en=request.form.get('company_en', ''),

            usage_uz=request.form.get('usage_uz', ''),
            usage_ru=request.form.get('usage_ru', ''),
            usage_en=request.form.get('usage_en', ''),

            not_usage_uz=request.form.get('not_usage_uz', ''),
            not_usage_ru=request.form.get('not_usage_ru', ''),
            not_usage_en=request.form.get('not_usage_en', ''),

            storage_uz=request.form.get('storage_uz', ''),
            storage_ru=request.form.get('storage_ru', ''),
            storage_en=request.form.get('storage_en', ''),

            expiry_uz=request.form.get('expiry_uz', ''),
            expiry_ru=request.form.get('expiry_ru', ''),
            expiry_en=request.form.get('expiry_en', ''),

            certificate_uz=request.form.get('certificate_uz', ''),
            certificate_ru=request.form.get('certificate_ru', ''),
            certificate_en=request.form.get('certificate_en', ''),

            promotion_uz=request.form.get('promotion_uz', ''),
            promotion_ru=request.form.get('promotion_ru', ''),
            promotion_en=request.form.get('promotion_en', ''),

            conclusion_uz=request.form.get('conclusion_uz', ''),
            conclusion_ru=request.form.get('conclusion_ru', ''),
            conclusion_en=request.form.get('conclusion_en', ''),

            image=filename
        )
        db.session.add(product)
        db.session.commit()

        flash("Mahsulot muvaffaqiyatli qo‘shildi ✅", "success")

        # QR code yaratish (public til tanlash sahifasiga)
        product.qr_code = _generate_qr_for_product(branch.id, product.id)
        db.session.commit()
        return redirect(url_for("dashboard", branch_id=branch.id, product_id=product.id))
    return render_template("product_form.html", branch=branch)


@app.route("/branches/<int:branch_id>/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_product(branch_id, product_id):
    branch = Branch.query.get_or_404(branch_id)
    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        # Uch tilda nom va tavsif
        product.name_uz = request.form.get('name_uz')
        product.name_ru = request.form.get('name_ru')
        product.name_en = request.form.get('name_en')

        product.for_whom_uz = request.form.get('for_whom_uz', '')
        product.for_whom_ru = request.form.get('for_whom_ru', '')
        product.for_whom_en = request.form.get('for_whom_en', '')

        product.description_uz = request.form.get('description_uz')
        product.description_ru = request.form.get('description_ru')
        product.description_en = request.form.get('description_en')

        # Tarkibiy qismi
        product.components_uz = request.form.get('components_uz')
        product.components_ru = request.form.get('components_ru')
        product.components_en = request.form.get('components_en')

        # Ishlab chiqaruvchi
        product.company_uz = request.form.get('company_uz')
        product.company_ru = request.form.get('company_ru')
        product.company_en = request.form.get('company_en')

        # Foydalanish tartibi
        product.usage_uz = request.form.get('usage_uz')
        product.usage_ru = request.form.get('usage_ru')
        product.usage_en = request.form.get('usage_en')

        # Foydalanish mumkin bo‘lmagan holatlar
        product.not_usage_uz = request.form.get('not_usage_uz')
        product.not_usage_ru = request.form.get('not_usage_ru')
        product.not_usage_en = request.form.get('not_usage_en')

        # Saqlash shartlari
        product.storage_uz = request.form.get('storage_uz')
        product.storage_ru = request.form.get('storage_ru')
        product.storage_en = request.form.get('storage_en')

        # Yaroqlilik muddati
        product.expiry_uz = request.form.get('expiry_uz')
        product.expiry_ru = request.form.get('expiry_ru')
        product.expiry_en = request.form.get('expiry_en')

        # Sertifikat
        product.certificate_uz = request.form.get('certificate_uz')
        product.certificate_ru = request.form.get('certificate_ru')
        product.certificate_en = request.form.get('certificate_en')

        # Aksiya va bonuslar
        product.promotion_uz = request.form.get('promotion_uz')
        product.promotion_ru = request.form.get('promotion_ru')
        product.promotion_en = request.form.get('promotion_en')

        # Xulosa
        product.conclusion_uz = request.form.get('conclusion_uz')
        product.conclusion_ru = request.form.get('conclusion_ru')
        product.conclusion_en = request.form.get('conclusion_en')

    # R2 client yaratamiz
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv("R2_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("R2_SECRET_KEY"),
    )

    # 📌 Rasm
    image_file = request.files.get('image')
    if image_file and image_file.filename != '':
        filename = _unique_filename(image_file.filename)
        s3.upload_fileobj(
            Fileobj=io.BytesIO(image_file.read()),
            Bucket=os.getenv("R2_BUCKET"),
            Key=f"uploads/{filename}",   # bucket ichida papka nomi
            ExtraArgs={"ContentType": image_file.content_type}
        )
        product.image = filename  # faqat nomini DB ga yozamiz

    # 📌 QR Code
    qr_file = request.files.get('qr_code')
    if qr_file and qr_file.filename != '':
        filename = _unique_filename(qr_file.filename)
        s3.upload_fileobj(
            Fileobj=io.BytesIO(qr_file.read()),
            Bucket=os.getenv("R2_BUCKET"),
            Key=f"qrcodes/{filename}",
            ExtraArgs={"ContentType": qr_file.content_type}
        )
        product.qr_code = filename

        db.session.commit()
        flash("Mahsulot muvaffaqiyatli tahrirlandi ✏️", "success")
        return redirect(url_for("dashboard", branch_id=branch.id))

    return render_template('edit_product.html', product=product)


@app.route("/branches/<int:branch_id>/products/<int:product_id>/delete", methods=["GET", "POST"])
@admin_required
def delete_product(branch_id, product_id):
    branch = Branch.query.get_or_404(branch_id)
    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
            aws_access_key_id=os.getenv("R2_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("R2_SECRET_KEY"),
        )

        try:
            # 📌 Eski rasmni R2 dan o‘chirish
            if product.image:
                s3.delete_object(
                    Bucket=os.getenv("R2_BUCKET"),
                    Key=f"uploads/{product.image}"
                )

            # 📌 Eski QR kodni R2 dan o‘chirish
            if product.qr_code:
                s3.delete_object(
                    Bucket=os.getenv("R2_BUCKET"),
                    Key=f"qrcodes/{product.qr_code}"
                )
        except Exception as e:
            print(f"Faylni o‘chirishda xato: {e}")
        db.session.delete(product)
        db.session.commit()
        flash("Mahsulot muvaffaqiyatli o‘chirildi 🗑️", "success")
        return redirect(url_for("dashboard", branch_id=branch.id))
    return render_template('confirm_delete.html', product=product)


import os
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session

auth_bp = Blueprint('auth', __name__)


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('auth.login'))
        return view_func(*args, **kwargs)
    return wrapper


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if (username == os.getenv('ADMIN_USERNAME', 'admin') and
                password == os.getenv('ADMIN_PASSWORD', 'admin123')):
            session['admin'] = True
            return redirect(url_for('dashboard'))
        error = "Login yoki parol noto‘g‘ri!"
    return render_template('login.html', error=error)


@auth_bp.route('/logout')
@admin_required
def logout():
    session.pop('admin', None)
    return redirect(url_for('auth.login'))
if __name__ == 'main':
    app.run(debug=True)