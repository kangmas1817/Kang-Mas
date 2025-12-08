# ===== LOAD ENVIRONMENT VARIABLES =====
import os
from dotenv import load_dotenv  # Tambahkan ini di import section

# Load .env file jika ada (untuk development)
load_dotenv()

# Configurations akan diambil dari environment variables atau default

# ===== IMPORTS =====
# ===== IMPORTS =====
from pathlib import Path
from flask import Flask, jsonify, request, redirect, url_for, session, flash, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import random
from functools import wraps
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
import smtplib
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename
import time
import os
from dotenv import load_dotenv  # Pastikan ini diimpor

# ===== INISIALISASI APLIKASI =====
app = Flask(__name__)

base_dir = Path(__file__).parent
db_path = base_dir / "kangmas_shop.db"

# ==== PERBAIKAN DATABASE ====
# Jika DATABASE_URI tidak ada, gunakan SQLite
if not os.getenv('DATABASE_URI'):
    os.environ['DATABASE_URI'] = f'sqlite:///{db_path}'
    print(f"✅ Database SQLite: {db_path}")

## ===== DATABASE CONFIGURATION FOR RENDER =====
# ===== DATABASE CONFIGURATION FOR RENDER =====
import os

# Konfigurasi database untuk Render
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    print("✅ DATABASE_URL terdeteksi dari environment")
    
    # Konversi URL untuk menggunakan psycopg3 (psycopg[binary]) driver
    # psycopg3 menggunakan prefix "postgresql+psycopg://"
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg://', 1)
    elif DATABASE_URL.startswith('postgresql://'):
        DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    print("✅ Menggunakan PostgreSQL dengan driver psycopg3 (psycopg[binary])")
    
else:
    # Untuk development lokal
    base_dir = Path(__file__).parent
    db_path = base_dir / "kangmas_shop.db"
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    print(f"✅ Development: Menggunakan SQLite di {db_path}")

# Secret Key
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'kang-mas-secret-2025')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True,
    'pool_size': 10,  # Tambah untuk PostgreSQL
    'max_overflow': 20,  # Tambah untuk PostgreSQL
    'pool_timeout': 30  # Tambah untuk PostgreSQL
}

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Ensure upload folders exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'products'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'logos'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'assets'), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ===== GOOGLE OAUTH CONFIG =====
# ===== GOOGLE OAUTH CONFIG =====
# Load dari environment variables
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '916789780383-6ohg1tuhl1938t3ufid1ltl3u27b2m9a.apps.googleusercontent.com')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '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')

# Untuk development, izinkan insecure transport
# Untuk production di Render, set ke '0'
OAUTHLIB_INSECURE_TRANSPORT = os.environ.get('OAUTHLIB_INSECURE_TRANSPORT', '1')
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = OAUTHLIB_INSECURE_TRANSPORT
print(f"🔐 OAuth config loaded - Insecure transport: {OAUTHLIB_INSECURE_TRANSPORT}")

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_product_image(file, product_name=None):
    """Save product image and return filename"""
    if file and allowed_file(file.filename):
        if product_name:
            safe_name = secure_filename(product_name)
            safe_name = safe_name.replace(' ', '_').lower()
            filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file.filename.rsplit('.', 1)[1].lower()}"
        else:
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
        file.save(filepath)
        return f'uploads/products/{filename}'
    return None

def save_logo(file):
    """Save logo and return filename"""
    if file and allowed_file(file.filename):
        filename = 'logo.png'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'logos', filename)
        file.save(filepath)
        return f'uploads/logos/{filename}'
    return None

def get_product_cost_price(product_name):
    """Mengembalikan harga cost berdasarkan nama produk"""
    cost_prices = {
        'Bibit Ikan Mas': 1000,
        'Ikan Mas Konsumsi': 13500
    }
    return cost_prices.get(product_name, 1000)

# ===== OAuth flow configuration =====
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def get_google_flow():
    """Create Google OAuth flow with dynamic redirect URIs"""
    # Dapatkan base URL dari environment atau default
    # RENDER_EXTERNAL_URL tersedia di Render, RENDER_EXTERNAL_HOSTNAME juga bisa
    base_url = os.environ.get('RENDER_EXTERNAL_URL')
    
    if not base_url:
        # Jika tidak di Render, coba environment lain atau gunakan localhost
        base_url = os.environ.get('BASE_URL', 'http://localhost:5000')
    
    print(f"🔗 Using base URL for OAuth: {base_url}")
    
    # Buat redirect URIs - termasuk untuk development dan production
    redirect_uris = [
        f"{base_url}/google-callback"
    ]
    
    # Tambahkan localhost untuk development
    if 'localhost' in base_url or '127.0.0.1' in base_url:
        redirect_uris.extend([
            "http://localhost:5000/google-callback",
            "http://127.0.0.1:5000/google-callback"
        ])
    
    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": redirect_uris
            }
        },
        scopes=[
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email",
            "openid"
        ]
    )
    return flow

# ===== GOLDEN OCEAN COLOR PALETTE =====
COLORS = {
    'primary': '#B55123',    # DARK MANGO - Gold/Orange tua sebagai primary
    'secondary': '#E47A24',  # APRICOT - Gold/Orange medium
    'accent': '#7A6B5E',     # PINEAPPLE - Brown Gold
    'success': '#38a169',    # Kembali ke hijau untuk success (kontras lebih baik)
    'warning': '#d69e2e',    # Golden yellow untuk warning
    'error': '#BF2020',      # BLOOD ORANGE - Red
    'dark': '#2d3748',
    'light': '#fef6eb',      # Light golden tint
    'white': '#ffffff',
    'teal': '#E47A24',       # APRICOT - Gold/Orange
    'navy': '#B55123',       # DARK MANGO - Gold tua
    'ocean-light': '#fef6eb', # Light golden cream
    'ocean-medium': '#E47A24', # APRICOT - Gold medium
    'ocean-deep': '#B55123',   # DARK MANGO - Gold tua
    'gold-light': '#fef6eb',
    'gold-medium': '#E47A24',
    'gold-deep': '#B55123',
    'gold-dark': '#7A6B5E'
}

# ===== DATABASE MODELS =====
class User(UserMixin, db.Model): #Menyimpan data pengguna
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    full_name = db.Column(db.String(100), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    avatar = db.Column(db.String(200), default='👤')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    google_id = db.Column(db.String(100), unique=True)
    email_verified = db.Column(db.Boolean, default=False)
    verification_code = db.Column(db.String(6))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_verification_code(self):
        self.verification_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        return self.verification_code

class Product(db.Model): #Menyimpan data produk ikan mas
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    cost_price = db.Column(db.Float, default=1000)
    stock = db.Column(db.Integer, nullable=False)
    size_cm = db.Column(db.Float)
    weight_kg = db.Column(db.Float)
    category = db.Column(db.String(50), default='ikan_mas')
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_featured = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    image_url = db.Column(db.String(500))

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    payment_method = db.Column(db.String(50))
    payment_status = db.Column(db.String(20), default='unpaid')
    shipping_address = db.Column(db.Text, nullable=False)
    shipping_method = db.Column(db.String(50))
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    completed_date = db.Column(db.DateTime)
    tracking_info = db.Column(db.Text)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    cost_price = db.Column(db.Float)

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    balance = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_number = db.Column(db.String(20), unique=True, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text, nullable=False)
    journal_type = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    journal_details = db.relationship('JournalDetail', backref='journal_entry', lazy=True)

class JournalDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    journal_id = db.Column(db.Integer, db.ForeignKey('journal_entry.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    debit = db.Column(db.Float, default=0)
    credit = db.Column(db.Float, default=0)
    description = db.Column(db.Text)
    account = db.relationship('Account', backref='journal_details')

class CashFlow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InventoryCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'pembelian', 'penjualan', 'penyesuaian'
    transaction_number = db.Column(db.String(50))
    quantity_in = db.Column(db.Integer, default=0)
    quantity_out = db.Column(db.Integer, default=0)
    unit_cost = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    balance_quantity = db.Column(db.Integer, nullable=False)
    balance_value = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InventoryTransaction(db.Model):
    __tablename__ = 'inventory_transaction'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'pembelian', 'penjualan', 'penyesuaian', 'saldo_awal'
    quantity_in = db.Column(db.Integer, default=0)
    quantity_out = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    balance_quantity = db.Column(db.Integer, nullable=False)
    balance_unit_price = db.Column(db.Float, nullable=False)
    balance_total = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship('Product', backref='inventory_transactions')

class ClosingEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_number = db.Column(db.String(20), unique=True, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    closing_details = db.relationship('ClosingDetail', backref='closing_entry', lazy=True)

class ClosingDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    closing_id = db.Column(db.Integer, db.ForeignKey('closing_entry.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    debit = db.Column(db.Float, default=0)
    credit = db.Column(db.Float, default=0)
    description = db.Column(db.Text)
    account = db.relationship('Account', backref='closing_details')

class AppSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===== DATABASE MIGRATION =====
def reset_database_safe():
    """Safely reset database by creating new one"""
    try:
        # Cek dulu apakah database sudah ada
        db_path = Path("kangmas_shop.db")
        if db_path.exists():
            print("Database sudah ada, menggunakan yang existing...")
            return True

        # Jika tidak ada, buat baru
        db.create_all()
        print("New database created successfully!")
        return True
    except Exception as e:
        print(f"Cannot reset database: {e}")
        print("Trying to continue with existing database...")
        return False

# ===== TEMPLATE TRANSAKSI OTOMATIS LENGKAP BUDIDAYA IKAN MAS =====
TRANSACTION_TEMPLATES = {
    'setoran_modal': {
        'name': 'Setoran Modal Awal',
        'description': 'Pemilik menyetor modal awal ke usaha',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Setoran modal pemilik'},
            {'account_type': 'modal', 'side': 'credit', 'description': 'Modal pemilik'}
        ]
    },
 
    'pembelian_sederhana': {
        'name': 'Pembelian Ikan',
        'description': 'Input pembelian produk dengan pilihan produk dan metode pembayaran',
        'entries': [
            {'account_type': 'persediaan', 'side': 'debit', 'description': 'Pembelian persediaan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang dagang'}
        ],
        'inventory_effect': {'type': 'auto', 'action': 'in'}
    },
    'pembelian_peralatan_kredit': {
        'name': 'Pembelian Peralatan Kredit',
        'description': 'Membeli peralatan untuk budidaya ikan secara kredit',
        'entries': [
            {'account_type': 'peralatan', 'side': 'debit', 'description': 'Peralatan budidaya'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang dagang'}
        ]
    },
    'pembelian_perlengkapan_tunai': {
        'name': 'Pembelian Perlengkapan Tunai',
        'description': 'Membeli perlengkapan budidaya yang sifatnya habis pakai',
        'entries': [
            {'account_type': 'perlengkapan', 'side': 'debit', 'description': 'Perlengkapan budidaya'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'pembelian_bibit_campur': {
        'name': 'Pembelian Bibit Ikan (Tunai + Kredit)',
        'description': 'Membeli bibit ikan, sebagian tunai dan sebagian kredit',
        'entries': [
            {'account_type': 'persediaan', 'side': 'debit', 'description': 'Pembelian bibit ikan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang dagang'}
        ],
        'inventory_effect': {'type': 'bibit', 'action': 'in'}
    },
    'pelunasan_utang_peralatan': {
        'name': 'Pelunasan Utang Peralatan',
        'description': 'Melunasi faktur pembelian peralatan dari toko',
        'entries': [
            {'account_type': 'hutang', 'side': 'debit', 'description': 'Pelunasan utang peralatan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran kas'}
        ]
    },
    'pelunasan_utang_bibit': {
        'name': 'Pelunasan Utang Pembelian Bibit',
        'description': 'Melunasi faktur pembelian bibit yang sebelumnya kredit',
        'entries': [
            {'account_type': 'hutang', 'side': 'debit', 'description': 'Pelunasan utang bibit'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran kas'}
        ]
    },
    'pembelian_peralatan_tunai': {
        'name': 'Pembelian Peralatan Tunai',
        'description': 'Membeli alat tambahan (baskom, sortir, serokan) secara tunai',
        'entries': [
            {'account_type': 'peralatan', 'side': 'debit', 'description': 'Peralatan tambahan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'penambahan_bibit_alami': {
        'name': 'Penambahan Bibit dari Perkembangbiakan',
        'description': 'Mendapat tambahan bibit dari proses pembiakan alami',
        'entries': [
            {'account_type': 'persediaan', 'side': 'debit', 'description': 'Penambahan bibit alami'},
            {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan dari perkembangbiakan'}
        ],
        'inventory_effect': {'type': 'bibit', 'action': 'in'}
    },
    'pembelian_obat_ikan': {
        'name': 'Pembelian Obat/Vitamin Ikan',
        'description': 'Membeli obat pencegah penyakit untuk budidaya',
        'entries': [
            {'account_type': 'perlengkapan', 'side': 'debit', 'description': 'Obat dan vitamin ikan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'biaya_listrik_air': {
        'name': 'Pembayaran Biaya Listrik dan Air',
        'description': 'Membayar biaya listrik dan air bulan berjalan',
        'entries': [
            {'account_type': 'beban_listrik', 'side': 'debit', 'description': 'Biaya listrik dan air'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },

    'penjualan_sederhana': {
        'name': 'Penjualan Ikan',
        'description': 'Input penjualan produk dengan pilihan produk dan metode pembayaran',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan kas dari penjualan'},
            {'account_type': 'piutang', 'side': 'debit', 'description': 'Piutang penjualan'},
            {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan'},
            {'account_type': 'hpp', 'side': 'debit', 'description': 'Harga Pokok Produksi'},
            {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan'}
        ],
        'inventory_effect': {'type': 'auto', 'action': 'out'}
    },

    'penerimaan_piutang': {
        'name': 'Penerimaan Pembayaran Piutang',
        'description': 'Menerima pembayaran dari pelanggan atas penjualan kredit',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan kas dari piutang'},
            {'account_type': 'piutang', 'side': 'credit', 'description': 'Piutang dilunasi'}
        ]
    },
    'biaya_reparasi_kendaraan': {
        'name': 'Biaya Reparasi Kendaraan',
        'description': 'Mengeluarkan biaya reparasi kendaraan operasional',
        'entries': [
            {'account_type': 'beban_lain', 'side': 'debit', 'description': 'Biaya reparasi kendaraan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },

    'kerugian_bibit_ikan': {
        'name': 'Kerugian Bibit Ikan',
        'description': 'Kerugian Bibit ikan',
        'entries': [
            {'account_type': 'beban_kerugian', 'side': 'debit', 'description': 'Beban kerugian bibit mati'},
            {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan bibit'}
        ],
        'inventory_effect': {'type': 'bibit', 'action': 'out'},
        'inputs': [  # TAMBAHKAN INPUT QUANTITY
            {'name': 'quantity', 'label': 'Jumlah Bibit yang Mati (ekor)', 'type': 'number', 'required': True},
            {'name': 'unit_cost', 'label': 'Harga Cost per Unit', 'type': 'number', 'required': True, 'default': 1000}
        ]
    },
}

# ===== TEMPLATE JURNAL PENYESUAIAN BARU =====
ADJUSTMENT_TEMPLATES = {
    'penyesuaian_perlengkapan': {
        'name': 'Penyesuaian Perlengkapan',
        'description': 'Penyesuaian nilai perlengkapan berdasarkan stock opname',
        'calculation': 'Beban Perlengkapan = Saldo Perlengkapan (Neraca Saldo Sebelum Penyesuaian) - Nilai Tersisa',
        'entries': [
            {'account_type': 'beban_perlengkapan', 'side': 'debit', 'description': 'Beban pemakaian perlengkapan'},
            {'account_type': 'perlengkapan', 'side': 'credit', 'description': 'Pengurangan nilai perlengkapan'}
        ],
        'inputs': [
            {'name': 'nilai_tersisa', 'label': 'Nilai Perlengkapan Tersisa (Hasil Stock Opname)', 'type': 'number', 'required': True}
        ]
    },
    'penyusutan_aset_tetap': {
        'name': 'Penyusutan Aset Tetap',
        'description': 'Penyusutan aset tetap metode garis lurus',
        'calculation': 'Beban Penyusutan = (Harga Perolehan - Nilai Residu) / Umur Manfaat',
        'entries': [
            {'account_type': 'beban_penyusutan', 'side': 'debit', 'description': 'Beban penyusutan aset'},
            {'account_type': 'akumulasi_penyusutan', 'side': 'credit', 'description': 'Akumulasi penyusutan'}
        ],
        'inputs': [
            {'name': 'harga_perolehan', 'label': 'Harga Perolehan Aset', 'type': 'number', 'required': True},
            {'name': 'nilai_residu', 'label': 'Nilai Residu', 'type': 'number', 'required': True},
            {'name': 'umur_manfaat', 'label': 'Umur Manfaat (tahun)', 'type': 'number', 'required': True}
        ]
    },
    'penyesuaian_peralatan': {
        'name': 'Penyesuaian Peralatan',
        'description': 'Penyesuaian nilai peralatan berdasarkan nilai tersisa',
        'calculation': 'Beban Peralatan = Saldo Peralatan (Neraca Saldo Sebelum Penyesuaian) - Nilai Tersisa',
        'entries': [
            {'account_type': 'beban_peralatan', 'side': 'debit', 'description': 'Beban pemakaian peralatan'},
            {'account_type': 'peralatan', 'side': 'credit', 'description': 'Pengurangan nilai peralatan'}
        ],
        'inputs': [
            {'name': 'nilai_tersisa', 'label': 'Nilai Peralatan Tersisa', 'type': 'number', 'required': True}
        ]
    },
    'penyusutan_kendaraan': {
        'name': 'Penyusutan Kendaraan',
        'description': 'Penyusutan kendaraan metode garis lurus',
        'calculation': 'Beban Penyusutan = (Harga Perolehan - Nilai Residu) / Umur Manfaat',
        'entries': [
            {'account_type': 'beban_penyusutan', 'side': 'debit', 'description': 'Beban penyusutan kendaraan'},
            {'account_type': 'akumulasi_penyusutan', 'side': 'credit', 'description': 'Akumulasi penyusutan kendaraan'}
        ],
        'inputs': [
            {'name': 'harga_perolehan', 'label': 'Harga Perolehan Kendaraan', 'type': 'number', 'required': True},
            {'name': 'nilai_residu', 'label': 'Nilai Residu', 'type': 'number', 'required': True},
            {'name': 'umur_manfaat', 'label': 'Umur Manfaat (tahun)', 'type': 'number', 'required': True}
        ]
    },
   
    'akrual_pendapatan': {
        'name': 'Akrual Pendapatan',
        'description': 'Pencatatan pendapatan yang sudah diterima tapi belum diakui',
        'calculation': 'Pendapatan Diterima Dimuka = Total Pendapatan - Pendapatan Diakui',
        'entries': [
            {'account_type': 'pendapatan', 'side': 'debit', 'description': 'Pendapatan diterima dimuka'},
            {'account_type': 'pendapatan_diterima_dimuka', 'side': 'credit', 'description': 'Pendapatan yang diakui'}
        ],
        'inputs': [
            {'name': 'pendapatan_diakui', 'label': 'Pendapatan yang Sudah Diakui', 'type': 'number', 'required': True}
        ]
    },
    'akrual_beban': {
        'name': 'Akrual Beban',
        'description': 'Pencatatan beban yang sudah terjadi tapi belum dibayar',
        'calculation': 'Beban = Beban yang sudah terjadi - Beban yang sudah dibayar',
        'entries': [
            {'account_type': 'beban_operasional', 'side': 'debit', 'description': 'Beban yang masih harus dibayar'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang beban'}
        ],
        'inputs': [
            {'name': 'beban_terjadi', 'label': 'Beban yang Sudah Terjadi', 'type': 'number', 'required': True}
        ]
    },
    'penyesuaian_piutang_tak_tertagih': {
        'name': 'Penyesuaian Piutang Tak Tertagih',
        'description': 'Penyisihan piutang yang diperkirakan tidak dapat ditagih',
        'calculation': 'Penyisihan Piutang = Total Piutang x % Tak Tertagih',
        'entries': [
            {'account_type': 'beban_kerugian', 'side': 'debit', 'description': 'Beban piutang tak tertagih'},
            {'account_type': 'penyisihan_piutang', 'side': 'credit', 'description': 'Penyisihan piutang tak tertagih'}
        ],
        'inputs': [
            {'name': 'total_piutang', 'label': 'Total Piutang Usaha', 'type': 'number', 'required': True},
            {'name': 'persentase_tak_tertagih', 'label': 'Persentase Tak Tertagih (%)', 'type': 'number', 'required': True}
        ]
    },
    'penyesuaian_biaya_listrik': {
        'name': 'Penyesuaian Biaya Listrik',
        'description': 'Penyesuaian biaya listrik yang sudah digunakan tapi belum dibayar',
        'calculation': 'Beban Listrik = Pemakaian kWh x Tarif per kWh',
        'entries': [
            {'account_type': 'beban_listrik', 'side': 'debit', 'description': 'Beban listrik akrual'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang biaya listrik'}
        ],
        'inputs': [
            {'name': 'pemakaian_kwh', 'label': 'Pemakaian kWh', 'type': 'number', 'required': True},
            {'name': 'tarif_per_kwh', 'label': 'Tarif per kWh', 'type': 'number', 'required': True}
        ]
    },
    'penyesuaian_biaya_air': {
        'name': 'Penyesuaian Biaya Air',
        'description': 'Penyesuaian biaya air yang sudah digunakan tapi belum dibayar',
        'calculation': 'Beban Air = Pemakaian m³ x Tarif per m³',
        'entries': [
            {'account_type': 'beban_listrik', 'side': 'debit', 'description': 'Beban air akrual'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang biaya air'}
        ],
        'inputs': [
            {'name': 'pemakaian_m3', 'label': 'Pemakaian Air (m³)', 'type': 'number', 'required': True},
            {'name': 'tarif_per_m3', 'label': 'Tarif per m³', 'type': 'number', 'required': True}
        ]
    },
    'penyesuaian_penyusutan_bangunan': {
        'name': 'Penyesuaian Penyusutan Bangunan',
        'description': 'Penyusutan bangunan kolam dan gudang',
        'calculation': 'Beban Penyusutan = (Harga Perolehan - Nilai Residu) / Umur Manfaat',
        'entries': [
            {'account_type': 'beban_penyusutan', 'side': 'debit', 'description': 'Beban penyusutan bangunan'},
            {'account_type': 'akumulasi_penyusutan', 'side': 'credit', 'description': 'Akumulasi penyusutan bangunan'}
        ],
        'inputs': [
            {'name': 'harga_perolehan', 'label': 'Harga Perolehan Bangunan', 'type': 'number', 'required': True},
            {'name': 'nilai_residu', 'label': 'Nilai Residu Bangunan', 'type': 'number', 'required': True},
            {'name': 'umur_manfaat', 'label': 'Umur Manfaat (tahun)', 'type': 'number', 'required': True}
        ]
    },
    'penyesuaian_biaya_gaji': {
        'name': 'Penyesuaian Biaya Gaji',
        'description': 'Penyesuaian biaya gaji karyawan yang sudah bekerja tapi belum dibayar',
        'calculation': 'Beban Gaji = Jumlah Hari Kerja x Upah per Hari',
        'entries': [
            {'account_type': 'beban_gaji', 'side': 'debit', 'description': 'Beban gaji akrual'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang gaji'}
        ],
        'inputs': [
            {'name': 'jumlah_hari', 'label': 'Jumlah Hari Kerja', 'type': 'number', 'required': True},
            {'name': 'upah_per_hari', 'label': 'Upah per Hari', 'type': 'number', 'required': True}
        ]
    },
    'penyesuaian_pajak': {
        'name': 'Penyesuaian Pajak',
        'description': 'Penyesuaian beban pajak yang sudah menjadi kewajiban',
        'calculation': 'Beban Pajak = Penghasilan Kena Pajak x Tarif Pajak',
        'entries': [
            {'account_type': 'beban_lain', 'side': 'debit', 'description': 'Beban pajak'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang pajak'}
        ],
        'inputs': [
            {'name': 'penghasilan_kena_pajak', 'label': 'Penghasilan Kena Pajak', 'type': 'number', 'required': True},
            {'name': 'tarif_pajak', 'label': 'Tarif Pajak (%)', 'type': 'number', 'required': True}
        ]
    },
    'penyesuaian_biaya_sewa': {
        'name': 'Penyesuaian Biaya Sewa',
        'description': 'Penyesuaian biaya sewa yang sudah digunakan tapi belum dibayar',
        'calculation': 'Beban Sewa = (Biaya Sewa Tahunan / 12) x Bulan Terpakai',
        'entries': [
            {'account_type': 'beban_operasional', 'side': 'debit', 'description': 'Beban sewa akrual'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang sewa'}
        ],
        'inputs': [
            {'name': 'biaya_sewa_tahunan', 'label': 'Biaya Sewa Tahunan', 'type': 'number', 'required': True},
            {'name': 'bulan_terpakai', 'label': 'Bulan yang Sudah Terpakai', 'type': 'number', 'required': True}
        ]
    },
    'penyesuaian_biaya_bunga': {
        'name': 'Penyesuaian Biaya Bunga',
        'description': 'Penyesuaian biaya bunga pinjaman yang sudah terjadi',
        'calculation': 'Beban Bunga = Pokok Pinjaman x Suku Bunga x Waktu',
        'entries': [
            {'account_type': 'beban_lain', 'side': 'debit', 'description': 'Beban bunga'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang bunga'}
        ],
        'inputs': [
            {'name': 'pokok_pinjaman', 'label': 'Pokok Pinjaman', 'type': 'number', 'required': True},
            {'name': 'suku_bunga', 'label': 'Suku Bunga (%)', 'type': 'number', 'required': True},
            {'name': 'periode_bulan', 'label': 'Periode (bulan)', 'type': 'number', 'required': True}
        ]
    }
}

# ===== GOOGLE OAUTH ROUTES =====
@app.route('/google-login')
def google_login():
    try:
        flow = get_google_flow()
        flow.redirect_uri = url_for('google_callback', _external=True)
        
        # Generate state untuk security
        state = os.urandom(16).hex()
        session['state'] = state
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='select_account',
            state=state
        )
        
        print(f"🔗 Google OAuth URL generated: {authorization_url}")
        return redirect(authorization_url)
        
    except Exception as e:
        print(f"❌ Error generating Google OAuth URL: {str(e)}")
        flash('Error saat mengarahkan ke Google. Silakan coba lagi.', 'error')
        return redirect('/login')
    
@app.route('/google-callback')
def google_callback():
    try:
        print("🔄 Google OAuth callback received")
        print(f"📧 Request URL: {request.url}")
        
        # Dapatkan state untuk security check
        state = session.get('state')
        if not state:
            print("⚠️ No state found in session")
            flash('Sesi tidak valid. Silakan coba login kembali.', 'error')
            return redirect('/login')
        
        # Buat flow dengan redirect_uri yang benar
        flow = get_google_flow()
        
        # Gunakan _external=True untuk mendapatkan URL lengkap
        flow.redirect_uri = url_for('google_callback', _external=True)
        print(f"🔗 Redirect URI set to: {flow.redirect_uri}")
        
        # Fetch token
        authorization_response = request.url
        flow.fetch_token(
            authorization_response=authorization_response,
            state=state
        )
        
        # Verifikasi credentials
        credentials = flow.credentials
        id_info = id_token.verify_oauth2_token(
            credentials.id_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )
        
        google_id = id_info.get('sub')
        email = id_info.get('email')
        name = id_info.get('name')
        
        print(f"✅ Google OAuth successful for: {email}")
        
        # Cari atau buat user
        user = User.query.filter_by(email=email).first()

        if not user:
            user = User(
                email=email,
                full_name=name,
                user_type='customer',
                google_id=google_id,
                email_verified=True,
                avatar='👤'
            )
            db.session.add(user)
            db.session.commit()
            flash('Akun berhasil dibuat dengan Google!', 'success')
            print(f"✅ New user created: {email}")
        else:
            if not user.google_id:
                user.google_id = google_id
                db.session.commit()
                print(f"✅ Existing user updated with Google ID: {email}")
        
        # Login user
        login_user(user)
        flash(f'Berhasil login dengan Google! Selamat datang {name}', 'success')
        return redirect('/')

    except Exception as e:
        print(f"❌ Google OAuth error: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error saat login dengan Google. Silakan coba lagi.', 'error')
        return redirect('/login')
    
# ===== EMAIL CONFIG =====
EMAIL_CONFIG = {
    'smtp_server': os.getenv('EMAIL_SERVER', 'smtp.gmail.com'),
    'smtp_port': int(os.getenv('EMAIL_PORT', '587')),  # Default ke 587
    'sender_email': os.getenv('EMAIL_USERNAME', 'kang.mas1817@gmail.com'),
    'sender_password': os.getenv('EMAIL_PASSWORD', 'TugasSiaKangMas')
}

print(f"📧 Email config loaded:")
print(f"  - Server: {EMAIL_CONFIG['smtp_server']}")
print(f"  - Port: {EMAIL_CONFIG['smtp_port']}")
print(f"  - Sender: {EMAIL_CONFIG['sender_email']}")

def send_verification_email(email, verification_code):
    try:
        subject = "Kode Verifikasi Kang-Mas Shop"
        body = f"""
        Halo!

        Terima kasih telah mendaftar di Kang-Mas Shop.

        Kode verifikasi Anda adalah: {verification_code}

        Masukkan kode ini di halaman verifikasi untuk mengaktifkan akun Anda.

        Kode ini berlaku selama 10 menit.

        Salam,
        Tim Kang-Mas Shop
        """

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = email

        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# ===== DECORATORS =====
def seller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Silakan login terlebih dahulu.', 'error')
            return redirect('/login')
        if current_user.user_type != 'seller':
            flash('Akses ditolak. Hanya untuk seller.', 'error')
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

def customer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Silakan login terlebih dahulu.', 'error')
            return redirect('/login')
        if current_user.user_type != 'customer':
            flash('Akses ditolak. Hanya untuk customer.', 'error')
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

# ===== AKUNTANSI FUNCTIONS =====
def generate_unique_transaction_number(prefix='TRX'):
    """Generate unique transaction number dengan timestamp dan random number"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_num = random.randint(100, 999)
    return f"{prefix}{timestamp}{random_num}"

def create_cod_sales_journal(order):
    """Buat jurnal penjualan untuk order COD yang selesai - LENGKAP dengan HPP"""
    try:
        # Hitung total harga produk dan HPP
        product_total = 0
        hpp_total = 0
        for item in OrderItem.query.filter_by(order_id=order.id).all():
            product_total += item.price * item.quantity  # Harga jual
            hpp_total += item.cost_price * item.quantity  # Harga beli/HPP

        # Buat jurnal penjualan LENGKAP
        transaction_number = generate_unique_transaction_number('COD')
        description = f"Penjualan COD Order #{order.order_number}"

        # Get accounts
        kas_account = Account.query.filter_by(type='kas').first()
        pendapatan_account = Account.query.filter_by(type='pendapatan').first()
        hpp_account = Account.query.filter_by(type='hpp').first()
        persediaan_account = Account.query.filter_by(type='persediaan').first()

        if kas_account and pendapatan_account and hpp_account and persediaan_account:
            entries = [
                # Entri 1: Kas dan Pendapatan
                {
                    'account_id': kas_account.id,
                    'debit': product_total,
                    'credit': 0,
                    'description': f'Penerimaan kas dari penjualan COD order #{order.order_number}'
                },
                {
                    'account_id': pendapatan_account.id,
                    'debit': 0,
                    'credit': product_total,
                    'description': f'Pendapatan penjualan COD order #{order.order_number}'
                },
                
                # Entri 2: HPP dan Persediaan
                {
                    'account_id': hpp_account.id,
                    'debit': hpp_total,
                    'credit': 0,
                    'description': f'HPP penjualan COD order #{order.order_number}'
                },
                {
                    'account_id': persediaan_account.id,
                    'debit': 0,
                    'credit': hpp_total,
                    'description': f'Pengurangan persediaan COD order #{order.order_number}'
                }
            ]

            journal = create_journal_entry(
                transaction_number,
                order.completed_date or datetime.now(),
                description,
                'sales',
                entries
            )

            print(f"✅ Jurnal COD LENGKAP dibuat untuk order #{order.order_number}:")
            print(f"   Penjualan: Rp {product_total:,.0f}")
            print(f"   HPP: Rp {hpp_total:,.0f}")
            print(f"   Laba Kotor: Rp {product_total - hpp_total:,.0f}")

            # Update kartu persediaan untuk setiap produk yang dijual
            for item in OrderItem.query.filter_by(order_id=order.id).all():
                product = Product.query.get(item.product_id)
                if product:
                    update_inventory_card(
                        product_id=product.id,
                        transaction_type='penjualan',
                        transaction_number=transaction_number,
                        quantity=item.quantity,
                        unit_cost=product.cost_price,
                        date=order.completed_date or datetime.now()
                    )
                    print(f"✅ Kartu persediaan penjualan updated untuk {product.name}: {item.quantity} units")

            return journal

    except Exception as e:
        print(f"Error creating COD sales journal: {e}")
    return None

def create_journal_entry(transaction_number, date, description, journal_type, entries): #Membuat jurnal dengan validasi balance
    try:
        print(f"🔄 Memulai create_journal_entry: {transaction_number}")

        # Cek apakah transaction number sudah ada
        existing_journal = JournalEntry.query.filter_by(transaction_number=transaction_number).first()
        if existing_journal:
            # Jika sudah ada, generate yang baru
            transaction_number = generate_unique_transaction_number()
            print(f"🔄 Transaction number sudah ada, generate baru: {transaction_number}")

        journal = JournalEntry(
            transaction_number=transaction_number,
            date=date,
            description=description,
            journal_type=journal_type
        )
        db.session.add(journal)
        db.session.flush()  # Untuk dapat journal.id

        print(f"✅ Journal entry created: {journal.id}")

        # VERIFIKASI: Total debit harus sama dengan total credit
        total_debit = sum(entry.get('debit', 0) for entry in entries)
        total_credit = sum(entry.get('credit', 0) for entry in entries)

        print(f"💰 Total Debit: {total_debit}, Total Credit: {total_credit}")

        if total_debit != total_credit:
            raise ValueError(f"Jurnal tidak balance! Debit: {total_debit}, Kredit: {total_credit}")

        for entry in entries:
            detail = JournalDetail(
                journal_id=journal.id,
                account_id=entry['account_id'],
                debit=entry.get('debit', 0),
                credit=entry.get('credit', 0),
                description=entry.get('description', '')
            )
            db.session.add(detail)

            # Update account balance dengan benar
            account = db.session.get(Account, entry['account_id'])
            if account:
                if account.category in ['asset', 'expense']:
                    # Debit increases, credit decreases
                    account.balance += entry.get('debit', 0) - entry.get('credit', 0)
                    print(f"📈 Update {account.name}: +{entry.get('debit', 0)} -{entry.get('credit', 0)} = {account.balance}")
                else:
                    # Credit increases, debit decreases
                    account.balance += entry.get('credit', 0) - entry.get('debit', 0)
                    print(f"📈 Update {account.name}: +{entry.get('credit', 0)} -{entry.get('debit', 0)} = {account.balance}")

        db.session.commit()
        print(f"✅ Journal entry successfully committed: {journal.transaction_number}")
        return journal
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating journal entry: {e}")
        import traceback
        traceback.print_exc()
        raise e

def create_journal_from_template(template_key, date, amounts, inputs=None):
    """Membuat jurnal dari template dengan amount yang diberikan dan update kartu persediaan - DIPERBAIKI"""
    try:
        template = TRANSACTION_TEMPLATES[template_key]
        accounts_map = {}

        # Build accounts mapping
        for account in Account.query.all():
            accounts_map[account.type] = account.id

        entries = []
        amount_index = 0
        amount_keys = list(amounts.keys())

        # Hitung total untuk transaksi yang melibatkan persediaan
        total_persediaan = 0
        quantity = 0  # Untuk inventory effect

        print(f"📝 Membuat jurnal dari template: {template_key}")
        print(f" Amounts: {amounts}")
        print(f" Inputs: {inputs}")

        for template_entry in template['entries']:
            account_type = template_entry['account_type']

            # Handle multiple entries with same account type
            if amount_index < len(amount_keys):
                current_amount_key = amount_keys[amount_index]
                if current_amount_key.startswith(account_type):
                    amount = amounts[current_amount_key]
                    amount_index += 1
                else:
                    amount = amounts.get(account_type, 0)
            else:
                amount = amounts.get(account_type, 0)

            # Jika ada input quantity, gunakan itu untuk hitung amount
            if inputs and 'quantity' in inputs and 'unit_cost' in inputs:
                if account_type == 'persediaan' and template_entry['side'] == 'credit':
                    quantity = inputs.get('quantity', 0)
                    unit_cost = inputs.get('unit_cost', 1000)
                    amount = quantity * unit_cost
                    print(f"📦 Menggunakan input quantity: {quantity} x {unit_cost} = {amount}")

            # Kumpulkan informasi untuk kartu persediaan
            if account_type == 'persediaan':
                if template_entry['side'] == 'debit':
                    total_persediaan += amount  # Pembelian/penambahan
                elif template_entry['side'] == 'credit':
                    total_persediaan -= amount  # Pengurangan/penjualan/kerugian

            if account_type in accounts_map:
                entry = {
                    'account_id': accounts_map[account_type],
                    'description': template_entry['description']
                }
                if template_entry['side'] == 'debit':
                    entry['debit'] = amount
                    entry['credit'] = 0
                else:
                    entry['debit'] = 0
                    entry['credit'] = amount

                entries.append(entry)

        # Create journal entry dengan transaction number yang unique
        transaction_number = generate_unique_transaction_number()
        journal = create_journal_entry(
            transaction_number,
            date,
            template['description'],
            'general',
            entries
        )

        # PERBAIKAN: Update inventory dengan quantity dari inputs
        if 'inventory_effect' in template and inputs:
            print(f"🔄 Memanggil update_inventory_from_journal untuk {template_key}")
            print(f"📦 Quantity: {quantity}, Total persediaan: {total_persediaan}")
            update_inventory_from_journal(journal, template, inputs, quantity)
        else:
            print("ℹ️ Template tidak punya inventory effect atau inputs")

        return journal

    except Exception as e:
        print(f"Error creating journal from template {template_key}: {e}")
        import traceback
        traceback.print_exc()
        return None

# ===== FUNGSI UPDATE INVENTORY DARI JURNAL =====
def update_inventory_from_journal(journal, template, inputs, quantity):
    """Update kartu persediaan berdasarkan jurnal template dengan quantity dari inputs"""
    try:
        inventory_effect = template['inventory_effect']
        product_type = inventory_effect['type']  # 'bibit' atau 'ikan_konsumsi'
        action = inventory_effect['action']      # 'in' atau 'out'

        # Tentukan produk berdasarkan jenis
        if product_type == 'bibit':
            product_name = "Bibit Ikan Mas"
            category = 'bibit'
            unit_cost = inputs.get('unit_cost', 1000)
        elif product_type == 'ikan_konsumsi':
            product_name = "Ikan Mas Konsumsi"
            category = 'konsumsi'
            unit_cost = inputs.get('unit_cost', 13500)
        else:
            return

        # Cari produk berdasarkan nama dan kategori
        product = Product.query.filter_by(name=product_name, category=category).first()
        if not product:
            print(f"❌ Produk {product_name} tidak ditemukan")
            return

        print(f"📦 Processing inventory update: {product_name}, Quantity: {quantity}, Action: {action}")

        if action == 'out':
            # Update stok produk - KELUAR (kerugian)
            if product.stock >= quantity:
                product.stock -= quantity
                print(f"✅ Stok {product.name} berkurang {quantity} menjadi {product.stock}")

                # Buat transaksi inventory
                create_inventory_transaction(
                    product_id=product.id,
                    date=journal.date,
                    description=f"{journal.description}",
                    transaction_type='penyesuaian',
                    quantity_in=0,
                    quantity_out=quantity,
                    unit_price=unit_cost
                )
            else:
                print(f"⚠️ Stok tidak mencukupi untuk {product.name}. Stok: {product.stock}, Butuh: {quantity}")

        db.session.commit()
        print(f"✅ Kartu persediaan updated untuk {product.name}: {action} {quantity} units")

    except Exception as e:
        print(f"❌ Error updating inventory from journal: {e}")
        db.session.rollback()

# ===== FUNGSI UPDATE HPP OTOMATIS =====
def update_hpp_automatically(order):
    """Update HPP secara otomatis saat penjualan"""
    try:
        for item in OrderItem.query.filter_by(order_id=order.id).all():
            product = Product.query.get(item.product_id)
            if product:
                # Hitung HPP berdasarkan quantity yang dijual
                hpp_value = item.quantity * product.cost_price

                # Buat jurnal HPP
                transaction_number = generate_unique_transaction_number('HPP')
                description = f"Harga Pokok Produksi untuk penjualan {product.name}" - Order #{order.order_number}"

                # Get accounts
                hpp_account = Account.query.filter_by(type='hpp').first()
                persediaan_account = Account.query.filter_by(type='persediaan').first()

                if hpp_account and persediaan_account:
                    entries = [
                        {
                            'account_id': hpp_account.id,
                            'debit': hpp_value,
                            'credit': 0,
                            'description': f'HPP {product.name} - {item.quantity} units'
                        },
                        {
                            'account_id': persediaan_account.id,
                            'debit': 0,
                            'credit': hpp_value,
                            'description': f'Pengurangan persediaan {product.name}'
                        }
                    ]

                    create_journal_entry(
                        transaction_number,
                        order.completed_date or datetime.now(),
                        description,
                        'hpp',
                        entries
                    )

                    print(f"✅ Jurnal HPP dibuat: {hpp_value:,.0f} untuk {product.name}")

    except Exception as e:
        print(f"Error updating HPP automatically: {e}")

# ===== FUNGSI CREATE INVENTORY TRANSACTION =====
def update_inventory_card(product_id, transaction_type, transaction_number, quantity, unit_cost, date=None):
    """Update kartu persediaan untuk produk tertentu dengan harga cost yang sesuai"""
    try:
        print(f"🔄 [INVENTORY CARD] Memulai update inventory: Product {product_id}, Type: {transaction_type}, Qty: {quantity}")

        if date is None:
            date = datetime.now()

        # Dapatkan produk untuk mengetahui harga cost
        product = Product.query.get(product_id)
        if not product:
            print(f"❌ Product tidak ditemukan: {product_id}")
            return None

        COST_PRICE = product.cost_price

        # Dapatkan balance terakhir
        last_entry = InventoryCard.query.filter_by(product_id=product_id).order_by(InventoryCard.date.desc()).first()

        if last_entry:
            balance_quantity = last_entry.balance_quantity
            balance_value = last_entry.balance_value
            print(f"📊 [INVENTORY CARD] Last balance: Qty={balance_quantity}, Value={balance_value}")
        else:
            balance_quantity = 0
            balance_value = 0
            print(f"📊 [INVENTORY CARD] No previous entries, starting from zero")

        # Hitung quantity dan value baru
        if transaction_type == 'penjualan':
            quantity_in = 0
            quantity_out = quantity
            balance_quantity -= quantity

            # Hitung HPP dengan average cost
            hpp_value = quantity * COST_PRICE
            balance_value -= hpp_value

            print(f"📉 [INVENTORY CARD] Penjualan: -{quantity} units, HPP: {hpp_value}, new balance: {balance_quantity}")

        elif transaction_type == 'pembelian':
            quantity_in = quantity
            quantity_out = 0
            balance_quantity += quantity

            # Hitung average cost baru
            total_value = balance_value + (quantity * unit_cost)
            balance_value = total_value

            print(f"📈 [INVENTORY CARD] Pembelian: +{quantity} units, new balance: {balance_quantity}")
        else:  # penyesuaian
            quantity_in = quantity if quantity > 0 else 0
            quantity_out = abs(quantity) if quantity < 0 else 0
            balance_quantity += quantity
            balance_value += quantity * COST_PRICE

        total_cost = quantity * unit_cost

        # Buat entry baru
        inventory_entry = InventoryCard(
            product_id=product_id,
            date=date,
            transaction_type=transaction_type,
            transaction_number=transaction_number,
            quantity_in=quantity_in,
            quantity_out=quantity_out,
            unit_cost=unit_cost,
            total_cost=total_cost,
            balance_quantity=balance_quantity,
            balance_value=balance_value
        )

        db.session.add(inventory_entry)

        # Update stock produk
        if product:
            product.stock = balance_quantity
            # Update harga cost dengan average cost
            if balance_quantity > 0:
                product.cost_price = balance_value / balance_quantity
            print(f"📦 [INVENTORY CARD] Stock produk diupdate: {product.name} = {balance_quantity}, Cost: {product.cost_price}")

        db.session.commit()

        print(f"✅ [INVENTORY CARD] Kartu persediaan updated: {transaction_type} {quantity} units for product {product_id}")
        return inventory_entry

    except Exception as e:
        print(f"❌ [INVENTORY CARD] Error updating inventory card: {e}")
        db.session.rollback()
        return None

# ===== PERBAIKAN FUNGSI JURNAL PENJUALAN =====
def create_sales_journal(order):
    """Buat jurnal penjualan otomatis saat order completed - LENGKAP dengan HPP"""
    try:
        print(f"🔄 [DEBUG] Memulai pembuatan jurnal penjualan LENGKAP untuk order #{order.order_number}")

        # Hitung total harga produk saja (TANPA ONGKIR)
        product_total = 0
        hpp_total = 0
        order_items = OrderItem.query.filter_by(order_id=order.id).all()

        for item in order_items:
            product_total += item.price * item.quantity  # Harga jual
            hpp_total += item.cost_price * item.quantity  # Harga beli/HPP
            print(f"📦 [DEBUG] Produk: {item.product_id}, Qty: {item.quantity}, Price: {item.price}, Cost: {item.cost_price}")

        print(f"💰 [DEBUG] Total penjualan: Rp {product_total:,.0f}")
        print(f"📉 [DEBUG] Total HPP: Rp {hpp_total:,.0f}")

        # Buat jurnal penjualan LENGKAP
        transaction_number = generate_unique_transaction_number('SALES')
        description = f"Penjualan Order #{order.order_number}"

        # Get accounts
        kas_account = Account.query.filter_by(type='kas').first()
        pendapatan_account = Account.query.filter_by(type='pendapatan').first()
        hpp_account = Account.query.filter_by(type='hpp').first()
        persediaan_account = Account.query.filter_by(type='persediaan').first()

        if not kas_account:
            print("❌ [DEBUG] Akun Kas tidak ditemukan")
            return None
        if not pendapatan_account:
            print("❌ [DEBUG] Akun Pendapatan tidak ditemukan")
            return None
        if not hpp_account:
            print("❌ [DEBUG] Akun HPP tidak ditemukan")
            return None
        if not persediaan_account:
            print("❌ [DEBUG] Akun Persediaan tidak ditemukan")
            return None

        print(f"✅ [DEBUG] Akun ditemukan: Kas({kas_account.code}), Pendapatan({pendapatan_account.code}), HPP({hpp_account.code}), Persediaan({persediaan_account.code})")

        entries = [
            # Entri 1: Kas dan Pendapatan (pakai harga jual)
            {
                'account_id': kas_account.id,
                'debit': product_total,
                'credit': 0,
                'description': f'Penerimaan penjualan order #{order.order_number}'
            },
            {
                'account_id': pendapatan_account.id,
                'debit': 0,
                'credit': product_total,
                'description': f'Pendapatan penjualan order #{order.order_number}'
            },
            
            # Entri 2: HPP dan Persediaan (pakai harga beli)
            {
                'account_id': hpp_account.id,
                'debit': hpp_total,
                'credit': 0,
                'description': f'HPP penjualan order #{order.order_number}'
            },
            {
                'account_id': persediaan_account.id,
                'debit': 0,
                'credit': hpp_total,
                'description': f'Pengurangan persediaan order #{order.order_number}'
            }
        ]

        print(f"📝 [DEBUG] Membuat jurnal dengan {len(entries)} entries")

        journal = create_journal_entry(
            transaction_number,
            order.completed_date or datetime.now(),
            description,
            'sales',
            entries
        )

        if journal:
            print(f"✅ [DEBUG] Jurnal penjualan LENGKAP berhasil dibuat: {journal.transaction_number}")
            print(f"📊 [DEBUG] Total Penjualan: Rp {product_total:,.0f}")
            print(f"📊 [DEBUG] Total HPP: Rp {hpp_total:,.0f}")
            print(f"📊 [DEBUG] Laba Kotor: Rp {product_total - hpp_total:,.0f}")
        else:
            print("❌ [DEBUG] Gagal membuat jurnal penjualan")
            return None

        # Update kartu persediaan untuk setiap produk yang dijual
        for item in order_items:
            product = Product.query.get(item.product_id)
            if product:
                print(f"📊 [DEBUG] Update kartu persediaan untuk {product.name}: {item.quantity} units")

                # DEBUG: Cek stok sebelum update
                print(f"📦 [DEBUG] Stok sebelum: {product.stock}")

                # Panggil fungsi update inventory
                result = update_inventory_card(
                    product_id=product.id,
                    transaction_type='penjualan',
                    transaction_number=transaction_number,
                    quantity=item.quantity,
                    unit_cost=product.cost_price,
                    date=order.completed_date or datetime.now()
                )

                if result:
                    print(f"✅ [DEBUG] Kartu persediaan berhasil diupdate")
                else:
                    print(f"❌ [DEBUG] Gagal update kartu persediaan")

                # DEBUG: Cek stok setelah update
                db.session.refresh(product)
                print(f"📦 [DEBUG] Stok setelah: {product.stock}")

        return journal

    except Exception as e:
        print(f"❌ [DEBUG] Error creating sales journal: {e}")
        import traceback
        traceback.print_exc()
    return None

# ===== PERBAIKAN FUNGSI JURNAL PEMBELIAN =====
def create_purchase_journal(order):
    """Buat jurnal pembelian otomatis saat order completed - TANPA ONGKIR"""
    try:
        # Hitung total cost dari order items (TANPA ONGKIR)
        total_cost = 0
        for item in OrderItem.query.filter_by(order_id=order.id).all():
            total_cost += item.cost_price * item.quantity

        # Buat jurnal pembelian
        transaction_number = generate_unique_transaction_number('PURCH')
        description = f"Pembelian Persediaan Order #{order.order_number}"

        # Get accounts
        kas_account = Account.query.filter_by(type='kas').first()
        persediaan_account = Account.query.filter_by(type='persediaan').first()

        if kas_account and persediaan_account:
            entries = [
                {
                    'account_id': persediaan_account.id,
                    'debit': total_cost,
                    'credit': 0,
                    'description': f'Pembelian persediaan order #{order.order_number}'
                },
                {
                    'account_id': kas_account.id,
                    'debit': 0,
                    'credit': total_cost,
                    'description': f'Pembayaran pembelian order #{order.order_number}'
                }
            ]

            journal = create_journal_entry(
                transaction_number,
                order.completed_date or datetime.now(),
                description,
                'purchase',
                entries
            )

            print(f"✅ Jurnal pembelian dibuat untuk order #{order.order_number}: Rp {total_cost:,.0f}")

            # Update kartu persediaan untuk setiap produk
            for item in OrderItem.query.filter_by(order_id=order.id).all():
                product = Product.query.get(item.product_id)
                if product:
                    update_inventory_card(
                        product_id=product.id,
                        transaction_type='pembelian',
                        transaction_number=transaction_number,
                        quantity=item.quantity,
                        unit_cost=item.cost_price,
                        date=order.completed_date or datetime.now()
                    )
                    print(f"✅ Kartu persediaan updated untuk {product.name}: {item.quantity} units")

            return journal

    except Exception as e:
        print(f"Error creating purchase journal: {e}")
    return None

# ===== FUNGSI BUKU BESAR =====
def get_ledger_data():
    """Ambil data untuk buku besar - MENGGUNAKAN SALDO AWAL DARI DATABASE"""
    try:
        # Dapatkan semua akun
        all_accounts = Account.query.order_by(Account.code).all()

        ledger_html = ""

        for account in all_accounts:
            # ✅✅✅ BENAR: Hitung saldo awal REAL dari database
            
            # Langkah 1: Mulai dari saldo awal di database
            saldo_awal_murni = account.balance  # Ini dari form edit saldo awal
            
            # Langkah 2: KURANGI efek dari SEMUA transaksi jurnal
            # (karena account.balance sudah termasuk semua jurnal)
            semua_jurnal = JournalDetail.query.filter_by(account_id=account.id).all()
            
            total_efek_jurnal = 0
            for detail in semua_jurnal:
                if account.category in ['asset', 'expense']:
                    # Asset/Expense: Debit (+), Credit (-)
                    total_efek_jurnal += detail.debit - detail.credit
                else:
                    # Liability/Equity/Revenue: Credit (+), Debit (-)
                    total_efek_jurnal += detail.credit - detail.debit
            
            # Saldo awal murni = Saldo sekarang - efek semua jurnal
            opening_balance = saldo_awal_murni - total_efek_jurnal
            
            # Debug info
            print(f"📊 [LEDGER] {account.code} - {account.name}:")
            print(f"   Saldo database: {saldo_awal_murni:,.0f}")
            print(f"   Total efek jurnal: {total_efek_jurnal:,.0f}")
            print(f"   Saldo awal murni: {opening_balance:,.0f}")

            # Hanya tampilkan akun yang punya saldo atau transaksi
            journal_details = JournalDetail.query.join(JournalEntry).filter(
                JournalDetail.account_id == account.id,
                JournalEntry.journal_type.in_(['general', 'sales', 'purchase', 'hpp', 'adjustment'])
            ).order_by(JournalEntry.date, JournalDetail.id).all()

            if abs(opening_balance) > 0.01 or journal_details:  # Toleransi kecil
                account_html = f'''
                <div class="card" style="margin-bottom: 2rem;">
                    <h4 style="color: var(--primary); margin-bottom: 1rem;">
                        {account.code} - {account.name}
                    </h4>
                '''

                if journal_details:
                    account_html += '''
                    <div style="overflow-x: auto;">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Tanggal</th>
                                    <th>Keterangan</th>
                                    <th>Debit</th>
                                    <th>Kredit</th>
                                    <th>Saldo</th>
                                </tr>
                            </thead>
                            <tbody>
                    '''

                    running_balance = opening_balance

                    # Tambahkan baris saldo awal
                    account_html += f'''
                    <tr style="background: rgba(49, 130, 206, 0.05);">
                        <td>Saldo Awal</td>
                        <td><strong>Saldo Awal Periode</strong></td>
                        <td></td>
                        <td></td>
                        <td class="{'debit' if running_balance >= 0 else 'credit'}">Rp {abs(running_balance):,.0f}</td>
                    </tr>
                    '''

                    for detail in journal_details:
                        journal = detail.journal_entry

                        # Update running balance sesuai kategori akun
                        if account.category in ['asset', 'expense']:
                            running_balance += detail.debit - detail.credit
                        else:
                            running_balance += detail.credit - detail.debit

                        account_html += f'''
                        <tr>
                            <td>{journal.date.strftime('%d/%m/%Y')}</td>
                            <td>{journal.description}</td>
                            <td class="debit">{"Rp {0:,.0f}".format(detail.debit) if detail.debit > 0 else ""}</td>
                            <td class="credit">{"Rp {0:,.0f}".format(detail.credit) if detail.credit > 0 else ""}</td>
                            <td class="{'debit' if running_balance >= 0 else 'credit'}">Rp {abs(running_balance):,.0f}</td>
                        </tr>
                        '''

                    account_html += '''
                            </tbody>
                        </table>
                    </div>
                    '''
                else:
                    # Jika tidak ada transaksi, tampilkan saldo awal saja
                    if abs(opening_balance) > 0.01:
                        account_html += f'''
                        <p>Saldo Awal: <span class="{'debit' if opening_balance >= 0 else 'credit'}">
                            Rp {abs(opening_balance):,.0f}
                        </span></p>
                        '''

                account_html += '</div>'
                ledger_html += account_html

        return ledger_html if ledger_html else '<div class="card"><p>Belum ada transaksi untuk ditampilkan di buku besar.</p></div>'

    except Exception as e:
        print(f"Error generating ledger data: {e}")
        import traceback
        traceback.print_exc()
        return '<div class="card"><p>Error loading ledger data.</p></div>'

# ===== FUNGSI KARTU PERSEDIAAN BARU =====
def get_inventory_card_html(product_id=None):
    """Generate HTML untuk kartu persediaan dengan format seperti screenshot"""
    try:
        # Jika product_id tidak diberikan, ambil produk pertama
        if not product_id:
            product = Product.query.filter_by(seller_id=current_user.id).first()
            if product:
                product_id = product.id
            else:
                return '''
                <div class="card">
                    <h4 style="color: var(--primary);">Kartu Persediaan</h4>
                    <p>Belum ada produk. Silakan tambah produk terlebih dahulu.</p>
                </div>
                '''

        product = Product.query.get(product_id)
        if not product:
            return '<div class="card"><p>Produk tidak ditemukan</p></div>'

        # Dapatkan semua transaksi inventory untuk produk ini
        transactions = InventoryTransaction.query.filter_by(
            product_id=product_id
        ).order_by(InventoryTransaction.date, InventoryTransaction.id).all()

        if not transactions:
            return f'''
            <div class="card">
                <h4 style="color: var(--primary);">Kartu Persediaan - {product.name}</h4>
                <p>Belum ada transaksi untuk produk ini.</p>
            </div>
            '''

        # Header tabel dengan format yang benar
        table_html = f'''
        <div class="card">
            <h4 style="color: var(--primary); margin-bottom: 1.5rem;">
                <i class="fas fa-boxes"></i> Kartu Persediaan - {product.name}
            </h4>

            <div style="overflow-x: auto;">
                <table class="table" style="font-size: 0.9rem; min-width: 1400px; border-collapse: collapse;">
                    <thead>
                        <tr style="background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%); color: white;">
                            <th rowspan="2" style="padding: 12px; text-align: center; vertical-align: middle; border: 1px solid #ddd;">TANGGAL</th>
                            <th rowspan="2" style="padding: 12px; text-align: center; vertical-align: middle; border: 1px solid #ddd;">DESKRIPSI</th>
                            <th colspan="3" style="padding: 12px; text-align: center; border: 1px solid #ddd;">IN</th>
                            <th colspan="3" style="padding: 12px; text-align: center; border: 1px solid #ddd;">OUT</th>
                            <th colspan="3" style="padding: 12px; text-align: center; border: 1px solid #ddd;">BALANCE</th>
                        </tr>
                        <tr style="background: rgba(49, 130, 206, 0.1);">
                            <!-- IN Sub-headers -->
                            <th style="padding: 10px; text-align: center; border: 1px solid #ddd; background: rgba(56, 161, 105, 0.2);">Quantity</th>
                            <th style="padding: 10px; text-align: center; border: 1px solid #ddd; background: rgba(56, 161, 105, 0.2);">Harga Per Unit</th>
                            <th style="padding: 10px; text-align: center; border: 1px solid #ddd; background: rgba(56, 161, 105, 0.2);">Jumlah</th>

                            <!-- OUT Sub-headers -->
                            <th style="padding: 10px; text-align: center; border: 1px solid #ddd; background: rgba(229, 62, 62, 0.2);">Quantity</th>
                            <th style="padding: 10px; text-align: center; border: 1px solid #ddd; background: rgba(229, 62, 62, 0.2);">Harga Per Unit</th>
                            <th style="padding: 10px; text-align: center; border: 1px solid #ddd; background: rgba(229, 62, 62, 0.2);">Jumlah</th>

                            <!-- BALANCE Sub-headers -->
                            <th style="padding: 10px; text-align: center; border: 1px solid #ddd; background: rgba(49, 130, 206, 0.2);">Quantity</th>
                            <th style="padding: 10px; text-align: center; border: 1px solid #ddd; background: rgba(49, 130, 206, 0.2);">Harga Per Unit</th>
                            <th style="padding: 10px; text-align: center; border: 1px solid #ddd; background: rgba(49, 130, 206, 0.2);">Jumlah</th>
                        </tr>
                    </thead>
                    <tbody>
        '''

        # Harga cost tetap Rp 1,000
        COST_PRICE = 1000

        for transaction in transactions:
            # Tentukan data untuk kolom IN dan OUT berdasarkan jenis transaksi
            if transaction.transaction_type == 'pembelian':
                in_qty = transaction.quantity_in
                in_price = transaction.unit_price
                in_total = transaction.total_amount
                out_qty = 0
                out_price = 0
                out_total = 0
            elif transaction.transaction_type == 'penjualan':
                in_qty = 0
                in_price = 0
                in_total = 0
                out_qty = transaction.quantity_out
                out_price = transaction.unit_price  # Harga cost (bukan harga jual)
                out_total = transaction.total_amount
            else:  # saldo_awal, penyesuaian, dll
                in_qty = transaction.quantity_in
                in_price = transaction.unit_price
                in_total = transaction.total_amount
                out_qty = transaction.quantity_out
                out_price = transaction.unit_price
                out_total = transaction.total_amount

            # Hitung balance
            balance_quantity = transaction.balance_quantity
            balance_unit_price = COST_PRICE  # SELALU Rp 1,000
            balance_total = balance_quantity * COST_PRICE  # Hitung ulang dengan harga cost

            # Format numbers dengan separator
            def format_number(num):
                return f"{num:,.0f}" if num != 0 else "-"

            def format_currency(num):
                return f"Rp {num:,.0f}" if num != 0 else "-"

            table_html += f'''
            <tr>
                <!-- Tanggal & Deskripsi -->
                <td style="padding: 10px; text-align: center; border: 1px solid #ddd; font-weight: 500;">{transaction.date.strftime('%d/%m/%Y')}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{transaction.description}</td>

                <!-- IN Columns -->
                <td style="padding: 10px; text-align: right; border: 1px solid #ddd; background: rgba(56, 161, 105, 0.05);">{format_number(in_qty)}</td>
                <td style="padding: 10px; text-align: right; border: 1px solid #ddd; background: rgba(56, 161, 105, 0.05);">{format_currency(in_price)}</td>
                <td style="padding: 10px; text-align: right; border: 1px solid #ddd; background: rgba(56, 161, 105, 0.05);">{format_currency(in_total)}</td>

                <!-- OUT Columns -->
                <td style="padding: 10px; text-align: right; border: 1px solid #ddd; background: rgba(229, 62, 62, 0.05);">{format_number(out_qty)}</td>
                <td style="padding: 10px; text-align: right; border: 1px solid #ddd; background: rgba(229, 62, 62, 0.05);">{format_currency(out_price)}</td>
                <td style="padding: 10px; text-align: right; border: 1px solid #ddd; background: rgba(229, 62, 62, 0.05);">{format_currency(out_total)}</td>

                <!-- BALANCE Columns -->
                <td style="padding: 10px; text-align: right; border: 1px solid #ddd; background: rgba(49, 130, 206, 0.05); font-weight: bold;">{format_number(balance_quantity)}</td>
                <td style="padding: 10px; text-align: right; border: 1px solid #ddd; background: rgba(49, 130, 206, 0.05); font-weight: bold;">{format_currency(balance_unit_price)}</td>
                <td style="padding: 10px; text-align: right; border: 1px solid #ddd; background: rgba(49, 130, 206, 0.05); font-weight: bold;">{format_currency(balance_total)}</td>
            </tr>
            '''

        table_html += '''
                    </tbody>
                </table>
            </div>
        '''

        return table_html

    except Exception as e:
        print(f"Error generating inventory card: {e}")
        return f'<div class="card"><p>Error loading inventory card: {str(e)}</p></div>'

# ===== FUNGSI CREATE INVENTORY TRANSACTION =====
def create_inventory_transaction(product_id, date, description, transaction_type,
                               quantity_in, quantity_out, unit_price):
    """Membuat transaksi persediaan dan menghitung balance dengan harga cost yang sesuai"""
    try:
        # Dapatkan produk untuk mengetahui harga cost
        product = Product.query.get(product_id)
        if not product:
            print(f"❌ Product tidak ditemukan: {product_id}")
            return None

        # Gunakan harga cost dari produk
        COST_PRICE = product.cost_price

        print(f"🔄 [INVENTORY] Product: {product.name}, Cost Price: {COST_PRICE}")

        # Dapatkan transaksi terakhir untuk produk ini
        last_transaction = InventoryTransaction.query.filter_by(
            product_id=product_id
        ).order_by(InventoryTransaction.date.desc(), InventoryTransaction.id.desc()).first()

        # Hitung balance baru
        if last_transaction:
            balance_quantity = last_transaction.balance_quantity + quantity_in - quantity_out
            # Untuk balance value, gunakan metode average cost
            if balance_quantity > 0:
                if quantity_in > 0:
                    # Pembelian: hitung average cost baru
                    total_value = last_transaction.balance_total + (quantity_in * unit_price)
                    balance_unit_price = total_value / balance_quantity
                else:
                    # Penjualan: gunakan average cost dari transaksi terakhir
                    balance_unit_price = last_transaction.balance_unit_price
            else:
                balance_unit_price = COST_PRICE
        else:
            # Transaksi pertama
            balance_quantity = quantity_in - quantity_out
            if quantity_in > 0:
                balance_unit_price = unit_price
            else:
                balance_unit_price = COST_PRICE

        balance_total = balance_quantity * balance_unit_price

        # Hitung total amount dengan benar
        if quantity_in > 0:
            # Untuk pembelian: total = quantity_in * unit_price (harga beli)
            total_amount = quantity_in * unit_price
        elif quantity_out > 0:
            # Untuk penjualan: total = quantity_out * balance_unit_price (HPP)
            total_amount = quantity_out * balance_unit_price
        else:
            total_amount = 0

        # Untuk penjualan, gunakan average cost sebagai unit_price
        if transaction_type == 'penjualan':
            unit_price = balance_unit_price

        # Buat transaksi baru
        transaction = InventoryTransaction(
            product_id=product_id,
            date=date,
            description=description,
            transaction_type=transaction_type,
            quantity_in=quantity_in,
            quantity_out=quantity_out,
            unit_price=unit_price,
            total_amount=total_amount,
            balance_quantity=balance_quantity,
            balance_unit_price=balance_unit_price,
            balance_total=balance_total
        )

        db.session.add(transaction)

        # Update stock produk
        if product:
            product.stock = balance_quantity
            # Update harga cost produk dengan average cost terbaru
            product.cost_price = balance_unit_price
            print(f"✅ Stock produk diupdate: {product.name} = {balance_quantity}, Cost Price: {balance_unit_price}")

        db.session.commit()

        print(f"✅ Inventory transaction created: {transaction_type} {quantity_in} in, {quantity_out} out, total: {total_amount}")
        print(f"📊 Balance: Qty={balance_quantity}, Unit Price={balance_unit_price}, Total={balance_total}")
        return transaction

    except Exception as e:
        print(f"❌ Error creating inventory transaction: {e}")
        db.session.rollback()
        return None

def update_inventory_card(product_id, transaction_type, transaction_number, quantity, unit_cost, date=None):
    """Update kartu persediaan untuk produk tertentu dengan harga cost yang sesuai"""
    try:
        print(f"🔄 [INVENTORY CARD] Memulai update inventory: Product {product_id}, Type: {transaction_type}, Qty: {quantity}")

        if date is None:
            date = datetime.now()

        # Dapatkan produk untuk mengetahui harga cost
        product = Product.query.get(product_id)
        if not product:
            print(f"❌ Product tidak ditemukan: {product_id}")
            return None

        COST_PRICE = product.cost_price

        # Dapatkan balance terakhir
        last_entry = InventoryCard.query.filter_by(product_id=product_id).order_by(InventoryCard.date.desc()).first()

        if last_entry:
            balance_quantity = last_entry.balance_quantity
            balance_value = last_entry.balance_value
            print(f"📊 [INVENTORY CARD] Last balance: Qty={balance_quantity}, Value={balance_value}")
        else:
            balance_quantity = 0
            balance_value = 0
            print(f"📊 [INVENTORY CARD] No previous entries, starting from zero")

        # Hitung quantity dan value baru
        if transaction_type == 'penjualan':
            quantity_in = 0
            quantity_out = quantity
            balance_quantity -= quantity

            # Hitung HPP dengan average cost
            hpp_value = quantity * COST_PRICE
            balance_value -= hpp_value

            print(f"📉 [INVENTORY CARD] Penjualan: -{quantity} units, HPP: {hpp_value}, new balance: {balance_quantity}")

        elif transaction_type == 'pembelian':
            quantity_in = quantity
            quantity_out = 0
            balance_quantity += quantity

            # Hitung average cost baru
            total_value = balance_value + (quantity * unit_cost)
            balance_value = total_value

            print(f"📈 [INVENTORY CARD] Pembelian: +{quantity} units, new balance: {balance_quantity}")
        else:  # penyesuaian
            quantity_in = quantity if quantity > 0 else 0
            quantity_out = abs(quantity) if quantity < 0 else 0
            balance_quantity += quantity
            balance_value += quantity * COST_PRICE

        total_cost = quantity * unit_cost

        # Buat entry baru
        inventory_entry = InventoryCard(
            product_id=product_id,
            date=date,
            transaction_type=transaction_type,
            transaction_number=transaction_number,
            quantity_in=quantity_in,
            quantity_out=quantity_out,
            unit_cost=unit_cost,
            total_cost=total_cost,
            balance_quantity=balance_quantity,
            balance_value=balance_value
        )

        db.session.add(inventory_entry)

        # Update stock produk
        if product:
            product.stock = balance_quantity
            # Update harga cost dengan average cost
            if balance_quantity > 0:
                product.cost_price = balance_value / balance_quantity
            print(f"📦 [INVENTORY CARD] Stock produk diupdate: {product.name} = {balance_quantity}, Cost: {product.cost_price}")

        db.session.commit()

        print(f"✅ [INVENTORY CARD] Kartu persediaan updated: {transaction_type} {quantity} units for product {product_id}")
        return inventory_entry

    except Exception as e:
        print(f"❌ [INVENTORY CARD] Error updating inventory card: {e}")
        db.session.rollback()
        return None

def get_balance_sheet():
    """Generate balance sheet HTML yang seimbang"""
    try:
        # Get asset accounts (positive balances only)
        asset_accounts = Account.query.filter_by(category='asset').filter(Account.balance > 0).all()
        total_assets = sum(acc.balance for acc in asset_accounts)

        # Get liability accounts (positive balances only)
        liability_accounts = Account.query.filter_by(category='liability').filter(Account.balance > 0).all()
        total_liabilities = sum(acc.balance for acc in liability_accounts)

        # Get equity accounts
        equity_accounts = Account.query.filter_by(category='equity').all()

        # Calculate net income/loss
        revenue_accounts = Account.query.filter_by(category='revenue').all()
        expense_accounts = Account.query.filter_by(category='expense').all()
        total_revenue = sum(acc.balance for acc in revenue_accounts)
        total_expenses = sum(acc.balance for acc in expense_accounts)
        net_income = total_revenue - total_expenses

        # Calculate total equity (modal + laba/rugi)
        total_equity = sum(acc.balance for acc in equity_accounts) + net_income

        assets_html = ""
        for acc in asset_accounts:
            assets_html += f'''
            <tr>
                <td>{acc.name}</td>
                <td class="debit">Rp {acc.balance:,.0f}</td>
            </tr>
            '''

        liabilities_html = ""
        for acc in liability_accounts:
            liabilities_html += f'''
            <tr>
                <td>{acc.name}</td>
                <td class="credit">Rp {acc.balance:,.0f}</td>
            </tr>
            '''

        equity_html = ""
        for acc in equity_accounts:
            if acc.balance != 0:  # Hanya tampilkan equity yang ada saldonya
                equity_html += f'''
                <tr>
                    <td>{acc.name}</td>
                    <td class="credit">Rp {acc.balance:,.0f}</td>
                </tr>
                '''

        # Tampilkan laba/rugi
        if net_income != 0:
            equity_html += f'''
            <tr>
                <td>{"Laba Bersih" if net_income > 0 else "Rugi Bersih"}</td>
                <td class="credit">Rp {abs(net_income):,.0f}</td>
            </tr>
            '''

        is_balanced = total_assets == (total_liabilities + total_equity)

        return f'''
        <div class="grid grid-2">
            <div>
                <h4>ASET</h4>
                <table class="table">
                    <tbody>
                        {assets_html}
                        <tr style="font-weight: bold; border-top: 2px solid var(--primary);">
                            <td>Total Aset</td>
                            <td class="debit">Rp {total_assets:,.0f}</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <div>
                <h4>KEWAJIBAN & EKUITAS</h4>
                <table class="table">
                    <tbody>
                        {liabilities_html}
                        <tr style="font-weight: bold;">
                            <td>Total Kewajiban</td>
                            <td class="credit">Rp {total_liabilities:,.0f}</td>
                        </tr>
                        {equity_html}
                        <tr style="font-weight: bold; border-top: 2px solid var(--primary);">
                            <td>Total Ekuitas</td>
                            <td class="credit">Rp {total_equity:,.0f}</td>
                        </tr>
                        <tr style="font-weight: bold; border-top: 2px solid var(--primary); background: rgba(49, 130, 206, 0.1);">
                            <td>Total Kewajiban & Ekuitas</td>
                            <td class="credit">Rp {total_liabilities + total_equity:,.0f}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <div style="margin-top: 2rem; padding: 1.5rem; background: {'rgba(56, 161, 105, 0.1)' if is_balanced else 'rgba(229, 62, 62, 0.1)'}; border-radius: var(--border-radius);">
            <h4 style="color: {'var(--success)' if is_balanced else 'var(--error)'};">
                {'✅ NERACA SEIMBANG' if is_balanced else '❌ NERACA TIDAK SEIMBANG'}
            </h4>
            <p><strong>Aset = Kewajiban + Ekuitas</strong></p>
            <p>Rp {total_assets:,.0f} = Rp {total_liabilities:,.0f} + Rp {total_equity:,.0f}</p>
            <p>Rp {total_assets:,.0f} = Rp {total_liabilities + total_equity:,.0f}</p>
        </div>
        '''
    except Exception as e:
        print(f"Error generating balance sheet: {e}")
        return f'<p>Error loading balance sheet: {e}</p>'

def get_initial_balances():
    """Mengambil saldo awal dari database - OTOMATIS"""
    try:
        accounts = Account.query.all()
        initial_balances = {}

        for account in accounts:
            initial_balances[account.type] = account.balance

        return initial_balances
    except Exception as e:
        print(f"Error getting initial balances: {e}")
        return {}

def get_saldo_awal_html():
    """Generate HTML untuk saldo awal MURNI - HANYA SALDO AWAL dari database, TANPA efek jurnal"""
    try:
        # PERBAIKAN: Ambil semua akun REAL (Aset, Kewajiban, Ekuitas)
        accounts = Account.query.filter(
            Account.category.in_(['asset', 'liability', 'equity'])
        ).order_by(Account.code).all()

        saldo_html = ""
        total_debit = 0
        total_credit = 0

        for account in accounts:
            # ===== PERBAIKAN UTAMA =====
            # SALDO AWAL MURNI = saldo database MINUS efek SEMUA jurnal (umum + penyesuaian)
            # karena di database, account.balance sudah termasuk efek semua transaksi
            
            # 1. Ambil saldo dari database (sudah termasuk semua efek transaksi)
            saldo_database = account.balance
            
            # 2. Hitung total efek dari SEMUA jurnal (umum + penyesuaian)
            semua_detail = JournalDetail.query.filter_by(account_id=account.id).all()
            
            total_efek_jurnal = 0
            for detail in semua_detail:
                if account.category in ['asset', 'expense']:
                    # Asset/Expense: Debit (+), Credit (-)
                    total_efek_jurnal += detail.debit - detail.credit
                else:
                    # Liability/Equity/Revenue: Credit (+), Debit (-)
                    total_efek_jurnal += detail.credit - detail.debit
            
            # 3. Saldo awal murni = Saldo database - efek semua jurnal
            # Karena saldo database sudah termasuk efek jurnal, kita KURANGI efeknya
            # untuk mendapatkan saldo awal asli
            saldo_awal_murni = saldo_database - total_efek_jurnal
            
            print(f"🔍 [SALDO AWAL MURNI] {account.code} - {account.name}:")
            print(f"   Saldo database: {saldo_database:,.0f}")
            print(f"   Total efek jurnal: {total_efek_jurnal:,.0f}")
            print(f"   Saldo awal murni: {saldo_awal_murni:,.0f}")
            
            # Skip akun yang saldo 0
            if abs(saldo_awal_murni) < 0.01:
                continue

            # Tentukan debit/credit berdasarkan kategori akun
            if account.category in ['asset']:
                # Asset: Saldo positif = Debit
                if saldo_awal_murni >= 0:
                    debit = saldo_awal_murni
                    credit = 0
                else:
                    debit = 0
                    credit = abs(saldo_awal_murni)
            else:
                # Liability & Equity: Saldo positif = Credit
                if saldo_awal_murni >= 0:
                    debit = 0
                    credit = saldo_awal_murni
                else:
                    debit = abs(saldo_awal_murni)
                    credit = 0

            total_debit += debit
            total_credit += credit

            saldo_html += f'''
            <tr>
                <td>{account.name}</td>
                <td>{account.code}</td>
                <td class="debit">{"Rp {0:,.0f}".format(debit) if debit > 0 else ""}</td>
                <td class="credit">{"Rp {0:,.0f}".format(credit) if credit > 0 else ""}</td>
            </tr>
            '''

        is_balanced = abs(total_debit - total_credit) < 0.01

        saldo_html += f'''
        <tr style="font-weight: bold; border-top: 2px solid var(--primary); background: rgba(56, 161, 105, 0.1);">
            <td colspan="2">TOTAL</td>
            <td class="debit">Rp {total_debit:,.0f}</td>
            <td class="credit">Rp {total_credit:,.0f}</td>
        </tr>
        <tr style="background: rgba(56, 161, 105, 0.2);">
            <td colspan="4" style="text-align: center; color: {'var(--success)' if is_balanced else 'var(--error)'}; font-weight: bold;">
                {'✅ SALDO AWAL SEIMBANG' if is_balanced else '❌ SALDO AWAL TIDAK SEIMBANG'}
            </td>
        </tr>
        '''

        # Tambahkan info tentang akun nominal
        saldo_html += f'''
        <tr style="background: rgba(156, 163, 175, 0.1);">
            <td colspan="4" style="text-align: center; color: #6B7280; font-size: 0.9rem; padding: 0.5rem;">
                <i class="fas fa-info-circle"></i> 
                <strong>Catatan:</strong> 
                Saldo awal murni dari database, TANPA efek jurnal umum & penyesuaian. 
                Pendapatan & Beban tidak memiliki saldo awal (selalu 0).
            </td>
        </tr>
        '''

        return saldo_html

    except Exception as e:
        print(f"❌ Error generating saldo awal murni: {e}")
        import traceback
        traceback.print_exc()
        return '<tr><td colspan="4">Error loading saldo awal murni</td></tr>'

def get_equity_change_statement():
    """Generate Laporan Perubahan Ekuitas HTML"""
    try:
        # Get equity accounts
        equity_accounts = Account.query.filter_by(category='equity').all()
        modal_account = Account.query.filter_by(type='modal').first()

        # Get revenue and expense accounts for net income calculation
        revenue_accounts = Account.query.filter_by(category='revenue').all()
        expense_accounts = Account.query.filter_by(category='expense').all()

        # Calculate net income/loss
        total_revenue = sum(acc.balance for acc in revenue_accounts)
        total_expenses = sum(acc.balance for acc in expense_accounts)
        net_income = total_revenue - total_expenses

        # Calculate beginning equity (modal awal)
        beginning_equity = sum(acc.balance for acc in equity_accounts)

        # Calculate ending equity (modal akhir = modal awal + laba/rugi)
        ending_equity = beginning_equity + net_income

        # Format untuk modal awal dan akhir
        beginning_equity_formatted = f"Rp {beginning_equity:,.0f}" if beginning_equity != 0 else "Rp 0"
        ending_equity_formatted = f"Rp {ending_equity:,.0f}" if ending_equity != 0 else "Rp 0"
        net_income_formatted = f"Rp {abs(net_income):,.0f}" if net_income != 0 else "Rp 0"

        return f'''
        <table class="table">
            <thead>
                <tr>
                    <th>Keterangan</th>
                    <th>Jumlah</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Modal Awal Periode</strong></td>
                    <td class="credit">{beginning_equity_formatted}</td>
                </tr>
                <tr>
                    <td style="padding-left: 2rem;">
                        <strong>{'Laba Bersih' if net_income >= 0 else 'Rugi Bersih'} Periode</strong>
                    </td>
                    <td class="{'credit' if net_income >= 0 else 'debit'}">
                        {'+' if net_income >= 0 else '-'} {net_income_formatted}
                    </td>
                </tr>
                <tr style="font-weight: bold; border-top: 2px solid var(--primary); background: rgba(56, 161, 105, 0.1);">
                    <td><strong>Modal Akhir Periode</strong></td>
                    <td class="credit"><strong>{ending_equity_formatted}</strong></td>
                </tr>
            </tbody>
        </table>

        <div style="margin-top: 1rem; padding: 1rem; background: rgba(49, 130, 206, 0.05); border-radius: var(--border-radius);">
            <h5 style="color: var(--primary); margin-bottom: 0.5rem;">Keterangan:</h5>
            <p style="margin: 0.25rem 0; font-size: 0.9rem;">
                <strong>Modal Akhir = Modal Awal + Laba Bersih (atau - Rugi Bersih)</strong>
            </p>
            <p style="margin: 0.25rem 0; font-size: 0.9rem;">
                {ending_equity_formatted} = {beginning_equity_formatted} {'+' if net_income >= 0 else ''} {net_income_formatted}
            </p>
        </div>
        '''
    except Exception as e:
        print(f"Error generating equity change statement: {e}")
        return '<p>Error loading equity change statement</p>'

# ===== FUNGSI JURNAL PENYESUAIAN BARU =====
def get_account_balance_before_adjustment(account_type):
    """Mendapatkan saldo akun dari NERACA SALDO SEBELUM PENYESUAIAN"""
    try:
        account = Account.query.filter_by(type=account_type).first()
        if not account:
            return 0

        # ✅ PERBAIKAN: Mulai dari saldo database
        saldo_buku_besar = account.balance  # Ambil dari database

        # KURANGI efek dari jurnal penyesuaian
        adjustment_details = JournalDetail.query.join(JournalEntry).filter(
            JournalDetail.account_id == account.id,
            JournalEntry.journal_type == 'adjustment'
        ).all()

        for detail in adjustment_details:
            if account.category in ['asset', 'expense']:
                # Asset/Expense: Debit menambah, Credit mengurangi
                saldo_buku_besar -= (detail.debit - detail.credit)
            else:
                # Liability/Equity/Revenue: Credit menambah, Debit mengurangi
                saldo_buku_besar -= (detail.credit - detail.debit)

        return saldo_buku_besar

    except Exception as e:
        print(f"Error getting balance before adjustment: {e}")
        return 0

def create_adjustment_journal(template_key, date, inputs):
    """Membuat jurnal penyesuaian berdasarkan template"""
    try:
        template = ADJUSTMENT_TEMPLATES[template_key]
        accounts_map = {}

        # Build accounts mapping
        for account in Account.query.all():
            accounts_map[account.type] = account

        entries = []
        amounts = {}

        # Hitung amount berdasarkan template - PERBAIKAN: gunakan saldo dari neraca sebelum penyesuaian
        if template_key == 'penyesuaian_perlengkapan':
            saldo_perlengkapan = get_account_balance_before_adjustment('perlengkapan')
            nilai_tersisa = float(inputs.get('nilai_tersisa', 0))
            beban = saldo_perlengkapan - nilai_tersisa

            if beban <= 0:
                raise ValueError("Nilai tersisa tidak boleh lebih besar dari saldo perlengkapan")

            amounts = {
                'beban_perlengkapan': beban,
                'perlengkapan': beban
            }

        elif template_key == 'penyusutan_aset_tetap':
            harga_perolehan = float(inputs.get('harga_perolehan', 0))
            nilai_residu = float(inputs.get('nilai_residu', 0))
            umur_manfaat = float(inputs.get('umur_manfaat', 1))

            if umur_manfaat <= 0:
                raise ValueError("Umur manfaat harus lebih dari 0")

            beban = (harga_perolehan - nilai_residu) / umur_manfaat

            amounts = {
                'beban_penyusutan': beban,
                'akumulasi_penyusutan': beban
            }

        elif template_key == 'penyesuaian_peralatan':
            saldo_peralatan = get_account_balance_before_adjustment('peralatan')
            nilai_tersisa = float(inputs.get('nilai_tersisa', 0))
            beban = saldo_peralatan - nilai_tersisa

            if beban <= 0:
                raise ValueError("Nilai tersisa tidak boleh lebih besar dari saldo peralatan")

            amounts = {
                'beban_peralatan': beban,
                'peralatan': beban
            }

        elif template_key == 'penyusutan_kendaraan':
            harga_perolehan = float(inputs.get('harga_perolehan', 0))
            nilai_residu = float(inputs.get('nilai_residu', 0))
            umur_manfaat = float(inputs.get('umur_manfaat', 1))

            if umur_manfaat <= 0:
                raise ValueError("Umur manfaat harus lebih dari 0")

            beban = (harga_perolehan - nilai_residu) / umur_manfaat

            amounts = {
                'beban_penyusutan': beban,
                'akumulasi_penyusutan': beban
            }

        # Buat entries untuk jurnal
        for template_entry in template['entries']:
            account_type = template_entry['account_type']

            if account_type in accounts_map:
                entry = {
                    'account_id': accounts_map[account_type].id,
                    'description': template_entry['description']
                }

                if template_entry['side'] == 'debit':
                    entry['debit'] = amounts.get(account_type, 0)
                    entry['credit'] = 0
                else:
                    entry['debit'] = 0
                    entry['credit'] = amounts.get(account_type, 0)

                entries.append(entry)

        # Create journal entry dengan type 'adjustment'
        journal = create_journal_entry(
            generate_unique_transaction_number('ADJ'),
            date,
            template['description'],
            'adjustment',
            entries
        )

        return journal

    except Exception as e:
        print(f"Error creating adjustment journal: {e}")
        raise e

# ==== TAMBAH FUNGSI KARTU PERSEDIAAN DI SINI ====
def update_inventory_card(product_id, transaction_type, transaction_number, quantity, unit_cost, date=None):
    """Update kartu persediaan untuk produk tertentu dengan harga cost tetap"""
    try:
        print(f"🔄 [INVENTORY] Memulai update inventory: Product {product_id}, Type: {transaction_type}, Qty: {quantity}")

        if date is None:
            date = datetime.now()

        # Harga cost tetap Rp 1,000
        COST_PRICE = 1000

        # Dapatkan balance terakhir
        last_entry = InventoryCard.query.filter_by(product_id=product_id).order_by(InventoryCard.date.desc()).first()

        if last_entry:
            balance_quantity = last_entry.balance_quantity
            balance_value = last_entry.balance_value
            print(f"📊 [INVENTORY] Last balance: Qty={balance_quantity}, Value={balance_value}")
        else:
            balance_quantity = 0
            balance_value = 0
            print(f"📊 [INVENTORY] No previous entries, starting from zero")

        # Hitung quantity dan value baru
        if transaction_type == 'penjualan':
            quantity_in = 0
            quantity_out = quantity
            balance_quantity -= quantity

            # Hitung HPP dengan harga cost tetap
            hpp_value = quantity * COST_PRICE
            balance_value -= hpp_value

            print(f"📉 [INVENTORY] Penjualan: -{quantity} units, HPP: {hpp_value}, new balance: {balance_quantity}")

        elif transaction_type == 'pembelian':
            quantity_in = quantity
            quantity_out = 0
            balance_quantity += quantity
            balance_value += quantity * COST_PRICE
            print(f"📈 [INVENTORY] Pembelian: +{quantity} units, new balance: {balance_quantity}")
        else:  # penyesuaian
            quantity_in = quantity if quantity > 0 else 0
            quantity_out = abs(quantity) if quantity < 0 else 0
            balance_quantity += quantity
            balance_value += quantity * COST_PRICE

        total_cost = quantity * COST_PRICE

        # Buat entry baru
        inventory_entry = InventoryCard(
            product_id=product_id,
            date=date,
            transaction_type=transaction_type,
            transaction_number=transaction_number,
            quantity_in=quantity_in,
            quantity_out=quantity_out,
            unit_cost=COST_PRICE,
            total_cost=total_cost,
            balance_quantity=balance_quantity,
            balance_value=balance_value
        )

        db.session.add(inventory_entry)

        # Update stock produk
        product = Product.query.get(product_id)
        if product:
            product.stock = balance_quantity
            print(f"📦 [INVENTORY] Stock produk diupdate: {product.name} = {balance_quantity}")

        db.session.commit()

        print(f"✅ [INVENTORY] Kartu persediaan updated: {transaction_type} {quantity} units for product {product_id}")
        return inventory_entry

    except Exception as e:
        print(f"❌ [INVENTORY] Error updating inventory card: {e}")
        db.session.rollback()
        return None

def calculate_hpp(product_id, quantity_sold):
    """Hitung HPP dengan metode FIFO"""
    try:
        # Dapatkan semua pembelian yang masih ada stok
        purchases = InventoryCard.query.filter_by(
            product_id=product_id,
            transaction_type='pembelian'
        ).filter(InventoryCard.balance_quantity > 0).order_by(InventoryCard.date).all()

        hpp_value = 0
        remaining_quantity = quantity_sold

        for purchase in purchases:
            if remaining_quantity <= 0:
                break

            available_quantity = purchase.balance_quantity
            quantity_to_use = min(remaining_quantity, available_quantity)

            hpp_value += quantity_to_use * purchase.unit_cost
            remaining_quantity -= quantity_to_use

        return hpp_value

    except Exception as e:
        print(f"Error calculating HPP: {e}")
        return 0

# ==== TAMBAH FUNGSI JURNAL PENUTUP DI SINI ====
def create_closing_entries():
    """Buat jurnal penutup yang benar sesuai prinsip akuntansi"""
    try:
        print("🔄 Membuat jurnal penutup yang benar...")
        
        # 1. Hitung total pendapatan dan beban (TANPA HPP)
        revenue_accounts = Account.query.filter_by(category='revenue').all()
        expense_accounts = Account.query.filter(
            Account.category == 'expense',
            Account.type != 'hpp'  # KECUALI HPP
        ).all()
        
        total_revenue = sum(acc.balance for acc in revenue_accounts)
        total_expenses = sum(acc.balance for acc in expense_accounts)
        net_income = total_revenue - total_expenses
        
        print(f"📊 Total Pendapatan: Rp {total_revenue:,.0f}")
        print(f"📊 Total Beban (tanpa HPP): Rp {total_expenses:,.0f}")
        print(f"📊 Laba/Rugi Bersih: Rp {net_income:,.0f}")
        
        if total_revenue == 0 and total_expenses == 0:
            print("ℹ️ Tidak ada akun nominal untuk ditutup")
            return None
        
        # Buat akun Ikhtisar Laba Rugi jika belum ada
        ikhtisar_account = Account.query.filter_by(type='ikhtisar_laba_rugi').first()
        if not ikhtisar_account:
            ikhtisar_account = Account(
                code='399',
                name='Ikhtisar Laba Rugi',
                type='ikhtisar_laba_rugi',
                category='temporary',
                balance=0
            )
            db.session.add(ikhtisar_account)
            db.session.flush()
            print("✅ Akun Ikhtisar Laba Rugi dibuat")
        
        # Buat jurnal penutup
        transaction_number = generate_unique_transaction_number('CLS')
        date = datetime.now()
        
        # ===== 1. TUTUP AKUN PENDAPATAN =====
        print("1️⃣ Menutup akun pendapatan...")
        if total_revenue > 0:
            entry1 = JournalEntry(
                transaction_number=f"{transaction_number}-1",
                date=date,
                description="Penutupan akun pendapatan ke Ikhtisar Laba Rugi",
                journal_type='closing_revenue'
            )
            db.session.add(entry1)
            db.session.flush()
            
            # Tutup setiap akun pendapatan
            for revenue_acc in revenue_accounts:
                if revenue_acc.balance > 0:
                    # Debit akun pendapatan (mengurangi ke nol)
                    detail1 = JournalDetail(
                        journal_id=entry1.id,
                        account_id=revenue_acc.id,
                        debit=revenue_acc.balance,
                        credit=0,
                        description=f'Penutupan akun pendapatan {revenue_acc.name}'
                    )
                    db.session.add(detail1)
                    
                    # Credit ikhtisar laba rugi
                    detail2 = JournalDetail(
                        journal_id=entry1.id,
                        account_id=ikhtisar_account.id,
                        debit=0,
                        credit=revenue_acc.balance,
                        description=f'Penerimaan pendapatan {revenue_acc.name}'
                    )
                    db.session.add(detail2)
                    
                    # Update saldo pendapatan jadi 0
                    revenue_acc.balance = 0
                    
                    print(f"   ✅ Pendapatan {revenue_acc.name}: Rp {revenue_acc.balance:,.0f} ditutup")
            
            db.session.commit()
            print("✅ Semua akun pendapatan ditutup")
        
        # ===== 2. TUTUP AKUN BEBAN (TANPA HPP) =====
        print("2️⃣ Menutup akun beban (tanpa HPP)...")
        if total_expenses > 0:
            entry2 = JournalEntry(
                transaction_number=f"{transaction_number}-2",
                date=date,
                description="Penutupan akun beban ke Ikhtisar Laba Rugi",
                journal_type='closing_expense'
            )
            db.session.add(entry2)
            db.session.flush()
            
            # Tutup setiap akun beban (KECUALI HPP)
            for expense_acc in expense_accounts:
                if expense_acc.balance > 0 and expense_acc.type != 'hpp':
                    # Debit ikhtisar laba rugi
                    detail1 = JournalDetail(
                        journal_id=entry2.id,
                        account_id=ikhtisar_account.id,
                        debit=expense_acc.balance,
                        credit=0,
                        description=f'Beban {expense_acc.name}'
                    )
                    db.session.add(detail1)
                    
                    # Credit akun beban (mengurangi ke nol)
                    detail2 = JournalDetail(
                        journal_id=entry2.id,
                        account_id=expense_acc.id,
                        debit=0,
                        credit=expense_acc.balance,
                        description=f'Penutupan akun beban {expense_acc.name}'
                    )
                    db.session.add(detail2)
                    
                    # Update saldo beban jadi 0
                    expense_acc.balance = 0
                    
                    print(f"   ✅ Beban {expense_acc.name}: Rp {expense_acc.balance:,.0f} ditutup")
                elif expense_acc.type == 'hpp' and expense_acc.balance > 0:
                    print(f"   ⚠️ HPP {expense_acc.name}: Rp {expense_acc.balance:,.0f} TIDAK ditutup (sudah 0 dari penyesuaian)")
            
            db.session.commit()
            print("✅ Semua akun beban (tanpa HPP) ditutup")
        
        # ===== 3. TUTUP IKHTISAR LABA RUGI KE MODAL =====
        print("3️⃣ Menutup Ikhtisar Laba Rugi ke Modal...")
        
        # Hitung saldo akhir ikhtisar
        ikhtisar_debit = sum(d.debit for d in ikhtisar_account.journal_details)
        ikhtisar_credit = sum(d.credit for d in ikhtisar_account.journal_details)
        ikhtisar_balance = ikhtisar_credit - ikhtisar_debit  # Credit - Debit
        
        print(f"   Saldo Ikhtisar: Rp {ikhtisar_balance:,.0f}")
        
        # Dapatkan akun modal
        modal_account = Account.query.filter_by(type='modal').first()
        if not modal_account:
            modal_account = Account(
                code='301',
                name='Modal Pemilik',
                type='modal',
                category='equity',
                balance=0
            )
            db.session.add(modal_account)
            db.session.flush()
            print("✅ Akun Modal dibuat")
        
        entry3 = JournalEntry(
            transaction_number=f"{transaction_number}-3",
            date=date,
            description=f"Pemindahan {'laba' if ikhtisar_balance >= 0 else 'rugi'} ke Modal",
            journal_type='closing_ikhtisar'
        )
        db.session.add(entry3)
        db.session.flush()
        
        if ikhtisar_balance >= 0:  # LABA
            # Laba: Debit Ikhtisar, Credit Modal
            detail1 = JournalDetail(
                journal_id=entry3.id,
                account_id=ikhtisar_account.id,
                debit=ikhtisar_balance,
                credit=0,
                description='Pemindahan laba ke modal'
            )
            detail2 = JournalDetail(
                journal_id=entry3.id,
                account_id=modal_account.id,
                debit=0,
                credit=ikhtisar_balance,
                description='Penambahan modal dari laba'
            )
            
            # Update saldo modal
            modal_account.balance += ikhtisar_balance
            
            print(f"   ✅ Laba Rp {ikhtisar_balance:,.0f} ditambahkan ke modal")
        else:  # RUGI
            # Rugi: Debit Modal, Credit Ikhtisar
            rugi_amount = abs(ikhtisar_balance)
            
            detail1 = JournalDetail(
                journal_id=entry3.id,
                account_id=modal_account.id,
                debit=rugi_amount,
                credit=0,
                description='Pengurangan modal karena rugi'
            )
            detail2 = JournalDetail(
                journal_id=entry3.id,
                account_id=ikhtisar_account.id,
                debit=0,
                credit=rugi_amount,
                description='Pemindahan rugi dari ikhtisar'
            )
            
            # Update saldo modal
            modal_account.balance -= rugi_amount
            
            print(f"   ✅ Rugi Rp {rugi_amount:,.0f} dikurangi dari modal")
        
        db.session.add(detail1)
        db.session.add(detail2)
        
        # ===== 4. TUTUP AKUN PRIVE (jika ada) =====
        print("4️⃣ Menutup akun prive...")
        # Cari akun prive
        prive_accounts = Account.query.filter_by(type='prive').all()
        
        if prive_accounts:
            entry4 = JournalEntry(
                transaction_number=f"{transaction_number}-4",
                date=date,
                description="Penutupan akun prive ke Modal",
                journal_type='closing_prive'
            )
            db.session.add(entry4)
            db.session.flush()
            
            for prive_acc in prive_accounts:
                if prive_acc.balance > 0:
                    # Prive normal balance di debit, jadi untuk menutup:
                    # Debit Modal, Credit Prive
                    
                    detail1 = JournalDetail(
                        journal_id=entry4.id,
                        account_id=modal_account.id,
                        debit=prive_acc.balance,
                        credit=0,
                        description=f'Pengurangan modal untuk prive {prive_acc.name}'
                    )
                    detail2 = JournalDetail(
                        journal_id=entry4.id,
                        account_id=prive_acc.id,
                        debit=0,
                        credit=prive_acc.balance,
                        description='Penutupan akun prive'
                    )
                    
                    db.session.add(detail1)
                    db.session.add(detail2)
                    
                    # Update saldo modal dan prive
                    modal_account.balance -= prive_acc.balance
                    prive_acc.balance = 0
                    
                    print(f"   ✅ Prive {prive_acc.name}: Rp {prive_acc.balance:,.0f} ditutup")
        
        # ===== COMMIT SEMUA PERUBAHAN =====
        db.session.commit()
        
        print("✅ JURNAL PENUTUP SELESAI DIBUAT")
        print(f"📋 Ringkasan:")
        print(f"   - Pendapatan ditutup: Rp {total_revenue:,.0f}")
        print(f"   - Beban ditutup: Rp {total_expenses:,.0f}")
        print(f"   - HPP TIDAK DITUTUP (sudah 0 dari penyesuaian)")
        print(f"   - {'Laba' if net_income >= 0 else 'Rugi'} bersih: Rp {abs(net_income):,.0f}")
        print(f"   - Saldo Modal akhir: Rp {modal_account.balance:,.0f}")
        
        # BUAT CLOSING ENTRY UNTUK TRACKING
        closing_entry = ClosingEntry(
            transaction_number=transaction_number,
            date=date,
            description=f"Jurnal Penutup Periode - {'Laba' if net_income >= 0 else 'Rugi'} Rp {abs(net_income):,.0f}"
        )
        db.session.add(closing_entry)
        
        # Simpan detail ke ClosingDetail untuk record
        for journal_entry in [entry1, entry2, entry3, entry4]:
            if journal_entry:
                for detail in journal_entry.journal_details:
                    closing_detail = ClosingDetail(
                        closing_id=closing_entry.id,
                        account_id=detail.account_id,
                        debit=detail.debit,
                        credit=detail.credit,
                        description=detail.description
                    )
                    db.session.add(closing_detail)
        
        db.session.commit()
        
        return closing_entry
        
    except Exception as e:
        print(f"❌ Error creating closing entries: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return None
        
def verify_closing_entries():
    """Verifikasi apakah jurnal penutup sudah benar"""
    try:
        print("🔍 Verifikasi Jurnal Penutup...")
        
        # Cek pendapatan - HARUS 0
        revenue_accounts = Account.query.filter_by(category='revenue').all()
        total_revenue = sum(acc.balance for acc in revenue_accounts)
        
        # Cek beban (tanpa HPP) - HARUS 0
        expense_accounts = Account.query.filter(
            Account.category == 'expense',
            Account.type != 'hpp'
        ).all()
        total_expenses = sum(acc.balance for acc in expense_accounts)
        
        # Cek HPP - BOLEH TIDAK 0 (karena penyesuaian)
        hpp_accounts = Account.query.filter_by(type='hpp').all()
        total_hpp = sum(acc.balance for acc in hpp_accounts)
        
        print(f"📊 Status Akhir:")
        print(f"   Total Pendapatan: Rp {total_revenue:,.0f} {'✅ NOL' if total_revenue == 0 else '❌ BELUM NOL'}")
        print(f"   Total Beban (tanpa HPP): Rp {total_expenses:,.0f} {'✅ NOL' if total_expenses == 0 else '❌ BELUM NOL'}")
        print(f"   Total HPP: Rp {total_hpp:,.0f} {'⚠️ BOLEH TIDAK NOL' if total_hpp != 0 else '✅ OK'}")
        
        if total_revenue == 0 and total_expenses == 0:
            print("✅ Jurnal penutup sudah benar!")
            return True
        else:
            print("⚠️ Jurnal penutup belum sempurna")
            return False
            
    except Exception as e:
        print(f"Error verifying closing entries: {e}")
        return False

        # ===== 2. TUTUP AKUN BEBAN =====
        print("2️⃣ Menutup akun beban...")
        if total_expenses > 0:
            entry2 = JournalEntry(
                transaction_number=f"{transaction_number}-2",
                date=date,
                description="Penutupan akun beban ke Ikhtisar Laba Rugi",
                journal_type='closing_expense'
            )
            db.session.add(entry2)
            db.session.flush()
            
            # Tutup setiap akun beban
            for expense_acc in expense_accounts:
                if expense_acc.balance > 0:
                    # Debit ikhtisar laba rugi
                    detail1 = JournalDetail(
                        journal_id=entry2.id,
                        account_id=ikhtisar_account.id,
                        debit=expense_acc.balance,
                        credit=0,
                        description=f'Beban {expense_acc.name}'
                    )
                    db.session.add(detail1)
                    
                    # Credit akun beban (mengurangi ke nol)
                    detail2 = JournalDetail(
                        journal_id=entry2.id,
                        account_id=expense_acc.id,
                        debit=0,
                        credit=expense_acc.balance,
                        description=f'Penutupan akun beban {expense_acc.name}'
                    )
                    db.session.add(detail2)
                    
                    # Update saldo beban jadi 0
                    expense_acc.balance = 0
                    
                    print(f"   ✅ Beban {expense_acc.name}: Rp {expense_acc.balance:,.0f} ditutup")
            
            db.session.commit()
            print("✅ Semua akun beban ditutup")
        
        # ===== 3. TUTUP IKHTISAR LABA RUGI KE MODAL =====
        print("3️⃣ Menutup Ikhtisar Laba Rugi ke Modal...")
        
        # Hitung saldo akhir ikhtisar
        ikhtisar_debit = sum(d.debit for d in ikhtisar_account.journal_details)
        ikhtisar_credit = sum(d.credit for d in ikhtisar_account.journal_details)
        ikhtisar_balance = ikhtisar_credit - ikhtisar_debit  # Credit - Debit
        
        print(f"   Saldo Ikhtisar: Rp {ikhtisar_balance:,.0f}")
        
        # Dapatkan akun modal
        modal_account = Account.query.filter_by(type='modal').first()
        if not modal_account:
            modal_account = Account(
                code='301',
                name='Modal Pemilik',
                type='modal',
                category='equity',
                balance=0
            )
            db.session.add(modal_account)
            db.session.flush()
            print("✅ Akun Modal dibuat")
        
        entry3 = JournalEntry(
            transaction_number=f"{transaction_number}-3",
            date=date,
            description=f"Pemindahan {'laba' if ikhtisar_balance >= 0 else 'rugi'} ke Modal",
            journal_type='closing_ikhtisar'
        )
        db.session.add(entry3)
        db.session.flush()
        
        if ikhtisar_balance >= 0:  # LABA
            # Laba: Debit Ikhtisar, Credit Modal
            detail1 = JournalDetail(
                journal_id=entry3.id,
                account_id=ikhtisar_account.id,
                debit=ikhtisar_balance,
                credit=0,
                description='Pemindahan laba ke modal'
            )
            detail2 = JournalDetail(
                journal_id=entry3.id,
                account_id=modal_account.id,
                debit=0,
                credit=ikhtisar_balance,
                description='Penambahan modal dari laba'
            )
            
            # Update saldo modal
            modal_account.balance += ikhtisar_balance
            
            print(f"   ✅ Laba Rp {ikhtisar_balance:,.0f} ditambahkan ke modal")
        else:  # RUGI
            # Rugi: Debit Modal, Credit Ikhtisar
            rugi_amount = abs(ikhtisar_balance)
            
            detail1 = JournalDetail(
                journal_id=entry3.id,
                account_id=modal_account.id,
                debit=rugi_amount,
                credit=0,
                description='Pengurangan modal karena rugi'
            )
            detail2 = JournalDetail(
                journal_id=entry3.id,
                account_id=ikhtisar_account.id,
                debit=0,
                credit=rugi_amount,
                description='Pemindahan rugi dari ikhtisar'
            )
            
            # Update saldo modal
            modal_account.balance -= rugi_amount
            
            print(f"   ✅ Rugi Rp {rugi_amount:,.0f} dikurangi dari modal")
        
        db.session.add(detail1)
        db.session.add(detail2)
        
        # ===== 4. TUTUP AKUN PRIVE (jika ada) =====
        print("4️⃣ Menutup akun prive...")
        # Cari akun prive
        prive_accounts = Account.query.filter_by(type='prive').all()
        
        if prive_accounts:
            entry4 = JournalEntry(
                transaction_number=f"{transaction_number}-4",
                date=date,
                description="Penutupan akun prive ke Modal",
                journal_type='closing_prive'
            )
            db.session.add(entry4)
            db.session.flush()
            
            for prive_acc in prive_accounts:
                if prive_acc.balance > 0:
                    # Prive normal balance di debit, jadi untuk menutup:
                    # Debit Modal, Credit Prive
                    
                    detail1 = JournalDetail(
                        journal_id=entry4.id,
                        account_id=modal_account.id,
                        debit=prive_acc.balance,
                        credit=0,
                        description=f'Pengurangan modal untuk prive {prive_acc.name}'
                    )
                    detail2 = JournalDetail(
                        journal_id=entry4.id,
                        account_id=prive_acc.id,
                        debit=0,
                        credit=prive_acc.balance,
                        description='Penutupan akun prive'
                    )
                    
                    db.session.add(detail1)
                    db.session.add(detail2)
                    
                    # Update saldo modal dan prive
                    modal_account.balance -= prive_acc.balance
                    prive_acc.balance = 0
                    
                    print(f"   ✅ Prive {prive_acc.name}: Rp {prive_acc.balance:,.0f} ditutup")
        
        # ===== COMMIT SEMUA PERUBAHAN =====
        db.session.commit()
        
        # Buat closing entry untuk tracking
        closing_entry = ClosingEntry(
            transaction_number=transaction_number,
            date=date,
            description=f"Jurnal Penutup Periode - {'Laba' if net_income >= 0 else 'Rugi'} Rp {abs(net_income):,.0f}"
        )
        db.session.add(closing_entry)
        
        # Simpan detail ke ClosingDetail untuk record
        for journal_entry in [entry1, entry2, entry3, entry4]:
            if journal_entry:
                for detail in journal_entry.journal_details:
                    closing_detail = ClosingDetail(
                        closing_id=closing_entry.id,
                        account_id=detail.account_id,
                        debit=detail.debit,
                        credit=detail.credit,
                        description=detail.description
                    )
                    db.session.add(closing_detail)
        
        db.session.commit()
        
        print("✅ JURNAL PENUTUP SELESAI DIBUAT")
        print(f"📋 Ringkasan:")
        print(f"   - Pendapatan ditutup: Rp {total_revenue:,.0f}")
        print(f"   - Beban ditutup: Rp {total_expenses:,.0f}")
        print(f"   - {'Laba' if net_income >= 0 else 'Rugi'} bersih: Rp {abs(net_income):,.0f}")
        print(f"   - Saldo Modal akhir: Rp {modal_account.balance:,.0f}")
        
        return closing_entry
        
    except Exception as e:
        print(f"❌ Error creating closing entries: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return None

def get_post_closing_trial_balance():
    """Generate Neraca Saldo Setelah Penutupan (Post-Closing Trial Balance) YANG BENAR"""
    try:
        # ===== 1. HITUNG SALDO MODAL AKHIR =====
        # Dapatkan akun modal
        modal_account = Account.query.filter_by(type='modal').first()
        
        # Hitung laba/rugi dari akun pendapatan dan beban
        revenue_accounts = Account.query.filter_by(category='revenue').all()
        expense_accounts = Account.query.filter_by(category='expense').all()
        
        total_revenue = sum(acc.balance for acc in revenue_accounts)
        total_expenses = sum(acc.balance for acc in expense_accounts)
        net_income = total_revenue - total_expenses
        
        # Dapatkan akun prive
        prive_accounts = Account.query.filter_by(type='prive').all()
        total_prive = sum(acc.balance for acc in prive_accounts)
        
        # Hitung modal akhir
        # Modal Akhir = Modal Awal + Laba Bersih - Prive
        modal_awal = modal_account.balance if modal_account else 0
        modal_akhir = modal_awal + net_income - total_prive
        
        # ===== 2. TENTUKAN LABA ATAU RUGI =====
        laba_rugi_text = "Laba" if net_income >= 0 else "Rugi"
        laba_rugi_color = "success" if net_income >= 0 else "error"
        
        # ===== 3. FILTER AKUN REAL SAJA =====
        # Akun yang muncul di post-closing trial balance:
        # - Asset (Aset) - TETAP muncul
        # - Liability (Kewajiban) - TETAP muncul  
        # - Equity (Modal) - HANYA dengan saldo akhir yang sudah dihitung
        # - TIDAK termasuk: Pendapatan, Beban, Prive, Ikhtisar Laba Rugi (harus 0)
        
        # Get REAL accounts
        real_accounts = Account.query.filter(
            Account.category.in_(['asset', 'liability', 'equity'])
        ).order_by(Account.code).all()
        
        # ===== 3. BUAT TABLE HTML =====
        table_html = f'''
        <div class="card">
            <h4 style="color: var(--primary); margin-bottom: 1.5rem;">
                <i class="fas fa-balance-scale"></i> Neraca Saldo Setelah Penutupan (Post-Closing Trial Balance)
            </h4>
            
            <div style="background: var(--ocean-light); padding: 1.5rem; border-radius: var(--border-radius); margin-bottom: 1.5rem;">
                <h5 style="color: var(--primary); margin-bottom: 0.5rem;">
                    <i class="fas fa-info-circle"></i> Informasi Modal:
                </h5>
                <table style="width: 100%; font-size: 0.9rem;">
                    <tr>
                        <td>Modal Awal</td>
                        <td style="text-align: right;">Rp {modal_awal:,.0f}</td>
                    </tr>
                    <tr>
                        <td>{laba_rugi_text} Bersih Periode</td>
                        <td style="text-align: right; color: var(--{laba_rugi_color});">
                            {'+' if net_income >= 0 else '-'} Rp {abs(net_income):,.0f}
                        </td>
                    </tr>
        '''
        
        if total_prive > 0:
            table_html += f'''
                    <tr>
                        <td>Prive</td>
                        <td style="text-align: right; color: var(--error);">- Rp {total_prive:,.0f}</td>
                    </tr>
            '''
            
        table_html += f'''
                    <tr style="font-weight: bold; border-top: 1px solid var(--primary);">
                        <td>Modal Akhir (Digunakan di Neraca)</td>
                        <td style="text-align: right; color: var(--primary); font-size: 1.1rem;">
                            Rp {modal_akhir:,.0f}
                        </td>
                    </tr>
                </table>
            </div>
            
            <div style="overflow-x: auto;">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Kode Akun</th>
                            <th>Nama Akun</th>
                            <th>Debit</th>
                            <th>Kredit</th>
                        </tr>
                    </thead>
                    <tbody>
        '''
        
        total_debit = 0
        total_credit = 0
        
        for account in real_accounts:
            # Tentukan saldo yang akan ditampilkan
            if account.type == 'modal':
                # Gunakan saldo modal akhir yang sudah dihitung
                balance_to_show = modal_akhir
            else:
                # Gunakan saldo normal dari database
                balance_to_show = account.balance
            
            # Skip akun dengan saldo 0
            if balance_to_show == 0:
                continue
            
            # Tentukan debit/credit
            if account.category == 'asset':
                # Aset: saldo positif di debit
                if balance_to_show >= 0:
                    debit = balance_to_show
                    credit = 0
                else:
                    debit = 0
                    credit = abs(balance_to_show)
            else:
                # Kewajiban & Modal: saldo positif di credit
                if balance_to_show >= 0:
                    debit = 0
                    credit = balance_to_show
                else:
                    debit = abs(balance_to_show)
                    credit = 0
            
            total_debit += debit
            total_credit += credit
            
            # Tentukan kategori untuk styling
            if account.category == 'asset':
                account_category = 'ASET'
                category_class = 'success'
            elif account.category == 'liability':
                account_category = 'KEWAJIBAN'
                category_class = 'error'
            else:  # equity
                account_category = 'MODAL'
                category_class = 'primary'
            
            table_html += f'''
            <tr>
                <td><strong>{account.code}</strong></td>
                <td>
                    {account.name}
                    <br>
                    <small style="color: var(--{category_class}); font-size: 0.8rem; background: rgba(var(--{category_class}-rgb, 0, 0, 0), 0.1); padding: 2px 8px; border-radius: 12px;">
                        {account_category}
                    </small>
                </td>
                <td class="debit">{"Rp {0:,.0f}".format(debit) if debit > 0 else ""}</td>
                <td class="credit">{"Rp {0:,.0f}".format(credit) if credit > 0 else ""}</td>
            </tr>
            '''
        
        # Hitung apakah seimbang
        is_balanced = abs(total_debit - total_credit) < 0.01
        
        table_html += f'''
                    </tbody>
                    <tfoot>
                        <tr style="font-weight: bold; border-top: 2px solid var(--primary); background: rgba(56, 161, 105, 0.1);">
                            <td colspan="2">TOTAL</td>
                            <td class="debit">Rp {total_debit:,.0f}</td>
                            <td class="credit">Rp {total_credit:,.0f}</td>
                        </tr>
                        <tr style="background: {'rgba(56, 161, 105, 0.2)' if is_balanced else 'rgba(229, 62, 62, 0.2)'};">
                            <td colspan="4" style="text-align: center; color: {'var(--success)' if is_balanced else 'var(--error)'}; font-weight: bold;">
                                {'✅ NERACA SALDO SETELAH PENUTUPAN SEIMBANG' if is_balanced else '❌ NERACA SALDO SETELAH PENUTUPAN TIDAK SEIMBANG'}
                            </td>
                        </tr>
                    </tfoot>
                </table>
            </div>
            
            <!-- Verification Section -->
            <div style="margin-top: 2rem; padding: 1.5rem; background: {'rgba(56, 161, 105, 0.1)' if is_balanced else 'rgba(229, 62, 62, 0.1)'}; border-radius: var(--border-radius);">
                <h5 style="color: {'var(--success)' if is_balanced else 'var(--error)'}; margin-bottom: 1rem;">
                    <i class="fas fa-{'check-circle' if is_balanced else 'exclamation-circle'}"></i>
                    Verifikasi Keseimbangan
                </h5>
                
                <div style="font-size: 0.9rem;">
                    <p><strong>Persamaan Akuntansi:</strong></p>
                    <p style="margin: 0.5rem 0;">Aset = Kewajiban + Modal</p>
                    <p style="margin: 0.5rem 0; font-family: monospace;">
                        {total_debit:,.0f} = {total_credit:,.0f}
                    </p>
                    
                    {f'''
                    <div style="margin-top: 1rem; padding: 1rem; background: rgba(229, 62, 62, 0.2); border-radius: var(--border-radius);">
                        <p style="margin: 0; color: var(--error);">
                            <strong>Selisih:</strong> Rp {abs(total_debit - total_credit):,.0f}
                        </p>
                        <p style="margin: 0.5rem 0 0 0; color: var(--error); font-size: 0.85rem;">
                            <i class="fas fa-lightbulb"></i> Pastikan jurnal penutup sudah dibuat dengan benar!
                        </p>
                    </div>
                    ''' if not is_balanced else ''}
                </div>
            </div>
        </div>
        '''
        
        return table_html
        
    except Exception as e:
        print(f"Error generating post-closing trial balance: {e}")
        import traceback
        traceback.print_exc()
        return f'<div class="card"><p>Error loading post-closing trial balance: {str(e)}</p></div>'

def get_proper_closing_entries_html():
    """Generate HTML untuk jurnal penutup dengan format baru - DESKRIPSI DI HEADER"""
    try:
        # CARI DARI JournalEntry, bukan ClosingEntry
        closing_journals = JournalEntry.query.filter(
            JournalEntry.journal_type.in_(['closing_revenue', 'closing_expense', 'closing_ikhtisar', 'closing_prive'])
        ).order_by(JournalEntry.date.desc()).all()

        if not closing_journals:
            return '''
            <div class="card">
                <h4 style="color: var(--primary);">
                    <i class="fas fa-door-closed"></i> Belum Ada Jurnal Penutup
                </h4>
                <p style="color: #6B7280; margin-bottom: 1rem;">
                    Jurnal penutup akan dibuat secara otomatis di akhir periode akuntansi untuk menutup akun nominal.
                </p>
                
                <div style="background: var(--ocean-light); padding: 1.5rem; border-radius: var(--border-radius); margin: 1rem 0;">
                    <h5 style="color: var(--primary); margin-bottom: 0.5rem;">
                        <i class="fas fa-info-circle"></i> Apa itu Jurnal Penutup?
                    </h5>
                    <p style="margin-bottom: 0.5rem; font-size: 0.9rem;">
                        Jurnal penutup adalah jurnal yang dibuat di akhir periode akuntansi untuk:
                    </p>
                    <ol style="margin: 0; padding-left: 1.2rem; font-size: 0.9rem;">
                        <li>Menutup semua akun pendapatan</li>
                        <li>Menutup semua akun beban</li>
                        <li>Memindahkan saldo ke Ikhtisar Laba Rugi</li>
                        <li>Memindahkan laba/rugi ke akun Modal</li>
                        <li>Menutup akun Prive (jika ada)</li>
                    </ol>
                </div>
                
                <div class="grid grid-2" style="margin-top: 1.5rem;">
                    <div style="padding: 1rem; background: rgba(56, 161, 105, 0.1); border-radius: var(--border-radius);">
                        <h6 style="color: var(--success); margin-bottom: 0.5rem;">
                            <i class="fas fa-calculator"></i> Langkah-langkah:
                        </h6>
                        <ol style="margin: 0; padding-left: 1.2rem; font-size: 0.85rem;">
                            <li>Pendapatan → Ikhtisar Laba Rugi</li>
                            <li>Beban → Ikhtisar Laba Rugi</li>
                            <li>Ikhtisar Laba Rugi → Modal</li>
                            <li>Prive → Modal</li>
                        </ol>
                    </div>
                    
                    <div style="padding: 1rem; background: rgba(49, 130, 206, 0.1); border-radius: var(--border-radius);">
                        <h6 style="color: var(--primary); margin-bottom: 0.5rem;">
                            <i class="fas fa-check-circle"></i> Hasil Akhir:
                        </h6>
                        <ul style="margin: 0; padding-left: 1.2rem; font-size: 0.85rem;">
                            <li>Pendapatan = 0</li>
                            <li>Beban = 0</li>
                            <li>Modal = Modal Awal + Laba - Rugi</li>
                        </ul>
                    </div>
                </div>
            </div>
            '''

        # Group by transaction number
        transactions = {}
        for journal in closing_journals:
            # Ekstrak base transaction number (tanpa -1, -2, dll)
            base_number = journal.transaction_number.split('-')[0]
            if base_number not in transactions:
                transactions[base_number] = []
            transactions[base_number].append(journal)

        table_html = f'''
        <div class="card">
            <h4 style="color: var(--primary); margin-bottom: 1.5rem;">
                <i class="fas fa-door-closed"></i> Jurnal Penutup
                <span style="font-size: 0.9rem; color: #6B7280; font-weight: normal; margin-left: 1rem;">
                    ({len(closing_journals)} entri penutup)
                </span>
            </h4>
            
            <div style="overflow-x: auto;">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Tanggal</th>
                            <th>No. Transaksi</th>
                            <th>Akun</th>
                            <th>Ref</th>
                            <th>Debit</th>
                            <th>Kredit</th>
                        </tr>
                    </thead>
                    <tbody>
        '''

        for base_number, journals in transactions.items():
            # Sort journals by type untuk urutan yang benar
            type_order = ['closing_revenue', 'closing_expense', 'closing_ikhtisar', 'closing_prive']
            journals.sort(key=lambda x: type_order.index(x.journal_type) if x.journal_type in type_order else 99)
            
            # Group by journal untuk menghindari duplikasi header
            grouped_journals = {}
            for journal in journals:
                if journal.id not in grouped_journals:
                    grouped_journals[journal.id] = journal
            
            for journal in grouped_journals.values():
                # Add journal header - DESKRIPSI DI HEADER
                table_html += f'''
                <tr style="background: rgba(180, 81, 35, 0.1); font-weight: bold;">
                    <td>{journal.date.strftime('%d/%m/%Y %H:%M')}</td>
                    <td>{journal.transaction_number}</td>
                    <td colspan="4" style="color: var(--primary);">
                        {journal.description}
                    </td>
                </tr>
                '''
                
                # Add account details - TANPA DESKRIPSI
                for detail in journal.journal_details:
                    table_html += f'''
                    <tr>
                        <td style="border-left: 3px solid rgba(180, 81, 35, 0.3);"></td>
                        <td></td>
                        <td>{detail.account.name}</td>
                        <td>{detail.account.code}</td>
                        <td class="debit">{"Rp {0:,.0f}".format(detail.debit) if detail.debit > 0 else ""}</td>
                        <td class="credit">{"Rp {0:,.0f}".format(detail.credit) if detail.credit > 0 else ""}</td>
                    </tr>
                    '''
                
                # Total per jurnal
                total_debit = sum(d.debit for d in journal.journal_details)
                total_credit = sum(d.credit for d in journal.journal_details)
                
                table_html += f'''
                <tr style="background: rgba(180, 81, 35, 0.05);">
                    <td colspan="4" style="text-align: right; font-weight: bold; padding: 0.5rem 1rem; border-top: 1px solid rgba(180, 81, 35, 0.1);">
                        Total:
                    </td>
                    <td class="debit" style="font-weight: bold; border-top: 1px solid rgba(180, 81, 35, 0.1);">Rp {total_debit:,.0f}</td>
                    <td class="credit" style="font-weight: bold; border-top: 1px solid rgba(180, 81, 35, 0.1);">Rp {total_credit:,.0f}</td>
                </tr>
                <tr><td colspan="6" style="height: 1rem; background: transparent;"></td></tr>
                '''

        table_html += '''
                    </tbody>
                </table>
            </div>
            
            <!-- Button untuk membuat jurnal penutup baru -->
            <div style="margin-top: 2rem; text-align: center;">
                <button class="btn btn-success" onclick="createClosingEntries()" 
                        style="padding: 1rem 2rem; font-size: 1.1rem;">
                    <i class="fas fa-calculator"></i> Buat Jurnal Penutup Baru
                </button>
                
                <div style="margin-top: 1rem; color: #6B7280; font-size: 0.9rem;">
                    <i class="fas fa-info-circle"></i> Jurnal penutup akan menutup semua akun pendapatan dan beban, 
                    menghitung laba/rugi, dan memindahkannya ke akun Modal.
                </div>
            </div>
        </div>
        '''

        return table_html
        
    except Exception as e:
        print(f"Error generating closing entries: {e}")
        return '<div class="card"><p>Error loading closing entries</p></div>'

def get_adjustment_account_balances():
    """Mendapatkan saldo akun untuk ditampilkan di form penyesuaian - DARI DATABASE"""
    return {
        'perlengkapan': get_account_balance_before_adjustment('perlengkapan'),
        'peralatan': get_account_balance_before_adjustment('peralatan'),
        'kendaraan': get_account_balance_before_adjustment('kendaraan')
    }

# ===== DEEP OCEAN HTML TEMPLATES =====
def base_html(title, content, additional_css="", additional_js=""):
    settings = {s.key: s.value for s in AppSetting.query.all()}
    app_name = settings.get('app_name', 'Kang-Mas Shop')
    app_logo = settings.get('app_logo', '/static/uploads/logos/logo.png')

    floating_cart = ''
    if current_user.is_authenticated and current_user.user_type == 'customer':
        floating_cart = '''
        <a href="/cart" class="fab">
            <i class="fas fa-shopping-cart"></i>
            <span id="cart-count-fab" style="position: absolute; top: -5px; right: -5px; background: var(--error); color: white; border-radius: 50%; width: 20px; height: 20px; display: none; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: bold;">0</span>
        </a>
        '''
    
    return f'''
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {app_name}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="icon" href="{app_logo}" type="image/x-icon">
    <style>
        :root {{
            --primary: {COLORS['primary']};
            --secondary: {COLORS['secondary']};
            --accent: {COLORS['accent']};
            --success: {COLORS['success']};
            --warning: {COLORS['warning']};
            --error: {COLORS['error']};
            --dark: {COLORS['dark']};
            --light: {COLORS['light']};
            --white: {COLORS['white']};
            --teal: {COLORS['teal']};
            --navy: {COLORS['navy']};
            --ocean-light: {COLORS['ocean-light']};
            --ocean-medium: {COLORS['ocean-medium']};
            --ocean-deep: {COLORS['ocean-deep']};
            --shadow-sm: 0 2px 4px rgba(0,0,0,0.1);
            --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
            --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05);
            --shadow-xl: 0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04);
            --border-radius: 12px;
            --border-radius-lg: 16px;
            --border-radius-xl: 20px;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #f0f9ff 0%, #e6f3ff 100%);
            color: var(--dark);
            min-height: 100vh;
            line-height: 1.6;
        }}

        /* Ocean Navbar */
        .navbar {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            padding: 1rem 2rem;
            position: sticky;
            top: 0;
            z-index: 1000;
            box-shadow: var(--shadow-lg);
        }}

        .nav-container {{
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .nav-brand {{
            font-family: 'Poppins', sans-serif;
            font-size: 1.8rem;
            font-weight: 800;
            color: var(--white);
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        .nav-links {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .nav-link {{
            color: var(--white);
            text-decoration: none;
            padding: 0.75rem 1.5rem;
            border-radius: var(--border-radius);
            transition: all 0.3s ease;
            font-weight: 500;
        }}

        .nav-link:hover {{
            background: rgba(255, 255, 255, 0.2);
            transform: translateY(-2px);
        }}

        .user-menu {{
            display: flex;
            align-items: center;
            gap: 1rem;
            background: rgba(255, 255, 255, 0.2);
            padding: 0.75rem 1.5rem;
            border-radius: var(--border-radius);
            backdrop-filter: blur(10px);
        }}

        .avatar {{
            width: 45px;
            height: 45px;
            border-radius: 50%;
            background: var(--ocean-medium);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.3rem;
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}

        .badge {{
            padding: 0.4rem 1rem;
            border-radius: 25px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            background: var(--ocean-medium);
            color: var(--white);
            box-shadow: var(--shadow-sm);
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }}

        /* Ocean Cards */
        .card {{
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(10px);
            border-radius: var(--border-radius-lg);
            padding: 2rem;
            box-shadow: var(--shadow-lg);
            margin-bottom: 2rem;
            border: 1px solid rgba(255, 255, 255, 0.3);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}

        .card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
        }}

        .card:hover {{
            transform: translateY(-5px);
            box-shadow: var(--shadow-xl);
        }}

        /* Ocean Buttons */
        .btn {{
            padding: 0.875rem 2rem;
            border: none;
            border-radius: var(--border-radius);
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 0.75rem;
            cursor: pointer;
            transition: all 0.3s ease;
            font-weight: 600;
            font-size: 0.95rem;
        }}

        .btn-primary {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}

        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: var(--shadow-lg);
        }}

        .btn-success {{
            background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}

        .btn-warning {{
            background: linear-gradient(135deg, var(--warning) 0%, #b7791f 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}

        .btn-danger {{
            background: linear-gradient(135deg, var(--error) 0%, #c53030 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}

        .btn-info {{
            background: linear-gradient(135deg, var(--ocean-medium) 0%, var(--teal) 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}

        .grid {{
            display: grid;
            gap: 2rem;
        }}

        .grid-2 {{ grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); }}
        .grid-3 {{ grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
        .grid-4 {{ grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); }}

        /* Ocean Hero Section */
        .hero {{
            text-align: center;
            padding: 5rem 2rem;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            border-radius: var(--border-radius-xl);
            margin-bottom: 3rem;
            color: var(--white);
            position: relative;
            overflow: hidden;
        }}

        .hero::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000"><polygon fill="rgba(255,255,255,0.05)" points="0,1000 1000,0 1000,1000"/></svg>');
        }}

        .hero h1 {{
            font-size: 3.5rem;
            margin-bottom: 1.5rem;
            font-family: 'Poppins', sans-serif;
            font-weight: 800;
        }}

        .hero p {{
            font-size: 1.25rem;
            margin-bottom: 2rem;
            opacity: 0.9;
        }}

        /* Ocean Stats */
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin: 3rem 0;
        }}

        .stat-card {{
            background: linear-gradient(135deg, var(--white) 0%, var(--ocean-light) 100%);
            padding: 2.5rem 2rem;
            border-radius: var(--border-radius-lg);
            text-align: center;
            box-shadow: var(--shadow-lg);
            border: 1px solid rgba(255, 255, 255, 0.5);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}

        .stat-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
        }}

        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: var(--shadow-xl);
        }}

        .stat-number {{
            font-family: 'Poppins', sans-serif;
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--primary);
            margin-bottom: 0.5rem;
        }}

        .price {{
            font-family: 'Poppins', sans-serif;
            font-size: 2rem;
            font-weight: 700;
            color: var(--primary);
        }}

        /* Ocean Tables */
        .table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--white);
            border-radius: var(--border-radius);
            overflow: hidden;
            box-shadow: var(--shadow-lg);
        }}

        .table th, .table td {{
            padding: 1.25rem;
            text-align: left;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }}

        .table th {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            color: var(--white);
            font-weight: 600;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .table tr:hover {{
            background: rgba(49, 130, 206, 0.05);
        }}

        /* Ocean Forms */
        .form-group {{
            margin-bottom: 1.75rem;
        }}

        .form-label {{
            display: block;
            margin-bottom: 0.75rem;
            font-weight: 600;
            color: var(--dark);
            font-size: 0.95rem;
        }}

        .form-control {{
            width: 100%;
            padding: 1rem 1.25rem;
            border: 2px solid rgba(0,0,0,0.1);
            border-radius: var(--border-radius);
            font-size: 1rem;
            transition: all 0.3s ease;
            background: rgba(255, 255, 255, 0.8);
            font-family: 'Inter', sans-serif;
        }}

        .form-control:focus {{
            outline: none;
            border-color: var(--ocean-medium);
            box-shadow: 0 0 0 3px rgba(49, 130, 206, 0.1);
            background: var(--white);
        }}

        /* Fix untuk input number - biarkan normal */
        input[type="number"] {{
            text-align: right;
            font-family: 'Inter', sans-serif;
        }}

        /* Remove number input arrows di browser tertentu */
        input[type="number"]::-webkit-outer-spin-button,
        input[type="number"]::-webkit-inner-spin-button {{
            -webkit-appearance: none;
            margin: 0;
        }}

        input[type="number"] {{
            -moz-appearance: textfield;
        }}

        /* Ocean Tabs */
        .accounting-tabs {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 2rem;
            background: rgba(255, 255, 255, 0.6);
            padding: 0.5rem;
            border-radius: var(--border-radius);
            backdrop-filter: blur(10px);
        }}

        .tab {{
            padding: 1rem 2rem;
            background: transparent;
            border: none;
            border-radius: var(--border-radius);
            cursor: pointer;
            font-weight: 600;
            color: var(--dark);
            transition: all 0.3s ease;
            position: relative;
        }}

        .tab.active {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}

        .tab-content {{
            display: none;
        }}

        .tab-content.active {{
            display: block;
            animation: fadeIn 0.5s ease;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .debit {{
            color: var(--success);
            font-weight: 600;
            background: rgba(56, 161, 105, 0.1);
            padding: 0.5rem 1rem;
            border-radius: var(--border-radius);
        }}

        .credit {{
            color: var(--error);
            font-weight: 600;
            background: rgba(229, 62, 62, 0.1);
            padding: 0.5rem 1rem;
            border-radius: var(--border-radius);
        }}

        /* Product Cards */
        .product-image {{
            width: 100%;
            height: 300px; /* Fixed height untuk ratio 1:1 */
            object-fit: cover; /* Pastikan gambar tidak terdistorsi */
            border-radius: var(--border-radius);
            margin-bottom: 1.5rem;
            transition: transform 0.3s ease;
            box-shadow: var(--shadow-md);
        }}

        .product-card:hover .product-image {{
            transform: scale(1.05);
        }}

        /* Untuk gambar di form produk */
        .form-product-image {{
            width: 200px;
            height: 200px;
            object-fit: cover;
            border-radius: var(--border-radius);
            margin: 1rem 0;
        }}

        /* Tracking Steps */
        .tracking-steps {{
            display: flex;
            justify-content: space-between;
            margin: 2rem 0;
            position: relative;
        }}

        .tracking-steps::before {{
            content: '';
            position: absolute;
            top: 25px;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            z-index: 1;
            border-radius: 10px;
        }}

        .tracking-step {{
            text-align: center;
            position: relative;
            z-index: 2;
            flex: 1;
        }}

        .step-icon {{
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: var(--ocean-light);
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 0.75rem;
            transition: all 0.3s ease;
            font-size: 1.25rem;
            box-shadow: var(--shadow-md);
            border: 3px solid var(--white);
        }}

        .step-active {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            color: var(--white);
            transform: scale(1.1);
        }}

        .step-completed {{
            background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%);
            color: var(--white);
        }}

        /* Google Button */
        .google-btn {{
            background: #4285F4;
            color: white;
            width: 100%;
            justify-content: center;
            margin-top: 1rem;
            box-shadow: var(--shadow-md);
        }}

        .google-btn:hover {{
            background: #357ae8;
            transform: translateY(-2px);
            box-shadow: var(--shadow-lg);
        }}

        /* Divider */
        .divider {{
            text-align: center;
            margin: 1.5rem 0;
            position: relative;
        }}

        .divider::before {{
            content: '';
            position: absolute;
            top: 50%;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
        }}

        .divider span {{
            background: var(--white);
            padding: 0 1.5rem;
            position: relative;
            color: var(--dark);
            font-weight: 500;
        }}

        /* Flash Messages */
        .flash-messages {{
            position: fixed;
            top: 100px;
            right: 20px;
            z-index: 10000;
        }}

        .flash-message {{
            padding: 1.25rem 1.75rem;
            border-radius: var(--border-radius);
            margin-bottom: 0.75rem;
            font-weight: 500;
            box-shadow: var(--shadow-xl);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            animation: slideInRight 0.5s ease;
        }}

        @keyframes slideInRight {{
            from {{ transform: translateX(100%); opacity: 0; }}
            to {{ transform: translateX(0); opacity: 1; }}
        }}

        .flash-success {{
            background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%);
            color: white;
        }}

        .flash-error {{
            background: linear-gradient(135deg, var(--error) 0%, #c53030 100%);
            color: white;
        }}

        .flash-warning {{
            background: linear-gradient(135deg, var(--warning) 0%, #b7791f 100%);
            color: white;
        }}

        /* Logo Styling */
        .navbar-logo {{
            width: 140px !important; 
            height: 140px !important; 
            max-width: 140px;
            max-height: 140px;
            border-radius: 0 !important;
            box-shadow: none !important;
            object-fit: contain; 
            margin-right: 30px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            border: none !important;
            display: block;
            float: left;
            background: transparent !important;
            padding: 0;
        }}

        /* Ocean Modal Styles */
        .modal {{
            display: none;
            position: fixed;
            z-index: 10000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
            backdrop-filter: blur(10px);
        }}

        .modal-content {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(20px);
            margin: 10% auto;
            padding: 2.5rem;
            border-radius: var(--border-radius-xl);
            width: 90%;
            max-width: 500px;
            box-shadow: var(--shadow-xl);
            border: 1px solid rgba(255, 255, 255, 0.3);
            position: relative;
            animation: modalSlideIn 0.3s ease;
        }}

        @keyframes modalSlideIn {{
            from {{ transform: translateY(-50px); opacity: 0; }}
            to {{ transform: translateY(0); opacity: 1; }}
        }}

        .close {{
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            position: absolute;
            right: 1.5rem;
            top: 1.5rem;
            transition: color 0.3s ease;
        }}

        .close:hover {{
            color: var(--error);
        }}

        .modal-buttons {{
            display: flex;
            gap: 1rem;
            margin-top: 2rem;
        }}

        .modal-buttons .btn {{
            flex: 1;
        }}

        /* Status Badges */
        .status-text {{
            padding: 0.5rem 1rem;
            border-radius: 25px;
            font-weight: 600;
            display: inline-block;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            box-shadow: var(--shadow-sm);
        }}

        .status-pending {{
            background: linear-gradient(135deg, var(--warning) 0%, #b7791f 100%);
            color: white;
        }}

        .status-processing {{
            background: linear-gradient(135deg, var(--ocean-medium) 0%, var(--ocean-deep) 100%);
            color: white;
        }}

        .status-completed {{
            background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%);
            color: white;
        }}

        .status-cancelled {{
            background: linear-gradient(135deg, var(--error) 0%, #c53030 100%);
            color: white;
        }}

        .status-paid {{
            background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%);
            color: white;
        }}

        .status-unpaid {{
            background: linear-gradient(135deg, var(--error) 0%, #c53030 100%);
            color: white;
        }}

        /* Floating Action Button */
        .fab {{
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            box-shadow: var(--shadow-xl);
            cursor: pointer;
            z-index: 1000;
            transition: all 0.3s ease;
            text-decoration: none;
        }}

        .fab:hover {{
            transform: scale(1.1);
        }}

        /* Loading Animation */
        .loading {{
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
        }}

        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}

        /* Responsive Design */
        @media (max-width: 768px) {{
            .nav-links {{
                flex-direction: column;
                gap: 0.5rem;
            }}

            .hero h1 {{
                font-size: 2.5rem;
            }}

            .grid-2, .grid-3, .grid-4 {{
                grid-template-columns: 1fr;
            }}

            .container {{
                padding: 1rem;
            }}

            .stats {{
                grid-template-columns: 1fr;
            }}
        }}

        {additional_css}
    </style>
</head>
<body>
    <!-- Floating Cart Button -->
    {floating_cart}

    <nav class="navbar">
        <div class="nav-container">
            <a href="/" class="nav-brand">
                <img src="{app_logo}" alt="{app_name}" class="navbar-logo" 
                    style="background: none; border: none; box-shadow: none; width: 140px; height: 140px;"
                    onerror="this.style.display='none'">
                <span>{app_name}</span>
            </a>

            <div class="nav-links">
                {get_navigation()}
            </div>
        </div>
    </nav>

    <div class="flash-messages">
        {get_flash_messages()}
    </div>

    <div class="container">
        {content}
    </div>

    <!-- Ocean Payment Modal -->
    <div id="paymentModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('paymentModal')">&times;</span>
            <div style="text-align: center; margin-bottom: 1.5rem;">
                <div style="width: 60px; height: 60px; background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
                    <i class="fas fa-credit-card" style="color: white; font-size: 1.5rem;"></i>
                </div>
                <h2 style="margin-bottom: 0.5rem; color: var(--primary);">Pembayaran</h2>
                <p style="color: var(--dark); opacity: 0.7;">Selesaikan pembayaran untuk melanjutkan</p>
            </div>

            <div id="paymentInstructions" style="background: rgba(49, 130, 206, 0.05); padding: 1.5rem; border-radius: var(--border-radius); margin-bottom: 1.5rem;">
                <!-- Instructions will be loaded here -->
            </div>

            <div class="modal-buttons">
                <button class="btn btn-success" onclick="showSuccessModal()" style="width: 100%;">
                    <i class="fas fa-check-circle"></i>
                    Sudah Bayar
                </button>
            </div>
        </div>
    </div>

    <!-- Ocean Success Modal -->
    <div id="successModal" class="modal">
        <!-- Content akan diisi oleh JavaScript -->
    </div>

    <script>
        // Ocean JavaScript Functions
        function addToCart(productId) {{
            console.log('🛒 Adding product to cart:', productId);

            if (!productId) {{
                showNotification('Product ID tidak valid', 'error');
                return;
            }}

            const button = event.target;
            const originalText = button.innerHTML;

            // Show loading state
            button.innerHTML = '<div class="loading"></div> Menambahkan...';
            button.disabled = true;

            const cartData = {{
                product_id: parseInt(productId),
                quantity: 1
            }};

            fetch('/api/cart/add', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }},
                body: JSON.stringify(cartData)
            }})
            .then(response => {{
                if (!response.ok) {{
                    return response.json().then(errorData => {{
                        throw new Error(errorData.message || `HTTP error! status: ${{response.status}}`);
                    }});
                }}
                return response.json();
            }})
            .then(data => {{
                if (data.success) {{
                    showNotification('✅ ' + data.message, 'success');
                    updateCartCount();
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }})
            .catch(error => {{
                console.error('Fetch error:', error);
                let errorMessage = 'Gagal menambahkan ke keranjang';

                if (error.message.includes('HTTP error! status: 403')) {{
                    errorMessage = 'Hanya customer yang bisa menambah ke keranjang';
                }} else if (error.message.includes('HTTP error! status: 404')) {{
                    errorMessage = 'Produk tidak ditemukan';
                }} else if (error.message.includes('HTTP error! status: 400')) {{
                    errorMessage = 'Stock tidak mencukupi';
                }}

                showNotification('❌ ' + errorMessage, 'error');
            }})
            .finally(() => {{
                setTimeout(() => {{
                    button.innerHTML = originalText;
                    button.disabled = false;
                }}, 1000);
            }});
        }}

        function showTab(tabName, element) {{
            document.querySelectorAll('.tab-content').forEach(tab => {{
                tab.classList.remove('active');
            }});
            document.querySelectorAll('.tab').forEach(tab => {{
                tab.classList.remove('active');
            }});
            document.getElementById(tabName).classList.add('active');
            element.classList.add('active');
        }}

        function showNotification(message, type) {{
            const notification = document.createElement('div');
            notification.className = `flash-message flash-${{type}}`;
            notification.innerHTML = `
                <div style="display: flex; align-items: center; gap: 0.75rem;">
                    <i class="fas fa-${{type === 'success' ? 'check-circle' : 'exclamation-circle'}}"></i>
                    <span>${{message}}</span>
                </div>
            `;

            const flashContainer = document.querySelector('.flash-messages');
            flashContainer.appendChild(notification);

            setTimeout(() => {{
                notification.style.animation = 'slideInRight 0.5s ease reverse';
                setTimeout(() => {{
                    flashContainer.removeChild(notification);
                }}, 500);
            }}, 4000);
        }}

        function checkout() {{
            window.location.href = '/checkout';
        }}

        // ===== FUNGSI CHECKOUT BARU UNTUK COD =====
        function processCheckout() {{
            const shippingAddress = document.getElementById('shipping_address').value;
            const shippingMethod = document.getElementById('shipping_method').value;
            const paymentMethod = document.getElementById('payment_method').value;

            if (!shippingAddress) {{
                showNotification('Harap isi alamat pengiriman!', 'error');
                return;
            }}

            if (!shippingMethod) {{
                showNotification('Harap pilih metode pengiriman!', 'error');
                return;
            }}

            if (!paymentMethod) {{
                showNotification('Harap pilih metode pembayaran!', 'error');
                return;
            }}

            const formData = new FormData();
            formData.append('shipping_address', shippingAddress);
            formData.append('shipping_method', shippingMethod);
            formData.append('payment_method', paymentMethod);

            fetch('/process_checkout', {{
                method: 'POST',
                body: formData
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    if (data.is_cod) {{
                        // Untuk COD, langsung tampilkan sukses
                        showSuccessModalCOD(data.order_number, data.total_amount);
                    }} else {{
                        // Untuk non-COD, tampilkan instruksi pembayaran
                        showPaymentModal(data.order_number, data.payment_method, data.total_amount);
                    }}
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }});
        }}

        function resetBalances() {{
            if (!confirm('Apakah Anda yakin ingin mereset saldo awal? Tindakan ini akan mengembalikan saldo ke nilai default.')) {{
                return;
            }}

            const button = event.target;
            const originalText = button.innerHTML;

            button.innerHTML = '<div class="loading"></div> Resetting...';
            button.disabled = true;

            fetch('/seller/reset_balances', {{
                method: 'POST'
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    showNotification('✅ ' + data.message, 'success');
                    setTimeout(() => location.reload(), 2000);
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }})
            .catch(error => {{
                showNotification('❌ Terjadi error saat reset saldo', 'error');
            }})
            .finally(() => {{
                setTimeout(() => {{
                    button.innerHTML = originalText;
                    button.disabled = false;
                }}, 2000);
            }});
        }}

        // ===== 🆕 FUNGSI BARU UNTUK FORM PENJUALAN SEDERHANA =====
        // Data harga default
        const defaultPrices = {{
            'bibit': {{
                selling_price: 2000,
                cost_price: 1000,
                name: 'Bibit Ikan Mas'
            }},
            'konsumsi': {{
                selling_price: 20000,
                cost_price: 13500,
                name: 'Ikan Mas Konsumsi'
            }}
        }};

        // Fungsi untuk mengisi harga default
        function fillDefaultPrices() {{
            const productType = document.getElementById('product_type')?.value;

            if (productType && defaultPrices[productType]) {{
                const product = defaultPrices[productType];

                // Isi harga default
                const sellingPriceInput = document.getElementById('selling_price');
                const costPriceInput = document.getElementById('cost_price');
                const descriptionInput = document.getElementById('description');

                if (sellingPriceInput) sellingPriceInput.value = product.selling_price;
                if (costPriceInput) costPriceInput.value = product.cost_price;
                if (descriptionInput) descriptionInput.value = 'Penjualan ' + product.name;

                // Hitung ulang total
                calculateTotals();
            }} else if (productType === 'lainnya') {{
                // Kosongkan untuk produk lainnya
                const sellingPriceInput = document.getElementById('selling_price');
                const costPriceInput = document.getElementById('cost_price');
                const descriptionInput = document.getElementById('description');

                if (sellingPriceInput) sellingPriceInput.value = '';
                if (costPriceInput) costPriceInput.value = '';
                if (descriptionInput) descriptionInput.value = 'Penjualan produk lainnya';

                calculateTotals();
            }}
        }}

                // Fungsi untuk menghitung total
        function calculateTotals() {{
            const quantity = parseInt(document.getElementById('quantity')?.value) || 0;
            const sellingPrice = parseInt(document.getElementById('selling_price')?.value) || 0;
            const costPrice = parseInt(document.getElementById('cost_price')?.value) || 0;

            const totalSales = sellingPrice * quantity;
            const totalHpp = costPrice * quantity;

            const totalSalesInput = document.getElementById('total_sales');
            const totalHppInput = document.getElementById('total_hpp');

            if (totalSalesInput) totalSalesInput.value = totalSales;
            if (totalHppInput) totalHppInput.value = totalHpp;
        }}

        // ⬇️⬇️⬇️ TARUH DI SINI ⬇️⬇️⬇️
        // Fungsi untuk submit form penjualan sederhana
        function submitSalesForm() {{
            console.log("🔄 Submit Sales Form dipanggil");

            const productType = document.getElementById('product_type')?.value;
            const paymentMethod = document.getElementById('payment_method')?.value;
            const quantity = parseInt(document.getElementById('quantity')?.value) || 0;
            const sellingPrice = parseInt(document.getElementById('selling_price')?.value) || 0;
            const costPrice = parseInt(document.getElementById('cost_price')?.value) || 0;
            const description = document.getElementById('description')?.value;
            const dateInput = document.querySelector('input[name="date"]');
            const date = dateInput ? dateInput.value : new Date().toISOString().split('T')[0];
            const totalSales = parseInt(document.getElementById('total_sales')?.value) || 0;
            const totalHpp = parseInt(document.getElementById('total_hpp')?.value) || 0;

            console.log("📊 Data yang akan dikirim:", {{
                productType, paymentMethod, quantity, sellingPrice, costPrice, description, date
            }});

            // Validasi input
            if (!productType) {{
                alert('❌ Harap pilih jenis produk!');
                return;
            }}

            if (!paymentMethod) {{
                alert('❌ Harap pilih metode pembayaran!');
                return;
            }}

            if (!quantity || quantity <= 0) {{
                alert('❌ Harap isi quantity dengan angka lebih dari 0!');
                return;
            }}

            if (!sellingPrice || sellingPrice <= 0) {{
                alert('❌ Harap isi harga jual dengan angka lebih dari 0!');
                return;
            }}

            if (!costPrice || costPrice <= 0) {{
                alert('❌ Harap isi harga beli (HPP) dengan angka lebih dari 0!');
                return;
            }}

            // Data untuk dikirim
            const data = {{
                date: date,
                product_type: productType,
                payment_method: paymentMethod,
                quantity: quantity,
                selling_price: sellingPrice,
                cost_price: costPrice,
                description: description || 'Penjualan produk'
            }};

            // Tampilkan konfirmasi
            const productName = defaultPrices[productType] ? defaultPrices[productType].name : 'Produk';

            const confirmMessage = 'Konfirmasi Penjualan:\\n\\n' +
                                'Produk: ' + productName + '\\n' +
                                'Quantity: ' + quantity + ' unit\\n' +
                                'Harga Jual: Rp ' + sellingPrice.toLocaleString() + ' per unit\\n' +
                                'Harga Pokok Produksi: Rp ' + costPrice.toLocaleString() + ' per unit\\n' +
                                'Metode: ' + (paymentMethod === 'tunai' ? 'Tunai' : 'Kredit') + '\\n\\n' +
                                'Total Penjualan: Rp ' + totalSales.toLocaleString() + '\\n' +
                                'Total Harga Pokok Produksi: Rp ' + totalHpp.toLocaleString() + '\\n\\n' +
                                'Buat jurnal penjualan?';

            if (!confirm(confirmMessage)) {{
                return;
            }}

            // Tampilkan loading
            const button = event.target;
            const originalText = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> Memproses...';
            button.disabled = true;

            // Kirim data ke server
            fetch('/seller/add_sales_journal', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(data)
            }})
            .then(response => response.json())
            .then(result => {{
                console.log("✅ Response dari server:", result);
                if (result.success) {{
                    alert('✅ ' + result.message);
                    setTimeout(() => location.reload(), 1500);
                }} else {{
                    alert('❌ ' + result.message);
                    button.innerHTML = originalText;
                    button.disabled = false;
                }}
            }})
            .catch(error => {{
                console.error("❌ Error:", error);
                alert('❌ Terjadi error: ' + error);
                button.innerHTML = originalText;
                button.disabled = false;
            }});
        }}

        // ===== FUNGSI UNTUK FORM PEMBELIAN SEDERHANA =====
        // Data harga default untuk pembelian
        const purchaseDefaultPrices = {{
            'bibit': {{
                purchase_price: 1000,
                selling_price: 2000,
                name: 'Bibit Ikan Mas'
            }},
            'konsumsi': {{
                purchase_price: 13500,
                selling_price: 20000,
                name: 'Ikan Mas Konsumsi'
            }},
            'perlengkapan': {{
                purchase_price: 50000,
                selling_price: 0,
                name: 'Perlengkapan Budidaya'
            }},
            'peralatan': {{
                purchase_price: 100000,
                selling_price: 0,
                name: 'Peralatan Budidaya'
            }}
        }};

        // Fungsi untuk mengisi harga default pembelian
        function fillPurchaseDefaultPrices() {{
            const productType = document.getElementById('purchase_product_type')?.value;

            if (productType && purchaseDefaultPrices[productType]) {{
                const product = purchaseDefaultPrices[productType];

                const purchasePriceInput = document.getElementById('purchase_price');
                const sellingPriceInput = document.getElementById('selling_price');
                const descriptionInput = document.getElementById('purchase_description');

                if (purchasePriceInput) purchasePriceInput.value = product.purchase_price;
                if (sellingPriceInput) sellingPriceInput.value = product.selling_price;
                if (descriptionInput) descriptionInput.value = 'Pembelian ' + product.name;

                calculatePurchaseTotals();
            }}
        }}

        // Fungsi untuk menghitung total pembelian
        function calculatePurchaseTotals() {{
            const quantity = parseInt(document.getElementById('purchase_quantity')?.value) || 0;
            const purchasePrice = parseInt(document.getElementById('purchase_price')?.value) || 0;

            const totalPurchase = purchasePrice * quantity;

            const totalPurchaseInput = document.getElementById('purchase_total');
            if (totalPurchaseInput) totalPurchaseInput.value = totalPurchase;
        }}

        // Fungsi untuk submit form pembelian
        function submitPurchaseForm() {{
            console.log("🔄 Submit Purchase Form dipanggil");

            const productType = document.getElementById('purchase_product_type')?.value;
            const paymentMethod = document.getElementById('purchase_payment_method')?.value;
            const quantity = parseInt(document.getElementById('purchase_quantity')?.value) || 0;
            const purchasePrice = parseInt(document.getElementById('purchase_price')?.value) || 0;
            const sellingPrice = parseInt(document.getElementById('selling_price')?.value) || 0;
            const description = document.getElementById('purchase_description')?.value;
            const dateInput = document.querySelector('#purchaseJournalForm input[name="date"]');
            const date = dateInput ? dateInput.value : new Date().toISOString().split('T')[0];
            const totalPurchase = parseInt(document.getElementById('purchase_total')?.value) || 0;

            console.log("📊 Data pembelian yang akan dikirim:", {{
                productType, paymentMethod, quantity, purchasePrice, sellingPrice, description, date
            }});

            // Validasi input
            if (!productType) {{
                alert('❌ Harap pilih jenis produk!');
                return;
            }}

            if (!paymentMethod) {{
                alert('❌ Harap pilih metode pembayaran!');
                return;
            }}

            if (!quantity || quantity <= 0) {{
                alert('❌ Harap isi quantity dengan angka lebih dari 0!');
                return;
            }}

            if (!purchasePrice || purchasePrice <= 0) {{
                alert('❌ Harap isi harga beli dengan angka lebih dari 0!');
                return;
            }}

            // Data untuk dikirim
            const data = {{
                date: date,
                product_type: productType,
                payment_method: paymentMethod,
                quantity: quantity,
                purchase_price: purchasePrice,
                selling_price: sellingPrice,
                description: description || 'Pembelian produk'
            }};

            // Tampilkan konfirmasi
            const productName = purchaseDefaultPrices[productType] ? purchaseDefaultPrices[productType].name : 'Produk';

            const confirmMessage = 'Konfirmasi Pembelian:\\n\\n' +
                                'Produk: ' + productName + '\\n' +
                                'Quantity: ' + quantity + ' unit\\n' +
                                'Harga Beli: Rp ' + purchasePrice.toLocaleString() + ' per unit\\n' +
                                'Metode: ' + (paymentMethod === 'tunai' ? 'Tunai' : 'Kredit') + '\\n\\n' +
                                'Total Pembelian: Rp ' + totalPurchase.toLocaleString() + '\\n\\n' +
                                'Buat jurnal pembelian?';

            if (!confirm(confirmMessage)) {{
                return;
            }}

            // Tampilkan loading
            const button = event.target;
            const originalText = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> Memproses...';
            button.disabled = true;

            // Kirim data ke server
            fetch('/seller/add_purchase_journal', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(data)
            }})
            .then(response => response.json())
            .then(result => {{
                console.log("✅ Response dari server:", result);
                if (result.success) {{
                    alert('✅ ' + result.message);
                    setTimeout(() => location.reload(), 1500);
                }} else {{
                    alert('❌ ' + result.message);
                    button.innerHTML = originalText;
                    button.disabled = false;
                }}
            }})
            .catch(error => {{
                console.error("❌ Error:", error);
                alert('❌ Terjadi error: ' + error);
                button.innerHTML = originalText;
                button.disabled = false;
            }});
        }}

        // Event delegation untuk form penjualan sederhana
        document.addEventListener('change', function(e) {{
            // Handle product type change
            if (e.target && e.target.id === 'product_type') {{
                fillDefaultPrices();
            }}
        }});

        document.addEventListener('input', function(e) {{
            // Handle quantity and price changes
            if (e.target && (e.target.id === 'quantity' || e.target.id === 'selling_price' || e.target.id === 'cost_price')) {{
                calculateTotals();
            }}
        }});

        function showSuccessModalCOD(orderNumber, totalAmount) {{
            const modalContent = `
                <div class="modal-content">
                    <span class="close" onclick="closeModal('successModal')">&times;</span>
                    <div style="text-align: center;">
                        <div style="width: 80px; height: 80px; background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
                            <i class="fas fa-check" style="color: white; font-size: 2rem;"></i>
                        </div>
                        <h2 style="margin-bottom: 1rem; color: var(--success);">Pesanan COD Berhasil!</h2>
                        <p style="margin-bottom: 1rem; color: var(--dark);">
                            Pesanan COD Anda telah berhasil dibuat dan sedang diproses.
                        </p>
                        <p style="color: var(--dark); opacity: 0.7; font-size: 0.9rem; margin-bottom: 2rem;">
                            Order #: <strong>${{orderNumber}}</strong><br>
                            Total: <strong>Rp ${{totalAmount.toLocaleString()}}</strong><br>
                            Bayar ketika pesanan diterima
                        </p>
                    </div>

                    <div class="modal-buttons">
                        <button class="btn btn-success" onclick="closeModal('successModal'); window.location.href='/orders';" style="width: 100%;">
                            <i class="fas fa-list"></i>
                            Lihat Pesanan Saya
                        </button>
                        <button class="btn btn-primary" onclick="contactSellerCOD('${{orderNumber}}', ${{totalAmount}})" style="width: 100%;">
                            <i class="fab fa-whatsapp"></i>
                            Konfirmasi ke Penjual
                        </button>
                    </div>
                </div>
            `;

            // Create or update modal
            let modal = document.getElementById('successModal');
            if (!modal) {{
                modal = document.createElement('div');
                modal.id = 'successModal';
                modal.className = 'modal';
                document.body.appendChild(modal);
            }}
            modal.innerHTML = modalContent;
            modal.style.display = 'block';
        }}

        function contactSellerCOD(orderNumber, totalAmount) {{
            const message = `Hai Kak, saya telah membuat pesanan COD:

🛍️ Order #: ${{orderNumber}}
💰 Total: Rp ${{totalAmount.toLocaleString()}}
📦 Metode: Cash on Delivery

Mohon dipersiapkan pesanannya ya. Terima kasih! 😊`;

            const phone = '+6285876127696';
            const url = 'https://wa.me/' + phone + '?text=' + encodeURIComponent(message);
            window.open(url, '_blank');
        }}

        function showPaymentModal(orderNumber, paymentMethod, totalAmount) {{
            const paymentInstructions = {{
                'qris': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary); text-align: center;">
                        <i class="fas fa-qrcode"></i> PEMBAYARAN QRIS
                    </h4>
                    <div style="text-align: center; margin: 1rem 0;">
                        <img src="/static/assets/qris_code.jpg"
                             alt="QRIS Code Kang-Mas Shop"
                             style="max-width: 300px; width: 100%; height: auto; border-radius: var(--border-radius); border: 3px solid var(--primary); box-shadow: var(--shadow-lg);">
                    </div>

                    <div style="background: rgba(56, 161, 105, 0.1); padding: 1.5rem; border-radius: var(--border-radius); margin: 1.5rem 0; text-align: center;">
                        <h5 style="color: var(--success); margin-bottom: 0.5rem;">TOTAL PEMBAYARAN</h5>
                        <div style="font-size: 1.5rem; font-weight: bold; color: var(--success);">
                            Rp ${{totalAmount.toLocaleString()}}
                        </div>
                    </div>

                    <div style="background: var(--ocean-light); padding: 1rem; border-radius: var(--border-radius);">
                        <h5 style="color: var(--primary); margin-bottom: 0.5rem;"><i class="fas fa-info-circle"></i> Cara Bayar:</h5>
                        <ol style="margin: 0; padding-left: 1.2rem; font-size: 0.9rem;">
                            <li>Buka aplikasi e-wallet atau mobile banking Anda</li>
                            <li>Pilih menu <strong>Bayar</strong> atau <strong>Scan QR</strong></li>
                            <li>Scan kode QRIS di atas</li>
                            <li>Pastikan nominal sesuai: <strong>Rp ${{totalAmount.toLocaleString()}}</strong></li>
                            <li>Konfirmasi pembayaran</li>
                        </ol>
                    </div>

                    <div style="margin-top: 1rem; padding: 1rem; background: rgba(229, 62, 62, 0.1); border-radius: var(--border-radius);">
                        <p style="margin: 0; color: var(--error); font-size: 0.9rem; text-align: center;">
                            <i class="fas fa-exclamation-triangle"></i>
                            <strong>Jangan lupa screenshot bukti pembayaran!</strong>
                        </p>
                    </div>
                `,
                'bri': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary); text-align: center;">
                        <i class="fas fa-university"></i> TRANSFER BANK BRI
                    </h4>
                    <div style="background: white; padding: 1.5rem; border-radius: var(--border-radius); border-left: 4px solid var(--primary); text-align: center;">
                        <p style="margin: 0.75rem 0; font-size: 1.1rem;">
                            <strong>No. Rekening:</strong><br>
                            <span style="color: var(--primary); font-weight: bold; font-size: 1.3rem;">1234 5678 9012</span>
                        </p>
                        <p style="margin: 0.75rem 0; font-size: 1.1rem;">
                            <strong>Atas Nama:</strong><br>
                            <span style="color: var(--dark); font-weight: bold;">KANG-MAS SHOP</span>
                        </p>
                        <div style="margin: 1.5rem 0; padding: 1rem; background: rgba(56, 161, 105, 0.1); border-radius: var(--border-radius);">
                            <p style="margin: 0; color: var(--success); font-weight: bold; font-size: 1.2rem;">
                                TOTAL: Rp ${{totalAmount.toLocaleString()}}
                            </p>
                        </div>
                    </div>
                `,
                'bca': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary); text-align: center;">
                        <i class="fas fa-university"></i> TRANSFER BANK BCA
                    </h4>
                    <div style="background: white; padding: 1.5rem; border-radius: var(--border-radius); border-left: 4px solid var(--primary); text-align: center;">
                        <p style="margin: 0.75rem 0; font-size: 1.1rem;">
                            <strong>No. Rekening:</strong><br>
                            <span style="color: var(--primary); font-weight: bold; font-size: 1.3rem;">9876 5432 1098</span>
                        </p>
                        <p style="margin: 0.75rem 0; font-size: 1.1rem;">
                            <strong>Atas Nama:</strong><br>
                            <span style="color: var(--dark); font-weight: bold;">KANG-MAS SHOP</span>
                        </p>
                        <div style="margin: 1.5rem 0; padding: 1rem; background: rgba(56, 161, 105, 0.1); border-radius: var(--border-radius);">
                            <p style="margin: 0; color: var(--success); font-weight: bold; font-size: 1.2rem;">
                                TOTAL: Rp ${{totalAmount.toLocaleString()}}
                            </p>
                        </div>
                    </div>
                `,
                'mandiri': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary); text-align: center;">
                        <i class="fas fa-university"></i> TRANSFER BANK MANDIRI
                    </h4>
                    <div style="background: white; padding: 1.5rem; border-radius: var(--border-radius); border-left: 4px solid var(--primary); text-align: center;">
                        <p style="margin: 0.75rem 0; font-size: 1.1rem;">
                            <strong>No. Rekening:</strong><br>
                            <span style="color: var(--primary); font-weight: bold; font-size: 1.3rem;">1122 3344 5566</span>
                        </p>
                        <p style="margin: 0.75rem 0; font-size: 1.1rem;">
                            <strong>Atas Nama:</strong><br>
                            <span style="color: var(--dark); font-weight: bold;">KANG-MAS SHOP</span>
                        </p>
                        <div style="margin: 1.5rem 0; padding: 1rem; background: rgba(56, 161, 105, 0.1); border-radius: var(--border-radius);">
                            <p style="margin: 0; color: var(--success); font-weight: bold; font-size: 1.2rem;">
                                TOTAL: Rp ${{totalAmount.toLocaleString()}}
                            </p>
                        </div>
                    </div>
                `,
                'gopay': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary); text-align: center;">
                        <i class="fas fa-mobile-alt"></i> GOPAY
                    </h4>
                    <div style="background: white; padding: 1.5rem; border-radius: var(--border-radius); border-left: 4px solid #00AA13; text-align: center;">
                        <p style="margin: 0.75rem 0; font-size: 1.1rem;">
                            <strong>No. Telepon:</strong><br>
                            <span style="color: var(--primary); font-weight: bold; font-size: 1.3rem;">+62 896-5473-3875</span>
                        </p>
                        <p style="margin: 0.75rem 0; font-size: 1.1rem;">
                            <strong>Atas Nama:</strong><br>
                            <span style="color: var(--dark); font-weight: bold;">KANG-MAS SHOP</span>
                        </p>
                        <div style="margin: 1.5rem 0; padding: 1rem; background: rgba(56, 161, 105, 0.1); border-radius: var(--border-radius);">
                            <p style="margin: 0; color: var(--success); font-weight: bold; font-size: 1.2rem;">
                                TOTAL: Rp ${{totalAmount.toLocaleString()}}
                            </p>
                        </div>
                    </div>
                `,
                'dana': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary); text-align: center;">
                        <i class="fas fa-wallet"></i> DANA
                    </h4>
                    <div style="background: white; padding: 1.5rem; border-radius: var(--border-radius); border-left: 4px solid #00B2FF; text-align: center;">
                        <p style="margin: 0.75rem 0; font-size: 1.1rem;">
                            <strong>No. Telepon:</strong><br>
                            <span style="color: var(--primary); font-weight: bold; font-size: 1.3rem;">+62 896-5473-3875</span>
                        </p>
                        <p style="margin: 0.75rem 0; font-size: 1.1rem;">
                            <strong>Atas Nama:</strong><br>
                            <span style="color: var(--dark); font-weight: bold;">KANG-MAS SHOP</span>
                        </p>
                        <div style="margin: 1.5rem 0; padding: 1rem; background: rgba(56, 161, 105, 0.1); border-radius: var(--border-radius);">
                            <p style="margin: 0; color: var(--success); font-weight: bold; font-size: 1.2rem;">
                                TOTAL: Rp ${{totalAmount.toLocaleString()}}
                            </p>
                        </div>
                    </div>
                `
            }};

            // Tampilkan instruksi pembayaran
            document.getElementById('paymentInstructions').innerHTML = paymentInstructions[paymentMethod] || `
                <div style="text-align: center; padding: 2rem;">
                    <i class="fas fa-credit-card" style="font-size: 3rem; color: var(--primary); margin-bottom: 1rem;"></i>
                    <p>Silakan selesaikan pembayaran dengan metode <strong>${{paymentMethod.toUpperCase()}}</strong></p>
                    <p style="color: var(--success); font-weight: bold; font-size: 1.2rem;">Total: Rp ${{totalAmount.toLocaleString()}}</p>
                </div>
            `;

            document.getElementById('paymentModal').style.display = 'block';
            window.currentOrderNumber = orderNumber;
            window.currentPaymentMethod = paymentMethod;
            window.currentTotalAmount = totalAmount;
        }}

        function showSuccessModal() {{
            closeModal('paymentModal');

            const modalContent = `
                <div class="modal-content">
                    <span class="close" onclick="closeModal('successModal')">&times;</span>
                    <div style="text-align: center;">
                        <div style="width: 80px; height: 80px; background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
                            <i class="fas fa-check" style="color: white; font-size: 2rem;"></i>
                        </div>
                        <h2 style="margin-bottom: 1rem; color: var(--success);">Sukses!</h2>
                        <p style="margin-bottom: 1rem; color: var(--dark);">Pembayaran berhasil dikonfirmasi</p>
                        <p style="color: var(--dark); opacity: 0.7; font-size: 0.9rem; margin-bottom: 2rem;">
                            Pesanan Anda sedang diproses dan akan segera dikirim
                        </p>
                    </div>

                    <div class="modal-buttons">
                        <button class="btn btn-success" onclick="closeModal('successModal'); window.location.href='/orders';" style="width: 100%;">
                            <i class="fas fa-list"></i>
                            Lihat Pesanan Saya
                        </button>
                        <button class="btn btn-primary" onclick="contactSeller()" style="width: 100%;">
                            <i class="fab fa-whatsapp"></i>
                            Hubungi Penjual
                        </button>
                    </div>
                </div>
            `;

            let modal = document.getElementById('successModal');
            if (!modal) {{
                modal = document.createElement('div');
                modal.id = 'successModal';
                modal.className = 'modal';
                document.body.appendChild(modal);
            }}
            modal.innerHTML = modalContent;
            modal.style.display = 'block';

            confirmPayment();
        }}

        function closeModal(modalId) {{
            document.getElementById(modalId).style.display = 'none';
        }}

        function contactSeller() {{
            const orderNumber = window.currentOrderNumber;
            const totalAmount = window.currentTotalAmount;

            const message = "Hai Kak, saya telah melakukan pembayaran untuk:\\n\\n" +
                          "🛍️ Order #: " + orderNumber + "\\n" +
                          "💰 Total: Rp " + totalAmount.toLocaleString() + "\\n\\n" +
                          "Mohon konfirmasi pembayaran saya ya. Terima kasih! 😊";

            const phone = '+6285876127696';
            const url = 'https://wa.me/' + phone + '?text=' + encodeURIComponent(message);
            window.open(url, '_blank');
        }}

        function confirmPayment() {{
            fetch('/confirm_payment/' + window.currentOrderNumber, {{
                method: 'POST'
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    console.log('Payment confirmed successfully');
                }}
            }});
        }}

        function updateCartCount() {{
            fetch('/api/cart/count')
                .then(response => response.json())
                .then(data => {{
                    const cartBadge = document.getElementById('cart-count');
                    const cartFab = document.getElementById('cart-count-fab');

                    if (cartBadge) {{
                        cartBadge.textContent = data.count;
                        cartBadge.style.display = data.count > 0 ? 'flex' : 'none';
                    }}

                    if (cartFab) {{
                        cartFab.textContent = data.count;
                        cartFab.style.display = data.count > 0 ? 'flex' : 'none';
                    }}
                }});
        }}

        function resetBalances() {{
            const confirmMessage = '⚠️ PERINGATAN: RESET SALDO AWAL\\n\\n' +
                                 'Tindakan ini akan:\\n' +
                                 '1. Mengembalikan SEMUA saldo akun ke nilai default\\n' +
                                 '2. Mengatur ulang stok produk ke nilai awal\\n' +
                                 '3. TIDAK menghapus transaksi jurnal yang sudah ada\\n' +
                                 '4. Membutuhkan penyesuaian manual setelah reset\\n\\n' +
                                 'Apakah Anda yakin ingin mereset semua saldo ke default?';
            
            if (!confirm(confirmMessage)) {{
                return;
            }}
            
            // Tampilkan konfirmasi kedua
            const secondConfirm = '🔄 KONFIRMASI AKHIR\\n\\n' +
                                'Reset saldo akan:\\n' +
                                '• Kas: Rp 10,000,000\\n' +
                                '• Persediaan: Rp 5,000,000\\n' +
                                '• Perlengkapan: Rp 6,500,000\\n' +
                                '• Peralatan: Rp 5,000,000\\n' +
                                '• Utang: Rp 26,500,000\\n' +
                                '• Pendapatan: Rp 0\\n\\n' +
                                'Lanjutkan reset?';
            
            if (!confirm(secondConfirm)) {{
                return;
            }}
            
            const button = event.target;
            const originalText = button.innerHTML;

            button.innerHTML = '<div class="loading"></div> Resetting...';
            button.disabled = true;

            fetch('/seller/reset_balances', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{ confirm: true }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    showNotification('✅ ' + data.message, 'success');
                    setTimeout(() => location.reload(), 2000);
                }} else if (data.requires_confirm) {{
                    // Jika butuh konfirmasi, tampilkan modal konfirmasi
                    showResetConfirmationModal();
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }})
            .catch(error => {{
                showNotification('❌ Terjadi error saat reset saldo', 'error');
            }})
            .finally(() => {{
                setTimeout(() => {{
                    button.innerHTML = originalText;
                    button.disabled = false;
                }}, 2000);
            }});
        }}

        // Fungsi untuk menampilkan modal konfirmasi reset
        function showResetConfirmationModal() {{
            const modalContent = `
                <div class="modal-content">
                    <span class="close" onclick="closeModal('resetConfirmModal')">&times;</span>
                    <div style="text-align: center;">
                        <div style="width: 80px; height: 80px; background: linear-gradient(135deg, var(--warning) 0%, #b7791f 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
                            <i class="fas fa-exclamation-triangle" style="color: white; font-size: 2rem;"></i>
                        </div>
                        <h2 style="margin-bottom: 1rem; color: var(--warning);">Konfirmasi Reset</h2>
                        <p style="margin-bottom: 1rem; color: var(--dark);">
                            Reset saldo akan mengembalikan semua nilai ke default sistem.
                        </p>
                        <div style="text-align: left; background: rgba(229, 62, 62, 0.1); padding: 1rem; border-radius: var(--border-radius); margin: 1rem 0;">
                            <p style="margin: 0.5rem 0; font-weight: bold; color: var(--error);">
                                <i class="fas fa-bomb"></i> PERINGATAN:
                            </p>
                            <ul style="margin: 0.5rem 0; padding-left: 1.2rem; color: var(--error); font-size: 0.9rem;">
                                <li>Semua saldo akun akan diubah</li>
                                <li>Stok produk akan disesuaikan</li>
                                <li>Transaksi yang sudah ada TIDAK akan dihapus</li>
                                <li>Pastikan sudah backup data penting</li>
                            </ul>
                        </div>
                        <p style="color: var(--dark); opacity: 0.7; font-size: 0.9rem; margin-bottom: 2rem;">
                            Masukkan kata "RESET" untuk mengkonfirmasi:
                        </p>
                        <input type="text" id="resetConfirmInput" class="form-control" 
                               placeholder="Ketik RESET di sini" style="margin-bottom: 1rem;">
                    </div>

                    <div class="modal-buttons">
                        <button class="btn btn-danger" onclick="confirmReset()" 
                                style="width: 100%;" id="confirmResetBtn" disabled>
                            <i class="fas fa-bomb"></i>
                            Konfirmasi Reset
                        </button>
                    </div>
                </div>
            `;

            // Create modal
            let modal = document.createElement('div');
            modal.id = 'resetConfirmModal';
            modal.className = 'modal';
            modal.innerHTML = modalContent;
            document.body.appendChild(modal);
            modal.style.display = 'block';

            // Add input validation
            document.getElementById('resetConfirmInput').addEventListener('input', function() {{
                const confirmBtn = document.getElementById('confirmResetBtn');
                confirmBtn.disabled = this.value.toUpperCase() !== 'RESET';
            }});
        }}

        function confirmReset() {{
            const button = document.getElementById('confirmResetBtn');
            const originalText = button.innerHTML;

            button.innerHTML = '<div class="loading"></div> Resetting...';
            button.disabled = true;

            fetch('/seller/reset_balances', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{ confirm: true }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    closeModal('resetConfirmModal');
                    showNotification('✅ ' + data.message, 'success');
                    setTimeout(() => location.reload(), 1500);
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                    button.innerHTML = originalText;
                    button.disabled = false;
                }}
            }})
            .catch(error => {{
                showNotification('❌ Terjadi error saat reset saldo', 'error');
                button.innerHTML = originalText;
                button.disabled = false;
            }});
        }}

        function updateTracking(orderId, status) {{
            fetch('/update_tracking/' + orderId, {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    status: status,
                    tracking_info: document.getElementById('tracking-info-' + orderId).value
                }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    showNotification('✅ Status pengiriman diperbarui!', 'success');
                    setTimeout(() => location.reload(), 1000);
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }});
        }}

        function loadTransactionTemplate() {{
            const templateKey = document.getElementById('transaction_template').value;
            if (!templateKey) return;

            // === PENJUALAN SEDERHANA ===
            if (templateKey === 'penjualan_sederhana') {{
                fetch('/api/get_sales_form')
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            const formContainer = document.getElementById('templateFormContainer');
                            formContainer.innerHTML = data.form_html;
                        }} else {{
                            showNotification('❌ ' + data.message, 'error');
                        }}
                    }});
                return;
            }}

            // === PEMBELIAN SEDERHANA ===
            if (templateKey === 'pembelian_sederhana') {{
                fetch('/api/get_purchase_form')
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            const formContainer = document.getElementById('templateFormContainer');
                            formContainer.innerHTML = data.form_html;
                        }} else {{
                            showNotification('❌ ' + data.message, 'error');
                        }}
                    }});
                return;
            }}

            // === TEMPLATE LAINNYA ===
            fetch('/api/get_transaction_template/' + templateKey)
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        const formContainer = document.getElementById('templateFormContainer');
                        formContainer.innerHTML = data.form_html;

                        // Nonaktifkan formatting untuk input number
                        document.querySelectorAll('#templateFormContainer input[type="number"]').forEach(input => {{
                            // Biarkan input number bekerja normal
                            input.addEventListener('input', function() {{
                                // Hanya izinkan angka
                                this.value = this.value.replace(/[^\\d]/g, '');
                            }});
                        }});
                    }} else {{
                        showNotification('❌ ' + data.message, 'error');
                    }}
                }});
        }}

        function submitTemplateJournal() {{
            const formData = new FormData(document.getElementById('templateJournalForm'));
            const data = {{
                template_key: formData.get('template_key'),
                date: formData.get('date'),
                amounts: {{}},
                inputs: {{}}  // Tambah inputs
            }};

            // Collect amounts from form
            document.querySelectorAll('[id^=\"amount_\"]').forEach(input => {{
                const accountType = input.id.replace('amount_', '');
                data.amounts[accountType] = parseInt(input.value) || 0;
            }});

            // Collect inputs (quantity, unit_cost, dll)
            document.querySelectorAll('[id^=\"input_\"]').forEach(input => {{
                const inputName = input.id.replace('input_', '');
                data.inputs[inputName] = parseInt(input.value) || 0;
            }});

            // Validasi untuk template kerugian
            const templateKey = data.template_key;
            if (templateKey.includes('kerugian') || templateKey.includes('hibah')) {{
                if (!data.inputs.quantity || data.inputs.quantity <= 0) {{
                    showNotification('❌ Harap isi jumlah bibit yang mati/diberikan!', 'error');
                    return;
                }}
                if (!data.inputs.unit_cost || data.inputs.unit_cost <= 0) {{
                    showNotification('❌ Harap isi harga cost per unit!', 'error');
                    return;
                }}
            }}

            fetch('/seller/add_template_journal', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(data)
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    showNotification('✅ ' + data.message, 'success');
                    setTimeout(() => location.reload(), 1000);
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }});
        }}

        // Jurnal Penyesuaian Functions
        function loadAdjustmentTemplate() {{
            const templateKey = document.getElementById('adjustment_template').value;
            if (!templateKey) return;

            fetch('/api/get_adjustment_template/' + templateKey)
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        const formContainer = document.getElementById('adjustmentFormContainer');
                        formContainer.innerHTML = data.form_html;

                        // Add auto-format untuk input number
                        document.querySelectorAll('#adjustmentFormContainer input[type=\"number\"]').forEach(input => {{
                            input.addEventListener('input', function() {{
                                formatNumberInput(this);
                            }});

                            input.addEventListener('blur', function() {{
                                formatNumberInput(this);
                            }});

                            input.addEventListener('focus', function() {{
                                this.value = this.value.replace(/[^\\d]/g, '');
                            }});
                        }});
                    }} else {{
                        showNotification('❌ ' + data.message, 'error');
                    }}
                }});
        }}

        function submitAdjustmentJournal() {{
            const formData = new FormData(document.getElementById('adjustmentJournalForm'));
            const data = {{
                template_key: formData.get('template_key'),
                date: formData.get('date'),
                inputs: {{}}
            }};

            // Collect inputs from form dengan format number
            document.querySelectorAll('[id^=\"input_\"]').forEach(input => {{
                const inputName = input.id.replace('input_', '');
                data.inputs[inputName] = parseFormattedNumber(input.value);
            }});

            fetch('/seller/add_adjustment_journal', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(data)
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    showNotification('✅ ' + data.message, 'success');
                    setTimeout(() => location.reload(), 1000);
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }});
        }}

        // Jurnal Penutup Functions
        function createClosingEntries() {{
            // Tampilkan konfirmasi detail
            const confirmMessage = 'APAKAH ANDA YAKIN INGIN MEMBUAT JURNAL PENUTUP?\\n\\n' +
                                'Jurnal penutup akan:\\n' +
                                '1. Menutup semua akun pendapatan ke 0\\n' +
                                '2. Menutup semua akun beban ke 0\\n' +
                                '3. Menghitung laba/rugi bersih\\n' +
                                '4. Memindahkan laba/rugi ke akun Modal\\n' +
                                '5. Menutup akun Prive (jika ada)\\n\\n' +
                                'Proses ini TIDAK DAPAT DIBATALKAN!\\n\\n' +
                                'Lanjutkan membuat jurnal penutup?';

            if (!confirm(confirmMessage)) {{
                return;
            }}

            const button = event.target;
            const originalText = button.innerHTML;

            button.innerHTML = '<div class=\"loading\"></div> Membuat Jurnal Penutup...';
            button.disabled = true;

            fetch('/seller/create_closing_entries', {{
                method: 'POST'
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    showNotification('✅ ' + data.message, 'success');
                    
                    // 🔄 TAMPILKAN TAB JURNAL PENUTUP SETELAH BERHASIL
                    setTimeout(() => {{
                        // Aktifkan tab Jurnal Penutup
                        const closingTab = document.querySelector('[onclick*=\"jurnal-penutup\"]');
                        if (closingTab) {{
                            closingTab.click();
                        }}
                        
                        // Refresh konten tab Jurnal Penutup
                        refreshClosingTabContent();
                        
                        button.innerHTML = originalText;
                        button.disabled = false;
                    }}, 1500);
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                    button.innerHTML = originalText;
                    button.disabled = false;
                }}
            }})
            .catch(error => {{
                showNotification('❌ Terjadi error saat membuat jurnal penutup', 'error');
                button.innerHTML = originalText;
                button.disabled = false;
            }});
        }}

        // Fungsi untuk refresh konten tab Jurnal Penutup
        function refreshClosingTabContent() {{
            // Ambil tab content untuk Jurnal Penutup
            const closingTabContent = document.getElementById('jurnal-penutup');
            if (!closingTabContent) return;

            // Tampilkan loading
            closingTabContent.innerHTML = '<div style=\"text-align: center; padding: 2rem;\"><div class=\"loading\"></div> Memuat ulang data jurnal penutup...</div>';

            // Ambil data terbaru dari server
            fetch('/api/get_closing_entries_html')
            .then(response => response.text())
            .then(html => {{
                // Ganti konten tab dengan data terbaru
                closingTabContent.innerHTML = html;
                console.log('✅ Tab Jurnal Penutup di-refresh');
            }})
            .catch(error => {{
                console.error('Error refreshing closing tab:', error);
                closingTabContent.innerHTML = '<div class=\"card\"><p>Error loading closing entries</p></div>';
            }});
        }}

        // Number Formatting Functions - DISABLED untuk input number
        function formatNumberInput(input) {{
            // NONAKTIFKAN FORMATTING - biarkan input number seperti biasa
            // Hanya hapus karakter non-digit
            let value = input.value.replace(/[^\\d]/g, '');
            input.value = value; // Simpan nilai tanpa formatting
        }}

        function parseFormattedNumber(formattedValue) {{
            return parseInt(formattedValue.replace(/[^\\d]/g, '')) || 0;
        }}

        // Initialize when DOM is loaded
        document.addEventListener('DOMContentLoaded', function() {{
            updateCartCount();

            // Activate first tab by default
            const firstTab = document.querySelector('.tab');
            const firstTabContent = document.querySelector('.tab-content');
            if (firstTab && firstTabContent) {{
                firstTab.classList.add('active');
                firstTabContent.classList.add('active');
            }}

            // FIX: Remove auto-format untuk input number di form produk
            // Biarkan input number seperti biasa tanpa formatting
            document.querySelectorAll('input[type=\"number\"]').forEach(input => {{
                // Hapus event listener yang mengganggu
                input.removeEventListener('input', formatNumberInput);
                input.removeEventListener('blur', formatNumberInput);
                input.removeEventListener('focus', formatNumberInput);

                // Set nilai asli dari value attribute
                if (input.value) {{
                    input.value = input.value.replace(/\\./g, ''); // Hapus titik yang ada
                }}
            }});

            // Auto-hide flash messages after 5 seconds
            setTimeout(() => {{
                const flashMessages = document.querySelector('.flash-messages');
                if (flashMessages) {{
                    flashMessages.style.display = 'none';
                }}
            }}, 5000);

            // Close modal when clicking outside
            window.onclick = function(event) {{
                const modals = document.getElementsByClassName('modal');
                for (let modal of modals) {{
                    if (event.target == modal) {{
                        modal.style.display = 'none';
                    }}
                }}
            }}

            // Add smooth scrolling
            document.querySelectorAll('a[href^=\"#\"]').forEach(anchor => {{
                anchor.addEventListener('click', function (e) {{
                    e.preventDefault();
                    document.querySelector(this.getAttribute('href')).scrollIntoView({{
                        behavior: 'smooth'
                    }});
                }});
            }});
        }});
    </script>
</body>
</html>
'''

def get_navigation():
    if current_user.is_authenticated:
        user_badge = f"""
            <div class="user-menu">
                <div class="avatar">{current_user.avatar}</div>
                <div>
                    <div style="font-weight: 600; font-size: 0.95rem;">{current_user.full_name}</div>
                    <div class="badge">
                        {current_user.user_type.upper()}
                    </div>
                </div>
            </div>
        """

        nav_links = []

        if current_user.user_type == 'seller':
            nav_links.extend([
                '<a href="/seller/dashboard" class="nav-link"><i class="fas fa-chart-line"></i> Dashboard</a>',
                '<a href="/seller/orders" class="nav-link"><i class="fas fa-boxes"></i> Pesanan</a>',
                '<a href="/seller/inventory-card" class="nav-link"><i class="fas fa-boxes"></i> Kartu Persediaan</a>',
                '<a href="/seller/accounting" class="nav-link"><i class="fas fa-chart-bar"></i> Akuntansi</a>',
                '<a href="/seller/products" class="nav-link"><i class="fas fa-fish"></i> Produk</a>'
            ])
        elif current_user.user_type == 'customer':
            nav_links.extend([
                '<a href="/products" class="nav-link"><i class="fas fa-store"></i> Produk</a>',
                f'<a href="/cart" class="nav-link"><i class="fas fa-shopping-cart"></i> Keranjang <span id="cart-count" style="background: var(--error); color: white; border-radius: 50%; width: 20px; height: 20px; display: none; align-items: center; justify-content: center; font-size: 0.8rem; margin-left: 5px;">0</span></a>',
                '<a href="/orders" class="nav-link"><i class="fas fa-box"></i> Pesanan Saya</a>',
                '<a href="/profile" class="nav-link"><i class="fas fa-user"></i> Profile</a>'
            ])

        nav_links.append('<a href="/logout" class="nav-link"><i class="fas fa-sign-out-alt"></i> Logout</a>')

        return user_badge + ''.join(nav_links)
    else:
        return '''
            <a href="/login" class="nav-link"><i class="fas fa-sign-in-alt"></i> Login</a>
            <a href="/register" class="nav-link"><i class="fas fa-user-plus"></i> Register</a>
        '''

def get_flash_messages():
    messages = ""
    for category, message in get_flashed_messages(with_categories=True):
        messages += f'<div class="flash-message flash-{category}">{message}</div>'
    return messages

def get_account_options():
    accounts = Account.query.all()
    options = ""
    for account in accounts:
        options += f'<option value="{account.id}">{account.code} - {account.name}</option>'
    return options

def get_trial_balance_before_adjustment():
    """Neraca saldo sebelum penyesuaian - MENGGUNAKAN SALDO AWAL REAL dari database"""
    try:
        accounts = Account.query.order_by(Account.code).all()
        trial_balance_html = ""
        total_debit = total_credit = 0

        for account in accounts:
            # ✅✅✅ PERBAIKAN: HITUNG SALDO SEBELUM PENYESUAIAN DARI DATABASE
            
            # Langkah 1: Mulai dari saldo awal di database
            saldo_awal_murni = account.balance  # Saldo awal dari form edit
            
            # Langkah 2: KURANGI efek dari jurnal penyesuaian (karena ini "sebelum" penyesuaian)
            adjustment_details = JournalDetail.query.join(JournalEntry).filter(
                JournalDetail.account_id == account.id,
                JournalEntry.journal_type == 'adjustment'
            ).all()
            
            efek_penyesuaian = 0
            for detail in adjustment_details:
                if account.category in ['asset', 'expense']:
                    # Asset/Expense: Debit menambah, Credit mengurangi
                    efek_penyesuaian += detail.debit - detail.credit
                else:
                    # Liability/Equity/Revenue: Credit menambah, Debit mengurangi
                    efek_penyesuaian += detail.credit - detail.debit
            
            # Saldo sebelum penyesuaian = Saldo sekarang - efek penyesuaian
            saldo_sebelum_penyesuaian = saldo_awal_murni - efek_penyesuaian
            
            # Skip akun yang saldo 0
            if abs(saldo_sebelum_penyesuaian) < 0.01:  # Toleransi kecil
                continue

            # Tentukan posisi di neraca saldo
            if account.category in ['asset', 'expense']:
                if saldo_sebelum_penyesuaian >= 0:
                    debit = saldo_sebelum_penyesuaian
                    credit = 0
                else:
                    debit = 0
                    credit = abs(saldo_sebelum_penyesuaian)
            else:
                if saldo_sebelum_penyesuaian >= 0:
                    debit = 0
                    credit = saldo_sebelum_penyesuaian
                else:
                    debit = abs(saldo_sebelum_penyesuaian)
                    credit = 0

            total_debit += debit
            total_credit += credit

            trial_balance_html += f'''
            <tr>
                <td>{account.code}</td>
                <td>{account.name}</td>
                <td class="debit">{"Rp {0:,.0f}".format(debit) if debit > 0 else ""}</td>
                <td class="credit">{"Rp {0:,.0f}".format(credit) if credit > 0 else ""}</td>
            </tr>
            '''

        is_balanced = abs(total_debit - total_credit) < 0.01  # Toleransi kecil

        trial_balance_html += f'''
        <tr style="font-weight: bold; border-top: 2px solid var(--primary); background: rgba(56, 161, 105, 0.1);">
            <td colspan="2">TOTAL</td>
            <td class="debit">Rp {total_debit:,.0f}</td>
            <td class="credit">Rp {total_credit:,.0f}</td>
        </tr>
        <tr style="background: rgba(56, 161, 105, 0.2);">
            <td colspan="4" style="text-align: center; color: {'var(--success)' if is_balanced else 'var(--error)'}; font-weight: bold;">
                {'✅ NERACA SALDO SEBELUM PENYESUAIAN SEIMBANG' if is_balanced else '❌ NERACA SALDO SEBELUM PENYESUAIAN TIDAK SEIMBANG'}
            </td>
        </tr>
        '''

        return trial_balance_html

    except Exception as e:
        print(f"Error generating trial balance before adjustment: {e}")
        import traceback
        traceback.print_exc()
        return '<tr><td colspan="4">Error loading trial balance</td></tr>'

def get_trial_balance_after_adjustment():
    """Neraca saldo setelah penyesuaian = Saldo dari database (sudah termasuk semua jurnal)"""
    try:
        accounts = Account.query.order_by(Account.code).all()
        adjusted_trial_balance_html = ""
        total_debit = total_credit = 0

        # Gunakan saldo terkini dari database (sudah termasuk semua jurnal)
        for account in accounts:
            # Skip akun yang saldo 0
            if account.balance == 0:
                continue

            if account.category in ['asset', 'expense']:
                if account.balance >= 0:
                    debit = account.balance
                    credit = 0
                else:
                    debit = 0
                    credit = abs(account.balance)
            else:
                if account.balance >= 0:
                    debit = 0
                    credit = account.balance
                else:
                    debit = abs(account.balance)
                    credit = 0

            total_debit += debit
            total_credit += credit

            adjusted_trial_balance_html += f'''
            <tr>
                <td>{account.code}</td>
                <td>{account.name}</td>
                <td class="debit">{"Rp {0:,.0f}".format(debit) if debit > 0 else ""}</td>
                <td class="credit">{"Rp {0:,.0f}".format(credit) if credit > 0 else ""}</td>
            </tr>
            '''

        is_balanced = total_debit == total_credit

        adjusted_trial_balance_html += f'''
        <tr style="font-weight: bold; border-top: 2px solid var(--primary); background: rgba(56, 161, 105, 0.1);">
            <td colspan="2">TOTAL</td>
            <td class="debit">Rp {total_debit:,.0f}</td>
            <td class="credit">Rp {total_credit:,.0f}</td>
        </tr>
        <tr style="background: rgba(56, 161, 105, 0.2);">
            <td colspan="4" style="text-align: center; color: {'var(--success)' if is_balanced else 'var(--error)'}; font-weight: bold;">
                {'✅ NERACA SALDO SETELAH PENYESUAIAN SEIMBANG' if is_balanced else '❌ NERACA SALDO SETELAH PENYESUAIAN TIDAK SEIMBANG'}
            </td>
        </tr>
        '''

        return adjusted_trial_balance_html

    except Exception as e:
        print(f"Error generating adjusted trial balance: {e}")
        return '<tr><td colspan="4">Error loading adjusted trial balance</td></tr>'

def get_adjusted_trial_balance():
    """Generate neraca saldo setelah penyesuaian"""
    try:
        accounts = Account.query.order_by(Account.code).all()
        adjusted_trial_balance_html = ""
        total_debit = total_credit = 0

        # Ambil saldo terkini dari database (setelah penyesuaian)
        for account in accounts:
            # Skip akun yang saldo 0
            if account.balance == 0:
                continue

            if account.category in ['asset', 'expense']:
                if account.balance >= 0:
                    debit = account.balance
                    credit = 0
                else:
                    debit = 0
                    credit = abs(account.balance)
            else:
                if account.balance >= 0:
                    debit = 0
                    credit = account.balance
                else:
                    debit = abs(account.balance)
                    credit = 0

            total_debit += debit
            total_credit += credit

            adjusted_trial_balance_html += f'''
            <tr>
                <td>{account.code}</td>
                <td>{account.name}</td>
                <td class="debit">{"Rp {0:,.0f}".format(debit) if debit > 0 else ""}</td>
                <td class="credit">{"Rp {0:,.0f}".format(credit) if credit > 0 else ""}</td>
            </tr>
            '''

        is_balanced = total_debit == total_credit

        adjusted_trial_balance_html += f'''
        <tr style="font-weight: bold; border-top: 2px solid var(--primary); background: rgba(56, 161, 105, 0.1);">
            <td colspan="2">TOTAL</td>
            <td class="debit">Rp {total_debit:,.0f}</td>
            <td class="credit">Rp {total_credit:,.0f}</td>
        </tr>
        <tr style="background: rgba(56, 161, 105, 0.2);">
            <td colspan="4" style="text-align: center; color: {'var(--success)' if is_balanced else 'var(--error)'}; font-weight: bold;">
                {'✅ NERACA SALDO SETELAH PENYESUAIAN SEIMBANG' if is_balanced else '❌ NERACA SALDO SETELAH PENYESUAIAN TIDAK SEIMBANG'}
            </td>
        </tr>
        '''

        return adjusted_trial_balance_html

    except Exception as e:
        print(f"Error generating adjusted trial balance: {e}")
        return '<tr><td colspan="4">Error loading adjusted trial balance</td></tr>'

def get_general_journal_entries():
    """Tampilkan jurnal umum dengan format baru - DESKRIPSI DI HEADER"""
    try:
        journal_entries = JournalEntry.query.filter(
            JournalEntry.journal_type.in_(['general', 'sales', 'purchase', 'hpp'])
        ).order_by(JournalEntry.date.desc(), JournalEntry.id.desc()).all()

        if not journal_entries:
            return '''
            <div class="card">
                <h4 style="color: var(--primary);">Belum Ada Jurnal Umum</h4>
                <p>Belum ada transaksi jurnal yang tercatat.</p>
            </div>
            '''

        # HITUNG TOTAL KESELURUHAN
        total_all_debit = 0
        total_all_credit = 0
        
        for journal in journal_entries:
            total_all_debit += sum(d.debit for d in journal.journal_details)
            total_all_credit += sum(d.credit for d in journal.journal_details)

        table_html = f'''
        <div class="card">
            <h4 style="color: var(--primary); margin-bottom: 1.5rem;">
                <i class="fas fa-list"></i> Daftar Jurnal Umum
                <span style="font-size: 0.9rem; color: #6B7280; font-weight: normal; margin-left: 1rem;">
                    ({len(journal_entries)} transaksi)
                </span>
            </h4>
            
            <!-- TOTAL KESELURUHAN CARD -->
            <div style="background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%); color: white; padding: 1.5rem; border-radius: var(--border-radius); margin-bottom: 1.5rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h5 style="margin: 0; color: white;">
                            <i class="fas fa-calculator"></i> TOTAL KESELURUHAN JURNAL UMUM
                        </h5>
                        <p style="margin: 0.5rem 0 0 0; opacity: 0.9; font-size: 0.9rem;">
                            Seluruh transaksi jurnal umum yang tercatat
                        </p>
                    </div>
                    <div style="text-align: right;">
                        <div style="display: flex; gap: 2rem;">
                            <div>
                                <div style="font-size: 0.9rem; opacity: 0.9;">TOTAL DEBIT</div>
                                <div style="font-size: 1.5rem; font-weight: bold; color: #A7F3D0;">Rp {total_all_debit:,.0f}</div>
                            </div>
                            <div>
                                <div style="font-size: 0.9rem; opacity: 0.9;">TOTAL KREDIT</div>
                                <div style="font-size: 1.5rem; font-weight: bold; color: #FECACA;">Rp {total_all_credit:,.0f}</div>
                            </div>
                        </div>
                        <div style="margin-top: 0.5rem; padding: 0.5rem 1rem; background: rgba(255, 255, 255, 0.2); border-radius: var(--border-radius); font-size: 0.9rem;">
                            {"✅ SELARAS" if total_all_debit == total_all_credit else "⚠️ TIDAK SELARAS"}
                        </div>
                    </div>
                </div>
            </div>

            <div style="overflow-x: auto;">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Tanggal</th>
                            <th>No. Transaksi</th>
                            <th>Akun</th>
                            <th>Ref</th>
                            <th>Debit</th>
                            <th>Kredit</th>
                        </tr>
                    </thead>
                    <tbody>
        '''

        current_date = None
        
        for journal in journal_entries:
            # HEADER TRANSAKSI - TANGGAL, NO TRANSAKSI, DESKRIPSI
            journal_date = journal.date.strftime('%d/%m/%Y')
            
            # Header dengan deskripsi
            table_html += f'''
            <tr style="background: rgba(49, 130, 206, 0.1); font-weight: bold;">
                <td>{journal.date.strftime('%d/%m/%Y %H:%M')}</td>
                <td>{journal.transaction_number}</td>
                <td colspan="4" style="color: var(--primary);">
                    {journal.description}
                </td>
            </tr>
            '''

            # DETAIL AKUN - TANPA DESKRIPSI LAGI
            for detail in journal.journal_details:
                # Tentukan nominal dan kelas
                if detail.debit > 0:
                    debit_amount = detail.debit
                    credit_amount = ""
                    amount_class = "debit"
                else:
                    debit_amount = ""
                    credit_amount = detail.credit
                    amount_class = "credit"
                
                table_html += f'''
                <tr>
                    <td style="border-left: 3px solid rgba(49, 130, 206, 0.3);"></td>
                    <td></td>
                    <td>{detail.account.name}</td>
                    <td>{detail.account.code}</td>
                    <td class="debit">{"Rp {0:,.0f}".format(detail.debit) if detail.debit > 0 else ""}</td>
                    <td class="credit">{"Rp {0:,.0f}".format(detail.credit) if detail.credit > 0 else ""}</td>
                </tr>
                '''

            # TOTAL PER JURNAL
            total_debit = sum(d.debit for d in journal.journal_details)
            total_credit = sum(d.credit for d in journal.journal_details)
            
            table_html += f'''
            <tr style="background: rgba(0,0,0,0.02);">
                <td colspan="4" style="text-align: right; font-weight: bold; padding: 0.5rem 1rem; border-top: 1px solid rgba(0,0,0,0.1);">
                    Total Jurnal:
                </td>
                <td class="debit" style="font-weight: bold; border-top: 1px solid rgba(0,0,0,0.1);">Rp {total_debit:,.0f}</td>
                <td class="credit" style="font-weight: bold; border-top: 1px solid rgba(0,0,0,0.1);">Rp {total_credit:,.0f}</td>
            </tr>
            <tr><td colspan="6" style="height: 1rem; background: transparent;"></td></tr>
            '''

        table_html += '''
                    </tbody>
                </table>
            </div>
        </div>
        '''
        
        return table_html
        
    except Exception as e:
        print(f"Error generating general journal entries: {e}")
        return '<div class="card"><p>Error loading journal entries</p></div>'

def get_adjustment_journal_entries():
    """Tampilkan jurnal penyesuaian dengan format baru - DESKRIPSI DI HEADER"""
    try:
        journal_entries = JournalEntry.query.filter_by(journal_type='adjustment').order_by(
            JournalEntry.date.desc(), JournalEntry.id.desc()
        ).all()

        if not journal_entries:
            return '''
            <div class="card">
                <h4 style="color: var(--primary);">Belum Ada Jurnal Penyesuaian</h4>
                <p>Gunakan form Jurnal Penyesuaian di atas untuk menambahkan jurnal penyesuaian pertama.</p>
            </div>
            '''

        # HITUNG TOTAL KESELURUHAN
        total_all_debit = 0
        total_all_credit = 0
        
        for journal in journal_entries:
            total_all_debit += sum(d.debit for d in journal.journal_details)
            total_all_credit += sum(d.credit for d in journal.journal_details)

        table_html = f'''
        <div class="card">
            <h4 style="color: var(--primary); margin-bottom: 1.5rem;">
                <i class="fas fa-calculator"></i> Daftar Jurnal Penyesuaian
                <span style="font-size: 0.9rem; color: #6B7280; font-weight: normal; margin-left: 1rem;">
                    ({len(journal_entries)} penyesuaian)
                </span>
            </h4>
            
            <!-- TOTAL KESELURUHAN CARD -->
            <div style="background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%); color: white; padding: 1.5rem; border-radius: var(--border-radius); margin-bottom: 1.5rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h5 style="margin: 0; color: white;">
                            <i class="fas fa-balance-scale"></i> TOTAL KESELURUHAN JURNAL PENYESUAIAN
                        </h5>
                        <p style="margin: 0.5rem 0 0 0; opacity: 0.9; font-size: 0.9rem;">
                            Seluruh nilai penyesuaian akuntansi
                        </p>
                    </div>
                    <div style="text-align: right;">
                        <div style="display: flex; gap: 2rem;">
                            <div>
                                <div style="font-size: 0.9rem; opacity: 0.9;">TOTAL DEBIT</div>
                                <div style="font-size: 1.5rem; font-weight: bold; color: #A7F3D0;">Rp {total_all_debit:,.0f}</div>
                            </div>
                            <div>
                                <div style="font-size: 0.9rem; opacity: 0.9;">TOTAL KREDIT</div>
                                <div style="font-size: 1.5rem; font-weight: bold; color: #FECACA;">Rp {total_all_credit:,.0f}</div>
                            </div>
                        </div>
                        <div style="margin-top: 0.5rem; padding: 0.5rem 1rem; background: rgba(255, 255, 255, 0.2); border-radius: var(--border-radius); font-size: 0.9rem;">
                            Balance: {"✅ SELARAS" if total_all_debit == total_all_credit else "⚠️ TIDAK SELARAS"}
                        </div>
                    </div>
                </div>
            </div>

            <div style="overflow-x: auto;">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Tanggal</th>
                            <th>No. Transaksi</th>
                            <th>Akun</th>
                            <th>Ref</th>
                            <th>Debit</th>
                            <th>Kredit</th>
                        </tr>
                    </thead>
                    <tbody>
        '''
        
        for journal in journal_entries:
            # HEADER TRANSAKSI - TANGGAL, NO TRANSAKSI, DESKRIPSI
            table_html += f'''
            <tr style="background: rgba(56, 161, 105, 0.1); font-weight: bold;">
                <td>{journal.date.strftime('%d/%m/%Y %H:%M')}</td>
                <td>{journal.transaction_number}</td>
                <td colspan="4" style="color: var(--success);">
                    {journal.description}
                </td>
            </tr>
            '''

            # DETAIL AKUN - TANPA DESKRIPSI LAGI
            for detail in journal.journal_details:
                table_html += f'''
                <tr>
                    <td style="border-left: 3px solid rgba(56, 161, 105, 0.3);"></td>
                    <td></td>
                    <td>{detail.account.name}</td>
                    <td>{detail.account.code}</td>
                    <td class="debit">{"Rp {0:,.0f}".format(detail.debit) if detail.debit > 0 else ""}</td>
                    <td class="credit">{"Rp {0:,.0f}".format(detail.credit) if detail.credit > 0 else ""}</td>
                </tr>
                '''

            # TOTAL PER JURNAL
            total_debit = sum(d.debit for d in journal.journal_details)
            total_credit = sum(d.credit for d in journal.journal_details)
            
            table_html += f'''
            <tr style="background: rgba(56, 161, 105, 0.03);">
                <td colspan="4" style="text-align: right; font-weight: bold; padding: 0.5rem 1rem; border-top: 1px solid rgba(56, 161, 105, 0.1);">
                    Total Penyesuaian:
                </td>
                <td class="debit" style="font-weight: bold; border-top: 1px solid rgba(56, 161, 105, 0.1);">Rp {total_debit:,.0f}</td>
                <td class="credit" style="font-weight: bold; border-top: 1px solid rgba(56, 161, 105, 0.1);">Rp {total_credit:,.0f}</td>
            </tr>
            <tr><td colspan="6" style="height: 1rem; background: transparent;"></td></tr>
            '''

        table_html += '''
                    </tbody>
                </table>
            </div>
        </div>
        '''

        return table_html
        
    except Exception as e:
        print(f"Error generating adjustment journal entries: {e}")
        return '<div class="card"><p>Error loading adjustment journal entries</p></div>'

def verify_nominal_accounts_closed():
    """Verifikasi apakah semua akun nominal sudah ditutup (saldo = 0)"""
    try:
        # Cek akun nominal
        revenue_accounts = Account.query.filter_by(category='revenue').all()
        expense_accounts = Account.query.filter_by(category='expense').all()
        prive_accounts = Account.query.filter_by(type='prive').all()
        
        all_closed = True
        issues = []
        
        # Cek pendapatan
        for acc in revenue_accounts:
            if abs(acc.balance) > 0.01:
                all_closed = False
                issues.append(f"Pendapatan '{acc.name}' belum 0: Rp {acc.balance:,.0f}")
        
        # Cek beban
        for acc in expense_accounts:
            if abs(acc.balance) > 0.01:
                all_closed = False
                issues.append(f"Beban '{acc.name}' belum 0: Rp {acc.balance:,.0f}")
        
        # Cek prive
        for acc in prive_accounts:
            if abs(acc.balance) > 0.01:
                all_closed = False
                issues.append(f"Prive '{acc.name}' belum 0: Rp {acc.balance:,.0f}")
        
        return {
            'all_closed': all_closed,
            'issues': issues
        }
        
    except Exception as e:
        print(f"Error verifying nominal accounts: {e}")
        return {'all_closed': False, 'issues': [f'Error: {str(e)}']}

# ... di sini fungsi get_income_statement() dimulai ...

def get_income_statement():
    """Generate income statement HTML"""
    try:
        # Get revenue accounts
        revenue_accounts = Account.query.filter_by(category='revenue').all()
        total_revenue = sum(acc.balance for acc in revenue_accounts)

        # Get expense accounts
        expense_accounts = Account.query.filter_by(category='expense').all()
        total_expenses = sum(acc.balance for acc in expense_accounts)

        net_income = total_revenue - total_expenses

        revenue_html = ""
        for acc in revenue_accounts:
            if acc.balance > 0:
                revenue_html += f'''
                <tr>
                    <td>{acc.name}</td>
                    <td class="debit">Rp {acc.balance:,.0f}</td>
                </tr>
                '''

        expense_html = ""
        for acc in expense_accounts:
            if acc.balance > 0:
                expense_html += f'''
                <tr>
                    <td>{acc.name}</td>
                    <td class="credit">Rp {acc.balance:,.0f}</td>
                </tr>
                '''

        return f'''
        <table class="table">
            <thead>
                <tr>
                    <th>Pendapatan</th>
                    <th>Jumlah</th>
                </tr>
            </thead>
            <tbody>
                {revenue_html}
                <tr style="font-weight: bold; border-top: 2px solid var(--primary);">
                    <td>Total Pendapatan</td>
                    <td class="debit">Rp {total_revenue:,.0f}</td>
                </tr>
            </tbody>
        </table>

        <table class="table" style="margin-top: 2rem;">
            <thead>
                <tr>
                    <th>Beban</th>
                    <th>Jumlah</th>
                </tr>
            </thead>
            <tbody>
                {expense_html}
                <tr style="font-weight: bold; border-top: 2px solid var(--primary);">
                    <td>Total Beban</td>
                    <td class="credit">Rp {total_expenses:,.0f}</td>
                </tr>
            </tbody>
        </table>

        <div style="margin-top: 2rem; padding: 1.5rem; background: {'rgba(56, 161, 105, 0.1)' if net_income >= 0 else 'rgba(229, 62, 62, 0.1)'}; border-radius: var(--border-radius);">
            <h4 style="color: {'var(--success)' if net_income >= 0 else 'var(--error)'};">
                {'Laba Bersih' if net_income >= 0 else 'Rugi Bersih'}:
                <span style="{'debit' if net_income >= 0 else 'credit'}">Rp {abs(net_income):,.0f}</span>
            </h4>
        </div>
        '''
    except Exception as e:
        print(f"Error generating income statement: {e}")
        return '<p>Error loading income statement</p>'

# Dalam fungsi get_simplified_accounting_content(), cari bagian saldo awal dan perbaiki:
def get_simplified_accounting_content():
    """Konten akuntansi yang disederhanakan - OTOMATIS dari database"""
    
    # Get template options
    template_options = ""
    for key, template in TRANSACTION_TEMPLATES.items():
        template_options += f'<option value="{key}">{template["name"]}</option>'

    adjustment_options = ""
    for key, template in ADJUSTMENT_TEMPLATES.items():
        adjustment_options += f'<option value="{key}">{template["name"]}</option>'

    content = f'''
    <h1 style="color: var(--primary);"><i class="fas fa-chart-bar"></i> Sistem Akuntansi</h1>

    <div class="accounting-tabs">
        <button class="tab active" onclick="showTab(\'chart-of-accounts\', this)">Chart of Accounts</button>
        <button class="tab" onclick="showTab(\'saldo-awal\', this)">Saldo Awal</button>
        <button class="tab" onclick="showTab(\'jurnal-umum\', this)">Jurnal Umum</button>
        <button class="tab" onclick="showTab(\'buku-besar\', this)">Buku Besar</button>
        <button class="tab" onclick="showTab(\'neraca-saldo\', this)">Neraca Saldo</button>
        <button class="tab" onclick="showTab(\'jurnal-penyesuaian\', this)">Jurnal Penyesuaian</button>
        <button class="tab" onclick="showTab(\'neraca-saldo-setelah\', this)">Neraca Setelah Penyesuaian</button>
        <button class="tab" onclick="showTab(\'laporan-keuangan\', this)">Laporan Keuangan</button>
        <button class="tab" onclick="showTab(\'jurnal-penutup\', this)">Jurnal Penutup</button>
        <button class="tab" onclick="showTab(\'neraca-saldo-penutupan\', this)">Neraca Saldo Setelah Penutupan</button>
    </div>

    <div id="chart-of-accounts" class="tab-content active">
        {get_chart_of_accounts_content()}
    </div>

    <div id="saldo-awal" class="tab-content">
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <h3 style="color: var(--primary); margin: 0;"><i class="fas fa-file-invoice-dollar"></i> Saldo Awal</h3>
                <div>
                    <a href="/seller/edit_initial_balances" class="btn btn-warning">
                        <i class="fas fa-edit"></i> Edit Saldo Awal
                    </a>
                    <button class="btn btn-info" onclick="resetBalances()" style="margin-left: 0.5rem;">
                        <i class="fas fa-undo"></i> Reset Default
                    </button>
                </div>
            </div>
        
            <p style="margin-bottom: 1rem; color: #6B7280;">
                <i class="fas fa-info-circle"></i> Saldo awal diambil secara otomatis dari database. 
                <strong>Hanya menampilkan akun REAL (Aset, Kewajiban, Ekuitas).</strong>
                Pendapatan & Beban tidak memiliki saldo awal (selalu 0).
            </p>
        
            <div style="background: var(--ocean-light); padding: 1rem; border-radius: var(--border-radius); margin-bottom: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h5 style="color: var(--primary); margin: 0;">Neraca Saldo Awal (Akun REAL saja)</h5>
                        <p style="margin: 0.25rem 0 0 0; font-size: 0.9rem;">
                            Aset = Kewajiban + Ekuitas | Pendapatan & Beban = 0
                        </p>
                    </div>
                    <div style="text-align: right;">
                        <a href="/seller/edit_initial_balances" class="btn btn-sm btn-primary">
                            <i class="fas fa-calculator"></i> Sesuaikan Saldo REAL
                        </a>
                    </div>
                </div>
            </div>
        
            <table class="table">
                <thead>
                    <tr>
                        <th>Akun (REAL saja)</th>
                        <th>Kode</th>
                        <th>Debit</th>
                        <th>Kredit</th>
                    </tr>
                </thead>
                <tbody>
                    {get_saldo_awal_html()}
                </tbody>
            </table>
        
            <!-- Informasi tentang akun nominal -->
            <div style="margin-top: 1.5rem; padding: 1rem; background: rgba(156, 163, 175, 0.1); border-radius: var(--border-radius);">
                <h5 style="color: #6B7280; margin-bottom: 0.5rem;">
                    <i class="fas fa-info-circle"></i> Informasi Akun Nominal
                </h5>
                <p style="margin: 0; font-size: 0.9rem;">
                    <strong>Pendapatan & Beban</strong> adalah akun nominal yang saldo awalnya selalu 0.
                    Mereka tidak muncul di saldo awal karena akan ditutup di akhir periode akuntansi.
                    Akun nominal hanya akan memiliki saldo dari transaksi selama periode berjalan.
                </p>
            </div>
        
            <!-- Reset Warning -->
            <div style="margin-top: 1.5rem; padding: 1rem; background: rgba(229, 62, 62, 0.1); border-radius: var(--border-radius);">
                <h5 style="color: var(--error); margin-bottom: 0.5rem;">
                    <i class="fas fa-exclamation-triangle"></i> Reset ke Default
                </h5>
                <p style="margin: 0; font-size: 0.9rem;">
                    Tombol "Reset Default" akan mengembalikan semua saldo REAL ke nilai default sistem. 
                    <strong>Akun nominal (Pendapatan & Beban) akan direset ke 0.</strong>
                </p>
                <button class="btn btn-danger" onclick="resetBalances()" style="margin-top: 0.5rem;">
                    <i class="fas fa-bomb"></i> Reset Semua ke Nilai Default
                </button>
            </div>
        </div>
    </div>

    <div id="jurnal-umum" class="tab-content">
        <div class="card">
            <!-- BAGIAN BARU: Form untuk membuat jurnal baru -->
            <div style="margin-bottom: 2rem;">
                <h3 style="color: var(--primary); margin-bottom: 1rem;">
                    <i class="fas fa-plus-circle"></i> Buat Jurnal Umum Baru
                </h3>
                
                <div class="card" style="background: var(--ocean-light); padding: 1.5rem; border-radius: var(--border-radius);">
                    <h4 style="color: var(--primary); margin-bottom: 1rem;">
                        <i class="fas fa-calculator"></i> Pilih Template Transaksi
                    </h4>
                    
                    <div class="form-group">
                        <label class="form-label">Jenis Transaksi</label>
                        <select id="transaction_template" class="form-control" onchange="loadTransactionTemplate()">
                            <option value="">-- Pilih Template Transaksi --</option>
                            {template_options}
                        </select>
                    </div>
                    
                    <div id="templateFormContainer">
                        <!-- Form akan dimuat di sini otomatis -->
                    </div>
                </div>
            </div>
            
            <!-- Daftar jurnal yang sudah ada -->
            {get_general_journal_entries()}
        </div>
    </div>

    <div id="buku-besar" class="tab-content">
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-book"></i> Buku Besar</h3>
            <p style="margin-bottom: 1rem; color: #6B7280;">
                <i class="fas fa-info-circle"></i> Buku besar menampilkan semua transaksi per akun.
            </p>
            {get_ledger_data()}
        </div>
    </div>

    <div id="neraca-saldo" class="tab-content">
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-balance-scale"></i> Neraca Saldo Sebelum Penyesuaian</h3>
            <p style="margin-bottom: 1rem; color: #6B7280;">
                <i class="fas fa-info-circle"></i> Neraca saldo dihitung otomatis dari saldo awal + jurnal umum.
            </p>
            <table class="table">
                <thead>
                    <tr>
                        <th>Kode</th>
                        <th>Nama Akun</th>
                        <th>Debit</th>
                        <th>Kredit</th>
                    </tr>
                </thead>
                <tbody>
                    {get_trial_balance_before_adjustment()}
                </tbody>
            </table>
        </div>
    </div>

    <div id="jurnal-penyesuaian" class="tab-content">
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-calculator"></i> Jurnal Penyesuaian</h3>

            <div class="card">
                <h4 style="color: var(--primary);">Buat Jurnal Penyesuaian</h4>

                <div class="form-group">
                    <label class="form-label">Jenis Penyesuaian</label>
                    <select id="adjustment_template" class="form-control" onchange="loadAdjustmentTemplate()">
                        <option value="">Pilih Jenis Penyesuaian</option>
                        {adjustment_options}
                    </select>
                </div>

                <div id="adjustmentFormContainer">
                    <!-- Form akan dimuat di sini -->
                </div>
            </div>

            {get_adjustment_journal_entries()}
        </div>
    </div>

    <div id="neraca-saldo-setelah" class="tab-content">
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-balance-scale"></i> Neraca Saldo Setelah Penyesuaian</h3>
            <table class="table">
                <thead>
                    <tr>
                        <th>Kode</th>
                        <th>Nama Akun</th>
                        <th>Debit</th>
                        <th>Kredit</th>
                    </tr>
                </thead>
                <tbody>
                    {get_adjusted_trial_balance()}
                </tbody>
            </table>
        </div>
    </div>

    <div id="laporan-keuangan" class="tab-content">
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-chart-line"></i> Laporan Laba Rugi</h3>
            {get_income_statement()}
        </div>

        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-balance-scale-left"></i> Laporan Posisi Keuangan (Neraca)</h3>
            {get_balance_sheet()}
        </div>

        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-chart-line"></i> Laporan Perubahan Ekuitas</h3>
            {get_equity_change_statement()}
        </div>
    </div>

    <div id="jurnal-penutup" class="tab-content">
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-door-closed"></i> Jurnal Penutup</h3>
            
            <!-- Konten akan dimuat via JavaScript -->
            <div id="closing-tab-content">
                <div style="text-align: center; padding: 2rem;">
                    <div class="loading"></div> Memuat data jurnal penutup...
                </div>
            </div>
        </div>
    </div>

    <div id="neraca-saldo-penutupan" class="tab-content">
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-balance-scale"></i> Neraca Saldo Setelah Penutupan</h3>
            <p style="margin-bottom: 1rem; color: #6B7280;">
                <i class="fas fa-info-circle"></i> Neraca saldo yang hanya berisi akun REAL (Aset, Kewajiban, Modal) setelah semua akun nominal ditutup.
            </p>
            {get_post_closing_trial_balance()}
        </div>
    </div>

    <script>
    // Load closing entries saat tab dibuka
    document.addEventListener('DOMContentLoaded', function() {{
        // Add event listener untuk tab Jurnal Penutup
        const closingTab = document.querySelector('[onclick*="jurnal-penutup"]');
        if (closingTab) {{
            closingTab.addEventListener('click', function() {{
                loadClosingTabContent();
            }});
        }}
        
        // Add event listener untuk tab Neraca Saldo Setelah Penutupan
        const postClosingTab = document.querySelector('[onclick*="neraca-saldo-penutupan"]');
        if (postClosingTab) {{
            postClosingTab.addEventListener('click', function() {{
                // Jika perlu refresh data, bisa tambahkan di sini
                console.log("Tab Neraca Saldo Setelah Penutupan dibuka");
            }});
        }}
    }});

    function loadClosingTabContent() {{
        const container = document.getElementById('closing-tab-content');
        if (!container) return;
        
        fetch('/api/get_closing_entries_html')
        .then(response => response.text())
        .then(html => {{
            container.innerHTML = html;
        }})
        .catch(error => {{
            console.error('Error loading closing tab:', error);
            container.innerHTML = '<div class="card"><p>Error loading closing entries</p></div>';
        }});
    }}

    // Load saat pertama kali halaman dibuka jika tab jurnal-penutup aktif
    if (document.getElementById('jurnal-penutup').classList.contains('active')) {{
        loadClosingTabContent();
    }}
    
    // Load saat pertama kali halaman dibuka jika tab neraca-saldo-penutupan aktif
    if (document.getElementById('neraca-saldo-penutupan').classList.contains('active')) {{
        console.log("Tab Neraca Saldo Setelah Penutupan aktif saat halaman dimuat");
    }}
    </script>
    '''

    return content

def get_chart_of_accounts_content():
    """Generate content untuk Chart of Accounts tab"""
    try:
        # Get all accounts grouped by category
        assets = Account.query.filter_by(category='asset').order_by(Account.code).all()
        liabilities = Account.query.filter_by(category='liability').order_by(Account.code).all()
        equity = Account.query.filter_by(category='equity').order_by(Account.code).all()
        revenue = Account.query.filter_by(category='revenue').order_by(Account.code).all()
        expenses = Account.query.filter_by(category='expense').order_by(Account.code).all()

        total_assets = sum(acc.balance for acc in assets)
        total_liabilities = sum(acc.balance for acc in liabilities)
        total_equity = sum(acc.balance for acc in equity)
        total_revenue = sum(acc.balance for acc in revenue)
        total_expenses = sum(acc.balance for acc in expenses)

        return f'''
        <div class="card">
            <h3 style="color: var(--primary); margin-bottom: 1.5rem;">
                <i class="fas fa-sitemap"></i> Chart of Accounts
            </h3>
            <p style="margin-bottom: 2rem; color: #6B7280;">
                Daftar lengkap semua akun yang digunakan dalam sistem akuntansi Kang-Mas Shop
            </p>

            <!-- Quick Stats -->
            <div class="stats" style="margin-bottom: 2rem;">
                <div class="stat-card">
                    <div class="stat-number">{len(assets)}</div>
                    <div class="stat-label">Akun Aset</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{len(liabilities)}</div>
                    <div class="stat-label">Akun Kewajiban</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{len(equity)}</div>
                    <div class="stat-label">Akun Ekuitas</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{len(expenses)}</div>
                    <div class="stat-label">Akun Beban</div>
                </div>
            </div>

            <!-- ASET -->
            <div style="margin-bottom: 3rem;">
                <h4 style="color: var(--success); margin-bottom: 1rem; padding: 1rem; background: rgba(56, 161, 105, 0.1); border-radius: var(--border-radius); display: flex; justify-content: space-between; align-items: center;">
                    <span><i class="fas fa-wallet"></i> ASET (Assets) - Normal Balance: Debit</span>
                    <span class="debit">Total: Rp {total_assets:,.0f}</span>
                </h4>
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Kode</th>
                                <th>Nama Akun</th>
                                <th>Tipe</th>
                                <th>Saldo</th>
                                <th>Keterangan</th>
                            </tr>
                        </thead>
                        <tbody>
        ''' + ''.join([f'''
                            <tr>
                                <td><strong>{acc.code}</strong></td>
                                <td>{acc.name}</td>
                                <td><span class="badge" style="background: var(--success);">{acc.type}</span></td>
                                <td class="debit">Rp {acc.balance:,.0f}</td>
                                <td>Akun {acc.category.title()}</td>
                            </tr>''' for acc in assets]) + f'''
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- KEWAJIBAN -->
            <div style="margin-bottom: 3rem;">
                <h4 style="color: var(--error); margin-bottom: 1rem; padding: 1rem; background: rgba(229, 62, 62, 0.1); border-radius: var(--border-radius); display: flex; justify-content: space-between; align-items: center;">
                    <span><i class="fas fa-hand-holding-usd"></i> KEWAJIBAN (Liabilities) - Normal Balance: Credit</span>
                    <span class="credit">Total: Rp {total_liabilities:,.0f}</span>
                </h4>
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Kode</th>
                                <th>Nama Akun</th>
                                <th>Tipe</th>
                                <th>Saldo</th>
                                <th>Keterangan</th>
                            </tr>
                        </thead>
                        <tbody>
        ''' + ''.join([f'''
                            <tr>
                                <td><strong>{acc.code}</strong></td>
                                <td>{acc.name}</td>
                                <td><span class="badge" style="background: var(--error);">{acc.type}</span></td>
                                <td class="credit">Rp {acc.balance:,.0f}</td>
                                <td>Akun {acc.category.title()}</td>
                            </tr>''' for acc in liabilities]) + f'''
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- EKUITAS -->
            <div style="margin-bottom: 3rem;">
                <h4 style="color: var(--primary); margin-bottom: 1rem; padding: 1rem; background: rgba(49, 130, 206, 0.1); border-radius: var(--border-radius); display: flex; justify-content: space-between; align-items: center;">
                    <span><i class="fas fa-user-tie"></i> EKUITAS (Equity) - Normal Balance: Credit</span>
                    <span class="credit">Total: Rp {total_equity:,.0f}</span>
                </h4>
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Kode</th>
                                <th>Nama Akun</th>
                                <th>Tipe</th>
                                <th>Saldo</th>
                                <th>Keterangan</th>
                            </tr>
                        </thead>
                        <tbody>
        ''' + ''.join([f'''
                            <tr>
                                <td><strong>{acc.code}</strong></td>
                                <td>{acc.name}</td>
                                <td><span class="badge" style="background: var(--primary);">{acc.type}</span></td>
                                <td class="credit">Rp {acc.balance:,.0f}</td>
                                <td>Akun {acc.category.title()}</td>
                            </tr>''' for acc in equity]) + f'''
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- PENDAPATAN -->
            <div style="margin-bottom: 3rem;">
                <h4 style="color: var(--teal); margin-bottom: 1rem; padding: 1rem; background: rgba(49, 130, 206, 0.1); border-radius: var(--border-radius); display: flex; justify-content: space-between; align-items: center;">
                    <span><i class="fas fa-chart-line"></i> PENDAPATAN (Revenue) - Normal Balance: Credit</span>
                    <span class="credit">Total: Rp {total_revenue:,.0f}</span>
                </h4>
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Kode</th>
                                <th>Nama Akun</th>
                                <th>Tipe</th>
                                <th>Saldo</th>
                                <th>Keterangan</th>
                            </tr>
                        </thead>
                        <tbody>
        ''' + ''.join([f'''
                            <tr>
                                <td><strong>{acc.code}</strong></td>
                                <td>{acc.name}</td>
                                <td><span class="badge" style="background: var(--teal);">{acc.type}</span></td>
                                <td class="credit">Rp {acc.balance:,.0f}</td>
                                <td>Akun {acc.category.title()}</td>
                            </tr>''' for acc in revenue]) + f'''
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- BEBAN -->
            <div style="margin-bottom: 2rem;">
                <h4 style="color: var(--warning); margin-bottom: 1rem; padding: 1rem; background: rgba(214, 158, 46, 0.1); border-radius: var(--border-radius); display: flex; justify-content: space-between; align-items: center;">
                    <span><i class="fas fa-money-bill-wave"></i> BEBAN (Expenses) - Normal Balance: Debit</span>
                    <span class="debit">Total: Rp {total_expenses:,.0f}</span>
                </h4>
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Kode</th>
                                <th>Nama Akun</th>
                                <th>Tipe</th>
                                <th>Saldo</th>
                                <th>Keterangan</th>
                            </tr>
                        </thead>
                        <tbody>
        ''' + ''.join([f'''
                            <tr>
                                <td><strong>{acc.code}</strong></td>
                                <td>{acc.name}</td>
                                <td><span class="badge" style="background: var(--warning);">{acc.type}</span></td>
                                <td class="debit">Rp {acc.balance:,.0f}</td>
                                <td>Akun {acc.category.title()}</td>
                            </tr>''' for acc in expenses]) + f'''
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- SUMMARY - LAPORAN KEUANGAN -->
            <div class="card" style="background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%); color: white;">
                <h3 style="color: white; margin-bottom: 1rem;"><i class="fas fa-info-circle"></i> Laporan Keuangan yang Dihasilkan:</h3>
                <div class="grid grid-3">
                    <div>
                        <h4 style="color: white;">Laporan Laba Rugi</h4>
                        <ul style="color: white;">
                            <li>Pendapatan vs Beban</li>
                            <li>Menghitung Laba/Rugi</li>
                        </ul>
                    </div>
                    <div>
                        <h4 style="color: white;">Neraca</h4>
                        <ul style="color: white;">
                            <li>Aset = Kewajiban + Ekuitas</li>
                            <li>Posisi Keuangan</li>
                        </ul>
                    </div>
                    <div>
                        <h4 style="color: white;">Perubahan Ekuitas</h4>
                        <ul style="color: white;">
                            <li>Modal Awal vs Akhir</li>
                            <li>Pengaruh Laba/Rugi</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
        '''

    except Exception as e:
        print(f"Error generating chart of accounts content: {e}")
        return '<div class="card"><p>Error loading Chart of Accounts</p></div>'

# ===== ROUTES UTAMA =====
@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect('/login')

    try:
        settings = {s.key: s.value for s in AppSetting.query.all()}
        featured_products = Product.query.filter_by(is_featured=True).limit(4).all()

        # Featured Products HTML
        featured_html = ""
        for product in featured_products:
            weight_info = f"{product.weight_kg}kg" if product.weight_kg else f"{product.size_cm}cm"
            add_to_cart_btn = ''
            if current_user.user_type == 'customer':
                add_to_cart_btn = f'''
                <button class="btn btn-primary" onclick="addToCart({product.id})" style="margin-top: 1rem;">
                    <i class="fas fa-cart-plus"></i> Tambah ke Keranjang
                </button>
                '''

            featured_html += f'''
            <div class="card product-card" style="text-align: center; padding: 1.5rem;">
                <div style="position: relative;">
                    <img src="{product.image_url}" alt="{product.name}" class="product-image" 
                         style="height: 200px; object-fit: cover; border-radius: 12px;"
                         onerror="this.src='https://via.placeholder.com/300x200/4F46E5/ffffff?text=Kang+Mas+Shop'">
                    {product.is_featured and '<span style="position: absolute; top: 10px; right: 10px; background: var(--error); color: white; padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.8rem;">🔥 Unggulan</span>' or ''}
                </div>
                <h3 style="margin: 1rem 0 0.5rem 0; color: var(--dark); font-size: 1.2rem;">{product.name}</h3>
                <p style="color: #6B7280; font-size: 0.9rem; margin-bottom: 1rem; min-height: 40px;">{product.description[:60]}...</p>
                <div class="price" style="color: var(--primary); font-weight: bold; font-size: 1.3rem; margin-bottom: 0.5rem;">Rp {product.price:,.0f}</div>
                <div style="display: flex; justify-content: center; gap: 1rem; margin-bottom: 1rem;">
                    <span style="background: var(--ocean-light); padding: 0.25rem 0.75rem; border-radius: 15px; font-size: 0.8rem;">
                        <i class="fas fa-box"></i> Stock: {product.stock}
                    </span>
                    <span style="background: var(--ocean-light); padding: 0.25rem 0.75rem; border-radius: 15px; font-size: 0.8rem;">
                        <i class="fas fa-weight"></i> {weight_info}
                    </span>
                </div>
                {add_to_cart_btn}
            </div>
            '''

        # Determine user button based on user type
        if current_user.user_type == 'customer':
            user_button = '''
                <a href="/products" class="btn btn-primary" style="padding: 1rem 2rem; font-size: 1.1rem; margin-top: 1rem;">
                    <i class="fas fa-store"></i> Lihat Semua Produk
                </a>
                <a href="/cart" class="btn btn-success" style="padding: 1rem 2rem; font-size: 1.1rem; margin-top: 1rem; margin-left: 1rem;">
                    <i class="fas fa-shopping-cart"></i> Keranjang Saya
                </a>
            '''
        else:
            user_button = '''
                <a href="/seller/dashboard" class="btn btn-primary" style="padding: 1rem 2rem; font-size: 1.1rem; margin-top: 1rem;">
                    <i class="fas fa-chart-line"></i> Seller Dashboard
                </a>
                <a href="/seller/accounting" class="btn btn-success" style="padding: 1rem 2rem; font-size: 1.1rem; margin-top: 1rem; margin-left: 1rem;">
                    <i class="fas fa-chart-bar"></i> Sistem Akuntansi
                </a>
            '''

        content = f'''
        <!-- Hero Section -->
        <div class="hero" style="position: relative; overflow: hidden;">
            <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: linear-gradient(135deg, rgba(181, 81, 35, 0.9) 0%, rgba(228, 122, 36, 0.9) 100%); z-index: 1;"></div>
            <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: url('https://images.unsplash.com/photo-1516466723877-e4ec1d736c8a?q=80&w=2070&auto=format&fit=crop') center/cover; opacity: 0.3; z-index: 0;"></div>
            
            <div style="position: relative; z-index: 2; text-align: center; padding: 4rem 2rem;">
                <h1 style="font-size: 3.5rem; margin-bottom: 1.5rem; font-family: 'Poppins', sans-serif; font-weight: 800; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">
                    {settings.get('app_name', 'Kang-Mas Shop')}
                </h1>
                <p style="font-size: 1.25rem; margin-bottom: 1rem; opacity: 0.9; max-width: 600px; margin-left: auto; margin-right: auto;">
                    {settings.get('app_description', 'Sejak 2017 - Melayani dengan Kualitas Terbaik')}
                </p>
                <p style="font-size: 1.1rem; margin-bottom: 2rem; font-style: italic; opacity: 0.9;">
                    <i class="fas fa-fish"></i> Ikan mas segar langsung dari kolam Magelang
                </p>

                <div style="margin-top: 2rem; background: rgba(255,255,255,0.2); padding: 1.5rem; border-radius: var(--border-radius); backdrop-filter: blur(10px); max-width: 500px; margin-left: auto; margin-right: auto;">
                    <p style="font-size: 1.2rem; margin-bottom: 1rem;">
                        Selamat datang kembali, <strong style="color: var(--white);">{current_user.full_name}</strong>!
                    </p>
                    <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;">
                        {user_button}
                    </div>
                </div>
            </div>
        </div>

        <!-- Features Section -->
        <div style="margin: 4rem 0;">
            <h2 style="text-align: center; color: var(--primary); margin-bottom: 3rem; font-size: 2.5rem;">
                <i class="fas fa-star"></i> Mengapa Memilih Kami?
            </h2>
            
            <div class="grid grid-4">
                <div class="card" style="text-align: center; padding: 2rem;">
                    <div style="width: 70px; height: 70px; background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
                        <i class="fas fa-award" style="color: white; font-size: 1.8rem;"></i>
                    </div>
                    <h3 style="margin-bottom: 1rem; color: var(--dark);">Kualitas Terbaik</h3>
                    <p style="color: #6B7280;">Ikan segar langsung dari kolam dengan kualitas premium</p>
                </div>
                
                <div class="card" style="text-align: center; padding: 2rem;">
                    <div style="width: 70px; height: 70px; background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
                        <i class="fas fa-shipping-fast" style="color: white; font-size: 1.8rem;"></i>
                    </div>
                    <h3 style="margin-bottom: 1rem; color: var(--dark);">Pengiriman Cepat</h3>
                    <p style="color: #6B7280;">Dikirim langsung setelah panen, tetap segar sampai tujuan</p>
                </div>
                
                <div class="card" style="text-align: center; padding: 2rem;">
                    <div style="width: 70px; height: 70px; background: linear-gradient(135deg, var(--warning) 0%, #b7791f 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
                        <i class="fas fa-headset" style="color: white; font-size: 1.8rem;"></i>
                    </div>
                    <h3 style="margin-bottom: 1rem; color: var(--dark);">Customer Service</h3>
                    <p style="color: #6B7280;">Tim kami siap membantu 24/7 via WhatsApp</p>
                </div>
                
                <div class="card" style="text-align: center; padding: 2rem;">
                    <div style="width: 70px; height: 70px; background: linear-gradient(135deg, var(--error) 0%, #c53030 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
                        <i class="fas fa-shield-alt" style="color: white; font-size: 1.8rem;"></i>
                    </div>
                    <h3 style="margin-bottom: 1rem; color: var(--dark);">Garansi Kepuasan</h3>
                    <p style="color: #6B7280;">Garansi 100% uang kembali jika tidak puas</p>
                </div>
            </div>
        </div>

        <!-- Featured Products -->
        <div style="margin: 4rem 0;">
            <div style="text-align: center; margin-bottom: 2rem;">
                <h2 style="color: var(--primary); font-size: 2.5rem; margin-bottom: 1rem;">
                    <i class="fas fa-fire"></i> Produk Unggulan
                </h2>
                <p style="color: #6B7280; font-size: 1.1rem; max-width: 600px; margin: 0 auto;">
                    Produk terbaik pilihan pelanggan kami dengan kualitas premium
                </p>
            </div>
            
            <div class="grid grid-4">
                {featured_html or '''
                <div class="card" style="text-align: center; padding: 3rem; grid-column: span 4;">
                    <i class="fas fa-box-open" style="font-size: 3rem; color: #6B7280; margin-bottom: 1rem;"></i>
                    <h3>Belum Ada Produk Unggulan</h3>
                    <p>Silakan tambahkan produk dengan menandai sebagai "unggulan"</p>
                </div>
                '''}
            </div>
            
            {featured_products and '''
            <div style="text-align: center; margin-top: 3rem;">
                <a href="/products" class="btn btn-primary" style="padding: 1rem 3rem; font-size: 1.1rem;">
                    <i class="fas fa-store"></i> Lihat Semua Produk
                </a>
            </div>
            ''' or ''}
        </div>

        <!-- Stats Section -->
        <div style="margin: 4rem 0;">
            <div class="stats">
                <div class="stat-card" style="text-align: center;">
                    <div class="stat-number">7+</div>
                    <div class="stat-label">Tahun Pengalaman</div>
                    <p style="color: #6B7280; font-size: 0.9rem; margin-top: 0.5rem;">Sejak 2017</p>
                </div>
                <div class="stat-card" style="text-align: center;">
                    <div class="stat-number">1000+</div>
                    <div class="stat-label">Pelanggan Puas</div>
                    <p style="color: #6B7280; font-size: 0.9rem; margin-top: 0.5rem;">Seluruh Indonesia</p>
                </div>
                <div class="stat-card" style="text-align: center;">
                    <div class="stat-number">100%</div>
                    <div class="stat-label">Ikan Segar</div>
                    <p style="color: #6B7280; font-size: 0.9rem; margin-top: 0.5rem;">Garansi kesegaran</p>
                </div>
                <div class="stat-card" style="text-align: center;">
                    <div class="stat-number">24/7</div>
                    <div class="stat-label">Layanan</div>
                    <p style="color: #6B7280; font-size: 0.9rem; margin-top: 0.5rem;">Support WhatsApp</p>
                </div>
            </div>
        </div>

        <!-- Testimonials Section -->
        <div style="margin: 4rem 0;">
            <h2 style="text-align: center; color: var(--primary); margin-bottom: 3rem; font-size: 2.5rem;">
                <i class="fas fa-comment-dots"></i> Testimoni Pelanggan
            </h2>
            
            <div class="grid grid-3">
                <div class="card" style="padding: 2rem;">
                    <div style="display: flex; align-items: center; margin-bottom: 1.5rem;">
                        <div style="width: 50px; height: 50px; border-radius: 50%; background: var(--primary); color: white; display: flex; align-items: center; justify-content: center; margin-right: 1rem;">
                            <i class="fas fa-user"></i>
                        </div>
                        <div>
                            <h4 style="margin: 0; color: var(--dark);">Budi Santoso</h4>
                            <p style="margin: 0; color: #6B7280; font-size: 0.9rem;">Restoran Sari Rasa</p>
                        </div>
                    </div>
                    <p style="color: #6B7280; font-style: italic;">"Ikan masnya selalu segar, cocok untuk menu andalan restoran saya. Pengirimannya cepat dan tepat waktu!"</p>
                    <div style="color: var(--warning); margin-top: 1rem;">
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                    </div>
                </div>
                
                <div class="card" style="padding: 2rem;">
                    <div style="display: flex; align-items: center; margin-bottom: 1.5rem;">
                        <div style="width: 50px; height: 50px; border-radius: 50%; background: var(--success); color: white; display: flex; align-items: center; justify-content: center; margin-right: 1rem;">
                            <i class="fas fa-user"></i>
                        </div>
                        <div>
                            <h4 style="margin: 0; color: var(--dark);">Siti Aminah</h4>
                            <p style="margin: 0; color: #6B7280; font-size: 0.9rem;">Pemilik Kolam Ikan</p>
                        </div>
                    </div>
                    <p style="color: #6B7280; font-style: italic;">"Bibit ikan mas dari Kang-Mas Shop pertumbuhannya cepat dan sehat. Sudah 3 tahun langganan, tidak pernah mengecewakan."</p>
                    <div style="color: var(--warning); margin-top: 1rem;">
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star-half-alt"></i>
                    </div>
                </div>
                
                <div class="card" style="padding: 2rem;">
                    <div style="display: flex; align-items: center; margin-bottom: 1.5rem;">
                        <div style="width: 50px; height: 50px; border-radius: 50%; background: var(--error); color: white; display: flex; align-items: center; justify-content: center; margin-right: 1rem;">
                            <i class="fas fa-user"></i>
                        </div>
                        <div>
                            <h4 style="margin: 0; color: var(--dark);">Rudi Hartono</h4>
                            <p style="margin: 0; color: #6B7280; font-size: 0.9rem;">Pengusaha Ikan</p>
                        </div>
                    </div>
                    <p style="color: #6B7280; font-style: italic;">"Sistem akuntansinya sangat membantu mengelola keuangan usaha. Sekarang lebih mudah menghitung laba rugi."</p>
                    <div style="color: var(--warning); margin-top: 1rem;">
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                    </div>
                </div>
            </div>
        </div>

        <!-- About Section -->
        <div class="card" style="background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%); color: white; margin: 4rem 0; padding: 3rem;">
            <div class="grid grid-2">
                <div>
                    <h2 style="color: white; margin-bottom: 1.5rem; font-size: 2.5rem;">Tentang Kami</h2>
                    <p style="margin-bottom: 1.5rem; opacity: 0.9; font-size: 1.1rem;">
                        Kang-Mas Shop berdiri sejak 2017 dengan komitmen memberikan ikan mas berkualitas terbaik langsung dari kolam di Magelang. 
                        Kami mengutamakan kesegaran dan kepuasan pelanggan dalam setiap transaksi.
                    </p>
                    <p style="margin-bottom: 1.5rem; opacity: 0.9; font-size: 1.1rem;">
                        Selain menjual ikan mas segar, kami juga menyediakan sistem akuntansi terintegrasi untuk membantu pengusaha ikan mengelola keuangan dengan lebih baik.
                    </p>
                    <div style="display: flex; gap: 1rem; margin-top: 2rem;">
                        <a href="https://wa.me/6289654733875" target="_blank" class="btn" style="background: white; color: var(--primary);">
                            <i class="fab fa-whatsapp"></i> WhatsApp Kami
                        </a>
                        <a href="/products" class="btn" style="background: rgba(255,255,255,0.2); color: white; border: 1px solid white;">
                            <i class="fas fa-store"></i> Belanja Sekarang
                        </a>
                    </div>
                </div>
                <div style="display: flex; justify-content: center; align-items: center;">
                    <div style="background: rgba(255,255,255,0.1); padding: 2rem; border-radius: var(--border-radius); backdrop-filter: blur(10px);">
                        <h3 style="color: white; margin-bottom: 1rem;"><i class="fas fa-clock"></i> Jam Operasional</h3>
                        <ul style="list-style: none; padding: 0; margin: 0;">
                            <li style="margin-bottom: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid rgba(255,255,255,0.1);">Senin - Jumat: 08:00 - 17:00</li>
                            <li style="margin-bottom: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid rgba(255,255,255,0.1);">Sabtu: 08:00 - 15:00</li>
                            <li style="padding: 0.5rem 0;">Minggu: Tutup</li>
                        </ul>
                        <div style="margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid rgba(255,255,255,0.1);">
                            <p style="margin: 0; opacity: 0.9;"><i class="fas fa-phone"></i> +62 896-5473-3875</p>
                            <p style="margin: 0; opacity: 0.9;"><i class="fas fa-map-marker-alt"></i> Magelang, Jawa Tengah</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- CTA Section -->
        <div style="text-align: center; margin: 4rem 0;">
            <div class="card" style="background: var(--ocean-light); padding: 4rem 2rem;">
                <h2 style="color: var(--primary); margin-bottom: 1.5rem; font-size: 2.5rem;">Siap Membeli Ikan Segar?</h2>
                <p style="color: #6B7280; font-size: 1.1rem; max-width: 600px; margin: 0 auto 2rem;">
                    Bergabunglah dengan ribuan pelanggan puas kami dan dapatkan ikan mas berkualitas terbaik dengan harga kompetitif.
                </p>
                <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;">
                    {current_user.user_type == 'customer' and '''
                    <a href="/products" class="btn btn-primary" style="padding: 1rem 3rem; font-size: 1.1rem;">
                        <i class="fas fa-shopping-cart"></i> Belanja Sekarang
                    </a>
                    <a href="/cart" class="btn btn-success" style="padding: 1rem 3rem; font-size: 1.1rem;">
                        <i class="fas fa-cart-arrow-down"></i> Lihat Keranjang
                    </a>
                    ''' or '''
                    <a href="/seller/dashboard" class="btn btn-primary" style="padding: 1rem 3rem; font-size: 1.1rem;">
                        <i class="fas fa-chart-line"></i> Dashboard Seller
                    </a>
                    <a href="/seller/accounting" class="btn btn-success" style="padding: 1rem 3rem; font-size: 1.1rem;">
                        <i class="fas fa-calculator"></i> Sistem Akuntansi
                    </a>
                    '''}
                </div>
            </div>
        </div>
        '''
        
        return base_html('Home', content)
    except Exception as e:
        print(f"Error in index route: {e}")
        return base_html('Home', '''
        <div class="card" style="text-align: center; padding: 4rem;">
            <i class="fas fa-fish" style="font-size: 4rem; color: var(--primary); margin-bottom: 2rem;"></i>
            <h2 style="color: var(--primary);">Welcome to Kang-Mas Shop</h2>
            <p>Error loading content. Please try again.</p>
            <a href="/" class="btn btn-primary" style="margin-top: 1rem;">Refresh Page</a>
        </div>
        ''')
    
# ===== ROUTES AUTH =====
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        password = request.form.get('password')
        phone = request.form.get('phone')
        address = request.form.get('address')

        if User.query.filter_by(email=email).first():
            flash('Email sudah terdaftar!', 'error')
        else:
            user = User(
                email=email,
                full_name=full_name,
                user_type='customer',
                phone=phone,
                address=address
            )
            user.set_password(password)

            verification_code = user.generate_verification_code()
            db.session.add(user)
            db.session.commit()

            # ===========================================

            if send_verification_email(email, verification_code):
                session['pending_verification'] = user.id
                flash('Kode verifikasi telah dikirim ke email Anda!', 'success')
                return redirect('/verify_email')
            else:
                db.session.delete(user)
                db.session.commit()
                flash('Gagal mengirim email verifikasi. Silakan coba lagi.', 'error')

    content = '''
    <div style="max-width: 500px; margin: 0 auto;">
        <div class="card">
            <div style="text-align: center; margin-bottom: 2rem;">
                <div style="width: 80px; height: 80px; background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
                    <i class="fas fa-user-plus" style="color: white; font-size: 2rem;"></i>
                </div>
                <h2 style="color: var(--primary);">Daftar Akun Baru</h2>
            </div>

            <form method="POST">
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-envelope"></i> Email</label>
                    <input type="email" name="email" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-user"></i> Nama Lengkap</label>
                    <input type="text" name="full_name" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-lock"></i> Password</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-phone"></i> No. Telepon</label>
                    <input type="text" name="phone" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-map-marker-alt"></i> Alamat</label>
                    <textarea name="address" class="form-control" required></textarea>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">
                    <i class="fas fa-user-plus"></i> Daftar dengan Email
                </button>
            </form>

            <div class="divider">
                <span>atau</span>
            </div>

            <div style="text-align: center;">
                <a href="/google-login" class="btn google-btn">
                    <img src="https://developers.google.com/identity/images/g-logo.png"
                         style="width: 20px; height: 20px; margin-right: 10px; background: white; padding: 2px; border-radius: 2px;">
                    Daftar dengan Google
                </a>
            </div>

            <p style="text-align: center; margin-top: 1rem;">
                Sudah punya akun? <a href="/login" style="color: var(--primary); text-decoration: none; font-weight: 600;">Login di sini</a>
            </p>
        </div>
    </div>
    '''
    return base_html('Register', content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if not user.email_verified and not user.google_id:
                flash('Email belum diverifikasi! Silakan cek email Anda.', 'warning')
                return redirect('/verify_email')

            login_user(user, remember=True)
            flash(f'Berhasil login! Selamat datang {user.full_name}', 'success')
            return redirect('/')
        else:
            flash('Email atau password salah!', 'error')

    settings = {s.key: s.value for s in AppSetting.query.all()}
    app_logo = settings.get('app_logo', '/static/uploads/logos/logo.png')

    content = f'''
    <div style="max-width: 400px; margin: 0 auto;">
        <div class="card">
            <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 2rem;">
                <img src="{app_logo}" alt="Kang-Mas Shop" style="width: 50px; height: 50px; border-radius: 12px; box-shadow: var(--shadow-md);" onerror="this.style.display='none'">
                <h2 style="margin: 0; color: var(--primary);">Masuk ke Akun</h2>
            </div>

            <form method="POST">
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-envelope"></i> Email</label>
                    <input type="email" name="email" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-lock"></i> Password</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">
                    <i class="fas fa-sign-in-alt"></i> Login
                </button>
            </form>

            <div class="divider">
                <span>atau</span>
            </div>

            <div style="text-align: center;">
                <a href="/google-login" class="btn google-btn">
                    <img src="https://developers.google.com/identity/images/g-logo.png"
                         style="width: 20px; height: 20px; margin-right: 10px; background: white; padding: 2px; border-radius: 2px;">
                    Login dengan Google
                </a>
            </div>


            <p style="text-align: center; margin-top: 1rem;">
                Belum punya akun? <a href="/register" style="color: var(--primary); text-decoration: none; font-weight: 600;">Daftar sebagai Customer</a>
            </p>
        </div>
    </div>
    '''
    return base_html('Login', content)

@app.route('/verify_email', methods=['GET', 'POST'])
def verify_email():
    user_id = session.get('pending_verification')
    if not user_id:
        return redirect('/register')

    user = User.query.get(user_id)
    if not user:
        return redirect('/register')

    if request.method == 'POST':
        verification_code = request.form.get('verification_code')

        if user.verification_code == verification_code:
            user.email_verified = True
            user.verification_code = None
            db.session.commit()
            session.pop('pending_verification', None)

            login_user(user)
            flash('Email berhasil diverifikasi! Selamat datang.', 'success')
            return redirect('/')
        else:
            flash('Kode verifikasi salah! Silakan coba lagi.', 'error')

    content = f'''
    <div style="max-width: 400px; margin: 0 auto;">
        <div class="card">
            <h2 style="color: var(--primary);"><i class="fas fa-envelope"></i> Verifikasi Email</h2>
            <p>Kami telah mengirim kode verifikasi ke <strong>{user.email}</strong></p>
            <form method="POST">
                <div class="form-group">
                    <label class="form-label">Kode Verifikasi (6 digit)</label>
                    <input type="text" name="verification_code" class="form-control" maxlength="6" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">Verifikasi</button>
            </form>
            <p style="text-align: center; margin-top: 1rem;">
                Tidak menerima kode? <a href="/resend_verification">Kirim ulang</a>
            </p>
        </div>
    </div>
    '''
    return base_html('Verifikasi Email', content)

@app.route('/resend_verification')
def resend_verification():
    user_id = session.get('pending_verification')
    if user_id:
        user = User.query.get(user_id)
        if user:
            verification_code = user.generate_verification_code()
            db.session.commit()

            if send_verification_email(user.email, verification_code):
                flash('Kode verifikasi baru telah dikirim!', 'success')
            else:
                flash('Gagal mengirim email verifikasi. Silakan coba lagi.', 'error')

    return redirect('/verify_email')

@app.route('/logout')
def logout():
    logout_user()
    return redirect('/login')

# ===== ROUTES CUSTOMER =====
@app.route('/profile')
@login_required
def profile():
    try:
        if current_user.user_type == 'customer':
            total_orders = Order.query.filter_by(customer_id=current_user.id).count()
            total_spent_result = db.session.query(db.func.sum(Order.total_amount)).filter_by(customer_id=current_user.id).scalar()
            total_spent = total_spent_result if total_spent_result else 0
        else:
            total_orders = 0
            total_spent = 0

        content = f'''
        <div class="card">
            <h2 style="color: var(--primary);"><i class="fas fa-user"></i> Profile {current_user.user_type.title()}</h2>
            <div class="grid grid-2">
                <div>
                    <h4>Informasi Pribadi</h4>
                    <p><strong>Nama:</strong> {current_user.full_name}</p>
                    <p><strong>Email:</strong> {current_user.email}</p>
                    <p><strong>Alamat:</strong> {current_user.address or '-'}</p>
                    <p><strong>Tipe Akun:</strong> <span class="badge">{current_user.user_type.upper()}</span></p>
                </div>
                <div>
                    <h4>Statistik</h4>
                    {current_user.user_type == 'customer' and f'''
                    <p><strong>Total Order:</strong> {total_orders}</p>
                    f'<p><strong>Total Belanja:</strong> Rp {total_spent:,.0f}</p>'
                    ''' or '''
                    <p><strong>Role:</strong> Penjual/Pemilik Toko</p>
                    <p><strong>Akses:</strong> Manajemen Penuh</p>
                    '''}
                    <p><strong>Member sejak:</strong> {current_user.created_at.strftime('%d/%m/%Y')}</p>
                    <p><strong>Status Verifikasi:</strong> {'✅ Terverifikasi' if current_user.email_verified else '❌ Belum diverifikasi'}</p>
                </div>
            </div>
        </div>
        '''
        return base_html('Profile', content)
    except Exception as e:
        print(f"Error in profile route: {e}")
        flash('Terjadi error saat memuat profile.', 'error')
        return redirect('/')

@app.route('/products')
@login_required
def products():
    try:
        products_list = Product.query.filter_by(is_active=True).all()

        products_html = ""
        for product in products_list:
            weight_info = f"{product.weight_kg}kg" if product.weight_kg else f"{product.size_cm}cm"
            add_to_cart_btn = ''
            if current_user.user_type == 'customer':
                add_to_cart_btn = f'''
                <button class="btn btn-primary" onclick="addToCart({product.id})" style="margin-top: 1rem;">
                    <i class="fas fa-cart-plus"></i> Tambah ke Keranjang
                </button>
                '''

            products_html += f'''
            <div class="card">
                <img src="{product.image_url}" alt="{product.name}" class="product-image" onerror="this.style.display='none'">
                <h3>{product.name}</h3>
                <p>{product.description}</p>
                <div class="price">Rp {product.price:,.0f}</div>
                <p>Stock: {product.stock} | {weight_info}</p>
                {add_to_cart_btn}
            </div>
            '''

        content = f'''
        <h1 style="color: var(--primary);"><i class="fas fa-store"></i> Semua Produk</h1>
        <div class="grid grid-3">
            {products_html}
        </div>
        '''
        return base_html('Produk', content)
    except Exception as e:
        print(f"Error in products route: {e}")
        flash('Terjadi error saat memuat produk.', 'error')
        return redirect('/')

@app.route('/cart')
@login_required
def cart():
    try:
        # Hanya customer yang bisa akses cart
        if current_user.user_type != 'customer':
            flash('Hanya customer yang bisa mengakses keranjang belanja.', 'error')
            return redirect('/')

        cart_items = CartItem.query.filter_by(user_id=current_user.id).all()

        if not cart_items:
            content = '''
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-shopping-cart"></i> Keranjang Belanja</h2>
                <p>Keranjang belanja Anda kosong.</p>
                <a href="/products" class="btn btn-primary">Belanja Sekarang</a>
            </div>
            '''
        else:
            cart_html = ""
            total = 0

            for item in cart_items:
                product = Product.query.get(item.product_id)
                if product:  # Pastikan product exists
                    subtotal = product.price * item.quantity
                    total += subtotal

                    cart_html += f'''
                    <div class="card" style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1;">
                            <h4>{product.name}</h4>
                            <p>Rp {product.price:,.0f} x {item.quantity}</p>
                            <p>Subtotal: Rp {subtotal:,.0f}</p>
                        </div>
                        <div>
                            <form action="/remove_from_cart/{item.id}" method="POST" style="display: inline;">
                                <button type="submit" class="btn btn-danger">Hapus</button>
                            </form>
                        </div>
                    </div>
                    '''

            content = f'''
            <h1 style="color: var(--primary);"><i class="fas fa-shopping-cart"></i> Keranjang Belanja</h1>
            {cart_html}
            <div class="card">
                <h3>Total: Rp {total:,.0f}</h3>
                <button class="btn btn-success" onclick="checkout()">
                    <i class="fas fa-credit-card"></i> Checkout Sekarang
                </button>
            </div>
            '''

        return base_html('Keranjang', content)
    except Exception as e:
        print(f"Error in cart route: {e}")
        flash('Terjadi error saat memuat keranjang.', 'error')
        return redirect('/')

@app.route('/remove_from_cart/<int:cart_item_id>', methods=['POST'])
@login_required
def remove_from_cart(cart_item_id):
    try:
        if current_user.user_type != 'customer':
            flash('Akses ditolak.', 'error')
            return redirect('/')

        cart_item = CartItem.query.get(cart_item_id)
        if cart_item and cart_item.user_id == current_user.id:
            db.session.delete(cart_item)
            db.session.commit()
            flash('Produk dihapus dari keranjang', 'success')
        return redirect('/cart')
    except Exception as e:
        print(f"Error removing from cart: {e}")
        flash('Terjadi error saat menghapus dari keranjang.', 'error')
        return redirect('/cart')

@app.route('/checkout')
@login_required
def checkout_page():
    try:
        if current_user.user_type != 'customer':
            flash('Hanya customer yang bisa checkout.', 'error')
            return redirect('/')

        cart_items = CartItem.query.filter_by(user_id=current_user.id).all()

        if not cart_items:
            flash('Keranjang belanja Anda kosong', 'error')
            return redirect('/cart')

        total = 0
        for item in cart_items:
            product = Product.query.get(item.product_id)
            if product:
                total += product.price * item.quantity

        content = f'''
        <div style="max-width: 600px; margin: 0 auto;">
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-credit-card"></i> Checkout</h2>

                <div class="form-group">
                    <label class="form-label">Alamat Pengiriman</label>
                    <textarea id="shipping_address" class="form-control" required placeholder="Masukkan alamat lengkap pengiriman">{current_user.address or ''}</textarea>
                </div>

                <div class="form-group">
                    <label class="form-label">Metode Pengiriman</label>
                    <select id="shipping_method" class="form-control" required>
                        <option value="">Pilih metode pengiriman</option>
                        <option value="jne">JNE Reguler - Rp 15,000</option>
                        <option value="jnt">JNT Express - Rp 12,000</option>
                        <option value="pos">POS Indonesia - Rp 10,000</option>
                        <option value="grab">Grab Express - Rp 20,000</option>
                    </select>
                </div>

                <div class="form-group">
                    <label class="form-label">Metode Pembayaran</label>
                    <select id="payment_method" class="form-control" required>
                        <option value="">Pilih metode pembayaran</option>
                        <option value="bri">BRI (123456)</option>
                        <option value="bca">BCA (789012)</option>
                        <option value="mandiri">Mandiri (345678)</option>
                        <option value="qris">QRIS</option>
                        <option value="gopay">Gopay +6289654733875</option>
                        <option value="dana">Dana +6289654733875</option>
                        <option value="cod">Cash on Delivery (COD)</option>
                    </select>
                </div>

                <div class="card" style="background: var(--ocean-light);">
                    <h4>Ringkasan Pesanan</h4>
                    <p><strong>Total Belanja:</strong> Rp {total:,.0f}</p>
                    <p><strong>Ongkos Kirim:</strong> Rp 15,000</p>
                    <p><strong>Total Pembayaran:</strong> Rp {total + 15000:,.0f}</p>
                </div>

                <button class="btn btn-success" style="width: 100%; margin-top: 1rem;" onclick="processCheckout()">
                    <i class="fas fa-credit-card"></i> Proses Pembayaran
                </button>
            </div>
        </div>
        '''
        return base_html('Checkout', content)
    except Exception as e:
        print(f"Error in checkout route: {e}")
        flash('Terjadi error saat memuat halaman checkout.', 'error')
        return redirect('/cart')

@app.route('/process_checkout', methods=['POST'])
@login_required
def process_checkout():
    try:
        if current_user.user_type != 'customer':
            return jsonify({'success': False, 'message': 'Akses ditolak'})

        cart_items = CartItem.query.filter_by(user_id=current_user.id).all()

        if not cart_items:
            return jsonify({'success': False, 'message': 'Keranjang kosong'})

        shipping_address = request.form.get('shipping_address')
        shipping_method = request.form.get('shipping_method')
        payment_method = request.form.get('payment_method')

        if not shipping_address or not shipping_method or not payment_method:
            return jsonify({'success': False, 'message': 'Harap lengkapi semua data pengiriman dan pembayaran'})

        order_number = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
        total_amount = 0

        # Cek stok sebelum checkout
        for cart_item in cart_items:
            product = Product.query.get(cart_item.product_id)
            if not product or product.stock < cart_item.quantity:
                product_name = product.name if product else 'Produk'
                return jsonify({'success': False, 'message': f'Stock {product_name} tidak mencukupi'})

        order = Order(
            order_number=order_number,
            customer_id=current_user.id,
            total_amount=0,
            shipping_address=shipping_address,
            shipping_method=shipping_method,
            payment_method=payment_method,
            payment_status='unpaid',  # Status awal belum bayar
            status='pending'
        )

        # JIKA COD, LANGSUNG PROSES KE SUKSES
        if payment_method == 'cod':
            order.payment_status = 'pending_cod'  # Status khusus untuk COD
            order.status = 'processing'  # Langsung processing untuk COD

        db.session.add(order)
        db.session.flush()  # Untuk dapat order.id

        # Kurangi stok dan buat order items
        order_items = []
        for cart_item in cart_items:
            product = Product.query.get(cart_item.product_id)
            if product:
                product.stock -= cart_item.quantity  # Kurangi stok
                print(f"✅ Stok {product.name} berkurang {cart_item.quantity} menjadi {product.stock}")

                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=cart_item.quantity,
                    price=product.price,
                    cost_price=product.cost_price
                )
                db.session.add(order_item)
                order_items.append(order_item)
                total_amount += product.price * cart_item.quantity

        # Tambahkan ongkos kirim
        shipping_cost = 15000
        total_amount += shipping_cost

        order.total_amount = total_amount
        db.session.commit()

        # ===========================================

        # Hapus cart items
        CartItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()

        # JIKA COD, LANGSUNG KE SUKSES
        if payment_method == 'cod':
            return jsonify({
                'success': True,
                'message': 'Pesanan COD berhasil dibuat!',
                'order_number': order_number,
                'payment_method': payment_method,
                'total_amount': total_amount,
                'is_cod': True  # Flag untuk frontend
            })
        else:
            return jsonify({
                'success': True,
                'message': 'Checkout berhasil!',
                'order_number': order_number,
                'payment_method': payment_method,
                'total_amount': total_amount,
                'is_cod': False
            })
    except Exception as e:
        print(f"Error processing checkout: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Terjadi error saat proses checkout'})

@app.route('/confirm_payment/<order_number>', methods=['POST'])
@login_required
def confirm_payment(order_number):
    try:
        order = Order.query.filter_by(order_number=order_number, customer_id=current_user.id).first_or_404()

        # Update status pembayaran dan order
        order.payment_status = 'paid'
        order.status = 'processing'  # Status berubah dari pending ke processing

        db.session.commit()

        flash('Pembayaran berhasil dikonfirmasi! Pesanan sedang diproses.', 'success')
        return jsonify({'success': True, 'message': 'Pembayaran berhasil dikonfirmasi'})
    except Exception as e:
        print(f"Error confirming payment: {e}")
        return jsonify({'success': False, 'message': 'Terjadi error saat konfirmasi pembayaran'})

@app.route('/orders')
@login_required
def orders():
    try:
        if current_user.user_type == 'customer':
            orders_list = Order.query.filter_by(customer_id=current_user.id).order_by(Order.order_date.desc()).all()
            title = 'Pesanan Saya'
        else:
            orders_list = Order.query.order_by(Order.order_date.desc()).all()
            title = 'Semua Pesanan'

        if not orders_list:
            content = f'''
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-box"></i> {title}</h2>
                <p>Belum ada pesanan.</p>
                {current_user.user_type == 'customer' and '<a href="/products" class="btn btn-primary">Belanja Sekarang</a>' or ''}
            </div>
            '''
        else:
            orders_html = ""
            for order in orders_list:
                customer = User.query.get(order.customer_id) if current_user.user_type != 'customer' else current_user

                # Status dengan style text normal
                status_display = f"<span class='status-text status-{order.status}'>{order.status.upper()}</span>"
                payment_status_display = f"<span class='status-text status-{order.payment_status}'>{order.payment_status.upper()}</span>"

                customer_info = f"<p><strong>Customer:</strong> {customer.full_name}</p>" if current_user.user_type != 'customer' else ""

                orders_html += f'''
                <div class="card">
                    <h4>Order #{order.order_number}</h4>
                    {customer_info}
                    <p><strong>Total:</strong> Rp {order.total_amount:,.0f}</p>
                    <p><strong>Status:</strong> {status_display}</p>
                    <p><strong>Pembayaran:</strong> {payment_status_display}</p>
                    <p><strong>Metode:</strong> {order.payment_method} | <strong>Pengiriman:</strong> {order.shipping_method}</p>
                    <p><strong>Tanggal:</strong> {order.order_date.strftime('%d/%m/%Y %H:%M')}</p>
                    <p><strong>Alamat:</strong> {order.shipping_address}</p>
                    {order.tracking_info and f'<p><strong>Tracking:</strong> {order.tracking_info}</p>' or ''}

                    {current_user.user_type == 'seller' and order.payment_status == 'unpaid' and '''
                    <div style="margin-top: 1rem; padding: 1rem; background: rgba(229, 62, 62, 0.1); border-radius: 8px;">
                        <p style="color: var(--error); margin: 0;">
                            <strong>\u26A0\uFE0F Menunggu Pembayaran:</strong> Pesanan belum dapat diproses karena pembayaran belum diterima.
                        </p>
                    </div>
                    ''' or ''}

                    {current_user.user_type == 'seller' and order.payment_status == 'paid' and order.status == 'processing' and f'''
                    <form action="/seller/update_order_status/{order.id}" method="POST" style="margin-top: 1rem;">
                        <input type="hidden" name="status" value="completed">
                        <button type="submit" class="btn btn-success">Selesaikan Order</button>
                    </form>
                    ''' or ''}
                </div>
                '''

            content = f'''
            <h1 style="color: var(--primary);"><i class="fas fa-box"></i> {title}</h1>
            {orders_html}
            '''

        return base_html('Pesanan', content)
    except Exception as e:
        print(f"Error in orders route: {e}")
        flash('Terjadi error saat memuat pesanan.', 'error')
        return redirect('/')

# ===== ROUTES SELLER =====
@app.route('/seller/dashboard')
@login_required
@seller_required
def seller_dashboard():
    try:
        total_products = Product.query.filter_by(seller_id=current_user.id).count()
        total_orders = Order.query.count()
        total_sales_result = db.session.query(db.func.sum(Order.total_amount)).scalar()
        total_sales = total_sales_result if total_sales_result else 0
        total_customers = User.query.filter_by(user_type='customer').count()

        # Recent orders
        recent_orders = Order.query.order_by(Order.order_date.desc()).limit(5).all()
        recent_orders_html = ""
        for order in recent_orders:
            customer = User.query.get(order.customer_id)
            status_display = f"<span class='status-text status-{order.status}'>{order.status.upper()}</span>"
            recent_orders_html += f'''
            <div style="padding: 1rem; border-bottom: 1px solid rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: between; align-items: center;">
                    <div style="flex: 1;">
                        <strong>#{order.order_number}</strong>
                        <br><small>{customer.full_name if customer else 'Unknown'}</small>
                    </div>
                    <div>
                        {status_display}
                        <br><small>Rp {order.total_amount:,.0f}</small>
                    </div>
                </div>
            </div>
            '''

        content = f'''
        <h1 style="color: var(--primary);"><i class="fas fa-chart-line"></i> Seller Dashboard</h1>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{total_products}</div>
                <div class="stat-label">Total Produk</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_orders}</div>
                <div class="stat-label">Total Pesanan</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">Rp {total_sales:,.0f}</div>
                <div class="stat-label">Total Penjualan</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_customers}</div>
                <div class="stat-label">Total Customer</div>
            </div>
        </div>

        <div class="grid grid-2">
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-bolt"></i> Quick Actions</h3>
                <div style="display: flex; flex-direction: column; gap: 1rem;">
                    <a href="/seller/orders" class="btn btn-primary"><i class="fas fa-boxes"></i> Kelola Pesanan</a>
                    <a href="/seller/accounting" class="btn btn-success"><i class="fas fa-chart-bar"></i> Lihat Akuntansi</a>
                    <a href="/seller/products" class="btn btn-info"><i class="fas fa-fish"></i> Kelola Produk</a>
                </div>
            </div>

            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-list"></i> Pesanan Terbaru</h3>
                <div style="max-height: 300px; overflow-y: auto;">
                    {recent_orders_html or '<p style="text-align: center; padding: 2rem;">Belum ada pesanan</p>'}
                </div>
            </div>
        </div>

        <div class="grid grid-2">
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-money-bill-wave"></i> Ringkasan Keuangan</h3>
                <p><strong>Kas:</strong> Rp {Account.query.filter_by(type='kas').first().balance if Account.query.filter_by(type='kas').first() else 0:,.0f}</p>
                <p><strong>Pendapatan:</strong> Rp {Account.query.filter_by(type='pendapatan').first().balance if Account.query.filter_by(type='pendapatan').first() else 0:,.0f}</p>
                <p><strong>Laba Bersih:</strong> Rp {calculate_net_income():,.0f}</p>
            </div>

            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-chart-pie"></i> Status Pesanan</h3>
                <p><strong>Pending:</strong> {Order.query.filter_by(status='pending').count()} pesanan</p>
                <p><strong>Processing:</strong> {Order.query.filter_by(status='processing').count()} pesanan</p>
                <p><strong>Completed:</strong> {Order.query.filter_by(status='completed').count()} pesanan</p>
            </div>
        </div>
        '''

        return base_html('Seller Dashboard', content)
    except Exception as e:
        print(f"Error in seller dashboard: {e}")
        flash('Terjadi error saat memuat dashboard.', 'error')
        return redirect('/')

# ===== ROUTE EDIT SALDO AWAL =====
@app.route('/seller/edit_initial_balances', methods=['GET', 'POST'])
@login_required
@seller_required
def edit_initial_balances():
    """Edit saldo awal akun-akun HANYA untuk akun REAL (Aset, Kewajiban, Ekuitas)"""
    try:
        if request.method == 'POST':
            print("🔄 Processing edit initial balances...")
            
            # Dapatkan semua data dari form
            data = request.form
            
            # RESET: Hapus semua transaksi jurnal sebelum update saldo
            print("🔄 Resetting all journal entries before updating balances...")
            
            # 1. Hapus semua detail jurnal
            JournalDetail.query.delete()
            
            # 2. Hapus semua jurnal
            JournalEntry.query.delete()
            
            # 3. Hapus semua transaksi inventory
            InventoryTransaction.query.delete()
            
            # 4. Hapus semua kartu persediaan
            InventoryCard.query.delete()
            
            # 5. Hapus semua jurnal penutup
            ClosingEntry.query.delete()
            ClosingDetail.query.delete()
            
            print("✅ All previous transactions cleared!")
            
            # PERBAIKAN: Hanya update akun REAL (Aset, Kewajiban, Ekuitas)
            for key, value in data.items():
                if key.startswith('balance_'):
                    account_id = key.replace('balance_', '')
                    try:
                        account = Account.query.get(account_id)
                        
                        # PERBAIKAN: Hanya update jika akun REAL (bukan nominal)
                        if account and account.category in ['asset', 'liability', 'equity']:
                            if value and value.strip():
                                # Parse nilai, hapus titik pemisah ribuan jika ada
                                raw_value = str(value).replace('.', '').replace(',', '.').strip()
                                balance_value = float(raw_value)
                                
                                # Set balance langsung ke nilai yang diinput
                                account.balance = balance_value
                                
                                print(f"✅ Updated REAL account {account.code} - {account.name} to Rp {balance_value:,.0f}")
                        else:
                            # Untuk akun NOMINAL (Pendapatan & Beban), SET ke 0
                            if account and account.category in ['revenue', 'expense']:
                                account.balance = 0
                                print(f"ℹ️ Reset NOMINAL account {account.code} - {account.name} to 0")
                                
                    except ValueError as e:
                        print(f"❌ Error parsing value for account {account_id}: {e} - Value: '{value}'")
                        continue
                    except Exception as e:
                        print(f"❌ Error updating account {account_id}: {e}")
                        continue
            
            # Reset product stocks sesuai dengan saldo persediaan baru
            print("🔄 Updating product stocks based on inventory balance...")
            
            # Dapatkan account persediaan
            persediaan_account = Account.query.filter_by(type='persediaan').first()
            
            # Hitung distribusi persediaan
            if persediaan_account and persediaan_account.balance > 0:
                total_persediaan = persediaan_account.balance
                
                # Distribusi: 60% bibit, 40% konsumsi
                bibit_value = total_persediaan * 0.6  # 60%
                konsumsi_value = total_persediaan * 0.4  # 40%
                
                # Update atau create produk bibit
                bibit_product = Product.query.filter_by(name='Bibit Ikan Mas').first()
                if not bibit_product:
                    seller_id = User.query.filter_by(user_type='seller').first().id
                    bibit_product = Product(
                        name='Bibit Ikan Mas',
                        description='Bibit ikan mas segar ukuran 8cm',
                        price=2000,
                        cost_price=1000,
                        stock=0,
                        size_cm=8,
                        seller_id=seller_id,
                        category='bibit',
                        image_url='/static/uploads/products/bibit_ikan_mas.jpg'
                    )
                    db.session.add(bibit_product)
                
                # Hitung stock bibit (harga cost Rp 1,000)
                bibit_stock = int(bibit_value / 1000)
                bibit_product.stock = max(bibit_stock, 0)
                bibit_product.cost_price = 1000
                print(f"✅ Bibit Ikan Mas: {bibit_product.stock} units (Rp {bibit_value:,.0f})")
                
                # Update atau create produk konsumsi
                konsumsi_product = Product.query.filter_by(name='Ikan Mas Konsumsi').first()
                if not konsumsi_product:
                    seller_id = User.query.filter_by(user_type='seller').first().id
                    konsumsi_product = Product(
                        name='Ikan Mas Konsumsi',
                        description='Ikan mas segar siap konsumsi, berat 1kg',
                        price=20000,
                        cost_price=13500,
                        stock=0,
                        weight_kg=1,
                        seller_id=seller_id,
                        category='konsumsi',
                        image_url='/static/uploads/products/ikan_mas_konsumsi.jpg'
                    )
                    db.session.add(konsumsi_product)
                
                # Hitung stock konsumsi (harga cost Rp 13,500)
                konsumsi_stock = int(konsumsi_value / 13500)
                konsumsi_product.stock = max(konsumsi_stock, 0)
                konsumsi_product.cost_price = 13500
                print(f"✅ Ikan Mas Konsumsi: {konsumsi_product.stock} units (Rp {konsumsi_value:,.0f})")
            
            # Reset order status untuk memulai dari awal
            Order.query.update({
                'payment_status': 'unpaid',
                'status': 'pending'
            })
            
            # Clear cart items
            CartItem.query.delete()
            
            db.session.commit()
            print("✅ All balances updated successfully!")
            
            flash('✅ Saldo awal berhasil diperbarui! Sistem telah direset dengan saldo baru.', 'success')
            return redirect('/seller/accounting')
        
        # ===== GET METHOD - TAMPILKAN FORM EDIT =====
        
        # PERBAIKAN: Hanya ambil akun REAL (Aset, Kewajiban, Ekuitas)
        # JANGAN ambil akun nominal (Pendapatan, Beban)
        accounts = Account.query.filter(
            Account.category.in_(['asset', 'liability', 'equity'])
        ).order_by(Account.code).all()
        
        # Group accounts by category for better organization
        asset_accounts = [acc for acc in accounts if acc.category == 'asset']
        liability_accounts = [acc for acc in accounts if acc.category == 'liability']
        equity_accounts = [acc for acc in accounts if acc.category == 'equity']
        
        # PERBAIKAN: Juga get akun nominal untuk info (tapi tidak untuk diedit)
        nominal_accounts = Account.query.filter(
            Account.category.in_(['revenue', 'expense'])
        ).order_by(Account.code).all()
        
        # Generate form HTML
        form_html = '''
        <div class="card">
            <h2 style="color: var(--primary); margin-bottom: 1.5rem;">
                <i class="fas fa-edit"></i> Edit Saldo Awal - HANYA Akun REAL
            </h2>
            
            <div style="background: var(--ocean-light); padding: 1.5rem; border-radius: var(--border-radius); margin-bottom: 2rem;">
                <h4 style="color: var(--primary); margin-bottom: 0.5rem;">
                    <i class="fas fa-info-circle"></i> PETUNJUK PENGEDITAN SALDO AWAL
                </h4>
                <ul style="margin: 0; padding-left: 1.2rem; font-size: 0.9rem;">
                    <li><strong>✅ BOLEH Diedit:</strong> Aset, Kewajiban, Ekuitas</li>
                    <li><strong>❌ TIDAK BOLEH Diedit:</strong> Pendapatan & Beban (saldo awal selalu 0)</li>
                    <li><strong>Format:</strong> Debit (+) untuk Aset</li>
                    <li><strong>Format:</strong> Kredit (+) untuk Kewajiban & Ekuitas</li>
                    <li>Gunakan angka tanpa tanda titik atau koma (contoh: 1000000 untuk 1 juta)</li>
                    <li><strong style="color: var(--error);">⚠️ PERINGATAN:</strong> Semua transaksi sebelumnya akan dihapus!</li>
                </ul>
            </div>
            
            <form method="POST" id="editBalancesForm">
        '''
        
        # ASET (Debit Balance)
        if asset_accounts:
            form_html += f'''
            <div style="margin-bottom: 2rem;">
                <h3 style="color: var(--success); margin-bottom: 1rem; padding: 1rem; background: rgba(56, 161, 105, 0.1); border-radius: var(--border-radius);">
                    <i class="fas fa-wallet"></i> ASET - Normal Balance: Debit (+)
                </h3>
                <div class="grid grid-2">
            '''
            
            for account in asset_accounts:
                current_balance = int(account.balance) if account.balance else 0
                form_html += f'''
                <div class="form-group">
                    <label class="form-label">
                        {account.code} - {account.name}
                        <span style="color: var(--success); font-size: 0.85rem;">(Debit)</span>
                    </label>
                    <input type="text" 
                           name="balance_{account.id}" 
                           class="form-control balance-input"
                           value="{current_balance:,}" 
                           data-account-type="debit"
                           data-original-value="{current_balance}"
                           placeholder="Masukkan saldo debit" required>
                    <small style="color: #6B7280; font-size: 0.8rem;">
                        Saldo saat ini: <span class="debit">Rp {current_balance:,}</span>
                    </small>
                </div>
                '''
            
            form_html += '''
                </div>
            </div>
            '''
        
        # KEWAJIBAN (Credit Balance)
        if liability_accounts:
            form_html += f'''
            <div style="margin-bottom: 2rem;">
                <h3 style="color: var(--error); margin-bottom: 1rem; padding: 1rem; background: rgba(229, 62, 62, 0.1); border-radius: var(--border-radius);">
                    <i class="fas fa-hand-holding-usd"></i> KEWAJIBAN - Normal Balance: Kredit (+)
                </h3>
                <div class="grid grid-2">
            '''
            
            for account in liability_accounts:
                current_balance = int(account.balance) if account.balance else 0
                form_html += f'''
                <div class="form-group">
                    <label class="form-label">
                        {account.code} - {account.name}
                        <span style="color: var(--error); font-size: 0.85rem;">(Kredit)</span>
                    </label>
                    <input type="text" 
                           name="balance_{account.id}" 
                           class="form-control balance-input"
                           value="{current_balance:,}" 
                           data-account-type="credit"
                           data-original-value="{current_balance}"
                           placeholder="Masukkan saldo kredit" required>
                    <small style="color: #6B7280; font-size: 0.8rem;">
                        Saldo saat ini: <span class="credit">Rp {current_balance:,}</span>
                    </small>
                </div>
                '''
            
            form_html += '''
                </div>
            </div>
            '''
        
        # EKUITAS (Credit Balance)
        if equity_accounts:
            form_html += f'''
            <div style="margin-bottom: 2rem;">
                <h3 style="color: var(--primary); margin-bottom: 1rem; padding: 1rem; background: rgba(49, 130, 206, 0.1); border-radius: var(--border-radius);">
                    <i class="fas fa-user-tie"></i> EKUITAS - Normal Balance: Kredit (+)
                </h3>
                <div class="grid grid-2">
            '''
            
            for account in equity_accounts:
                current_balance = int(account.balance) if account.balance else 0
                form_html += f'''
                <div class="form-group">
                    <label class="form-label">
                        {account.code} - {account.name}
                        <span style="color: var(--primary); font-size: 0.85rem;">(Kredit)</span>
                    </label>
                    <input type="text" 
                           name="balance_{account.id}" 
                           class="form-control balance-input"
                           value="{current_balance:,}" 
                           data-account-type="credit"
                           data-original-value="{current_balance}"
                           placeholder="Masukkan saldo kredit" required>
                    <small style="color: #6B7280; font-size: 0.8rem;">
                        Saldo saat ini: <span class="credit">Rp {current_balance:,}</span>
                    </small>
                </div>
                '''
            
            form_html += '''
                </div>
            </div>
            '''
        
        # Balance Summary
        form_html += '''
            <div style="margin: 2rem 0; padding: 1.5rem; background: var(--ocean-light); border-radius: var(--border-radius);">
                <h4 style="color: var(--primary); margin-bottom: 1rem;">
                    <i class="fas fa-calculator"></i> Ringkasan Keseimbangan
                </h4>
                
                <div class="grid grid-2">
                    <div>
                        <h5>Total Debit (Aset)</h5>
                        <div id="total-debit" style="font-size: 1.5rem; font-weight: bold; color: var(--success);">
                            Rp 0
                        </div>
                    </div>
                    <div>
                        <h5>Total Kredit (Kewajiban + Ekuitas)</h5>
                        <div id="total-credit" style="font-size: 1.5rem; font-weight: bold; color: var(--error);">
                            Rp 0
                        </div>
                    </div>
                </div>
                
                <div id="balance-status" style="margin-top: 1rem; padding: 1rem; border-radius: var(--border-radius);">
                    <!-- Status akan diisi oleh JavaScript -->
                </div>
                
                <div style="margin-top: 1rem; font-size: 0.9rem; color: #6B7280;">
                    <p><strong>Rumus Keseimbangan:</strong> Aset = Kewajiban + Ekuitas</p>
                    <p>Pastikan kedua nilai sama sebelum menyimpan!</p>
                </div>
            </div>
            
            <!-- INFO AKUN NOMINAL (TIDAK BOLEH DEDIT) -->
            <div style="margin: 2rem 0; padding: 1.5rem; background: rgba(156, 163, 175, 0.1); border-left: 4px solid #9CA3AF; border-radius: var(--border-radius);">
                <h4 style="color: #6B7280; margin-bottom: 0.5rem;">
                    <i class="fas fa-info-circle"></i> INFO: Akun Nominal (Tidak Diedit)
                </h4>
                <p style="margin: 0.5rem 0; color: #6B7280;">
                    <strong>Pendapatan & Beban</strong> adalah akun nominal yang saldo awalnya selalu 0.
                    Mereka akan di-reset otomatis saat Anda menyimpan perubahan ini.
                </p>
                <div style="margin-top: 1rem; font-size: 0.9rem;">
                    <p><strong>Akun Pendapatan & Beban yang akan di-reset ke 0:</strong></p>
                    <ul style="margin: 0.5rem 0 0 1rem; color: #6B7280;">
        '''
        
        # Tampilkan daftar akun nominal yang akan direset
        for account in nominal_accounts:
            form_html += f'''
                        <li>{account.code} - {account.name} <span style="color: #9CA3AF;">(akan direset ke 0)</span></li>
            '''
        
        form_html += '''
                    </ul>
                </div>
            </div>
            
            <!-- Warning Card -->
            <div style="margin: 2rem 0; padding: 1.5rem; background: rgba(229, 62, 62, 0.1); border-left: 4px solid var(--error); border-radius: var(--border-radius);">
                <h4 style="color: var(--error); margin-bottom: 0.5rem;">
                    <i class="fas fa-exclamation-triangle"></i> PERINGATAN PENTING
                </h4>
                <p style="margin: 0.5rem 0; color: var(--error);">
                    <strong>Mengedit saldo awal akan:</strong>
                </p>
                <ul style="margin: 0.5rem 0 0 0; padding-left: 1.2rem; color: var(--error);">
                    <li>Menghapus SEMUA transaksi jurnal yang sudah ada</li>
                    <li>Menghapus SEMUA kartu persediaan</li>
                    <li>Merestok ulang produk berdasarkan saldo persediaan baru</li>
                    <li>Reset semua pesanan ke status "pending"</li>
                    <li>Kosongkan keranjang belanja</li>
                    <li><strong>Reset semua akun Pendapatan & Beban ke 0</strong></li>
                </ul>
                <p style="margin: 1rem 0 0 0; font-size: 0.9rem; color: var(--error);">
                    <strong>⏰ Waktu terbaik:</strong> Di awal periode akuntansi atau saat setup sistem baru.
                </p>
            </div>
            
            <div class="modal-buttons">
                <button type="button" class="btn btn-primary" onclick="calculateBalances()">
                    <i class="fas fa-calculator"></i> Hitung Ulang Keseimbangan
                </button>
                <button type="submit" class="btn btn-success" id="save-button" disabled>
                    <i class="fas fa-save"></i> Simpan Perubahan Saldo Awal
                </button>
                <button type="button" class="btn btn-danger" onclick="resetToOriginal()">
                    <i class="fas fa-undo"></i> Reset ke Nilai Asli
                </button>
                <a href="/seller/accounting" class="btn btn-warning">
                    <i class="fas fa-times"></i> Batal
                </a>
            </div>
            
            </form>
        </div>
        
        <!-- JavaScript untuk kalkulasi dan formatting -->
        <script>
        // Format number input dengan pemisah ribuan
        document.querySelectorAll('.balance-input').forEach(input => {
            // Format saat kehilangan fokus
            input.addEventListener('blur', function() {
                formatBalanceInput(this);
                calculateBalances();
            });
            
            // Hapus formatting saat mendapatkan fokus
            input.addEventListener('focus', function() {
                this.value = this.value.replace(/\\./g, '').replace(/,/g, '');
            });
            
            // Real-time validation
            input.addEventListener('input', function() {
                // Hanya izinkan angka
                this.value = this.value.replace(/[^\\d]/g, '');
                calculateBalances();
            });
        });
        
        function formatBalanceInput(input) {
            let value = input.value.replace(/\\./g, '').replace(/,/g, '');
            if (value) {
                // Format dengan titik sebagai pemisah ribuan
                value = parseInt(value).toLocaleString('id-ID');
                input.value = value;
            }
        }
        
        function parseBalanceValue(formattedValue) {
            return parseInt(formattedValue.replace(/\\./g, '').replace(/,/g, '')) || 0;
        }
        
        function calculateBalances() {
            let totalDebit = 0;
            let totalCredit = 0;
            
            // Hitung total debit dan kredit
            document.querySelectorAll('.balance-input').forEach(input => {
                const value = parseBalanceValue(input.value);
                const accountType = input.getAttribute('data-account-type');
                
                if (accountType === 'debit') {
                    totalDebit += value;
                } else if (accountType === 'credit') {
                    totalCredit += value;
                }
            });
            
            // Update display
            document.getElementById('total-debit').textContent = 'Rp ' + totalDebit.toLocaleString('id-ID');
            document.getElementById('total-credit').textContent = 'Rp ' + totalCredit.toLocaleString('id-ID');
            
            // Tentukan status keseimbangan
            const balanceStatus = document.getElementById('balance-status');
            const saveButton = document.getElementById('save-button');
            
            // Toleransi kecil untuk floating point
            const isBalanced = Math.abs(totalDebit - totalCredit) < 1;
            
            if (isBalanced) {
                balanceStatus.innerHTML = `
                    <div style="background: rgba(56, 161, 105, 0.1); padding: 1rem; border-radius: var(--border-radius); color: var(--success);">
                        <i class="fas fa-check-circle"></i>
                        <strong>NERACA SEIMBANG!</strong>
                        <p style="margin: 0.5rem 0 0 0; font-size: 0.9rem;">
                            Aset (Rp ${totalDebit.toLocaleString('id-ID')}) = Kewajiban + Ekuitas (Rp ${totalCredit.toLocaleString('id-ID')})
                        </p>
                    </div>
                `;
                saveButton.disabled = false;
                saveButton.style.opacity = '1';
                saveButton.innerHTML = '<i class="fas fa-save"></i> Simpan Perubahan Saldo Awal';
            } else {
                const difference = Math.abs(totalDebit - totalCredit);
                balanceStatus.innerHTML = `
                    <div style="background: rgba(229, 62, 62, 0.1); padding: 1rem; border-radius: var(--border-radius); color: var(--error);">
                        <i class="fas fa-exclamation-triangle"></i>
                        <strong>NERACA TIDAK SEIMBANG!</strong>
                        <p style="margin: 0.5rem 0 0 0; font-size: 0.9rem;">
                            Selisih: Rp ${difference.toLocaleString('id-ID')}
                        </p>
                        <p style="margin: 0.5rem 0 0 0; font-size: 0.9rem;">
                            Periksa kembali input Anda!
                        </p>
                    </div>
                `;
                saveButton.disabled = true;
                saveButton.style.opacity = '0.5';
                saveButton.innerHTML = '<i class="fas fa-ban"></i> Neraca Tidak Seimbang';
            }
        }
        
        function resetToOriginal() {
            if (confirm('Apakah Anda yakin ingin mengembalikan semua nilai ke saldo awal? Perubahan yang belum disimpan akan hilang.')) {
                document.querySelectorAll('.balance-input').forEach(input => {
                    const originalValue = input.getAttribute('data-original-value');
                    input.value = parseInt(originalValue).toLocaleString('id-ID');
                });
                calculateBalances();
            }
        }
        
        // Hitung saat pertama kali halaman dimuat
        document.addEventListener('DOMContentLoaded', function() {
            calculateBalances();
        });
        
        // Tambahkan konfirmasi sebelum submit
        document.getElementById('editBalancesForm').addEventListener('submit', function(event) {
            const confirmMessage = '⚠️ KONFIRMASI PERUBAHAN SALDO AWAL ⚠️\\n\\n' +
                                'Dengan menyimpan perubahan ini, Anda akan:\\n' +
                                '1. Mengatur ulang saldo awal akun REAL (Aset, Kewajiban, Ekuitas)\\n' +
                                '2. Reset semua akun NOMINAL (Pendapatan & Beban) ke 0\\n' +
                                '3. Menghapus SEMUA transaksi jurnal yang ada\\n' +
                                '4. Menghapus SEMUA kartu persediaan\\n' +
                                '5. Merestok ulang produk\\n' +
                                '6. Reset semua pesanan\\n' +
                                '7. Kosongkan keranjang belanja\\n\\n' +
                                'Tindakan ini TIDAK DAPAT DIBATALKAN!\\n\\n' +
                                'Apakah Anda yakin ingin melanjutkan?';
            
            if (!confirm(confirmMessage)) {
                event.preventDefault();
                return false;
            }
            
            // Tampilkan loading
            const saveButton = document.getElementById('save-button');
            saveButton.disabled = true;
            saveButton.innerHTML = '<div class="loading"></div> Memproses...';
            
            return true;
        });
        </script>
        '''
        
        content = f'''
        <div style="max-width: 1200px; margin: 0 auto;">
            <div class="card" style="margin-bottom: 2rem;">
                <h1 style="color: var(--primary); margin-bottom: 0.5rem;">
                    <i class="fas fa-edit"></i> Edit Saldo Awal Akuntansi
                </h1>
                <p style="color: #6B7280; margin-bottom: 1.5rem;">
                    <strong>Hanya edit akun REAL (Aset, Kewajiban, Ekuitas).</strong><br>
                    Pendapatan & Beban akan otomatis direset ke 0.
                </p>
                
                <!-- Quick Stats -->
                <div class="stats" style="margin-bottom: 1.5rem;">
                    <div class="stat-card">
                        <div class="stat-number">{len(asset_accounts)}</div>
                        <div class="stat-label">Akun Aset</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{len(liability_accounts)}</div>
                        <div class="stat-label">Akun Kewajiban</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{len(equity_accounts)}</div>
                        <div class="stat-label">Akun Ekuitas</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{len(nominal_accounts)}</div>
                        <div class="stat-label">Akun Nominal (auto reset)</div>
                    </div>
                </div>
            </div>
            
            {form_html}
            
            <!-- Current System Status -->
            <div class="card" style="margin-top: 2rem; background: rgba(49, 130, 206, 0.05);">
                <h4 style="color: var(--primary); margin-bottom: 1rem;">
                    <i class="fas fa-chart-line"></i> Status Sistem Saat Ini
                </h4>
                <div class="grid grid-4">
                    <div>
                        <p><strong>Total Transaksi Jurnal:</strong> {JournalEntry.query.count()}</p>
                    </div>
                    <div>
                        <p><strong>Kartu Persediaan:</strong> {InventoryCard.query.count()} entries</p>
                    </div>
                    <div>
                        <p><strong>Pesanan Aktif:</strong> {Order.query.filter(Order.status != 'completed').count()}</p>
                    </div>
                    <div>
                        <p><strong>Item di Keranjang:</strong> {CartItem.query.count()}</p>
                    </div>
                </div>
                <p style="margin-top: 1rem; font-size: 0.9rem; color: #6B7280;">
                    <i class="fas fa-info-circle"></i> Semua data di atas akan direset ketika Anda menyimpan perubahan saldo awal.
                </p>
            </div>
        </div>
        '''
        
        return base_html('Edit Saldo Awal', content)
        
    except Exception as e:
        print(f"❌ Error in edit_initial_balances: {e}")
        import traceback
        traceback.print_exc()
        flash('Terjadi error saat mengakses halaman edit saldo awal.', 'error')
        return redirect('/seller/accounting')

@app.route('/seller/reset_balances', methods=['POST'])
@login_required
@seller_required
def reset_balances():
    """Reset saldo awal ke nilai default - HANYA untuk akun REAL"""
    try:
        # Konfirmasi reset
        data = request.get_json() if request.is_json else {}
        confirm = data.get('confirm', False)
        
        if not confirm:
            return jsonify({
                'success': False, 
                'message': 'Konfirmasi reset diperlukan',
                'requires_confirm': True
            })
        
        # PERBAIKAN: Hanya reset akun REAL
        real_accounts = Account.query.filter(
            Account.category.in_(['asset', 'liability', 'equity'])
        ).all()
        
        nominal_accounts = Account.query.filter(
            Account.category.in_(['revenue', 'expense'])
        ).all()
        
        # Reset akun REAL ke default
        for account in real_accounts:
            if account.type == 'kas':
                account.balance = 10000000
            elif account.type == 'persediaan':
                account.balance = 5000000
            elif account.type == 'perlengkapan':
                account.balance = 6500000
            elif account.type == 'peralatan':
                account.balance = 5000000
            elif account.type == 'hutang':
                account.balance = 26500000  # 26.5 juta
            elif account.type == 'modal':
                account.balance = -11500000  # -11.5 juta (10+5+6.5+5 - 26.5)
            else:
                account.balance = 0
        
        # Reset akun NOMINAL ke 0
        for account in nominal_accounts:
            account.balance = 0
        
        print(f"✅ Reset {len(real_accounts)} akun REAL dan {len(nominal_accounts)} akun NOMINAL")

        # Reset product stocks sesuai saldo awal
        products = Product.query.all()
        for product in products:
            if product.name == 'Bibit Ikan Mas':
                product.stock = 2975
                product.cost_price = 1000
            elif product.name == 'Ikan Mas Konsumsi':
                product.stock = 150
                product.cost_price = 13500

        db.session.commit()

        flash('✅ Saldo awal berhasil direset ke nilai default!', 'success')
        return jsonify({
            'success': True, 
            'message': 'Saldo awal berhasil direset ke nilai default'
        })

    except Exception as e:
        print(f"Error resetting balances: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

def calculate_net_income():
    try:
        revenue_account = Account.query.filter_by(type='pendapatan').first()
        revenue = revenue_account.balance if revenue_account else 0

        expense_accounts = Account.query.filter(Account.category=='expense').all()
        expenses = sum(acc.balance for acc in expense_accounts)

        return revenue - expenses
    except Exception as e:
        print(f"Error calculating net income: {e}")
        return 0

@app.route('/seller/orders')
@login_required
@seller_required
def seller_orders():
    try:
        orders = Order.query.order_by(Order.order_date.desc()).all()

        orders_html = ""
        for order in orders:
            customer = User.query.get(order.customer_id)
            status_display = f"<span class='status-text status-{order.status}'>{order.status.upper()}</span>"
            payment_status_display = f"<span class='status-text status-{order.payment_status}'>{order.payment_status.upper()}</span>"

            tracking_steps = get_tracking_steps(order.status, order.tracking_info)

            orders_html += f'''
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div style="flex: 1;">
                        <h4>Order #{order.order_number}</h4>
                        <p><strong>Customer:</strong> {customer.full_name if customer else 'Unknown'}</p>
                        <p><strong>Total:</strong> Rp {order.total_amount:,.0f}</p>
                        <p><strong>Status:</strong> {status_display}</p>
                        <p><strong>Pembayaran:</strong> {payment_status_display}</p>
                        <p><strong>Metode:</strong> {order.payment_method} | <strong>Pengiriman:</strong> {order.shipping_method}</p>
                        <p><strong>Tanggal:</strong> {order.order_date.strftime('%d/%m/%Y %H:%M')}</p>

                        <div class="tracking-steps">
                            {tracking_steps}
                        </div>

                        {order.payment_status == 'paid' and f'''
                        <div class="form-group">
                            <label class="form-label">Update Status Pengiriman:</label>
                            <select id="tracking-info-{order.id}" class="form-control">
                                <option value="Pesanan diproses" {'selected' if order.tracking_info == 'Pesanan diproses' else ''}>Pesanan diproses</option>
                                <option value="Pesanan dikemas" {'selected' if order.tracking_info == 'Pesanan dikemas' else ''}>Pesanan dikemas</option>
                                <option value="Pesanan dikirim" {'selected' if order.tracking_info == 'Pesanan dikirim' else ''}>Pesanan dikirim</option>
                                <option value="Dalam perjalanan" {'selected' if order.tracking_info == 'Dalam perjalanan' else ''}>Dalam perjalanan</option>
                                <option value="Tiba di tujuan" {'selected' if order.tracking_info == 'Tiba di tujuan' else ''}>Tiba di tujuan</option>
                                <option value="Pesanan selesai" {'selected' if order.tracking_info == 'Pesanan selesai' else ''}>Pesanan selesai</option>
                            </select>
                        </div>
                        ''' or '''
                        <div style="margin-top: 1rem; padding: 1rem; background: rgba(229, 62, 62, 0.1); border-radius: 8px;">
                            <p style="color: var(--error); margin: 0;">
                                <strong>⚠️ Menunggu Pembayaran:</strong> Pesanan belum dapat diproses karena pembayaran belum diterima.
                            </p>
                        </div>
                        '''}
                    </div>
                    <div>
                        {get_order_actions(order)}
                        {order.payment_status == 'paid' and f'''
                        <button class="btn btn-info" onclick="updateTracking({order.id}, 'processing')">
                            <i class="fas fa-map-marker-alt"></i> Update Tracking
                        </button>
                        ''' or ''}
                    </div>
                </div>
            </div>
            '''

        content = f'''
        <h1 style="color: var(--primary);"><i class="fas fa-boxes"></i> Manajemen Pesanan</h1>
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{Order.query.filter_by(status='pending').count()}</div>
                <div class="stat-label">Pending</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{Order.query.filter_by(status='processing').count()}</div>
                <div class="stat-label">Diproses</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{Order.query.filter_by(status='completed').count()}</div>
                <div class="stat-label">Selesai</div>
            </div>
        </div>

        {orders_html}
        '''

        return base_html('Pesanan Seller', content)
    except Exception as e:
        print(f"Error in seller orders: {e}")
        flash('Terjadi error saat memuat pesanan.', 'error')
        return redirect('/seller/dashboard')

def get_tracking_steps(status, tracking_info):
    steps = [
        {'id': 'pending', 'label': 'Pesanan Diterima', 'icon': ''},
        {'id': 'processing', 'label': 'Diproses', 'icon': '⚙️'},
        {'id': 'packed', 'label': 'Dikemas', 'icon': ''},
        {'id': 'shipped', 'label': 'Dikirim', 'icon': ''},
        {'id': 'delivered', 'label': 'Tiba', 'icon': ''},
        {'id': 'completed', 'label': 'Selesai', 'icon': '✅'}
    ]

    # FIX: Mapping yang benar antara status database dan tracking steps
    status_mapping = {
        'pending': 0,      # Pesanan Diterima
        'processing': 1,   # Diproses
        'packed': 2,       # Dikemas
        'shipped': 3,      # Dikirim
        'delivered': 4,    # Tiba
        'completed': 5     # Selesai
    }

    # FIX: Gunakan mapping untuk menentukan step aktif
    current_index = status_mapping.get(status, 0)

    steps_html = ""
    for i, step in enumerate(steps):
        step_class = ""
        if i < current_index:
            step_class = "step-completed"
        elif i == current_index:
            step_class = "step-active"

        steps_html += f'''
        <div class="tracking-step">
            <div class="step-icon {step_class}">{step['icon']}</div>
            <div style="font-size: 0.8rem;">{step['label']}</div>
        </div>
        '''

    return steps_html

def get_order_actions(order):
    if order.payment_status != 'paid' and order.payment_method != 'cod':
        return '<span class="status-text status-unpaid">MENUNGGU PEMBAYARAN</span>'

    # FIX: Enable status updates untuk semua order yang sudah bayar atau COD
    status_buttons = {
        'pending': '''
            <form action="/seller/update_order_status/{order_id}" method="POST" style="display: inline;">
                <input type="hidden" name="status" value="processing">
                <button type="submit" class="btn btn-info">Proses Order</button>
            </form>
        ''',
        'processing': '''
            <form action="/seller/update_order_status/{order_id}" method="POST" style="display: inline;">
                <input type="hidden" name="status" value="packed">
                <button type="submit" class="btn btn-warning">Tandai Dikemas</button>
            </form>
        ''',
        'packed': '''
            <form action="/seller/update_order_status/{order_id}" method="POST" style="display: inline;">
                <input type="hidden" name="status" value="shipped">
                <button type="submit" class="btn btn-primary">Tandai Dikirim</button>
            </form>
        ''',
        'shipped': '''
            <form action="/seller/update_order_status/{order_id}" method="POST" style="display: inline;">
                <input type="hidden" name="status" value="delivered">
                <button type="submit" class="btn btn-info">Tandai Tiba</button>
            </form>
        ''',
        'delivered': '''
            <form action="/seller/update_order_status/{order_id}" method="POST" style="display: inline;">
                <input type="hidden" name="status" value="completed">
                <button type="submit" class="btn btn-success">Selesaikan Order</button>
            </form>
        ''',
        'completed': '<span class="status-text status-completed">SELESAI</span>'
    }

    return status_buttons.get(order.status, '').format(order_id=order.id)

# ===== ROUTE KARTU PERSEDIAAN BARU =====
@app.route('/seller/inventory-card')
@login_required
@seller_required
def seller_inventory_card():
    """Halaman kartu persediaan dengan format seperti screenshot"""
    try:
        products = Product.query.filter_by(seller_id=current_user.id).all()

        if not products:
            content = '''
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-boxes"></i> Kartu Persediaan</h2>
                <p>Belum ada produk. Silakan tambah produk terlebih dahulu.</p>
                <a href="/seller/add_product" class="btn btn-primary">
                    <i class="fas fa-plus"></i> Tambah Produk
                </a>
            </div>
            '''
            return base_html('Kartu Persediaan', content)

        # Product selection
        selected_product_id = request.args.get('product_id')
        if selected_product_id:
            selected_product = Product.query.get(selected_product_id)
        else:
            selected_product = products[0]
            selected_product_id = selected_product.id if selected_product else None

        # Generate inventory card HTML
        inventory_html = get_inventory_card_html(selected_product_id)

        # Product selection dropdown
        product_options = ""
        for product in products:
            selected = "selected" if selected_product and product.id == selected_product.id else ""
            product_options += f'<option value="{product.id}" {selected}>{product.name}</option>'

        # Summary info
        if selected_product:
            current_stock = selected_product.stock
            stock_value = current_stock * 1000  # Harga cost tetap
        else:
            current_stock = 0
            stock_value = 0

        content = f'''
        <div class="card">
            <h2 style="color: var(--primary); margin-bottom: 1.5rem;">
                <i class="fas fa-boxes"></i> Kartu Persediaan
            </h2>

            <div style="background: var(--ocean-light); padding: 1.5rem; border-radius: var(--border-radius); margin-bottom: 2rem;">
                <div class="grid grid-2">
                    <div>
                        <h4 style="color: var(--primary); margin-bottom: 0.5rem;"><i class="fas fa-info-circle"></i> Sistem Kartu Persediaan</h4>
                    </div>
                    <div style="text-align: center; padding: 1rem; background: white; border-radius: var(--border-radius);">
                        <h5 style="color: var(--primary); margin-bottom: 0.5rem;">Stock Saat Ini</h5>
                        <div style="font-size: 1.5rem; font-weight: bold; color: var(--success);">{current_stock:,} unit</div>
                        <div style="font-size: 1rem; color: var(--dark);">Nilai: Rp {stock_value:,}</div>
                    </div>
                </div>
            </div>

            <div class="form-group">
                <label class="form-label"><i class="fas fa-cube"></i> Pilih Produk:</label>
                <select id="productSelect" class="form-control" onchange="changeProduct()">
                    {product_options}
                </select>
            </div>

            {inventory_html}
        </div>

        <script>
        function changeProduct() {{
            const productId = document.getElementById('productSelect').value;
            window.location.href = '/seller/inventory-card?product_id=' + productId;
        }}

        // Auto-refresh setiap 30 detik untuk update real-time
        setTimeout(() => {{
            const currentProduct = document.getElementById('productSelect').value;
            if (currentProduct) {{
                window.location.href = '/seller/inventory-card?product_id=' + currentProduct;
            }}
        }}, 30000);
        </script>
        '''

        return base_html('Kartu Persediaan', content)

    except Exception as e:
        print(f"Error in seller inventory card: {e}")
        flash('Terjadi error saat memuat kartu persediaan.', 'error')
        return redirect('/seller/dashboard')

@app.route('/debug-inventory/<int:order_id>')
@login_required
@seller_required
def debug_inventory(order_id):
    """Route untuk debug inventory update"""
    try:
        order = Order.query.get(order_id)
        if not order:
            return jsonify({'success': False, 'message': 'Order tidak ditemukan'})

        print(f"🔍 [DEBUG] Order #{order.order_number}, Status: {order.status}, Payment: {order.payment_status}")

        # Force create sales journal untuk testing
        journal = create_sales_journal(order)

        if journal:
            return jsonify({
                'success': True,
                'message': f'Jurnal dibuat: {journal.transaction_number}',
                'journal_id': journal.id
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Gagal membuat jurnal'
            })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/seller/chart-of-accounts')
@login_required
@seller_required
def chart_of_accounts():
    """Chart of Accounts - Daftar semua akun dengan kode standar"""
    try:
        # Get all accounts grouped by category
        assets = Account.query.filter_by(category='asset').order_by(Account.code).all()
        liabilities = Account.query.filter_by(category='liability').order_by(Account.code).all()
        equity = Account.query.filter_by(category='equity').order_by(Account.code).all()
        revenue = Account.query.filter_by(category='revenue').order_by(Account.code).all()
        expenses = Account.query.filter_by(category='expense').order_by(Account.code).all()

        content = f'''
        <div class="card">
            <h2 style="color: var(--primary); margin-bottom: 1.5rem;">
                <i class="fas fa-sitemap"></i> Chart of Accounts
            </h2>
            <p style="margin-bottom: 2rem; color: #6B7280;">
                Daftar lengkap semua akun yang digunakan dalam sistem akuntansi Kang-Mas Shop
            </p>

            <!-- ASET -->
            <div style="margin-bottom: 3rem;">
                <h3 style="color: var(--success); margin-bottom: 1rem; padding: 1rem; background: rgba(56, 161, 105, 0.1); border-radius: var(--border-radius);">
                    <i class="fas fa-wallet"></i> ASET (Assets)
                </h3>
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Kode</th>
                                <th>Nama Akun</th>
                                <th>Tipe</th>
                                <th>Saldo</th>
                                <th>Keterangan</th>
                            </tr>
                        </thead>
                        <tbody>
        '''

        # Assets rows
        for account in assets:
            content += f'''
                            <tr>
                                <td><strong>{account.code}</strong></td>
                                <td>{account.name}</td>
                                <td><span class="badge" style="background: var(--success);">{account.type}</span></td>
                                <td class="debit">Rp {account.balance:,.0f}</td>
                                <td>Akun {account.category.title()} - Normal Balance: Debit</td>
                            </tr>
            '''

        content += f'''
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- KEWAJIBAN -->
            <div style="margin-bottom: 3rem;">
                <h3 style="color: var(--error); margin-bottom: 1rem; padding: 1rem; background: rgba(229, 62, 62, 0.1); border-radius: var(--border-radius);">
                    <i class="fas fa-hand-holding-usd"></i> KEWAJIBAN (Liabilities)
                </h3>
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Kode</th>
                                <th>Nama Akun</th>
                                <th>Tipe</th>
                                <th>Saldo</th>
                                <th>Keterangan</th>
                            </tr>
                        </thead>
                        <tbody>
        '''

        # Liabilities rows
        for account in liabilities:
            content += f'''
                            <tr>
                                <td><strong>{account.code}</strong></td>
                                <td>{account.name}</td>
                                <td><span class="badge" style="background: var(--error);">{account.type}</span></td>
                                <td class="credit">Rp {account.balance:,.0f}</td>
                                <td>Akun {account.category.title()} - Normal Balance: Credit</td>
                            </tr>
            '''

        content += f'''
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- EKUITAS -->
            <div style="margin-bottom: 3rem;">
                <h3 style="color: var(--primary); margin-bottom: 1rem; padding: 1rem; background: rgba(49, 130, 206, 0.1); border-radius: var(--border-radius);">
                    <i class="fas fa-user-tie"></i> EKUITAS (Equity)
                </h3>
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Kode</th>
                                <th>Nama Akun</th>
                                <th>Tipe</th>
                                <th>Saldo</th>
                                <th>Keterangan</th>
                            </tr>
                        </thead>
                        <tbody>
        '''

        # Equity rows
        for account in equity:
            content += f'''
                            <tr>
                                <td><strong>{account.code}</strong></td>
                                <td>{account.name}</td>
                                <td><span class="badge" style="background: var(--primary);">{account.type}</span></td>
                                <td class="credit">Rp {account.balance:,.0f}</td>
                                <td>Akun {account.category.title()} - Normal Balance: Credit</td>
                            </tr>
            '''

        content += f'''
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- PENDAPATAN -->
            <div style="margin-bottom: 3rem;">
                <h3 style="color: var(--teal); margin-bottom: 1rem; padding: 1rem; background: rgba(49, 130, 206, 0.1); border-radius: var(--border-radius);">
                    <i class="fas fa-chart-line"></i> PENDAPATAN (Revenue)
                </h3>
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Kode</th>
                                <th>Nama Akun</th>
                                <th>Tipe</th>
                                <th>Saldo</th>
                                <th>Keterangan</th>
                            </tr>
                        </thead>
                        <tbody>
        '''

        # Revenue rows
        for account in revenue:
            content += f'''
                            <tr>
                                <td><strong>{account.code}</strong></td>
                                <td>{account.name}</td>
                                <td><span class="badge" style="background: var(--teal);">{account.type}</span></td>
                                <td class="credit">Rp {account.balance:,.0f}</td>
                                <td>Akun {account.category.title()} - Normal Balance: Credit</td>
                            </tr>
            '''

        content += f'''
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- BEBAN -->
            <div style="margin-bottom: 2rem;">
                <h3 style="color: var(--warning); margin-bottom: 1rem; padding: 1rem; background: rgba(214, 158, 46, 0.1); border-radius: var(--border-radius);">
                    <i class="fas fa-money-bill-wave"></i> BEBAN (Expenses)
                </h3>
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Kode</th>
                                <th>Nama Akun</th>
                                <th>Tipe</th>
                                <th>Saldo</th>
                                <th>Keterangan</th>
                            </tr>
                        </thead>
                        <tbody>
        '''

        # Expenses rows
        for account in expenses:
            content += f'''
                            <tr>
                                <td><strong>{account.code}</strong></td>
                                <td>{account.name}</td>
                                <td><span class="badge" style="background: var(--warning);">{account.type}</span></td>
                                <td class="debit">Rp {account.balance:,.0f}</td>
                                <td>Akun {account.category.title()} - Normal Balance: Debit</td>
                            </tr>
            '''

        content += f'''
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- SUMMARY -->
            <div class="card" style="background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%); color: white;">
                <h3 style="color: white; margin-bottom: 1rem;"><i class="fas fa-info-circle"></i> Keterangan Chart of Accounts</h3>
                <div class="grid grid-2">
                    <div>
                        <h4 style="color: white;">Aturan Kode Akun:</h4>
                        <ul style="color: white;">
                            <li><strong>1xx</strong> - Aset (Assets)</li>
                            <li><strong>2xx</strong> - Kewajiban (Liabilities)</li>
                            <li><strong>3xx</strong> - Ekuitas (Equity)</li>
                            <li><strong>4xx</strong> - Pendapatan (Revenue)</li>
                            <li><strong>5xx</strong> - Beban (Expenses)</li>
                        </ul>
                    </div>
                    <div>
                        <h4 style="color: white;">Normal Balance:</h4>
                        <ul style="color: white;">
                            <li><span style="color: var(--success);">💚 Debit</span> - Aset & Beban</li>
                            <li><span style="color: var(--error);">❤️ Credit</span> - Kewajiban, Ekuitas & Pendapatan</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
        '''

        return base_html('Chart of Accounts', content)

    except Exception as e:
        print(f"Error in chart_of_accounts: {e}")
        flash('Terjadi error saat memuat Chart of Accounts.', 'error')
        return redirect('/seller/accounting')

# ===== PERBAIKAN FUNGSI UPDATE ORDER STATUS =====
@app.route('/seller/update_order_status/<int:order_id>', methods=['POST'])
@login_required
@seller_required
def update_order_status(order_id):
    try:
        order = Order.query.get(order_id)
        new_status = request.form.get('status')

        if order:
            old_status = order.status
            order.status = new_status

            # Update tracking info berdasarkan status
            if new_status == 'packed':
                order.tracking_info = 'Pesanan dikemas'
            elif new_status == 'shipped':
                order.tracking_info = 'Pesanan dikirim'
            elif new_status == 'delivered':
                order.tracking_info = 'Pesanan tiba di tujuan'

            # BUAT JURNAL OTOMATIS SAAT ORDER COMPLETED
            if new_status == 'completed':
                order.completed_date = datetime.now()

                # BUAT JURNAL PENJUALAN OTOMATIS
                if order.payment_method == 'cod':
                    # Untuk COD, buat jurnal penjualan
                    journal = create_cod_sales_journal(order)
                    if journal:
                        flash('Order COD diselesaikan! Jurnal penjualan otomatis dibuat.', 'success')
                    else:
                        flash('Order COD diselesaikan, tapi gagal membuat jurnal.', 'warning')
                elif order.payment_status == 'paid':
                    # Untuk non-COD yang sudah bayar, buat jurnal penjualan
                    journal = create_sales_journal(order)
                    if journal:
                        flash('Order diselesaikan! Jurnal penjualan otomatis dibuat.', 'success')
                    else:
                        flash('Order diselesaikan, tapi gagal membuat jurnal.', 'warning')
                else:
                    flash('Order diselesaikan! (Menunggu pembayaran)', 'success')

            db.session.commit()

            # Pesan status
            status_messages = {
                'processing': 'Status order diperbarui ke Diproses',
                'packed': 'Status order diperbarui ke Dikemas',
                'shipped': 'Status order diperbarui ke Dikirim',
                'delivered': 'Status order diperbarui ke Tiba',
                'completed': 'Order diselesaikan!'
            }
            flash(status_messages.get(new_status, 'Status order diperbarui!'), 'success')

        else:
            flash('Order tidak ditemukan!', 'error')

        return redirect('/seller/orders')
    except Exception as e:
        print(f"Error updating order status: {e}")
        flash('Terjadi error saat mengupdate status order.', 'error')
        return redirect('/seller/orders')

@app.route('/update_tracking/<int:order_id>', methods=['POST'])
@login_required
@seller_required
def update_tracking(order_id):
    try:
        order = Order.query.get(order_id)
        if order and order.payment_status == 'paid':
            data = request.get_json()
            order.tracking_info = data.get('tracking_info')

            tracking_mapping = {
                'Pesanan diproses': 'processing',
                'Pesanan dikemas': 'processing',
                'Pesanan dikirim': 'processing',
                'Dalam perjalanan': 'processing',
                'Tiba di tujuan': 'completed',
                'Pesanan selesai': 'completed'
            }

            new_status = tracking_mapping.get(order.tracking_info, order.status)
            if new_status != order.status:
                order.status = new_status
                if new_status == 'completed':
                    order.completed_date = datetime.now()
                    # Buat jurnal penjualan otomatis
                    create_sales_journal(order)

            db.session.commit()
            return jsonify({'success': True, 'message': 'Status pengiriman diperbarui'})

        return jsonify({'success': False, 'message': 'Order tidak ditemukan atau belum dibayar'})
    except Exception as e:
        print(f"Error updating tracking: {e}")
        return jsonify({'success': False, 'message': 'Terjadi error'})

@app.route('/seller/products')
@login_required
@seller_required
def seller_products():
    try:
        products = Product.query.filter_by(seller_id=current_user.id).all()

        products_html = ""
        for product in products:
            weight_info = f"{product.weight_kg}kg" if product.weight_kg else f"{product.size_cm}cm"
            products_html += f'''
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div style="flex: 1;">
                        <img src="{product.image_url}" alt="{product.name}" class="product-image" style="max-width: 200px;" onerror="this.style.display='none'">
                        <h4>{product.name}</h4>
                        <p>{product.description}</p>
                        <div class="price">Rp {product.price:,.0f}</div>
                        <p>Stock: {product.stock} | {weight_info} | Kategori: {product.category}</p>
                        <p>Harga Cost: Rp {product.cost_price:,.0f}</p>
                    </div>
                    <div>
                        <a href="/seller/edit_product/{product.id}" class="btn btn-warning"><i class="fas fa-edit"></i> Edit</a>
                    </div>
                </div>
            </div>
            '''

        content = f'''
        <h1 style="color: var(--primary);"><i class="fas fa-fish"></i> Manajemen Produk</h1>
        <a href="/seller/add_product" class="btn btn-primary"><i class="fas fa-plus"></i> Tambah Produk Baru</a>
        {products_html}
        '''

        return base_html('Produk Seller', content)
    except Exception as e:
        print(f"Error in seller products: {e}")
        flash('Terjadi error saat memuat produk.', 'error')
        return redirect('/seller/dashboard')

# TAMBAHKAN SETELAH ROUTE YANG DIHAPUS:

@app.route('/seller/inventory')
@login_required
@seller_required
def seller_inventory():
    """Kartu persediaan otomatis - hanya menampilkan data dari transaksi"""
    try:
        products = Product.query.filter_by(seller_id=current_user.id).all()

        if not products:
            content = '''
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-boxes"></i> Kartu Persediaan</h2>
                <p>Belum ada produk. Silakan tambah produk terlebih dahulu.</p>
                <a href="/seller/add_product" class="btn btn-primary">
                    <i class="fas fa-plus"></i> Tambah Produk
                </a>
            </div>
            '''
            return base_html('Kartu Persediaan', content)

        # Product selection
        selected_product_id = request.args.get('product_id')
        if selected_product_id:
            selected_product = Product.query.get(selected_product_id)
        else:
            selected_product = products[0]

        # Get automatic inventory transactions
        transactions = []
        if selected_product:
            transactions = InventoryTransaction.query.filter_by(
                product_id=selected_product.id
            ).order_by(InventoryTransaction.date, InventoryTransaction.id).all()

        # Generate inventory card HTML
        inventory_html = generate_automatic_inventory_html(selected_product, transactions)

        # Product selection dropdown
        product_options = ""
        for product in products:
            selected = "selected" if selected_product and product.id == selected_product.id else ""
            product_options += f'<option value="{product.id}" {selected}>{product.name}</option>'

        content = f'''
        <div class="card">
            <h2 style="color: var(--primary); margin-bottom: 1.5rem;">
                <i class="fas fa-boxes"></i> Kartu Persediaan Otomatis
            </h2>

            <div style="background: var(--ocean-light); padding: 1.5rem; border-radius: var(--border-radius); margin-bottom: 2rem;">
                <h4 style="color: var(--primary); margin-bottom: 0.5rem;"><i class="fas fa-info-circle"></i> Sistem Otomatis</h4>
                <p style="margin: 0;">Kartu persediaan ini terupdate otomatis dari transaksi penjualan dan pembelian.
                Tidak perlu input manual!</p>
            </div>

            <div class="form-group">
                <label class="form-label">Pilih Produk:</label>
                <select id="productSelect" class="form-control" onchange="changeProduct()">
                    {product_options}
                </select>
            </div>

            {inventory_html}
        </div>

        <script>
        function changeProduct() {{
            const productId = document.getElementById('productSelect').value;
            window.location.href = '/seller/inventory?product_id=' + productId;
        }}
        </script>
        '''

        return base_html('Kartu Persediaan', content)

    except Exception as e:
        print(f"Error in seller inventory: {e}")
        flash('Terjadi error saat memuat kartu persediaan.', 'error')
        return redirect('/seller/dashboard')

@app.route('/test-auto-journal')
@login_required
@seller_required
def test_auto_journal():
    """Route untuk testing jurnal otomatis"""
    try:
        # Cari order yang completed tapi belum ada jurnal
        orders = Order.query.filter_by(status='completed').all()

        results = []
        for order in orders:
            # Cek apakah sudah ada jurnal untuk order ini
            existing_journal = JournalEntry.query.filter(
                JournalEntry.description.like(f"%{order.order_number}%")
            ).first()

            if not existing_journal:
                # Coba buat jurnal
                if order.payment_method == 'cod':
                    journal = create_cod_sales_journal(order)
                else:
                    journal = create_sales_journal(order)

                results.append({
                    'order': order.order_number,
                    'status': 'Jurnal dibuat' if journal else 'Gagal buat jurnal'
                })
            else:
                results.append({
                    'order': order.order_number,
                    'status': 'Jurnal sudah ada'
                })

        return jsonify({
            'success': True,
            'results': results
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

def generate_automatic_inventory_html(product, transactions):
    """Generate HTML untuk kartu persediaan otomatis dengan format yang benar"""
    if not product:
        return '<p>Produk tidak ditemukan</p>'

    if not transactions:
        return f'''
        <div style="text-align: center; padding: 3rem; color: #6B7280;">
            <i class="fas fa-inbox" style="font-size: 4rem; margin-bottom: 1rem;"></i>
            <h4>Belum Ada Transaksi</h4>
            <p>Transaksi persediaan akan tercatat otomatis ketika ada penjualan atau pembelian.</p>
        </div>
        '''

    # PERBAIKAN: Gunakan struktur tabel yang sesuai dengan screenshot
    table_html = f'''
    <div style="margin-top: 2rem;">
        <h3 style="color: var(--primary); margin-bottom: 1rem;">Item: {product.name}</h3>
        <div style="overflow-x: auto;">
            <table class="table" style="font-size: 0.9rem; min-width: 1000px;">
                <thead>
                    <tr>
                        <th>TANGGAL</th>
                        <th>DESKRIPSI</th>
                        <th style="text-align: center;" colspan="3">QUANTITY</th>
                        <th style="text-align: center;" colspan="3">HARGA PER UNIT</th>
                        <th style="text-align: center;" colspan="3">JUMLAH</th>
                    </tr>
                    <tr>
                        <th></th>
                        <th></th>
                        <!-- Quantity Sub-headers -->
                        <th style="text-align: center; background: rgba(56, 161, 105, 0.1);">IN</th>
                        <th style="text-align: center; background: rgba(229, 62, 62, 0.1);">OUT</th>
                        <th style="text-align: center; background: rgba(49, 130, 206, 0.1);">BALANCE</th>
                        <!-- Harga Sub-headers -->
                        <th style="text-align: center; background: rgba(56, 161, 105, 0.1);">IN</th>
                        <th style="text-align: center; background: rgba(229, 62, 62, 0.1);">OUT</th>
                        <th style="text-align: center; background: rgba(49, 130, 206, 0.1);">BALANCE</th>
                        <!-- Jumlah Sub-headers -->
                        <th style="text-align: center; background: rgba(56, 161, 105, 0.1);">IN</th>
                        <th style="text-align: center; background: rgba(229, 62, 62, 0.1);">OUT</th>
                        <th style="text-align: center; background: rgba(49, 130, 206, 0.1);">BALANCE</th>
                    </tr>
                </thead>
                <tbody>
    '''

    # Harga cost tetap Rp 1,000
    COST_PRICE = 1000

    for transaction in transactions:
        # Tentukan data untuk kolom IN dan OUT berdasarkan jenis transaksi
        if transaction.transaction_type == 'pembelian':
            in_qty = transaction.quantity_in
            in_price = transaction.unit_price
            in_total = transaction.total_amount
            out_qty = 0
            out_price = 0
            out_total = 0
        elif transaction.transaction_type == 'penjualan':
            in_qty = 0
            in_price = 0
            in_total = 0
            out_qty = transaction.quantity_out
            out_price = transaction.unit_price  # Harga cost (bukan harga jual)
            out_total = transaction.total_amount
        else:  # saldo_awal, penyesuaian, dll
            in_qty = transaction.quantity_in
            in_price = transaction.unit_price
            in_total = transaction.total_amount
            out_qty = transaction.quantity_out
            out_price = transaction.unit_price
            out_total = transaction.total_amount

        # PERBAIKAN: Selalu gunakan harga cost Rp 1,000 untuk kolom Balance
        balance_quantity = transaction.balance_quantity
        balance_unit_price = COST_PRICE  # SELALU Rp 1,000
        balance_total = balance_quantity * COST_PRICE  # Hitung ulang dengan harga cost

        # Format numbers dengan separator
        def format_number(num):
            return f"{num:,.0f}" if num != 0 else ""

        def format_currency(num):
            return f"Rp {num:,.0f}" if num != 0 else ""

        table_html += f'''
        <tr>
            <td>{transaction.date.strftime('%d/%m/%Y')}</td>
            <td>{transaction.description}</td>
            <!-- QUANTITY Columns -->
            <td style="text-align: right; background: rgba(56, 161, 105, 0.05);">{format_number(in_qty)}</td>
            <td style="text-align: right; background: rgba(229, 62, 62, 0.05);">{format_number(out_qty)}</td>
            <td style="text-align: right; background: rgba(49, 130, 206, 0.05); font-weight: bold;">{format_number(balance_quantity)}</td>
            <!-- HARGA PER UNIT Columns -->
            <td style="text-align: right; background: rgba(56, 161, 105, 0.05);">{format_currency(in_price)}</td>
            <td style="text-align: right; background: rgba(229, 62, 62, 0.05);">{format_currency(out_price)}</td>
            <td style="text-align: right; background: rgba(49, 130, 206, 0.05); font-weight: bold;">{format_currency(balance_unit_price)}</td>
            <!-- JUMLAH Columns -->
            <td style="text-align: right; background: rgba(56, 161, 105, 0.05);">{format_currency(in_total)}</td>
            <td style="text-align: right; background: rgba(229, 62, 62, 0.05);">{format_currency(out_total)}</td>
            <td style="text-align: right; background: rgba(49, 130, 206, 0.05); font-weight: bold;">{format_currency(balance_total)}</td>
        </tr>
        '''

    table_html += '''
                </tbody>
            </table>
        </div>

        <div style="margin-top: 1rem; padding: 1rem; background: var(--ocean-light); border-radius: var(--border-radius);">
            <h5 style="color: var(--primary); margin-bottom: 0.5rem;">Keterangan:</h5>
            <ul style="margin: 0; font-size: 0.9rem;">
                <li><strong style="color: var(--success);">IN (Hijau):</strong> Transaksi pembelian atau penambahan stok</li>
                <li><strong style="color: var(--error);">OUT (Merah):</strong> Transaksi penjualan atau pengurangan stok</li>
                <li><strong style="color: var(--primary);">BALANCE (Biru):</strong> Saldo akhir setelah transaksi</li>
                <li><strong>Harga Cost:</strong> Rp 1,000 per unit (tetap)</li>
                <li>Semua harga menggunakan <strong>harga cost tetap</strong> untuk perhitungan persediaan</li>
            </ul>
        </div>
    </div>
    '''

    return table_html

@app.route('/seller/add_product', methods=['GET', 'POST'])
@login_required
@seller_required
def add_product():
    try:
        if request.method == 'POST':
            name = request.form.get('name')
            description = request.form.get('description')
            price = float(request.form.get('price'))
            cost_price = float(request.form.get('cost_price'))
            stock = int(request.form.get('stock'))
            size_cm = request.form.get('size_cm')
            weight_kg = request.form.get('weight_kg')
            category = request.form.get('category')

            product = Product(
                name=name,
                description=description,
                price=price,
                cost_price=cost_price,
                stock=stock,
                size_cm=float(size_cm) if size_cm else None,
                weight_kg=float(weight_kg) if weight_kg else None,
                category=category,
                seller_id=current_user.id
            )

            # Handle image upload
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename != '':
                    filename = save_product_image(file, product.name)
                    if filename:
                        product.image_url = f'/static/{filename}'

            db.session.add(product)
            db.session.commit()

            # ===========================================

            flash('Produk berhasil ditambahkan dan disinkronisasi ke cloud!', 'success')
            return redirect('/seller/products')

        # GET Method - Tampilkan form
        content = '''
        <div style="max-width: 600px; margin: 0 auto;">
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-plus"></i> Tambah Produk Baru</h2>

                <form method="POST" enctype="multipart/form-data" id="addProductForm">
                    <div class="form-group">
                        <label class="form-label">Gambar Produk</label>
                        <input type="file" name="image" class="form-control" accept="image/*">
                        <small>Format: PNG, JPG, JPEG, GIF, WEBP (max 16MB)</small>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Nama Produk</label>
                        <input type="text" name="name" class="form-control" required>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Deskripsi</label>
                        <textarea name="description" class="form-control" required></textarea>
                    </div>

                    <div class="grid grid-2">
                        <div class="form-group">
                            <label class="form-label">Harga Jual</label>
                            <input type="number" name="price" class="form-control" step="1" min="0" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Harga Cost</label>
                            <input type="number" name="cost_price" class="form-control" step="1" min="0" required>
                        </div>
                    </div>

                    <div class="grid grid-3">
                        <div class="form-group">
                            <label class="form-label">Stock</label>
                            <input type="number" name="stock" class="form-control" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Kategori</label>
                            <select name="category" class="form-control" required>
                                <option value="bibit">Bibit</option>
                                <option value="konsumsi">Konsumsi</option>
                                <option value="ikan_mas">Ikan Mas</option>
                            </select>
                        </div>
                    </div>

                    <div class="grid grid-2">
                        <div class="form-group">
                            <label class="form-label">Ukuran (cm)</label>
                            <input type="number" name="size_cm" class="form-control" step="0.1">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Berat (kg)</label>
                            <input type="number" name="weight_kg" class="form-control" step="0.1">
                        </div>
                    </div>

                    <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Simpan Produk</button>
                </form>
            </div>
        </div>

        <script>
        // Nonaktifkan formatting untuk input number di form ini
        document.querySelectorAll('#addProductForm input[type="number"]').forEach(input => {
            // Biarkan input number seperti biasa tanpa formatting
            input.addEventListener('input', function(e) {
                // Biarkan input seperti biasa
            });

            input.addEventListener('blur', function(e) {
                // Biarkan input seperti biasa
            });

            input.addEventListener('focus', function(e) {
                // Biarkan input seperti biasa
            });
        });
        </script>
        '''
        return base_html('Tambah Produk', content)

    except Exception as e:
        print(f"Error in add_product: {e}")
        flash('Terjadi error saat menambah produk.', 'error')
        return redirect('/seller/products')

@app.route('/seller/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
@seller_required
def edit_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)

        if request.method == 'POST':
            product.name = request.form.get('name')
            product.description = request.form.get('description')

            # Parse harga tanpa formatting
            price_str = request.form.get('price', '0').replace('.', '').replace(',', '')
            cost_price_str = request.form.get('cost_price', '0').replace('.', '').replace(',', '')

            product.price = float(price_str) if price_str else 0
            product.cost_price = float(cost_price_str) if cost_price_str else 0
            product.stock = int(request.form.get('stock', 0))
            product.size_cm = float(request.form.get('size_cm')) if request.form.get('size_cm') else None
            product.weight_kg = float(request.form.get('weight_kg')) if request.form.get('weight_kg') else None
            product.category = request.form.get('category')

            # Handle image upload
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename != '':
                    filename = save_product_image(file, product.name)
                    if filename:
                        product.image_url = f'/static/{filename}'

            db.session.commit()
            flash('Produk berhasil diperbarui!', 'success')
            return redirect('/seller/products')

        content = f'''
        <div style="max-width: 600px; margin: 0 auto;">
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-edit"></i> Edit Produk</h2>

                <form method="POST" enctype="multipart/form-data" id="editProductForm">
                    <div class="form-group">
                        <label class="form-label">Gambar Produk</label>
                        <input type="file" name="image" class="form-control" accept="image/*">
                        <small>Upload gambar baru untuk mengganti gambar saat ini</small>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Nama Produk</label>
                        <input type="text" name="name" class="form-control" value="{product.name}" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Deskripsi</label>
                        <textarea name="description" class="form-control" required>{product.description}</textarea>
                    </div>
                    <div class="grid grid-2">
                        <div class="form-group">
                            <label class="form-label">Harga Jual</label>
                            <input type="number" name="price" class="form-control" step="1" min="0" value="{int(product.price)}" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Harga Cost</label>
                            <input type="number" name="cost_price" class="form-control" step="1" min="0" value="{int(product.cost_price)}" required>
                        </div>
                    </div>
                    <div class="grid grid-3">
                        <div class="form-group">
                            <label class="form-label">Stock</label>
                            <input type="number" name="stock" class="form-control" value="{product.stock}" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Kategori</label>
                            <select name="category" class="form-control" required>
                                <option value="bibit" {'selected' if product.category == 'bibit' else ''}>Bibit</option>
                                <option value="konsumsi" {'selected' if product.category == 'konsumsi' else ''}>Konsumsi</option>
                                <option value="ikan_mas" {'selected' if product.category == 'ikan_mas' else ''}>Ikan Mas</option>
                            </select>
                        </div>
                    </div>
                    <div class="grid grid-2">
                        <div class="form-group">
                            <label class="form-label">Ukuran (cm)</label>
                            <input type="number" name="size_cm" class="form-control" step="0.1" value="{product.size_cm or ''}">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Berat (kg)</label>
                            <input type="number" name="weight_kg" class="form-control" step="0.1" value="{product.weight_kg or ''}">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Update Produk</button>
                </form>

                <div style="margin-top: 2rem;">
                    <h4>Gambar Saat Ini:</h4>
                    <img src="{product.image_url}" alt="{product.name}"
                         style="max-width: 200px; height: auto; border-radius: 8px; margin-top: 1rem;"
                         onerror="this.style.display='none'">
                </div>
            </div>
        </div>

        <script>
        // Nonaktifkan formatting untuk input number di form ini
        document.querySelectorAll('#editProductForm input[type=\"number\"]').forEach(input => {{
            // Hapus formatting yang mengganggu
            input.addEventListener('input', function(e) {{
                // Biarkan input seperti biasa
            }});

            input.addEventListener('blur', function(e) {{
                // Biarkan input seperti biasa
            }});

            input.addEventListener('focus', function(e) {{
                // Biarkan input seperti biasa
            }});
        }});
        </script>
        '''
        return base_html('Edit Produk', content)
    except Exception as e:
        print(f"Error editing product: {e}")
        flash('Terjadi error saat mengupdate produk.', 'error')
        return redirect('/seller/products')

# ===== ROUTES AKUNTANSI =====
@app.route('/seller/accounting')
@login_required
@seller_required
def seller_accounting():
    try:
        content = get_simplified_accounting_content()
        return base_html('Akuntansi', content)
    except Exception as e:
        print(f"Error in accounting: {e}")
        flash('Terjadi error saat memuat data akuntansi.', 'error')
        return redirect('/seller/dashboard')

@app.route('/api/get_closing_entries_html')
@login_required
@seller_required
def get_closing_entries_html():
    """Return HTML untuk tab Jurnal Penutup"""
    try:
        # Ambil HTML jurnal penutup yang sudah ada
        closing_html = get_proper_closing_entries_html()
        
        # Buat button untuk create closing entries
        button_html = '''
        <div style="margin-bottom: 2rem;">
            <button class="btn btn-success" onclick="createClosingEntries()" 
                    style="padding: 1rem 2rem; font-size: 1.1rem;">
                <i class="fas fa-calculator"></i> Buat Jurnal Penutup Otomatis
            </button>
            
            <div style="margin-top: 1rem; color: #6B7280; font-size: 0.9rem;">
                <i class="fas fa-info-circle"></i> Tombol ini akan menutup semua akun pendapatan dan beban, 
                menghitung laba/rugi, dan memindahkannya ke akun Modal.
            </div>
        </div>
        '''
        
        return button_html + closing_html
        
    except Exception as e:
        print(f"Error getting closing entries HTML: {e}")
        return '<div class="card"><p>Error loading closing entries</p></div>'

@app.route('/api/get_transaction_template/<template_key>')
@login_required
@seller_required
def get_transaction_template(template_key):
    try:
        if template_key not in TRANSACTION_TEMPLATES:
            return jsonify({'success': False, 'message': 'Template tidak ditemukan'})

        template = TRANSACTION_TEMPLATES[template_key]
        accounts_map = {}

        # Build accounts mapping
        for account in Account.query.all():
            accounts_map[account.type] = account

        form_html = f'''
        <form id="templateJournalForm">
            <input type="hidden" name="template_key" value="{template_key}">

            <div class="form-group">
                <label class="form-label">Tanggal Transaksi</label>
                <input type="date" name="date" class="form-control" required value="{datetime.now().strftime('%Y-%m-%d')}">
            </div>

            <div class="form-group">
                <label class="form-label">Keterangan</label>
                <input type="text" name="description" class="form-control" value="{template['description']}" required>
            </div>
        '''

        # Tampilkan input fields jika ada
        if 'inputs' in template:
            form_html += '<h4 style="margin: 1.5rem 0 1rem 0; color: var(--primary);">Detail Input:</h4>'
            
            for input_field in template['inputs']:
                default_value = input_field.get('default', '')
                form_html += f'''
                <div class="form-group">
                    <label class="form-label">{input_field['label']}</label>
                    <input type="number" id="input_{input_field['name']}" name="{input_field['name']}"
                           class="form-control" step="1" min="0" {'required' if input_field['required'] else ''}
                           value="{default_value}"
                           placeholder="Masukkan {input_field['label'].lower()}">
                </div>
                '''

        form_html += '<h4 style="margin: 1.5rem 0 1rem 0; color: var(--primary);">Detail Akun:</h4>'

        # Counter untuk handle duplicate account types
        account_counters = {}

        for i, entry in enumerate(template['entries']):
            account = accounts_map.get(entry['account_type'])
            if account:
                # Handle duplicate account types
                if entry['account_type'] in account_counters:
                    account_counters[entry['account_type']] += 1
                    input_id = f"amount_{entry['account_type']}_{account_counters[entry['account_type']]}"
                else:
                    account_counters[entry['account_type']] = 1
                    input_id = f"amount_{entry['account_type']}"

                form_html += f'''
                <div class="form-group">
                    <label class="form-label">
                        {account.code} - {account.name}
                        <span style="color: {'var(--success)' if entry['side'] == 'debit' else 'var(--error)'}; font-weight: 600;">
                            ({'Debit' if entry['side'] == 'debit' else 'Kredit'})
                        </span>
                    </label>
                    <input type="number" id="{input_id}" name="{input_id}"
                           class="form-control" step="1" min="0" required
                           placeholder="Masukkan nominal {entry['description']}">
                </div>
                '''

        form_html += '''
            <button type="button" class="btn btn-primary" onclick="submitTemplateJournal()">
                <i class="fas fa-save"></i> Simpan Jurnal
            </button>
        </form>

        <script>
        // Auto-calculate amounts based on inputs for kerugian templates
        function calculateKerugianAmounts() {
            const templateKey = document.querySelector('input[name="template_key"]').value;
            
            if (templateKey.includes('kerugian') || templateKey.includes('hibah')) {
                const quantityInput = document.getElementById('input_quantity');
                const unitCostInput = document.getElementById('input_unit_cost');
                const persediaanInput = document.getElementById('amount_persediaan');
                
                if (quantityInput && unitCostInput && persediaanInput) {
                    const quantity = parseInt(quantityInput.value) || 0;
                    const unitCost = parseInt(unitCostInput.value) || 1000;
                    const totalAmount = quantity * unitCost;
                    
                    persediaanInput.value = totalAmount;
                    
                    // Auto-fill beban_kerugian dengan jumlah yang sama
                    const bebanKerugianInput = document.getElementById('amount_beban_kerugian') || 
                                              document.getElementById('amount_beban_kerugian_1');
                    if (bebanKerugianInput) {
                        bebanKerugianInput.value = totalAmount;
                    }
                }
            }
        }

        // Add event listeners to input fields
        document.addEventListener('DOMContentLoaded', function() {
            const quantityInput = document.getElementById('input_quantity');
            const unitCostInput = document.getElementById('input_unit_cost');
            
            if (quantityInput) {
                quantityInput.addEventListener('input', calculateKerugianAmounts);
            }
            if (unitCostInput) {
                unitCostInput.addEventListener('input', calculateKerugianAmounts);
            }
            
            // Calculate on page load
            setTimeout(calculateKerugianAmounts, 100);
        });
        </script>
        '''

        return jsonify({'success': True, 'form_html': form_html})

    except Exception as e:
        print(f"Error getting transaction template: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/get_sales_form')
@login_required
@seller_required
def get_sales_form():
    """Return form HTML untuk input penjualan sederhana"""
    form_html = '''
    <div class="card">
        <h4 style="color: var(--primary); margin-bottom: 1.5rem;">
            <i class="fas fa-cash-register"></i> Form Penjualan Sederhana
        </h4>

        <form id="salesJournalForm">
            <div class="form-group">
                <label class="form-label">Tanggal Penjualan</label>
                <input type="date" name="date" class="form-control" required value="''' + datetime.now().strftime('%Y-%m-%d') + '''">
            </div>

            <div class="form-group">
                <label class="form-label">Jenis Produk</label>
                <select name="product_type" id="product_type" class="form-control" required>
                    <option value="">Pilih Jenis Produk</option>
                    <option value="bibit">Bibit Ikan Mas</option>
                    <option value="konsumsi">Ikan Mas Konsumsi</option>
                    <option value="lainnya">Produk Lainnya</option>
                </select>
            </div>

            <div class="form-group">
                <label class="form-label">Metode Pembayaran</label>
                <select name="payment_method" id="payment_method" class="form-control" required>
                    <option value="">Pilih Metode Pembayaran</option>
                    <option value="tunai">Tunai</option>
                    <option value="kredit">Kredit</option>
                </select>
            </div>

            <div class="form-group">
                <label class="form-label">Quantity</label>
                <input type="number" name="quantity" id="quantity" class="form-control" min="1" required
                       placeholder="Masukkan jumlah">
            </div>

            <div class="grid grid-2">
                <div class="form-group">
                    <label class="form-label">Harga Jual per Unit</label>
                    <input type="number" id="selling_price" name="selling_price" class="form-control"
                           min="0" required placeholder="Masukkan harga jual">
                </div>
                <div class="form-group">
                    <label class="form-label">Harga Pokok Produksi per Unit</label>
                    <input type="number" id="cost_price" name="cost_price" class="form-control"
                           min="0" required placeholder="Masukkan harga pokok produksi">
                </div>
            </div>

            <div class="grid grid-2">
                <div class="form-group">
                    <label class="form-label">Total Penjualan</label>
                    <input type="number" id="total_sales" class="form-control" readonly
                           style="background-color: #e8f5e8; font-weight: bold; color: #16a34a;">
                </div>
                <div class="form-group">
                    <label class="form-label">Total HPP</label>
                    <input type="number" id="total_hpp" class="form-control" readonly
                           style="background-color: #ffe8e8; font-weight: bold; color: #dc2626;">
                </div>
            </div>

            <div class="form-group">
                <label class="form-label">Keterangan</label>
                <input type="text" name="description" id="description" class="form-control"
                       placeholder="Contoh: Penjualan bibit ikan mas ke Budi">
            </div>

            <button type="button" class="btn btn-success" onclick="submitSalesForm()"
                    style="width: 100%; padding: 1rem;">
                <i class="fas fa-calculator"></i> Buat Jurnal Penjualan
            </button>
        </form>
    </div>

    <script>
    // Inisialisasi event listeners setelah form dimuat
    document.addEventListener('DOMContentLoaded', function() {
        console.log("✅ Form penjualan sederhana dimuat");
    });
    </script>
    '''

    return jsonify({'success': True, 'form_html': form_html})

@app.route('/api/get_purchase_form')
@login_required
@seller_required
def get_purchase_form():
    """Return form HTML untuk input pembelian sederhana - HANYA UNTUK IKAN"""
    form_html = '''
    <div class="card">
        <h4 style="color: var(--primary); margin-bottom: 1.5rem;">
            <i class="fas fa-shopping-cart"></i> Form Pembelian Sederhana - Hanya untuk Ikan
        </h4>

        <form id="purchaseJournalForm">
            <div class="form-group">
                <label class="form-label">Tanggal Pembelian</label>
                <input type="date" name="date" class="form-control" required value="''' + datetime.now().strftime('%Y-%m-%d') + '''">
            </div>

            <div class="form-group">
                <label class="form-label">Jenis Ikan</label>
                <select name="product_type" id="purchase_product_type" class="form-control" required>
                    <option value="">Pilih Jenis Ikan</option>
                    <option value="bibit">Bibit Ikan Mas</option>
                    <option value="konsumsi">Ikan Mas Konsumsi</option>
                </select>
            </div>

            <div class="form-group">
                <label class="form-label">Metode Pembayaran</label>
                <select name="payment_method" id="purchase_payment_method" class="form-control" required>
                    <option value="">Pilih Metode Pembayaran</option>
                    <option value="tunai">Tunai</option>
                    <option value="kredit">Kredit</option>
                </select>
            </div>

            <div class="form-group">
                <label class="form-label">Quantity</label>
                <input type="number" name="quantity" id="purchase_quantity" class="form-control" min="1" required
                       placeholder="Masukkan jumlah" oninput="calculatePurchaseTotals()">
            </div>

            <div class="grid grid-2">
                <div class="form-group">
                    <label class="form-label">Harga Beli per Unit</label>
                    <input type="number" id="purchase_price" name="purchase_price" class="form-control"
                           min="0" required placeholder="Masukkan harga beli" oninput="calculatePurchaseTotals()">
                </div>
                <div class="form-group">
                    <label class="form-label">Harga Jual per Unit</label>
                    <input type="number" id="selling_price" name="selling_price" class="form-control"
                           min="0" required placeholder="Masukkan harga jual">
                </div>
            </div>

            <div class="form-group">
                <label class="form-label">Total Pembelian</label>
                <input type="number" id="purchase_total" class="form-control" readonly
                       style="background-color: #e8f5e8; font-weight: bold; color: #16a34a; font-size: 1.1rem; padding: 1rem;"
                       placeholder="0">
            </div>

            <div class="form-group">
                <label class="form-label">Keterangan</label>
                <input type="text" name="description" id="purchase_description" class="form-control"
                       placeholder="Contoh: Pembelian bibit ikan mas dari Supplier A">
            </div>

            <button type="button" class="btn btn-success" onclick="submitPurchaseForm()"
                    style="width: 100%; padding: 1rem;">
                <i class="fas fa-calculator"></i> Buat Jurnal Pembelian
            </button>
        </form>
    </div>

    <script>
    // Data harga default untuk pembelian IKAN SAJA
    const purchaseDefaultPrices = {
        'bibit': {
            purchase_price: 1000,
            selling_price: 2000,
            name: 'Bibit Ikan Mas'
        },
        'konsumsi': {
            purchase_price: 13500,
            selling_price: 20000,
            name: 'Ikan Mas Konsumsi'
        }
    };

    // Fungsi untuk menghitung total pembelian
    function calculatePurchaseTotals() {
        const quantity = parseInt(document.getElementById('purchase_quantity').value) || 0;
        const purchasePrice = parseInt(document.getElementById('purchase_price').value) || 0;

        const totalPurchase = purchasePrice * quantity;

        const totalPurchaseInput = document.getElementById('purchase_total');
        if (totalPurchaseInput) {
            totalPurchaseInput.value = totalPurchase;
            // Format tampilan dengan titik sebagai pemisah ribuan
            totalPurchaseInput.style.color = totalPurchase > 0 ? '#16a34a' : '#6b7280';
        }
    }

    // Fungsi untuk mengisi harga default pembelian
    function fillPurchaseDefaultPrices() {
        const productType = document.getElementById('purchase_product_type').value;

        if (productType && purchaseDefaultPrices[productType]) {
            const product = purchaseDefaultPrices[productType];

            const purchasePriceInput = document.getElementById('purchase_price');
            const sellingPriceInput = document.getElementById('selling_price');
            const descriptionInput = document.getElementById('purchase_description');

            if (purchasePriceInput) purchasePriceInput.value = product.purchase_price;
            if (sellingPriceInput) sellingPriceInput.value = product.selling_price;
            if (descriptionInput) descriptionInput.value = 'Pembelian ' + product.name;

            calculatePurchaseTotals();
        }
    }

    // Event listeners untuk form pembelian
    document.addEventListener('DOMContentLoaded', function() {
        console.log("✅ Form pembelian sederhana dimuat - HANYA UNTUK IKAN");

        // Isi harga default ketika jenis produk dipilih
        document.getElementById('purchase_product_type').addEventListener('change', fillPurchaseDefaultPrices);

        // Hitung ulang total ketika quantity atau harga berubah
        document.getElementById('purchase_quantity').addEventListener('input', calculatePurchaseTotals);
        document.getElementById('purchase_price').addEventListener('input', calculatePurchaseTotals);

        // Juga hitung saat form pertama kali dimuat
        calculatePurchaseTotals();
    });

    // Fungsi untuk submit form pembelian
    function submitPurchaseForm() {
        console.log("🔄 Submit Purchase Form dipanggil");

        const productType = document.getElementById('purchase_product_type').value;
        const paymentMethod = document.getElementById('purchase_payment_method').value;
        const quantity = parseInt(document.getElementById('purchase_quantity').value) || 0;
        const purchasePrice = parseInt(document.getElementById('purchase_price').value) || 0;
        const sellingPrice = parseInt(document.getElementById('selling_price').value) || 0;
        const description = document.getElementById('purchase_description').value;
        const dateInput = document.querySelector('#purchaseJournalForm input[name="date"]');
        const date = dateInput ? dateInput.value : new Date().toISOString().split('T')[0];
        const totalPurchase = parseInt(document.getElementById('purchase_total').value) || 0;

        console.log("📊 Data pembelian yang akan dikirim:", {
            productType, paymentMethod, quantity, purchasePrice, sellingPrice, description, date, totalPurchase
        });

        // Validasi input
        if (!productType) {
            alert('❌ Harap pilih jenis ikan!');
            return;
        }

        if (!paymentMethod) {
            alert('❌ Harap pilih metode pembayaran!');
            return;
        }

        if (!quantity || quantity <= 0) {
            alert('❌ Harap isi quantity dengan angka lebih dari 0!');
            return;
        }

        if (!purchasePrice || purchasePrice <= 0) {
            alert('❌ Harap isi harga beli dengan angka lebih dari 0!');
            return;
        }

        if (!sellingPrice || sellingPrice <= 0) {
            alert('❌ Harap isi harga jual dengan angka lebih dari 0!');
            return;
        }

        // Data untuk dikirim
        const data = {
            date: date,
            product_type: productType,
            payment_method: paymentMethod,
            quantity: quantity,
            purchase_price: purchasePrice,
            selling_price: sellingPrice,
            description: description || 'Pembelian ikan'
        };

        // Tampilkan konfirmasi
        const productName = purchaseDefaultPrices[productType] ? purchaseDefaultPrices[productType].name : 'Ikan';

        const confirmMessage = 'Konfirmasi Pembelian Ikan:\\n\\n' +
                            'Jenis Ikan: ' + productName + '\\n' +
                            'Quantity: ' + quantity + ' unit\\n' +
                            'Harga Beli: Rp ' + purchasePrice.toLocaleString() + ' per unit\\n' +
                            'Harga Jual: Rp ' + sellingPrice.toLocaleString() + ' per unit\\n' +
                            'Metode: ' + (paymentMethod === 'tunai' ? 'Tunai' : 'Kredit') + '\\n\\n' +
                            'Total Pembelian: Rp ' + totalPurchase.toLocaleString() + '\\n\\n' +
                            'Buat jurnal pembelian?';

        if (!confirm(confirmMessage)) {
            return;
        }

        // Tampilkan loading
        const button = event.target;
        const originalText = button.innerHTML;
        button.innerHTML = '<div class="loading"></div> Memproses...';
        button.disabled = true;

        // Kirim data ke server
        fetch('/seller/add_purchase_journal', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(result => {
            console.log("✅ Response dari server:", result);
            if (result.success) {
                alert('✅ ' + result.message);
                setTimeout(() => location.reload(), 1500);
            } else {
                alert('❌ ' + result.message);
                button.innerHTML = originalText;
                button.disabled = false;
            }
        })
        .catch(error => {
            console.error("❌ Error:", error);
            alert('❌ Terjadi error: ' + error);
            button.innerHTML = originalText;
            button.disabled = false;
        });
    }
    </script>
    '''

    return jsonify({'success': True, 'form_html': form_html})

@app.route('/seller/add_sales_journal', methods=['POST'])
@login_required
@seller_required
def add_sales_journal():
    """Proses input penjualan sederhana dan buat jurnal otomatis"""
    try:
        data = request.get_json()
        print("📦 Data received:", data)

        date = datetime.strptime(data['date'], '%Y-%m-%d')
        product_type = data['product_type']
        payment_method = data['payment_method']
        quantity = data['quantity']
        selling_price = data['selling_price']
        cost_price = data['cost_price']
        description = data['description']

        print(f"📦 Processing sales: {product_type}, Qty: {quantity}, Price: {selling_price}, Cost: {cost_price}")

        # Validasi
        if selling_price <= 0 or cost_price <= 0 or quantity <= 0:
            return jsonify({'success': False, 'message': 'Harga dan quantity harus lebih dari 0'})

        # Nama produk berdasarkan jenis
        product_names = {
            'bibit': 'Bibit Ikan Mas',
            'konsumsi': 'Ikan Mas Konsumsi'
        }

        product_name = product_names.get(product_type, 'Produk')

        # Hitung total
        total_sales = selling_price * quantity
        total_hpp = cost_price * quantity

        print(f"💰 Totals - Sales: {total_sales}, HPP: {total_hpp}")

        # Dapatkan account IDs
        kas_account = Account.query.filter_by(type='kas').first()
        piutang_account = Account.query.filter_by(type='piutang').first()
        pendapatan_account = Account.query.filter_by(type='pendapatan').first()
        hpp_account = Account.query.filter_by(type='hpp').first()
        persediaan_account = Account.query.filter_by(type='persediaan').first()

        if not all([kas_account, piutang_account, pendapatan_account, hpp_account, persediaan_account]):
            return jsonify({'success': False, 'message': 'Akun-akun yang diperlukan tidak ditemukan'})

        # Buat entries jurnal
        entries = []

        # Entri untuk pendapatan (menggunakan harga jual)
        if payment_method == 'tunai':
            entries.append({
                'account_id': kas_account.id,
                'debit': total_sales,
                'credit': 0,
                'description': f'Penerimaan kas dari {description}'
            })
        else:  # kredit
            entries.append({
                'account_id': piutang_account.id,
                'debit': total_sales,
                'credit': 0,
                'description': f'Piutang dari {description}'
            })

        entries.append({
            'account_id': pendapatan_account.id,
            'debit': 0,
            'credit': total_sales,
            'description': f'Pendapatan dari {description}'
        })

        # Entri untuk HPP (menggunakan harga beli)
        entries.append({
            'account_id': hpp_account.id,
            'debit': total_hpp,
            'credit': 0,
            'description': f'Harga Pokok Produksi {product_name} - {quantity} unit'
        })

        entries.append({
            'account_id': persediaan_account.id,
            'debit': 0,
            'credit': total_hpp,
            'description': f'Pengurangan persediaan {product_name}'
        })

        # Buat jurnal entry
        transaction_number = generate_unique_transaction_number('SALES')
        journal = create_journal_entry(
            transaction_number,
            date,
            description,
            'sales',
            entries
        )

        if journal:
            print(f"✅ Journal created: {journal.transaction_number}")

            # Update kartu persediaan
            product = Product.query.filter_by(name=product_name).first()

            if product:
                print(f"📦 Updating product stock: {product.name}, current: {product.stock}")

                # Update stok produk
                product.stock -= quantity

                # Buat transaksi inventory
                inventory_transaction = create_inventory_transaction(
                    product_id=product.id,
                    date=date,
                    description=description,
                    transaction_type='penjualan',
                    quantity_in=0,
                    quantity_out=quantity,
                    unit_price=cost_price  # Gunakan harga cost untuk inventory
                )

                if inventory_transaction:
                    print(f"✅ Inventory transaction created for {product.name}")

                db.session.commit()
                print(f"✅ Stock updated: {product.name} = {product.stock}")

                return jsonify({
                    'success': True,
                    'message': f'Jurnal penjualan berhasil dibuat! Total Penjualan: Rp {total_sales:,}, Total HPP: Rp {total_hpp:,}'
                })
            else:
                print(f"❌ Product not found: {product_name}")
                return jsonify({'success': False, 'message': f'Produk {product_name} tidak ditemukan di database'})
        else:
            print("❌ Failed to create journal")
            return jsonify({'success': False, 'message': 'Gagal membuat jurnal'})

    except Exception as e:
        print(f"❌ Error adding sales journal: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Terjadi error: {str(e)}'})


@app.route('/seller/add_purchase_journal', methods=['POST'])
@login_required
@seller_required
def add_purchase_journal():
    """Proses input pembelian sederhana dan buat jurnal otomatis - HANYA UNTUK IKAN"""
    try:
        data = request.get_json()
        print("📦 Data pembelian received:", data)

        date = datetime.strptime(data['date'], '%Y-%m-%d')
        product_type = data['product_type']
        payment_method = data['payment_method']
        quantity = data['quantity']
        purchase_price = data['purchase_price']
        selling_price = data.get('selling_price', 0)
        description = data['description']

        print(f"📦 Processing purchase: {product_type}, Qty: {quantity}, Price: {purchase_price}")

        # Validasi - hanya terima bibit dan konsumsi
        if product_type not in ['bibit', 'konsumsi']:
            return jsonify({'success': False, 'message': 'Hanya pembelian ikan (bibit/konsumsi) yang diperbolehkan'})

        if purchase_price <= 0 or quantity <= 0:
            return jsonify({'success': False, 'message': 'Harga dan quantity harus lebih dari 0'})

        # Nama produk berdasarkan jenis
        product_names = {
            'bibit': 'Bibit Ikan Mas',
            'konsumsi': 'Ikan Mas Konsumsi'
        }

        product_name = product_names.get(product_type, 'Ikan')

        # Hitung total
        total_purchase = purchase_price * quantity

        print(f"💰 Total Pembelian: {total_purchase}")

        # Dapatkan account IDs
        kas_account = Account.query.filter_by(type='kas').first()
        hutang_account = Account.query.filter_by(type='hutang').first()
        persediaan_account = Account.query.filter_by(type='persediaan').first()

        if not all([kas_account, hutang_account, persediaan_account]):
            return jsonify({'success': False, 'message': 'Akun-akun yang diperlukan tidak ditemukan'})

        # Buat entries jurnal - SELALU gunakan persediaan untuk ikan
        entries = []

        # Entri untuk pembelian (debit ke persediaan)
        entries.append({
            'account_id': persediaan_account.id,
            'debit': total_purchase,
            'credit': 0,
            'description': f'Pembelian {product_name} - {description}'
        })

        # Entri untuk pembayaran (credit)
        if payment_method == 'tunai':
            entries.append({
                'account_id': kas_account.id,
                'debit': 0,
                'credit': total_purchase,
                'description': f'Pembayaran tunai untuk {description}'
            })
        else:  # kredit
            entries.append({
                'account_id': hutang_account.id,
                'debit': 0,
                'credit': total_purchase,
                'description': f'Utang dagang untuk {description}'
            })

        # Buat jurnal entry
        transaction_number = generate_unique_transaction_number('PURCH')
        journal = create_journal_entry(
            transaction_number,
            date,
            description,
            'general',
            entries
        )

        if journal:
            print(f"✅ Purchase journal created: {journal.transaction_number}")

            # Update kartu persediaan untuk ikan
            product = Product.query.filter_by(name=product_name).first()

            if product:
                print(f"📦 Updating product stock: {product.name}, current: {product.stock}")

                # Update stok produk
                product.stock += quantity
                # Update harga cost
                if purchase_price > 0:
                    product.cost_price = purchase_price
                # Update harga jual
                if selling_price > 0:
                    product.price = selling_price

                # Buat transaksi inventory
                inventory_transaction = create_inventory_transaction(
                    product_id=product.id,
                    date=date,
                    description=description,
                    transaction_type='pembelian',
                    quantity_in=quantity,
                    quantity_out=0,
                    unit_price=purchase_price
                )

                if inventory_transaction:
                    print(f"✅ Inventory transaction created for {product.name}")
            else:
                # Buat produk baru jika tidak ada
                seller_id = User.query.filter_by(user_type='seller').first().id
                new_product = Product(
                    name=product_name,
                    description=f"{product_name} - Auto created from purchase",
                    price=selling_price if selling_price > 0 else purchase_price * 1.5,
                    cost_price=purchase_price,
                    stock=quantity,
                    seller_id=seller_id,
                    category=product_type
                )
                db.session.add(new_product)
                print(f"✅ New product created: {product_name}")

            db.session.commit()
            print(f"✅ Purchase processed successfully")

            return jsonify({
                'success': True,
                'message': f'Jurnal pembelian {product_name} berhasil dibuat! Total Pembelian: Rp {total_purchase:,}'
            })
        else:
            print("❌ Failed to create purchase journal")
            return jsonify({'success': False, 'message': 'Gagal membuat jurnal pembelian'})

    except Exception as e:
        print(f"❌ Error adding purchase journal: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Terjadi error: {str(e)}'})

@app.route('/api/get_adjustment_template/<template_key>')
@login_required
@seller_required
def get_adjustment_template(template_key):
    try:
        if template_key not in ADJUSTMENT_TEMPLATES:
            return jsonify({'success': False, 'message': 'Template penyesuaian tidak ditemukan'})

        template = ADJUSTMENT_TEMPLATES[template_key]

        # Dapatkan saldo dari neraca sebelum penyesuaian untuk ditampilkan
        saldo_info = ""
        if template_key == 'penyesuaian_perlengkapan':
            saldo = get_account_balance_before_adjustment('perlengkapan')
            saldo_info = f"<p><strong>Saldo Perlengkapan (Neraca Sebelum Penyesuaian): Rp {saldo:,.0f}</strong></p>"
        elif template_key == 'penyesuaian_peralatan':
            saldo = get_account_balance_before_adjustment('peralatan')
            saldo_info = f"<p><strong>Saldo Peralatan (Neraca Sebelum Penyesuaian): Rp {saldo:,.0f}</strong></p>"

        form_html = f'''
        <form id="adjustmentJournalForm">
            <input type="hidden" name="template_key" value="{template_key}">

            <div class="form-group">
                <label class="form-label">Tanggal Penyesuaian</label>
                <input type="date" name="date" class="form-control" required value="{datetime.now().strftime('%Y-%m-%d')}">
            </div>

            <div class="form-group">
                <label class="form-label">Keterangan</label>
                <input type="text" name="description" class="form-control" value="{template['description']}" required>
            </div>

            <div style="background: var(--ocean-light); padding: 1rem; border-radius: var(--border-radius); margin: 1rem 0;">
                <h5 style="color: var(--primary); margin-bottom: 0.5rem;">Rumus Perhitungan:</h5>
                <p style="margin: 0; font-size: 0.9rem;">{template['calculation']}</p>
                {saldo_info}
            </div>

            <h4 style="margin: 1.5rem 0 1rem 0; color: var(--primary);">Data Input:</h4>
        '''

        for input_field in template['inputs']:
            form_html += f'''
            <div class="form-group">
                <label class="form-label">{input_field['label']}</label>
                <input type="number" id="input_{input_field['name']}" name="{input_field['name']}"
                       class="form-control" step="0.01" min="0" {'required' if input_field['required'] else ''}
                       placeholder="Masukkan {input_field['label'].lower()}">
            </div>
            '''

        form_html += '''
            <button type="button" class="btn btn-success" onclick="submitAdjustmentJournal()">
                <i class="fas fa-calculator"></i> Hitung & Simpan Jurnal Penyesuaian
            </button>
        </form>
        '''

        return jsonify({'success': True, 'form_html': form_html})

    except Exception as e:
        print(f"Error getting adjustment template: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/seller/add_template_journal', methods=['POST'])
@login_required
@seller_required
def add_template_journal():
    try:
        data = request.get_json()
        template_key = data['template_key']
        date = datetime.strptime(data['date'], '%Y-%m-%d')
        amounts = data['amounts']
        inputs = data.get('inputs', {})  # Ambil inputs dari request

        if template_key not in TRANSACTION_TEMPLATES:
            return jsonify({'success': False, 'message': 'Template tidak ditemukan'})

        # Create journal from template dengan inputs
        journal = create_journal_from_template(template_key, date, amounts, inputs)

        if journal:
            return jsonify({'success': True, 'message': 'Jurnal berhasil disimpan'})
        else:
            return jsonify({'success': False, 'message': 'Gagal membuat jurnal'})

    except Exception as e:
        print(f"Error adding template journal: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/seller/add_adjustment_journal', methods=['POST'])
@login_required
@seller_required
def add_adjustment_journal():
    try:
        data = request.get_json()
        template_key = data['template_key']
        date = datetime.strptime(data['date'], '%Y-%m-%d')
        inputs = data['inputs']

        if template_key not in ADJUSTMENT_TEMPLATES:
            return jsonify({'success': False, 'message': 'Template penyesuaian tidak ditemukan'})

        # Create adjustment journal
        journal = create_adjustment_journal(template_key, date, inputs)

        return jsonify({'success': True, 'message': 'Jurnal penyesuaian berhasil disimpan'})
    except Exception as e:
        print(f"Error adding adjustment journal: {e}")
        return jsonify({'success': False, 'message': str(e)})

# ==== TAMBAH ROUTE JURNAL PENUTUP DI SINI ====
@app.route('/seller/create_closing_entries', methods=['POST'])
@login_required
@seller_required
def create_closing_entries_route():
    try:
        # Cek apakah sudah ada jurnal penutup di periode ini
        recent_closing = ClosingEntry.query.filter(
            ClosingEntry.date >= datetime.now().replace(day=1)
        ).first()
        
        if recent_closing:
            return jsonify({
                'success': False,
                'message': 'Jurnal penutup untuk periode ini sudah dibuat. Silakan tunggu periode berikutnya.'
            })
        
        closing_entry = create_closing_entries()

        if closing_entry:
            return jsonify({
                'success': True,
                'message': f'Jurnal penutup berhasil dibuat! Laba/Rugi: Rp {calculate_net_income():,.0f}'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Tidak ada akun nominal yang perlu ditutup.'
            })

    except Exception as e:
        print(f"Error creating closing entries: {e}")
        return jsonify({
            'success': False,
            'message': f'Terjadi error: {str(e)}'
        })

# ===== API ROUTES =====
@app.route('/api/cart/add', methods=['POST'])
@login_required
def api_cart_add():
    try:
        print("=== API CART ADD CALLED ===")
        print("Current User:", current_user.id, current_user.email, current_user.user_type)

        # Check if user is customer
        if current_user.user_type != 'customer':
            print("❌ User is not customer")
            return jsonify({'success': False, 'message': 'Hanya customer yang bisa menambah ke keranjang'})

        # Check content type
        if not request.is_json:
            print("❌ Request is not JSON")
            return jsonify({'success': False, 'message': 'Request harus berupa JSON'})

        data = request.get_json()
        print("📦 Received data:", data)

        if not data:
            print("❌ No data received")
            return jsonify({'success': False, 'message': 'Data tidak valid'})

        product_id = data.get('product_id')
        quantity = data.get('quantity', 1)

        if not product_id:
            print("❌ No product_id provided")
            return jsonify({'success': False, 'message': 'Product ID tidak ditemukan'})

        # Convert to integer
        try:
            product_id = int(product_id)
            quantity = int(quantity)
        except (ValueError, TypeError):
            print("❌ Invalid product_id or quantity")
            return jsonify({'success': False, 'message': 'Product ID atau quantity tidak valid'})

        product = Product.query.get(product_id)
        if not product:
            print("❌ Product not found with ID:", product_id)
            return jsonify({'success': False, 'message': 'Produk tidak ditemukan'})

        print(f"✅ Product found: {product.name}, Stock: {product.stock}")

        # Check stock
        if product.stock < quantity:
            print(f"❌ Insufficient stock: {product.stock} < {quantity}")
            return jsonify({'success': False, 'message': f'Stock {product.name} tidak mencukupi. Stok tersedia: {product.stock}'})

        # Check if item already in cart
        existing_item = CartItem.query.filter_by(
            user_id=current_user.id,
            product_id=product_id
        ).first()

        if existing_item:
            # Check if adding more would exceed stock
            if product.stock < (existing_item.quantity + quantity):
                print(f"❌ Would exceed stock: {existing_item.quantity} + {quantity} > {product.stock}")
                return jsonify({'success': False, 'message': f'Stock tidak mencukupi untuk jumlah yang diminta. Stok tersedia: {product.stock}'})

            existing_item.quantity += quantity
            print(f"✅ Updated existing item: {existing_item.quantity}")
        else:
            cart_item = CartItem(
                user_id=current_user.id,
                product_id=product_id,
                quantity=quantity
            )
            db.session.add(cart_item)
            print("✅ Created new cart item")

        db.session.commit()
        print("✅ Cart updated successfully")

        # Get updated cart count
        cart_count = CartItem.query.filter_by(user_id=current_user.id).count()
        print(f"🛒 Cart count: {cart_count}")

        return jsonify({
            'success': True,
            'message': f'{product.name} berhasil ditambahkan ke keranjang!',
            'cart_count': cart_count
        })

    except Exception as e:
        print(f"💥 ERROR in api_cart_add: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Terjadi error sistem: {str(e)}'})

@app.route('/api/cart/count')
@login_required
def api_cart_count():
    try:
        if current_user.user_type != 'customer':
            return jsonify({'count': 0})

        count = CartItem.query.filter_by(user_id=current_user.id).count()
        print(f"🛒 Cart count requested: {count}")
        return jsonify({'count': count})
    except Exception as e:
        print(f"Error getting cart count: {e}")
        return jsonify({'count': 0})

# ===== CREATE SELLER ROUTE =====
@app.route('/create-seller')
def create_seller():
    try:
        seller = User.query.filter_by(email='kang.mas1817@gmail.com').first()
        if not seller:
            seller = User(
                email='kang.mas1817@gmail.com',
                full_name='Pemilik Kang-Mas Shop',
                user_type='seller',
                phone='+6289654733875',
                address='Magelang, Jawa Tengah',
                avatar='👑',
                email_verified=True
            )
            seller.set_password('TugasSiaKangMas')
            db.session.add(seller)
            db.session.commit()
            return '✅ Seller account created successfully!<br><a href="/login">Go to Login</a>'
        return '✅ Seller account already exists!<br><a href="/login">Go to Login</a>'
    except Exception as e:
        return f'❌ Error creating seller: {str(e)}'

# ===== FUNGSI CREATE_INITIAL_JOURNALS =====
def create_initial_journals():
    """Membuat jurnal umum awal - TANPA membuat jurnal saldo awal"""
    try:
        # Cek apakah sudah ada jurnal (selain saldo awal)
        if JournalEntry.query.filter(JournalEntry.journal_type != 'opening_balance').count() > 0:
            print("Jurnal sudah ada, skip pembuatan initial journals")
            return

        print("Tidak membuat jurnal saldo awal - saldo sudah tercatat di balance akun")

        # HAPUS bagian sync ke Supabase di sini

    except Exception as e:
        print(f"Error in create_initial_journals: {e}")

# ===== FUNGSI CREATE_INITIAL_DATA =====
def create_initial_data():
    # Create seller account
    seller = User.query.filter_by(email='kang.mas1817@gmail.com').first()
    if not seller:
        seller = User(
            email='kang.mas1817@gmail.com',
            full_name='Pemilik Kang-Mas Shop',
            user_type='seller',
            phone='+6289654733875',
            address='Magelang, Jawa Tengah',
            avatar='👑',
            email_verified=True
        )
        seller.set_password('TugasSiaKangMas')
        db.session.add(seller)
        print("✅ Seller account created successfully")

    # Create demo customer
    customer = User.query.filter_by(email='customer@example.com').first()
    if not customer:
        customer = User(
            email='customer@example.com',
            full_name='Budi Santoso',
            user_type='customer',
            phone='087654321098',
            address='Jl. Contoh No. 123, Jakarta',
            avatar='👨',
            email_verified=True
        )
        customer.set_password('customer123')
        db.session.add(customer)
        print("✅ Customer account created successfully")

    # Create accounts dengan saldo awal YANG DIPERBAIKI
    if Account.query.count() == 0:
        accounts = [
            # Asset Accounts - Debit Balance
            {'code': '101', 'name': 'Kas', 'type': 'kas', 'category': 'asset', 'balance': 10000000},
            {'code': '102', 'name': 'Piutang Usaha', 'type': 'piutang', 'category': 'asset', 'balance': 0},
            {'code': '103', 'name': 'Persediaan Barang Dagang', 'type': 'persediaan', 'category': 'asset', 'balance': 5000000},
            {'code': '104', 'name': 'Perlengkapan Toko', 'type': 'perlengkapan', 'category': 'asset', 'balance': 6500000},
            {'code': '105', 'name': 'Peralatan Toko', 'type': 'peralatan', 'category': 'asset', 'balance': 5000000},

            # AKUN BARU UNTUK TEMPLATE
            {'code': '106', 'name': 'Akumulasi Penyusutan', 'type': 'akumulasi_penyusutan', 'category': 'asset', 'balance': 0},
            {'code': '107', 'name': 'Penyisihan Piutang', 'type': 'penyisihan_piutang', 'category': 'asset', 'balance': 0},
            {'code': '108', 'name': 'Pendapatan Diterima Dimuka', 'type': 'pendapatan_diterima_dimuka', 'category': 'liability', 'balance': 0},
            {'code': '301', 'name': 'Modal Pemilik', 'type': 'modal', 'category': 'equity', 'balance': 0},

            # Liability Accounts - Credit Balance - DIPERBAIKI
            {'code': '201', 'name': 'Utang Dagang', 'type': 'hutang', 'category': 'liability', 'balance': 26500000},  # DARI 20jt MENJADI 26.5jt

            # Revenue Accounts - Credit Balance - DIPERBAIKI
            {'code': '401', 'name': 'Pendapatan Penjualan', 'type': 'pendapatan', 'category': 'revenue', 'balance': 0},  # DARI 6.5jt MENJADI 0

            # Expense Accounts - Debit Balance
            {'code': '501', 'name': 'Harga Pokok Produksi', 'type': 'hpp', 'category': 'expense', 'balance': 0},
            {'code': '502', 'name': 'Beban Gaji', 'type': 'beban_gaji', 'category': 'expense', 'balance': 0},
            {'code': '503', 'name': 'Beban Listrik dan Air', 'type': 'beban_listrik', 'category': 'expense', 'balance': 0},
            {'code': '504', 'name': 'Beban Perlengkapan', 'type': 'beban_perlengkapan', 'category': 'expense', 'balance': 0},
            {'code': '505', 'name': 'Beban Penyusutan', 'type': 'beban_penyusutan', 'category': 'expense', 'balance': 0},
            {'code': '506', 'name': 'Beban Transportasi', 'type': 'beban_transport', 'category': 'expense', 'balance': 0},
            {'code': '507', 'name': 'Beban Operasional', 'type': 'beban_operasional', 'category': 'expense', 'balance': 0},
            {'code': '520', 'name': 'Beban Kerugian', 'type': 'beban_kerugian', 'category': 'expense', 'balance': 0},
            {'code': '529', 'name': 'Beban Lain-lain', 'type': 'beban_lain', 'category': 'expense', 'balance': 0},
        ]

        for acc_data in accounts:
            account = Account(**acc_data)
            db.session.add(account)
        print("✅ Accounts created successfully with corrected balances")

    # Create products
    # Create products dengan stock sesuai saldo awal
    if Product.query.count() == 0:
        seller_id = User.query.filter_by(user_type='seller').first().id
        products = [
            {
                'name': 'Bibit Ikan Mas',
                'description': 'Bibit ikan mas segar ukuran 8cm, kualitas terbaik untuk pembesaran',
                'price': 2000,
                'cost_price': 1000,  # Harga cost untuk HPP
                'stock': 2975,  # DIPERBAIKI: 2975 ekor sesuai saldo awal
                'size_cm': 8,
                'seller_id': seller_id,
                'category': 'bibit',
                'image_url': '/static/uploads/products/bibit_ikan_mas.jpg'
            },
            {
                'name': 'Ikan Mas Konsumsi',
                'description': 'Ikan mas segar siap konsumsi, berat 1kg',
                'price': 20000,
                'cost_price': 13500,  # Harga cost untuk HPP
                'stock': 150,  # DIPERBAIKI: 150 ekor sesuai saldo awal
                'weight_kg': 1,
                'seller_id': seller_id,
                'category': 'konsumsi',
                'is_featured': True,
                'image_url': '/static/uploads/products/ikan_mas_konsumsi.jpg'
            }
        ]

        for prod_data in products:
            product = Product(**prod_data)
            db.session.add(product)
            db.session.flush()  # Untuk dapat product.id

            # Buat entry awal di kartu persediaan dengan harga cost yang benar
            if product.name == 'Bibit Ikan Mas':
                unit_cost = 1000
                total_value = 2975 * 1000  # 2,975,000
            else:  # Ikan Mas Konsumsi
                unit_cost = 13500
                total_value = 150 * 13500  # 2,025,000

            # Buat transaksi inventory untuk saldo awal
            inventory_transaction = InventoryTransaction(
                product_id=product.id,
                date=datetime.now(),
                description='SALDO AWAL - Persediaan awal periode',
                transaction_type='saldo_awal',
                quantity_in=product.stock,
                quantity_out=0,
                unit_price=unit_cost,
                total_amount=total_value,
                balance_quantity=product.stock,
                balance_unit_price=unit_cost,
                balance_total=total_value
            )
            db.session.add(inventory_transaction)

            # Juga buat di InventoryCard untuk kompatibilitas
            inventory_card = InventoryCard(
                product_id=product.id,
                date=datetime.now(),
                transaction_type='saldo_awal',
                transaction_number='SALDO_AWAL',
                quantity_in=product.stock,
                quantity_out=0,
                unit_cost=unit_cost,
                total_cost=total_value,
                balance_quantity=product.stock,
                balance_value=total_value
            )
            db.session.add(inventory_card)

            print(f"✅ Kartu persediaan saldo awal dibuat untuk {product.name}: {product.stock} unit @ Rp {unit_cost:,} = Rp {total_value:,}")

        # Hitung total persediaan untuk verifikasi
        total_persediaan = (2975 * 1000) + (150 * 13500)
        print(f"📊 Total Saldo Persediaan: Rp {total_persediaan:,} (Bibit: 2,975,000 + Konsumsi: 2,025,000)")

    # Commit semua perubahan
    db.session.commit()

    # Buat jurnal umum setelah data initial dibuat
    create_initial_journals()

# ===== INISIALISASI DATABASE =====
def init_database():
    """Initialize database and create initial data"""
    with app.app_context():
        try:
            # Buat semua tabel
            db.create_all()
            print("✅ Database tables created successfully!")
            
            # Cek apakah sudah ada data
            if User.query.count() == 0:
                create_initial_data()
                print("✅ Initial data created successfully!")
            else:
                print("✅ Database already has data, skipping initial data creation")
                
            print("🔐 Seller Login: kang.mas1817@gmail.com / TugasSiaKangMas")
            print("🔐 Customer Login: customer@example.com / customer123")
            
        except Exception as e:
            print(f"❌ Error initializing database: {e}")
            import traceback
            traceback.print_exc()

# ===== JALANKAN APLIKASI =====
if __name__ == '__main__':
    # Inisialisasi database
    init_database()
    
    # Jalankan app
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    print(f"🚀 Server starting on port {port} (debug: {debug_mode})")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
