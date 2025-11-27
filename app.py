import os
import logging
from pathlib import Path
from flask import Flask, jsonify, request, redirect, url_for, session, flash, get_flashed_messages # pyright: ignore[reportMissingImports]
from flask_sqlalchemy import SQLAlchemy # pyright: ignore[reportMissingImports]
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user # pyright: ignore[reportMissingImports]
from werkzeug.security import generate_password_hash, check_password_hash # pyright: ignore[reportMissingImports]
from datetime import datetime, timedelta
import json
import random
from functools import wraps
from google.oauth2 import id_token # pyright: ignore[reportMissingImports]
from google.auth.transport import requests as google_requests # pyright: ignore[reportMissingImports]
from google_auth_oauthlib.flow import Flow # pyright: ignore[reportMissingImports]
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv # pyright: ignore[reportMissingImports]
from werkzeug.utils import secure_filename # pyright: ignore[reportMissingImports]
import time

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)

# ===== 🎯 TEMPATKAN DI SINI - SETELAH app = Flask(__name__) =====
# ==== KONFIGURASI SUPABASE YANG LEBIH AMAN ====
def init_supabase():
    """Initialize Supabase client dengan error handling"""
    SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase credentials missing. SUPABASE_URL=%r", bool(SUPABASE_URL))
        return None
    else:
        try:
            from supabase import create_client
            client = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("Supabase client created successfully")
            return client
        except Exception as e:
            logger.exception("Failed to create Supabase client: %s", e)
            return None

# Inisialisasi Supabase
supabase = init_supabase()
# ===== END OF SUPABASE CONFIG =====

base_dir = Path(__file__).parent
db_path = base_dir / "kangmas_shop.db"

# ==== PERBAIKAN DATABASE - TAMBAHKAN INI ====
# Jika DATABASE_URI tidak ada, gunakan SQLite
if not os.getenv('DATABASE_URI'):
    os.environ['DATABASE_URI'] = f'sqlite:///{db_path}'
    print(f"✅ Database SQLite: {db_path}")

# Database Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'kang-mas-secret-2025')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True
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
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')

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
    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [
                    "http://localhost:5000/google-callback",
                    "http://127.0.0.1:5000/google-callback"
                ]
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
class User(UserMixin, db.Model):
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

class Product(db.Model):
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

# ===== SUPABASE HELPER FUNCTIONS =====
# ==== GANTI fungsi helper Supabase ====
def supabase_insert(table: str, data: dict):
    """Insert data ke Supabase dengan error handling"""
    if supabase is None:
        logger.warning("Supabase client not available. Cannot insert to %s", table)
        return None
        
    try:
        response = supabase.table(table).insert(data).execute()
        if hasattr(response, 'error') and response.error:
            logger.error("Supabase insert error: %s", response.error)
            return None
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error("Error inserting to Supabase: %s", e)
        return None

def supabase_select(table: str, query=None):
    """Select data dari Supabase dengan error handling"""
    if supabase is None:
        logger.warning("Supabase client not available. Cannot select from %s", table)
        return []
        
    try:
        if query:
            response = supabase.table(table).select("*").eq(query[0], query[1]).execute()
        else:
            response = supabase.table(table).select("*").execute()
        
        if hasattr(response, 'error') and response.error:
            logger.error("Supabase select error: %s", response.error)
            return []
        return response.data
    except Exception as e:
        logger.error("Error selecting from Supabase: %s", e)
        return []

def supabase_update(table: str, data: dict, id: int):
    """Update data di Supabase dengan error handling"""
    if supabase is None:
        logger.warning("Supabase client not available. Cannot update %s", table)
        return None
        
    try:
        response = supabase.table(table).update(data).eq('id', id).execute()
        if hasattr(response, 'error') and response.error:
            logger.error("Supabase update error: %s", response.error)
            return None
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error("Error updating Supabase: %s", e)
        return None

def supabase_delete(table: str, id: int):
    """Delete data dari Supabase dengan error handling"""
    if supabase is None:
        logger.warning("Supabase client not available. Cannot delete from %s", table)
        return False
        
    try:
        response = supabase.table(table).delete().eq('id', id).execute()
        if hasattr(response, 'error') and response.error:
            logger.error("Supabase delete error: %s", response.error)
            return False
        return True
    except Exception as e:
        logger.error("Error deleting from Supabase: %s", e)
        return False
    
def sync_to_supabase(model_class, table_name):
    """Sync data dari SQLAlchemy ke Supabase dengan error handling"""
    if supabase is None:
        logger.warning("Supabase client not available. Cannot sync %s", table_name)
        return False
        
    try:
        # Get all records from SQLAlchemy
        records = model_class.query.all()
        
        for record in records:
            # Convert SQLAlchemy object to dict
            if hasattr(record, 'to_dict'):
                data = record.to_dict()
            else:
                data = {column.name: getattr(record, column.name) 
                       for column in record.__table__.columns}
            
            # Check if record exists in Supabase
            existing = supabase_select(table_name, ('id', data['id']))
            
            if existing:
                # Update existing record
                result = supabase_update(table_name, data, data['id'])
                if result:
                    logger.info("✅ Updated %s record %s in Supabase", table_name, data['id'])
                else:
                    logger.warning("❌ Failed to update %s record %s", table_name, data['id'])
            else:
                # Insert new record
                result = supabase_insert(table_name, data)
                if result:
                    logger.info("✅ Inserted %s record %s to Supabase", table_name, data['id'])
                else:
                    logger.warning("❌ Failed to insert %s record %s", table_name, data['id'])
                    
        return True
    except Exception as e:
        logger.error("Error syncing %s to Supabase: %s", table_name, e)
        return False

# Tambahkan method to_dict untuk setiap model
def user_to_dict(self):
    return {
        'id': self.id,
        'email': self.email,
        'full_name': self.full_name,
        'user_type': self.user_type,
        'phone': self.phone,
        'address': self.address,
        'avatar': self.avatar,
        'created_at': self.created_at.isoformat() if self.created_at else None,
        'is_active': self.is_active,
        'google_id': self.google_id,
        'email_verified': self.email_verified
    }

def product_to_dict(self):
    return {
        'id': self.id,
        'name': self.name,
        'description': self.description,
        'price': float(self.price) if self.price else 0,
        'cost_price': float(self.cost_price) if self.cost_price else 0,
        'stock': self.stock,
        'size_cm': float(self.size_cm) if self.size_cm else None,
        'weight_kg': float(self.weight_kg) if self.weight_kg else None,
        'category': self.category,
        'seller_id': self.seller_id,
        'is_featured': self.is_featured,
        'is_active': self.is_active,
        'created_at': self.created_at.isoformat() if self.created_at else None,
        'image_url': self.image_url
    }

def order_to_dict(self):
    return {
        'id': self.id,
        'order_number': self.order_number,
        'customer_id': self.customer_id,
        'total_amount': float(self.total_amount) if self.total_amount else 0,
        'status': self.status,
        'payment_method': self.payment_method,
        'payment_status': self.payment_status,
        'shipping_address': self.shipping_address,
        'shipping_method': self.shipping_method,
        'order_date': self.order_date.isoformat() if self.order_date else None,
        'completed_date': self.completed_date.isoformat() if self.completed_date else None,
        'tracking_info': self.tracking_info
    }

def order_item_to_dict(self):
    return {
        'id': self.id,
        'order_id': self.order_id,
        'product_id': self.product_id,
        'quantity': self.quantity,
        'price': float(self.price) if self.price else 0,
        'cost_price': float(self.cost_price) if self.cost_price else 0
    }

# Attach methods to models
Order.to_dict = order_to_dict
OrderItem.to_dict = order_item_to_dict

# Attach methods to models
User.to_dict = user_to_dict
Product.to_dict = product_to_dict
# Tambahkan untuk model lainnya...

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
        # 🎯 PEMBELIAN UTAMA - GUNAKAN INI
    'pembelian_sederhana': {
        'name': 'Pembelian Sederhana',
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
        'name': 'Pembelian Peralatan Kecil Tunai',
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
    
    # ❌ PENJUALAN LAMA - DISEMBUNYIKAN
    # 'penjualan_bibit_kredit': {
    #     'name': 'Penjualan Bibit Ikan (Kredit) + HPP',
    #     'description': 'Menjual bibit ikan secara kredit',
    #     'entries': [
    #         {'account_type': 'piutang', 'side': 'debit', 'description': 'Piutang penjualan bibit'},
    #         {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan bibit'},
    #         {'account_type': 'hpp', 'side': 'debit', 'description': 'Harga Pokok Penjualan bibit'},
    #         {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan bibit'}
    #     ],
    #     'inventory_effect': {'type': 'bibit', 'action': 'out'}
    # },
    
    # 🎯 PENJUALAN UTAMA - GUNAKAN INI
    'penjualan_sederhana': {
        'name': 'Penjualan Sederhana',
        'description': 'Input penjualan produk dengan pilihan produk dan metode pembayaran',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan kas dari penjualan'},
            {'account_type': 'piutang', 'side': 'debit', 'description': 'Piutang penjualan'},
            {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan'},
            {'account_type': 'hpp', 'side': 'debit', 'description': 'Harga Pokok Penjualan'},
            {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan'}
        ],
        'inventory_effect': {'type': 'auto', 'action': 'out'}
    },
    
    # ❌ PENJUALAN LAMA - DISEMBUNYIKAN
    # 'penjualan_bibit_tunai': {
    #     'name': 'Penjualan Bibit Ikan (Tunai) + HPP',
    #     'description': 'Menjual bibit ikan secara tunai',
    #     'entries': [
    #         {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan penjualan bibit'},
    #         {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan bibit'},
    #         {'account_type': 'hpp', 'side': 'debit', 'description': 'Harga Pokok Penjualan bibit'},
    #         {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan bibit'}
    #     ],
    #     'inventory_effect': {'type': 'bibit', 'action': 'out'}
    # },
    
    'penerimaan_piutang': {
        'name': 'Penerimaan Pembayaran Piutang',
        'description': 'Menerima pembayaran dari pelanggan atas penjualan kredit',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan kas dari piutang'},
            {'account_type': 'piutang', 'side': 'credit', 'description': 'Piutang dilunasi'}
        ]
    },
    
    # ❌ PENJUALAN LAMA - DISEMBUNYIKAN
    # 'penjualan_ikan_tunai': {
    #     'name': 'Penjualan Ikan Konsumsi (Tunai) + HPP',
    #     'description': 'Menjual ikan mas konsumsi secara tunai',
    #     'entries': [
    #         {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan penjualan ikan'},
    #         {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan ikan'},
    #         {'account_type': 'hpp', 'side': 'debit', 'description': 'Harga Pokok Penjualan ikan'},
    #         {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan ikan'}
    #     ],
    #     'inventory_effect': {'type': 'ikan_konsumsi', 'action': 'out'}
    # },
    # 'penjualan_ikan_kredit': {
    #     'name': 'Penjualan Ikan Konsumsi (Kredit) + HPP',
    #     'description': 'Menjual ikan mas konsumsi secara kredit',
    #     'entries': [
    #         {'account_type': 'piutang', 'side': 'debit', 'description': 'Piutang penjualan ikan'},
    #         {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan ikan'},
    #         {'account_type': 'hpp', 'side': 'debit', 'description': 'Harga Pokok Penjualan ikan'},
    #         {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan ikan'}
    #     ],
    #     'inventory_effect': {'type': 'ikan_konsumsi', 'action': 'out'}
    # },
    
    'kerugian_bibit_mati': {
        'name': 'Kerugian Bibit Ikan Mati',
        'description': 'Bibit ikan mati dalam perjalanan/kolam sehingga tidak dapat dijual',
        'entries': [
            {'account_type': 'beban_kerugian', 'side': 'debit', 'description': 'Beban kerugian bibit mati'},
            {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan bibit'}
        ],
        'inventory_effect': {'type': 'bibit', 'action': 'out'}
    },
    'biaya_reparasi_kendaraan': {
        'name': 'Biaya Reparasi Kendaraan',
        'description': 'Mengeluarkan biaya reparasi kendaraan operasional',
        'entries': [
            {'account_type': 'beban_lain', 'side': 'debit', 'description': 'Biaya reparasi kendaraan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'pembelian_bibit_tunai': {
        'name': 'Pembelian Bibit Tunai',
        'description': 'Membeli bibit ikan mas secara tunai',
        'entries': [
            {'account_type': 'persediaan', 'side': 'debit', 'description': 'Pembelian bibit tunai'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ],
        'inventory_effect': {'type': 'bibit', 'action': 'in'}
    },
    
    # ❌ PENJUALAN LAMA - DISEMBUNYIKAN
    # 'penjualan_bibit_ongkir_pembeli': {
    #     'name': 'Penjualan Bibit - Ongkir Pembeli (Tunai)',
    #     'description': 'Menjual bibit, biaya pengiriman dibayar pembeli',
    #     'entries': [
    #         {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan penjualan bibit'},
    #         {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan bibit'},
    #         {'account_type': 'hpp', 'side': 'debit', 'description': 'Harga Pokok Penjualan bibit'},
    #         {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan bibit'}
    #     ],
    #     'inventory_effect': {'type': 'bibit', 'action': 'out'}
    # },
    
    'hibah_bibit_ke_keluarga': {
        'name': 'Bibit Diberikan ke Saudara (Kerugian)',
        'description': 'Bibit diambil oleh keluarga pemilik, dianggap kerugian usaha',
        'entries': [
            {'account_type': 'beban_kerugian', 'side': 'debit', 'description': 'Kerugian hibah bibit'},
            {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan bibit'}
        ],
        'inventory_effect': {'type': 'bibit', 'action': 'out'}
    },
    'kerugian_bibit_mati_lanjutan': {
        'name': 'Kerugian Bibit Mati Lanjutan',
        'description': 'Bibit mati secara alami di kolam',
        'entries': [
            {'account_type': 'beban_kerugian', 'side': 'debit', 'description': 'Beban kerugian bibit mati'},
            {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan bibit'}
        ],
        'inventory_effect': {'type': 'bibit', 'action': 'out'}
    }
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
    'penyesuaian_persediaan_bibit': {
        'name': 'Penyesuaian Persediaan Bibit',
        'description': 'Penyesuaian nilai persediaan bibit ikan berdasarkan stock opname',
        'calculation': 'HPP = Persediaan Awal - Persediaan Akhir',
        'entries': [
            {'account_type': 'hpp', 'side': 'debit', 'description': 'Harga pokok penjualan bibit'},
            {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan bibit'}
        ],
        'inputs': [
            {'name': 'persediaan_akhir', 'label': 'Persediaan Bibit Akhir (ekor)', 'type': 'number', 'required': True},
            {'name': 'harga_per_ekor', 'label': 'Harga Per Ekor Bibit', 'type': 'number', 'required': True}
        ]
    },
    'penyesuaian_persediaan_ikan': {
        'name': 'Penyesuaian Persediaan Ikan Konsumsi',
        'description': 'Penyesuaian nilai persediaan ikan konsumsi berdasarkan stock opname',
        'calculation': 'HPP = Persediaan Awal - Persediaan Akhir',
        'entries': [
            {'account_type': 'hpp', 'side': 'debit', 'description': 'Harga pokok penjualan ikan'},
            {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan ikan'}
        ],
        'inputs': [
            {'name': 'persediaan_akhir', 'label': 'Persediaan Ikan Akhir (kg)', 'type': 'number', 'required': True},
            {'name': 'harga_per_kg', 'label': 'Harga Per Kg Ikan', 'type': 'number', 'required': True}
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
    flow = get_google_flow()
    flow.redirect_uri = url_for('google_callback', _external=True)
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='select_account'
    )
    
    session['state'] = state
    return redirect(authorization_url)

@app.route('/google-callback')
def google_callback():
    try:
        flow = get_google_flow()
        flow.redirect_uri = url_for('google_callback', _external=True)
        flow.fetch_token(authorization_response=request.url)
        
        credentials = flow.credentials
        id_info = id_token.verify_oauth2_token(
            credentials.id_token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        
        google_id = id_info.get('sub')
        email = id_info.get('email')
        name = id_info.get('name')
        
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
        else:
            if not user.google_id:
                user.google_id = google_id
                db.session.commit()
        
        login_user(user)
        flash(f'Berhasil login dengan Google! Selamat datang {name}', 'success')
        return redirect('/')
        
    except Exception as e:
        print(f"Google OAuth error: {e}")
        flash('Error saat login dengan Google. Silakan coba lagi.', 'error')
        return redirect('/login')

# ===== EMAIL CONFIG =====
EMAIL_CONFIG = {
    'smtp_server': os.getenv('EMAIL_SERVER'),
    'smtp_port': int(os.getenv('EMAIL_PORT')),
    'sender_email': os.getenv('EMAIL_USERNAME'),
    'sender_password': os.getenv('EMAIL_PASSWORD')
}

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
    """Buat jurnal penjualan untuk order COD yang selesai"""
    try:
        # Hitung total harga produk saja (TANPA ONGKIR untuk jurnal)
        product_total = 0
        for item in OrderItem.query.filter_by(order_id=order.id).all():
            product_total += item.price * item.quantity
        
        # Buat jurnal penjualan
        transaction_number = generate_unique_transaction_number('COD')
        description = f"Penjualan COD Order #{order.order_number}"
        
        # Get accounts
        kas_account = Account.query.filter_by(type='kas').first()
        pendapatan_account = Account.query.filter_by(type='pendapatan').first()
        
        if kas_account and pendapatan_account:
            entries = [
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
                }
            ]
            
            journal = create_journal_entry(
                transaction_number,
                order.completed_date or datetime.now(),
                description,
                'sales',
                entries
            )
            
            print(f"✅ Jurnal COD dibuat untuk order #{order.order_number}: Rp {product_total:,.0f}")
            
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

def create_journal_entry(transaction_number, date, description, journal_type, entries):
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

def create_journal_from_template(template_key, date, amounts):
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
        
        print(f"📝 Membuat jurnal dari template: {template_key}")
        print(f" Amounts: {amounts}")
        
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
            
            # Kumpulkan informasi untuk kartu persediaan
            if account_type == 'persediaan' and template_entry['side'] == 'debit':
                total_persediaan += amount  # Pembelian/penambahan
            
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
        
        # PERBAIKAN: Panggil update inventory dengan parameter yang benar
        if 'inventory_effect' in template:
            print(f"🔄 Memanggil update_inventory_from_journal untuk {template_key}")
            print(f"📦 Total persediaan: {total_persediaan}")
            update_inventory_from_journal(journal, template, amounts, total_persediaan)
        else:
            print("ℹ️ Template tidak punya inventory effect")
        
        return journal
        
    except Exception as e:
        print(f"Error creating journal from template {template_key}: {e}")
        import traceback
        traceback.print_exc()
        return None

# ===== FUNGSI UPDATE INVENTORY DARI JURNAL =====
def update_inventory_from_journal(journal, template, amounts, total_amount):
    """Update kartu persediaan berdasarkan jurnal template"""
    try:
        inventory_effect = template['inventory_effect']
        product_type = inventory_effect['type']  # 'bibit' atau 'ikan_konsumsi'
        action = inventory_effect['action']      # 'in' atau 'out'
        
        # Tentukan produk berdasarkan jenis
        if product_type == 'bibit':
            product_name = "Bibit Ikan Mas"
            category = 'bibit'
        elif product_type == 'ikan_konsumsi':
            product_name = "Ikan Mas Konsumsi" 
            category = 'konsumsi'
        else:
            return
        
        # Cari produk berdasarkan nama dan kategori
        product = Product.query.filter_by(name=product_name, category=category).first()
        if not product:
            # Buat produk baru jika tidak ada
            seller_id = User.query.filter_by(user_type='seller').first().id
            product = Product(
                name=product_name,
                description=f"{product_name} - Auto created from journal",
                price=2000 if product_type == 'bibit' else 30000,
                cost_price=1000,
                stock=0,
                seller_id=seller_id,
                category=category
            )
            db.session.add(product)
            db.session.flush()
            print(f"✅ Produk baru dibuat: {product_name}")
        
        # Hitung quantity berdasarkan total amount dan harga cost
        quantity = int(total_amount / 1000)  # Harga cost tetap Rp 1,000
        
        if action == 'in':
            # Update stok produk - MASUK
            product.stock += quantity
            print(f"✅ Stok {product.name} bertambah {quantity} menjadi {product.stock}")
            
            # Buat transaksi inventory
            create_inventory_transaction(
                product_id=product.id,
                date=journal.date,
                description=f"{journal.description}",
                transaction_type='pembelian',
                quantity_in=quantity,
                quantity_out=0,
                unit_price=1000
            )
            
        elif action == 'out':
            # Update stok produk - KELUAR
            if product.stock >= quantity:
                product.stock -= quantity
                print(f"✅ Stok {product.name} berkurang {quantity} menjadi {product.stock}")
                
                # Buat transaksi inventory
                create_inventory_transaction(
                    product_id=product.id,
                    date=journal.date,
                    description=f"{journal.description}",
                    transaction_type='penjualan',
                    quantity_in=0,
                    quantity_out=quantity,
                    unit_price=1000
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
                description = f"HPP untuk penjualan {product.name} - Order #{order.order_number}"
                
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
    """Buat jurnal penjualan otomatis saat order completed - TANPA ONGKIR"""
    try:
        print(f"🔄 [DEBUG] Memulai pembuatan jurnal penjualan untuk order #{order.order_number}")
        
        # Hitung total harga produk saja (TANPA ONGKIR)
        product_total = 0
        order_items = OrderItem.query.filter_by(order_id=order.id).all()
        
        for item in order_items:
            product_total += item.price * item.quantity
            print(f"📦 [DEBUG] Produk: {item.product_id}, Qty: {item.quantity}, Price: {item.price}")
        
        print(f"💰 [DEBUG] Total penjualan: Rp {product_total:,.0f}")
        
        # Buat jurnal penjualan
        transaction_number = generate_unique_transaction_number('SALES')
        description = f"Penjualan Order #{order.order_number}"
        
        # Get accounts
        kas_account = Account.query.filter_by(type='kas').first()
        pendapatan_account = Account.query.filter_by(type='pendapatan').first()
        
        if not kas_account:
            print("❌ [DEBUG] Akun Kas tidak ditemukan")
            return None
        if not pendapatan_account:
            print("❌ [DEBUG] Akun Pendapatan tidak ditemukan")
            return None
            
        print(f"✅ [DEBUG] Akun ditemukan: Kas({kas_account.code}), Pendapatan({pendapatan_account.code})")
        
        entries = [
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
            print(f"✅ [DEBUG] Jurnal penjualan berhasil dibuat: {journal.transaction_number}")
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
    """Ambil data untuk buku besar - sesuai dengan perhitungan neraca saldo"""
    try:
        # Dapatkan semua akun
        all_accounts = Account.query.order_by(Account.code).all()
        
        ledger_html = ""
        
        for account in all_accounts:
            # Hitung saldo awal (sama dengan neraca saldo)
            opening_balance = 0
            if account.type == 'kas':
                opening_balance = 10000000
            elif account.type == 'persediaan':
                opening_balance = 5000000
            elif account.type == 'perlengkapan':
                opening_balance = 6500000
            elif account.type == 'peralatan':
                opening_balance = 5000000
            elif account.type == 'hutang':
                opening_balance = 20000000
            elif account.type == 'pendapatan':
                opening_balance = 6500000
            
            # Dapatkan semua transaksi jurnal umum untuk akun ini
            journal_details = JournalDetail.query.join(JournalEntry).filter(
                JournalDetail.account_id == account.id,
                JournalEntry.journal_type == 'general'
            ).order_by(JournalDetail.journal_id).all()
            
            # Hanya tampilkan akun yang punya saldo atau transaksi
            if abs(opening_balance) > 0 or journal_details:
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
                        <td>01/01/2025</td>
                        <td><strong>Saldo Awal</strong></td>
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
                    account_html += f'<p>Saldo: <span class="{"debit" if opening_balance >= 0 else "credit"}">Rp {abs(opening_balance):,.0f}</span></p>'
                
                account_html += '</div>'
                ledger_html += account_html
        
        return ledger_html if ledger_html else '<div class="card"><p>Belum ada transaksi untuk ditampilkan di buku besar.</p></div>'
        
    except Exception as e:
        print(f"Error generating ledger data: {e}")
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
    """Generate HTML untuk saldo awal MURNI tanpa pengaruh jurnal umum"""
    try:
        accounts = Account.query.order_by(Account.code).all()
        
        saldo_html = ""
        total_debit = 0
        total_credit = 0
        
        for account in accounts:
            # SALDO AWAL MURNI - tidak dipengaruhi jurnal umum
            saldo_awal = 0
            
            # Tentukan saldo awal berdasarkan akun
            if account.type == 'kas':
                saldo_awal = 10000000  # Debit
            elif account.type == 'persediaan':
                saldo_awal = 5000000   # Debit
            elif account.type == 'perlengkapan':
                saldo_awal = 6500000   # Debit
            elif account.type == 'peralatan':
                saldo_awal = 5000000   # Debit
            elif account.type == 'hutang':
                saldo_awal = 26500000  # Credit
            elif account.type == 'pendapatan':
                saldo_awal = 0         # Credit
            else:
                saldo_awal = 0
            
            # Skip akun yang saldo awal 0
            if saldo_awal == 0:
                continue
                
            # Tentukan debit/credit berdasarkan kategori akun
            if account.category in ['asset', 'expense']:
                # Asset/Expense: Saldo positif = Debit
                if saldo_awal >= 0:
                    debit = saldo_awal
                    credit = 0
                else:
                    debit = 0
                    credit = abs(saldo_awal)
            else:
                # Liability/Equity/Revenue: Saldo positif = Credit
                if saldo_awal >= 0:
                    debit = 0
                    credit = saldo_awal
                else:
                    debit = abs(saldo_awal)
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
        
        is_balanced = total_debit == total_credit
        
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
        
        return saldo_html
        
    except Exception as e:
        print(f"Error generating saldo awal: {e}")
        return '<tr><td colspan="4">Error loading saldo awal</td></tr>'
        
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
    """Mendapatkan saldo akun dari NERACA SALDO SEBELUM PENYESUAIAN (sama dengan buku besar)"""
    try:
        account = Account.query.filter_by(type=account_type).first()
        if not account:
            return 0
        
        # Hitung saldo dari buku besar (saldo awal + semua jurnal umum)
        saldo_buku_besar = 0
        
        # 1. Saldo awal YANG DIPERBAIKI
        if account.type == 'kas':
            saldo_buku_besar = 10000000  # Debit
        elif account.type == 'persediaan':
            saldo_buku_besar = 5000000   # Debit
        elif account.type == 'perlengkapan':
            saldo_buku_besar = 6500000   # Debit
        elif account.type == 'peralatan':
            saldo_buku_besar = 5000000   # Debit
        elif account.type == 'hutang':
            saldo_buku_besar = 26500000  # Credit - DIPERBAIKI dari 20jt menjadi 26.5jt
        elif account.type == 'pendapatan':
            saldo_buku_besar = 0         # Credit - DIPERBAIKI dari 6.5jt menjadi 0
        
        # 2. Tambahkan efek dari jurnal umum (type = 'general')
        general_journals = JournalDetail.query.join(JournalEntry).filter(
            JournalDetail.account_id == account.id,
            JournalEntry.journal_type == 'general'
        ).all()
        
        for detail in general_journals:
            if account.category in ['asset', 'expense']:
                # Asset/Expense: Debit menambah, Credit mengurangi
                saldo_buku_besar += detail.debit - detail.credit
            else:
                # Liability/Equity/Revenue: Credit menambah, Debit mengurangi
                saldo_buku_besar += detail.credit - detail.debit
        
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
    """Buat jurnal penutup untuk menutup akun nominal"""
    try:
        # Hitung laba/rugi bersih
        revenue_accounts = Account.query.filter_by(category='revenue').all()
        expense_accounts = Account.query.filter_by(category='expense').all()
        
        total_revenue = sum(acc.balance for acc in revenue_accounts)
        total_expenses = sum(acc.balance for acc in expense_accounts)
        net_income = total_revenue - total_expenses
        
        # Buat jurnal penutup
        transaction_number = generate_unique_transaction_number('CLS')
        description = f"Jurnal Penutup - {'Laba' if net_income >= 0 else 'Rugi'} Bersih Periode"
        
        entries = []
        
        # Tutup akun pendapatan
        for revenue_acc in revenue_accounts:
            if revenue_acc.balance > 0:
                entries.append({
                    'account_id': revenue_acc.id,
                    'debit': 0,
                    'credit': revenue_acc.balance,
                    'description': f'Penutupan akun pendapatan {revenue_acc.name}'
                })
        
        # Tutup akun beban
        for expense_acc in expense_accounts:
            if expense_acc.balance > 0:
                entries.append({
                    'account_id': expense_acc.id,
                    'debit': expense_acc.balance,
                    'credit': 0,
                    'description': f'Penutupan akun beban {expense_acc.name}'
                })
        
        # Transfer laba/rugi ke modal
        modal_account = Account.query.filter_by(type='modal').first()
        if not modal_account:
            # Buat akun modal jika belum ada
            modal_account = Account(
                code='301',
                name='Modal Pemilik',
                type='modal',
                category='equity',
                balance=0
            )
            db.session.add(modal_account)
            db.session.flush()
        
        if net_income >= 0:
            # Laba
            entries.append({
                'account_id': modal_account.id,
                'debit': 0,
                'credit': net_income,
                'description': 'Transfer laba bersih ke modal'
            })
        else:
            # Rugi
            entries.append({
                'account_id': modal_account.id,
                'debit': abs(net_income),
                'credit': 0,
                'description': 'Transfer rugi bersih ke modal'
            })
        
        # Buat jurnal penutup
        closing_entry = ClosingEntry(
            transaction_number=transaction_number,
            date=datetime.now(),
            description=description
        )
        db.session.add(closing_entry)
        db.session.flush()
        
        # Buat detail jurnal
        for entry_data in entries:
            detail = ClosingDetail(
                closing_id=closing_entry.id,
                account_id=entry_data['account_id'],
                debit=entry_data['debit'],
                credit=entry_data['credit'],
                description=entry_data['description']
            )
            db.session.add(detail)
            
            # Update saldo akun
            account = Account.query.get(entry_data['account_id'])
            if account.category in ['asset', 'expense']:
                account.balance += entry_data['debit'] - entry_data['credit']
            else:
                account.balance += entry_data['credit'] - entry_data['debit']
        
        db.session.commit()
        
        return closing_entry
        
    except Exception as e:
        print(f"Error creating closing entries: {e}")
        db.session.rollback()
        return None

def get_closing_entries_html():
    """Generate HTML untuk jurnal penutup"""
    try:
        closing_entries = ClosingEntry.query.order_by(ClosingEntry.date.desc()).all()
        
        if not closing_entries:
            return '''
            <div class="card">
                <h4 style="color: var(--primary);">Belum Ada Jurnal Penutup</h4>
                <p>Jurnal penutup akan dibuat di akhir periode akuntansi.</p>
            </div>
            '''
        
        table_html = '''
        <div class="card">
            <h4 style="color: var(--primary); margin-bottom: 1.5rem;"><i class="fas fa-door-closed"></i> Jurnal Penutup</h4>
            <div style="overflow-x: auto;">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Tanggal</th>
                            <th>No. Transaksi</th>
                            <th>Keterangan</th>
                            <th>Akun</th>
                            <th>Debit</th>
                            <th>Kredit</th>
                        </tr>
                    </thead>
                    <tbody>
        '''
        
        for closing in closing_entries:
            # Add transaction header
            table_html += f'''
            <tr style="background: rgba(180, 81, 35, 0.05);">
                <td><strong>{closing.date.strftime('%d/%m/%Y')}</strong></td>
                <td><strong>{closing.transaction_number}</strong></td>
                <td colspan="4"><strong>{closing.description}</strong></td>
            </tr>
            '''
            
            # Add account details
            for detail in closing.closing_details:
                table_html += f'''
                <tr>
                    <td></td>
                    <td></td>
                    <td></td>
                    <td>{detail.account.code} - {detail.account.name}</td>
                    <td class="debit">{"Rp {0:,.0f}".format(detail.debit) if detail.debit > 0 else ""}</td>
                    <td class="credit">{"Rp {0:,.0f}".format(detail.credit) if detail.credit > 0 else ""}</td>
                </tr>
                '''
        
        table_html += '''
                    </tbody>
                </table>
            </div>
        </div>
        '''
        
        return table_html
    except Exception as e:
        print(f"Error generating closing entries: {e}")
        return '<div class="card"><p>Error loading closing entries</p></div>'

def get_adjustment_account_balances():
    """Mendapatkan saldo akun untuk ditampilkan di form penyesuaian"""
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
            width: 45px;
            height: 45px;
            border-radius: 12px;
            object-fit: cover;
            margin-right: 12px;
            box-shadow: var(--shadow-md);
            border: 2px solid rgba(255, 255, 255, 0.3);
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
                <img src="{app_logo}" alt="{app_name}" class="navbar-logo" onerror="this.style.display='none'">
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
                                'Harga Beli: Rp ' + costPrice.toLocaleString() + ' per unit\\n' +
                                'Metode: ' + (paymentMethod === 'tunai' ? 'Tunai' : 'Kredit') + '\\n\\n' +
                                'Total Penjualan: Rp ' + totalSales.toLocaleString() + '\\n' +
                                'Total HPP: Rp ' + totalHpp.toLocaleString() + '\\n\\n' +
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
                amounts: {{}}
            }};
            
            // PERBAIKAN: Ambil nilai langsung tanpa parsing formatting
            document.querySelectorAll('[id^=\"amount_\"]').forEach(input => {{
                const accountType = input.id.replace('amount_', '');
                // Langsung ambil nilai numerik
                data.amounts[accountType] = parseInt(input.value) || 0;
            }});
            
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
            if (!confirm('Apakah Anda yakin ingin membuat jurnal penutup? Tindakan ini akan menutup semua akun pendapatan dan beban.')) {{
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
                    setTimeout(() => location.reload(), 2000);
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }})
            .catch(error => {{
                showNotification('❌ Terjadi error saat membuat jurnal penutup', 'error');
            }})
            .finally(() => {{
                setTimeout(() => {{
                    button.innerHTML = originalText;
                    button.disabled = false;
                }}, 2000);
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
    """Neraca saldo sebelum penyesuaian = Saldo dari database TANPA efek jurnal penyesuaian"""
    try:
        accounts = Account.query.order_by(Account.code).all()
        trial_balance_html = ""
        total_debit = total_credit = 0
        
        for account in accounts:
            # Hitung saldo TANPA jurnal penyesuaian
            saldo_sebelum_penyesuaian = 0
            
            # 1. Saldo awal
            if account.type == 'kas':
                saldo_sebelum_penyesuaian = 10000000  # Debit
            elif account.type == 'persediaan':
                saldo_sebelum_penyesuaian = 5000000   # Debit
            elif account.type == 'perlengkapan':
                saldo_sebelum_penyesuaian = 6500000   # Debit
            elif account.type == 'peralatan':
                saldo_sebelum_penyesuaian = 5000000   # Debit
            elif account.type == 'hutang':
                saldo_sebelum_penyesuaian = 26500000  # Credit
            elif account.type == 'pendapatan':
                saldo_sebelum_penyesuaian = 0         # Credit
            else:
                saldo_sebelum_penyesuaian = 0
            
            # 2. Tambahkan efek dari jurnal umum (type = 'general', 'sales', 'purchase', 'hpp') TANPA 'adjustment'
            general_journals = JournalDetail.query.join(JournalEntry).filter(
                JournalDetail.account_id == account.id,
                JournalEntry.journal_type.in_(['general', 'sales', 'purchase', 'hpp'])
            ).all()
            
            for detail in general_journals:
                if account.category in ['asset', 'expense']:
                    # Asset/Expense: Debit menambah, Credit mengurangi
                    saldo_sebelum_penyesuaian += detail.debit - detail.credit
                else:
                    # Liability/Equity/Revenue: Credit menambah, Debit mengurangi
                    saldo_sebelum_penyesuaian += detail.credit - detail.debit
            
            # Skip akun yang saldo 0
            if saldo_sebelum_penyesuaian == 0:
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
        
        is_balanced = total_debit == total_credit
        
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
    """Hanya tampilkan jurnal umum (type = 'general')"""
    try:
        journal_entries = JournalEntry.query.filter(
            JournalEntry.journal_type.in_(['general', 'sales'])
        ).order_by(JournalEntry.date.desc()).all()
        
        if not journal_entries:
            return '''
            <div class="card">
                <h4 style="color: var(--primary);">Belum Ada Jurnal Umum</h4>
                <p>Belum ada transaksi jurnal yang tercatat.</p>
            </div>
            '''
        
        table_html = '''
        <div class="card">
            <h4 style="color: var(--primary); margin-bottom: 1.5rem;"><i class="fas fa-list"></i> Daftar Jurnal Umum</h4>
            <div style="overflow-x: auto;">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Tanggal</th>
                            <th>No. Transaksi</th>
                            <th>Keterangan</th>
                            <th>Akun</th>
                            <th>Debit</th>
                            <th>Kredit</th>
                        </tr>
                    </thead>
                    <tbody>
        '''
        
        for journal in journal_entries:
            # Add transaction header
            table_html += f'''
            <tr style="background: rgba(49, 130, 206, 0.05);">
                <td><strong>{journal.date.strftime('%d/%m/%Y')}</strong></td>
                <td><strong>{journal.transaction_number}</strong></td>
                <td colspan="4"><strong>{journal.description}</strong></td>
            </tr>
            '''
            
            # Add account details
            for detail in journal.journal_details:
                table_html += f'''
                <tr>
                    <td></td>
                    <td></td>
                    <td></td>
                    <td>{detail.account.code} - {detail.account.name}</td>
                    <td class="debit">{"Rp {0:,.0f}".format(detail.debit) if detail.debit > 0 else ""}</td>
                    <td class="credit">{"Rp {0:,.0f}".format(detail.credit) if detail.credit > 0 else ""}</td>
                </tr>
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
    """Hanya tampilkan jurnal penyesuaian (type = 'adjustment')"""
    try:
        journal_entries = JournalEntry.query.filter_by(journal_type='adjustment').order_by(JournalEntry.date).all()
        
        if not journal_entries:
            return '''
            <div class="card">
                <h4 style="color: var(--primary);">Belum Ada Jurnal Penyesuaian</h4>
                <p>Gunakan form Jurnal Penyesuaian di atas untuk menambahkan jurnal penyesuaian pertama.</p>
            </div>
            '''
        
        table_html = '''
        <div class="card">
            <h4 style="color: var(--primary); margin-bottom: 1.5rem;"><i class="fas fa-list"></i> Daftar Jurnal Penyesuaian</h4>
            <div style="overflow-x: auto;">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Tanggal</th>
                            <th>No. Transaksi</th>
                            <th>Keterangan</th>
                            <th>Akun</th>
                            <th>Debit</th>
                            <th>Kredit</th>
                        </tr>
                    </thead>
                    <tbody>
        '''
        
        for journal in journal_entries:
            # Add transaction header
            table_html += f'''
            <tr style="background: rgba(56, 161, 105, 0.05);">
                <td><strong>{journal.date.strftime('%d/%m/%Y')}</strong></td>
                <td><strong>{journal.transaction_number}</strong></td>
                <td colspan="4"><strong>{journal.description}</strong></td>
            </tr>
            '''
            
            # Add account details
            for detail in journal.journal_details:
                table_html += f'''
                <tr>
                    <td></td>
                    <td></td>
                    <td></td>
                    <td>{detail.account.code} - {detail.account.name}</td>
                    <td class="debit">{"Rp {0:,.0f}".format(detail.debit) if detail.debit > 0 else ""}</td>
                    <td class="credit">{"Rp {0:,.0f}".format(detail.credit) if detail.credit > 0 else ""}</td>
                </tr>
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
        <button class="tab active" onclick="showTab('chart-of-accounts', this)">Chart of Accounts</button>
        <button class="tab" onclick="showTab('saldo-awal', this)">Saldo Awal</button>
        <button class="tab" onclick="showTab('jurnal-umum', this)">Jurnal Umum</button>
        <button class="tab" onclick="showTab('buku-besar', this)">Buku Besar</button>
        <button class="tab" onclick="showTab('neraca-saldo', this)">Neraca Saldo</button>
        <button class="tab" onclick="showTab('jurnal-penyesuaian', this)">Jurnal Penyesuaian</button>
        <button class="tab" onclick="showTab('neraca-saldo-setelah', this)">Neraca Setelah Penyesuaian</button>
        <button class="tab" onclick="showTab('jurnal-penutup', this)">Jurnal Penutup</button>
        <button class="tab" onclick="showTab('laporan-keuangan', this)">Laporan Keuangan</button>
    </div>
    
    <div id="chart-of-accounts" class="tab-content active">
        {get_chart_of_accounts_content()}
    </div>
    
    <div id="saldo-awal" class="tab-content">
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-file-invoice-dollar"></i> Saldo Awal</h3>
            <p style="margin-bottom: 1rem; color: #6B7280;">
                <i class="fas fa-info-circle"></i> Saldo awal diambil secara otomatis dari database.
            </p>
            <table class="table">
                <thead>
                    <tr>
                        <th>Akun</th>
                        <th>Kode</th>
                        <th>Debit</th>
                        <th>Kredit</th>
                    </tr>
                </thead>
                <tbody>
                    {get_saldo_awal_html()}
                </tbody>
            </table>
        </div>
    </div>
    
    <div id="jurnal-umum" class="tab-content">
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-book"></i> Jurnal Umum</h3>
            
            <div class="card">
                <h4 style="color: var(--primary);">Input Jurnal Otomatis</h4>
                
                <div class="form-group">
                    <label class="form-label">Jenis Transaksi</label>
                    <select id="transaction_template" class="form-control" onchange="loadTransactionTemplate()">
                        <option value="">Pilih Jenis Transaksi</option>
                        {template_options}
                    </select>
                </div>
                
                <div id="templateFormContainer">
                    <!-- Form will be loaded here -->
                </div>
            </div>
            
            {get_general_journal_entries()}
        </div>
    </div>
    
    <!-- TAMBAHKAN TAB CONTENT UNTUK BUKU BESAR -->
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

    <div id="jurnal-penutup" class="tab-content">
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-door-closed"></i> Jurnal Penutup</h3>
            
            <button class="btn btn-success" onclick="createClosingEntries()">
                <i class="fas fa-calculator"></i> Buat Jurnal Penutup Otomatis
            </button>
            
            {get_closing_entries_html()}
        </div>
    </div>
    
    <div id="laporan-keuangan" class="tab-content">
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-chart-line"></i> Laporan Laba Rugi</h3>
            {get_income_statement()}
        </div>
        
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-balance-scale-left"></i> Laporan Posisi Keuangan</h3>
            {get_balance_sheet()}
        </div>
        
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-chart-line"></i> Laporan Perubahan Ekuitas</h3>
            {get_equity_change_statement()}
        </div>
    </div>
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
@app.route("/")
def home():
    return "Hello from Flask!"

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect('/login')
    
    try:
        settings = {s.key: s.value for s in AppSetting.query.all()}
        featured_products = Product.query.filter_by(is_featured=True).limit(3).all()
        
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
                <div class="card product-card">
                    <img src="{product.image_url}" alt="{product.name}" class="product-image" onerror="this.style.display='none'">
                    <h3 style="margin-bottom: 0.5rem; color: var(--dark);">{product.name}</h3>
                    <p style="color: #6B7280; margin-bottom: 1rem;">{product.description}</p>
                    <div class="price" style="margin-bottom: 0.5rem;">Rp {product.price:,.0f}</div>
                    <p style="color: #6B7280; font-size: 0.9rem;">Stock: {product.stock} | {weight_info}</p>
                    {add_to_cart_btn}
                </div>
            '''
        
        content = f'''
        <div class="hero">
            <h1>{settings.get('app_name', 'Kang-Mas Shop')}</h1>
            <p>{settings.get('app_description', 'Sejak 2017 - Melayani dengan Kualitas Terbaik')}</p>
            <p><em>Ikan mas segar langsung dari kolam Magelang</em></p>
            
            <div style="margin-top: 2rem;">
                <p style="font-size: 1.2rem;">
                    Selamat datang kembali, <strong>{current_user.full_name}</strong>!
                </p>
                {current_user.user_type == 'customer' and '''
                <a href="/products" class="btn btn-primary" style="margin-top: 1rem;">
                    <i class="fas fa-store"></i> Lihat Semua Produk
                </a>
                ''' or '''
                <a href="/seller/dashboard" class="btn btn-primary" style="margin-top: 1rem;">
                    <i class="fas fa-chart-line"></i> Seller Dashboard
                </a>
                '''}
            </div>
        </div>

        <h2 style="margin-bottom: 2rem; text-align: center; color: var(--primary);">
            <i class="fas fa-star"></i> Produk Unggulan
        </h2>
        <div class="grid grid-3">
            {featured_html}
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">7+</div>
                <div class="stat-label">Tahun Pengalaman</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">1000+</div>
                <div class="stat-label">Pelanggan Puas</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">100%</div>
                <div class="stat-label">Ikan Segar</div>
            </div>
        </div>
        '''
        
        return base_html('Home', content)
    except Exception as e:
        print(f"Error in index route: {e}")
        return base_html('Home', '<div class="card"><h2>Welcome to Kang-Mas Shop</h2><p>Error loading content. Please try again.</p></div>')

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
            
            # ===== SYNC KE SUPABASE SETELAH COMMIT =====
            try:
                user_data = user.to_dict()
                supabase_insert('users', user_data)
                print(f"✅ User synced to Supabase: {user.email}")
            except Exception as sync_error:
                print(f"❌ Failed to sync user to Supabase: {sync_error}")
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
                    <p><strong>Total Belanja:</strong> Rp {total_spent:,.0f}</p>
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
        
        # ===== SYNC KE SUPABASE SETELAH COMMIT =====
        try:
            # Sync order ke Supabase
            order_data = order.to_dict()
            supabase_insert('orders', order_data)
            print(f"✅ Order synced to Supabase: {order.order_number}")
            
            # Sync order items ke Supabase
            for item in order_items:
                item_data = {
                    'order_id': item.order_id,
                    'product_id': item.product_id,
                    'quantity': item.quantity,
                    'price': float(item.price),
                    'cost_price': float(item.cost_price) if item.cost_price else 0
                }
                supabase_insert('order_items', item_data)
                print(f"✅ Order item synced to Supabase: Product {item.product_id}, Qty {item.quantity}")
            
        except Exception as sync_error:
            print(f"❌ Failed to sync order to Supabase: {sync_error}")
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
                            <strong>⚠️ Menunggu Pembayaran:</strong> Pesanan belum dapat diproses karena pembayaran belum diterima.
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

@app.route('/sync-to-supabase')
@login_required
@seller_required
def sync_to_supabase_route():
    """Route untuk manual sync ke Supabase"""
    try:
        tables = [
            (User, 'users'),
            (Product, 'products'),
            (Order, 'orders'),
            (OrderItem, 'order_items'),
            (Account, 'accounts'),
            (JournalEntry, 'journal_entries'),
            (JournalDetail, 'journal_details')
        ]
        
        results = []
        for model, table_name in tables:
            success = sync_to_supabase(model, table_name)
            results.append({
                'table': table_name,
                'success': success
            })
        
        return jsonify({
            'success': True,
            'message': 'Sync completed',
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Sync failed: {str(e)}'
        })

@app.route('/test-supabase-full')
def test_supabase_full():
    """Test koneksi dan operasi Supabase lengkap"""
    try:
        # Test 1: Connection
        response = supabase.table('users').select('*').limit(1).execute()
        
        # Test 2: Insert test data
        test_data = {
            'email': f'test_{int(time.time())}@example.com',
            'full_name': 'Test User',
            'user_type': 'customer',
            'created_at': datetime.now().isoformat()
        }
        
        insert_result = supabase_insert('users', test_data)
        
        # Test 3: Select data
        select_result = supabase_select('users', ('email', test_data['email']))
        
        return jsonify({
            'success': True,
            'connection_test': '✅ Berhasil',
            'insert_test': '✅ Berhasil' if insert_result else '❌ Gagal',
            'select_test': '✅ Berhasil' if select_result else '❌ Gagal',
            'test_data_inserted': insert_result,
            'test_data_retrieved': select_result
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'❌ Supabase test failed: {str(e)}'
        })

@app.route('/seller/reset_balances', methods=['POST'])
@login_required
@seller_required
def reset_balances():
    """Reset saldo awal ke nilai yang benar"""
    try:
        # Reset semua saldo account
        accounts = Account.query.all()
        for account in accounts:
            account.balance = 0
        
        # Set saldo awal yang benar
        kas = Account.query.filter_by(type='kas').first()
        persediaan = Account.query.filter_by(type='persediaan').first()
        perlengkapan = Account.query.filter_by(type='perlengkapan').first()
        peralatan = Account.query.filter_by(type='peralatan').first()
        hutang = Account.query.filter_by(type='hutang').first()
        pendapatan = Account.query.filter_by(type='pendapatan').first()
        
        if kas: kas.balance = 10000000
        if persediaan: persediaan.balance = 5000000
        if perlengkapan: perlengkapan.balance = 6500000
        if peralatan: peralatan.balance = 5000000
        if hutang: hutang.balance = 26500000  # 26.5 juta
        if pendapatan: pendapatan.balance = 0  # 0
        
        db.session.commit()
        
        flash('✅ Saldo awal berhasil direset! Pendapatan Penjualan = 0, Utang Dagang = Rp 26,500,000', 'success')
        return jsonify({'success': True, 'message': 'Saldo awal berhasil direset'})
        
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
            
            # ===== SYNC KE SUPABASE SETELAH COMMIT =====
            try:
                product_data = product.to_dict()
                supabase_insert('products', product_data)
                print(f"✅ Product synced to Supabase: {product.name}")
            except Exception as sync_error:
                print(f"❌ Failed to sync product to Supabase: {sync_error}")
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
            
            <h4 style="margin: 1.5rem 0 1rem 0; color: var(--primary);">Detail Akun:</h4>
        '''
        
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
                    <label class="form-label">Harga Beli per Unit (HPP)</label>
                    <input type="number" id="cost_price" name="cost_price" class="form-control" 
                           min="0" required placeholder="Masukkan harga beli">
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
            'description': f'HPP {product_name} - {quantity} unit'
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
        
        if template_key not in TRANSACTION_TEMPLATES:
            return jsonify({'success': False, 'message': 'Template tidak ditemukan'})
        
        # Create journal from template
        journal = create_journal_from_template(template_key, date, amounts)
        
        if journal:
            # HAPUS BARIS INI - tidak perlu panggil fungsi dobel
            # update_inventory_from_purchase_journal(journal, template_key, amounts)
            
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
        closing_entry = create_closing_entries()
        
        if closing_entry:
            return jsonify({
                'success': True, 
                'message': 'Jurnal penutup berhasil dibuat!'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Gagal membuat jurnal penutup'
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

# ===== TEST SUPABASE CONNECTION =====
@app.route('/test-supabase')
def test_supabase():
    try:
        # Test connection
        response = supabase.table('user').select('*').limit(1).execute()
        return jsonify({
            'success': True,
            'message': '✅ Supabase connection successful!',
            'data': response.data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'❌ Supabase connection failed: {str(e)}'
        })

# ===== FUNGSI CREATE_INITIAL_JOURNALS =====
def create_initial_journals():
    """Membuat jurnal umum awal - TANPA membuat jurnal saldo awal"""
    try:
        # Cek apakah sudah ada jurnal (selain saldo awal)
        if JournalEntry.query.filter(JournalEntry.journal_type != 'opening_balance').count() > 0:
            print("Jurnal sudah ada, skip pembuatan initial journals")
            return
        
        print("Tidak membuat jurnal saldo awal - saldo sudah tercatat di balance akun")
        
    except Exception as e:
        print(f"Error in create_initial_journals: {e}")

    print("🔄 Syncing initial data to Supabase...")
    initial_tables = [
        (User, 'users'),
        (Product, 'products'), 
        (Account, 'accounts')
    ]
    
    for model, table_name in initial_tables:
        success = sync_to_supabase(model, table_name)
        print(f"📊 {table_name}: {'✅ Success' if success else '❌ Failed'}")
    
    print("✅ Initial data sync completed!")

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
            {'code': '501', 'name': 'Harga Pokok Penjualan', 'type': 'hpp', 'category': 'expense', 'balance': 0},
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
    
    # ===== SYNC INITIAL DATA KE SUPABASE ===== 
    print("🔄 Syncing initial data to Supabase...")
    initial_tables = [
        (User, 'users'),
        (Product, 'products'), 
        (Account, 'accounts'),
        (InventoryTransaction, 'inventory_transactions'),
        (InventoryCard, 'inventory_cards')
    ]
    
    for model, table_name in initial_tables:
        success = sync_to_supabase(model, table_name)
        print(f"📊 {table_name}: {'✅ Success' if success else '❌ Failed'}")
    
    print("✅ Initial data sync completed!")

@app.route("/health")
def health():
    """Health check endpoint"""
    supabase_status = "connected" if supabase is not None else "disconnected"
    return jsonify({
        "status": "healthy", 
        "supabase": supabase_status,
        "timestamp": datetime.now().isoformat()
    }), 200

# ===== JALANKAN APLIKASI =====
if __name__ == '__main__':
    with app.app_context():
        try:
            # Coba buat database jika belum ada
            db.create_all()
            print("✅ Database created successfully!")
            
            # Isi data awal
            create_initial_data()
            print("✅ Initial data created successfully!")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            print("Trying to continue...")
        
        print("🔐 Seller Login: kang.mas1817@gmail.com / TugasSiaKangMas")
        print("🔐 Customer Login: customer@example.com / customer123")
        print("🚀 Server running on http://localhost:5000")
        print("🏥 Health check: http://localhost:5000/health")  # Tambahkan ini juga
    
    app.run(debug=True, port=5000)
