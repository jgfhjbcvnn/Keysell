import os
import sqlite3
import logging
import asyncio
import io
import csv
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import qrcode

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8249817052:AAG4w0Xk3CF23PKjDhwyR3ga_q1N1By5_nc"
OWNER_ID = 8477195695
UPI_ID = "anurag99999@fam"
BOT_NAME = "OGGY KEY SELLING"
BOT_LOGO = "🔰"

DB_FILE = "panel_bot.db"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== DATABASE SETUP ====================
def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            join_date TEXT,
            total_spent REAL DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            display_name TEXT,
            parent_id INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_date TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER,
            name TEXT,
            display_name TEXT,
            price_1day REAL DEFAULT 0,
            price_7days REAL DEFAULT 0,
            price_30days REAL DEFAULT 0,
            price_full REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_date TEXT,
            apk_file_id TEXT DEFAULT '',
            FOREIGN KEY (folder_id) REFERENCES folders(id)
        )
    ''')
    
    # Add apk_file_id column if missing (for existing DB)
    cursor.execute("PRAGMA table_info(products)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'apk_file_id' not in columns:
        cursor.execute("ALTER TABLE products ADD COLUMN apk_file_id TEXT DEFAULT ''")
    if 'apk_link' in columns:
        # Remove old apk_link column if exists
        try:
            cursor.execute("ALTER TABLE products DROP COLUMN apk_link")
        except:
            pass
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_value TEXT UNIQUE,
            product_id INTEGER,
            duration TEXT,
            is_used INTEGER DEFAULT 0,
            user_id INTEGER DEFAULT NULL,
            created_date TEXT,
            used_date TEXT,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            product_name TEXT,
            duration TEXT,
            amount REAL,
            status TEXT DEFAULT 'pending',
            payment_screenshot TEXT,
            panel_key TEXT,
            order_date TEXT,
            approved_date TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_deleted_keys (
            user_id INTEGER,
            key_value TEXT,
            deleted_date TEXT,
            PRIMARY KEY (user_id, key_value)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            key_value TEXT,
            request_type TEXT,
            status TEXT DEFAULT 'pending',
            request_date TEXT
        )
    ''')
    
    default_folders = [
        ('BGMI_Loader', 'BGMI Loader', 0),
        ('Game_Loader', 'Game Loader', 0),
        ('Kill_Loader', 'Kill Loader', 0),
        ('Lodaer', 'Lodaer', 0)
    ]
    for name, display, parent in default_folders:
        cursor.execute('''
            INSERT OR IGNORE INTO folders (name, display_name, parent_id, created_date)
            VALUES (?, ?, ?, ?)
        ''', (name, display, parent, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    
    conn.commit()
    conn.close()

# ==================== DATABASE FUNCTIONS ====================
def add_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, join_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, join_date, total_spent FROM users')
    users = cursor.fetchall()
    conn.close()
    return users

def get_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM orders WHERE status = "approved"')
    total_orders = cursor.fetchone()[0]
    cursor.execute('SELECT SUM(amount) FROM orders WHERE status = "approved"')
    total_revenue = cursor.fetchone()[0] or 0
    conn.close()
    return total_users, total_orders, total_revenue

def get_folders(parent_id=0):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, display_name FROM folders 
        WHERE parent_id = ? AND is_active = 1
        ORDER BY created_date DESC
    ''', (parent_id,))
    folders = cursor.fetchall()
    conn.close()
    return folders

def get_all_folders():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, display_name, parent_id, is_active 
        FROM folders ORDER BY parent_id, created_date
    ''')
    folders = cursor.fetchall()
    conn.close()
    return folders

def add_folder(name, display_name, parent_id=0):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO folders (name, display_name, parent_id, created_date)
            VALUES (?, ?, ?, ?)
        ''', (name, display_name, parent_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def update_folder(folder_id, display_name=None, is_active=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if display_name:
        cursor.execute('UPDATE folders SET display_name = ? WHERE id = ?', (display_name, folder_id))
    if is_active is not None:
        cursor.execute('UPDATE folders SET is_active = ? WHERE id = ?', (is_active, folder_id))
    conn.commit()
    conn.close()

def delete_folder(folder_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE folder_id = ?', (folder_id,))
    cursor.execute('DELETE FROM folders WHERE id = ?', (folder_id,))
    conn.commit()
    conn.close()

def get_products(folder_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, display_name, price_1day, price_7days, price_30days, price_full 
        FROM products WHERE folder_id = ? AND is_active = 1
        ORDER BY created_date DESC
    ''', (folder_id,))
    products = cursor.fetchall()
    conn.close()
    return products

def get_all_products():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.id, p.name, p.display_name, f.display_name, 
               p.price_1day, p.price_7days, p.price_30days, p.price_full, p.is_active,
               p.apk_file_id
        FROM products p
        JOIN folders f ON p.folder_id = f.id
        ORDER BY p.created_date DESC
    ''')
    products = cursor.fetchall()
    conn.close()
    return products

def add_product(folder_id, name, display_name, price_1day, price_7days, price_30days, price_full):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO products (folder_id, name, display_name, price_1day, price_7days, price_30days, price_full, created_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (folder_id, name, display_name, price_1day, price_7days, price_30days, price_full,
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False

def update_product_price(product_id, duration, price):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if duration == '1day':
        cursor.execute('UPDATE products SET price_1day = ? WHERE id = ?', (price, product_id))
    elif duration == '7days':
        cursor.execute('UPDATE products SET price_7days = ? WHERE id = ?', (price, product_id))
    elif duration == '30days':
        cursor.execute('UPDATE products SET price_30days = ? WHERE id = ?', (price, product_id))
    elif duration == 'full':
        cursor.execute('UPDATE products SET price_full = ? WHERE id = ?', (price, product_id))
    conn.commit()
    conn.close()

def set_product_apk_file(product_id, file_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET apk_file_id = ? WHERE id = ?', (file_id, product_id))
    conn.commit()
    conn.close()

def get_product_apk_file(product_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT apk_file_id FROM products WHERE id = ?', (product_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def delete_product_apk(product_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET apk_file_id = "" WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM keys WHERE product_id = ?', (product_id,))
    cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()

def add_key(key_value, product_id, duration):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO keys (key_value, product_id, duration, created_date)
            VALUES (?, ?, ?, ?)
        ''', (key_value, product_id, duration, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def get_keys_for_product(product_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT key_value, duration, is_used, created_date 
        FROM keys WHERE product_id = ?
        ORDER BY created_date DESC
    ''', (product_id,))
    keys = cursor.fetchall()
    conn.close()
    return keys

def create_order(user_id, product_id, product_name, duration, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (user_id, product_id, product_name, duration, amount, order_date)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, product_id, product_name, duration, amount,
          datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id

def update_order_payment(order_id, screenshot_file_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE orders 
        SET payment_screenshot = ?, status = 'pending_approval'
        WHERE order_id = ?
    ''', (screenshot_file_id, order_id))
    conn.commit()
    conn.close()

def get_pending_orders():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.order_id, o.user_id, u.username, u.first_name, o.product_name, 
               o.duration, o.amount, o.payment_screenshot, o.order_date
        FROM orders o
        JOIN users u ON o.user_id = u.user_id
        WHERE o.status = 'pending_approval'
        ORDER BY o.order_date DESC
    ''')
    orders = cursor.fetchall()
    conn.close()
    return orders

def approve_order(order_id, panel_key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, amount, product_id FROM orders WHERE order_id = ?', (order_id,))
    order = cursor.fetchone()
    if order:
        user_id, amount, product_id = order
        cursor.execute('''
            UPDATE orders 
            SET status = 'approved', panel_key = ?, approved_date = ?
            WHERE order_id = ?
        ''', (panel_key, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), order_id))
        cursor.execute('''
            UPDATE users 
            SET total_spent = total_spent + ?
            WHERE user_id = ?
        ''', (amount, user_id))
        cursor.execute('''
            UPDATE keys 
            SET is_used = 1, user_id = ?, used_date = ?
            WHERE key_value = ?
        ''', (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), panel_key))
        conn.commit()
        # Get APK file ID if any
        cursor.execute('SELECT apk_file_id FROM products WHERE id = ?', (product_id,))
        apk_row = cursor.fetchone()
        apk_file_id = apk_row[0] if apk_row else None
        conn.close()
        return True, user_id, apk_file_id
    conn.close()
    return False, None, None

def reject_order(order_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE orders 
        SET status = 'rejected'
        WHERE order_id = ?
    ''', (order_id,))
    conn.commit()
    conn.close()

def get_user_orders(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT order_id, product_name, duration, amount, status, panel_key, order_date
        FROM orders
        WHERE user_id = ?
        ORDER BY order_date DESC
    ''', (user_id,))
    orders = cursor.fetchall()
    conn.close()
    return orders

def get_user_keys(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.order_id, o.product_name, o.duration, o.panel_key, o.approved_date
        FROM orders o
        WHERE o.user_id = ? AND o.status = 'approved' AND o.panel_key IS NOT NULL
        ORDER BY o.approved_date DESC
    ''', (user_id,))
    keys = cursor.fetchall()
    cursor.execute('SELECT key_value FROM user_deleted_keys WHERE user_id = ?', (user_id,))
    deleted = set(row[0] for row in cursor.fetchall())
    conn.close()
    return [k for k in keys if k[3] not in deleted]

def delete_key_for_user(user_id, key_value):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO user_deleted_keys (user_id, key_value, deleted_date)
        VALUES (?, ?, ?)
    ''', (user_id, key_value, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

# ==================== QR CODE GENERATION ====================
def generate_upi_qr(amount, upi_id=UPI_ID, recipient_name="OGGY STORE"):
    upi_url = f"upi://pay?pa={upi_id}&pn={recipient_name}&am={amount}&cu=INR"
    qr = qrcode.make(upi_url)
    img_bytes = io.BytesIO()
    qr.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes

# ==================== TELEGRAM BOT ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username, user.first_name)
    is_admin = (user.id == OWNER_ID)
    
    welcome_text = f"""
{BOT_LOGO} <b>{BOT_NAME}</b> {BOT_LOGO}

╔══════════════════════════════════════╗
║      🎉 <b>WELCOME {user.first_name.upper()}!</b> 🎉      ║
╚══════════════════════════════════════╝

👤 <b>Your Profile:</b>
├─ 🆔 ID: <code>{user.id}</code>
├─ 📛 Name: {user.first_name}
└─ 📱 Username: @{user.username if user.username else 'Not set'}

🔥 <b>Fast & Reliable Loader Keys</b>
💳 <b>UPI ID:</b> <code>{UPI_ID}</code>

📌 <b>Use the buttons below</b>
    """
    
    keyboard = [
        [InlineKeyboardButton("🔑 My Keys 📋", callback_data="my_keys")],
        [InlineKeyboardButton("❌ Delete Key 🗑️", callback_data="delete_key")],
        [InlineKeyboardButton("🛒 Buy Key 💰", callback_data="browse_0")],
        [InlineKeyboardButton("🔄 Reset Key ♻️", callback_data="reset_key")]
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("⚙️ ADMIN PANEL ⚙️", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_folders(update, context, 0)

async def show_folders(update: Update, context: ContextTypes.DEFAULT_TYPE, parent_id=0, message=None):
    folders = get_folders(parent_id)
    products = get_products(parent_id)
    
    keyboard = []
    row = []
    for folder in folders:
        row.append(InlineKeyboardButton(f"📁 {folder[2]}", callback_data=f"folder_{folder[0]}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    for product in products:
        product_id, name, display_name, p1, p7, p30, pfull = product
        keyboard.append([InlineKeyboardButton(f"💰 {display_name}", callback_data=f"product_{product_id}")])
    
    if parent_id != 0:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT parent_id FROM folders WHERE id = ?', (parent_id,))
        result = cursor.fetchone()
        conn.close()
        if result:
            back_to = result[0]
            keyboard.append([InlineKeyboardButton("🔙 BACK", callback_data=f"folder_{back_to}" if back_to != 0 else "browse_0")])
    
    keyboard.append([InlineKeyboardButton("🏠 MAIN MENU", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "╔══════════════════════════════╗\n║     📦 SELECT PRODUCT 📦     ║\n╚══════════════════════════════╝\n\nBrowse through folders to find what you need."
    
    if message:
        await message.edit_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def show_product_durations(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id, message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, display_name, price_1day, price_7days, price_30days, price_full 
        FROM products WHERE id = ?
    ''', (product_id,))
    product = cursor.fetchone()
    conn.close()
    
    if not product:
        await message.edit_text("❌ Product not found!")
        return
    
    product_id, name, display_name, p1, p7, p30, pfull = product
    
    keyboard = []
    if p1 > 0:
        keyboard.append([InlineKeyboardButton(f"📅 1 DAY - ₹{p1}", callback_data=f"duration_{product_id}_1day_{p1}")])
    if p7 > 0:
        keyboard.append([InlineKeyboardButton(f"📅 7 DAYS - ₹{p7}", callback_data=f"duration_{product_id}_7days_{p7}")])
    if p30 > 0:
        keyboard.append([InlineKeyboardButton(f"📅 30 DAYS - ₹{p30}", callback_data=f"duration_{product_id}_30days_{p30}")])
    if pfull > 0:
        keyboard.append([InlineKeyboardButton(f"⭐ FULL SESSION - ₹{pfull}", callback_data=f"duration_{product_id}_full_{pfull}")])
    
    keyboard.append([InlineKeyboardButton("🔙 BACK", callback_data=f"folder_{product_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.edit_text(f"╔══════════════════════════════╗\n║     💰 {display_name} 💰     ║\n╚══════════════════════════════╝\n\nSelect duration:", reply_markup=reply_markup)

async def payment_with_qr(update: Update, context: ContextTypes.DEFAULT_TYPE, query, product_id, duration, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT display_name FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    conn.close()
    product_name = product[0] if product else "Product"
    
    duration_name = duration.replace('1day','1 Day').replace('7days','7 Days').replace('30days','30 Days').replace('full','Full Session')
    qr_image = generate_upi_qr(amount)
    
    caption = f"""
╔══════════════════════════════╗
║     💳 PAYMENT DETAILS 💳     ║
╚══════════════════════════════╝

📦 <b>Product:</b> {product_name}
📅 <b>Duration:</b> {duration_name}
💰 <b>Amount:</b> ₹{amount}

📱 <b>UPI ID:</b> <code>{UPI_ID}</code>

Scan the QR code or use UPI ID to pay.

<b>Steps:</b>
1️⃣ Scan QR or send to {UPI_ID}
2️⃣ Pay ₹{amount}
3️⃣ Take screenshot
4️⃣ Click below button

⚠️ Send screenshot ONLY after payment!
    """
    
    keyboard = [[InlineKeyboardButton("📸 SEND PAYMENT SCREENSHOT", callback_data=f"sendscreenshot_{product_id}_{duration}")],
                [InlineKeyboardButton("🔙 BACK", callback_data=f"product_{product_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_photo(photo=InputFile(qr_image, filename="qr.png"), caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    is_admin = (user.id == OWNER_ID)
    
    if data == "main_menu":
        await start_callback(query, user.id)
    elif data == "browse_0":
        await show_folders(update, context, 0, query.message)
    elif data == "my_keys":
        await my_keys_callback(query, user.id)
    elif data == "delete_key":
        await delete_key_selection(query, user.id)
    elif data == "reset_key":
        await reset_key_selection(query, user.id)
    elif data.startswith("delkey_"):
        key_value = data.replace("delkey_", "")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO admin_requests (user_id, key_value, request_type, request_date)
            VALUES (?, ?, ?, ?)
        ''', (user.id, key_value, 'delete', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        cursor.execute('SELECT request_id FROM admin_requests WHERE user_id = ? AND key_value = ? AND request_type = "delete" ORDER BY request_date DESC LIMIT 1', (user.id, key_value))
        req_id = cursor.fetchone()[0]
        conn.close()
        
        keyboard = [
            [InlineKeyboardButton("🗑️ Confirm Delete", callback_data=f"delete_confirm_{req_id}"),
             InlineKeyboardButton("❌ Cancel", callback_data=f"delete_cancel_{req_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(OWNER_ID, f"🗑️ <b>Delete Request</b>\n👤 {user.first_name}\n🆔 <code>{user.id}</code>\n🔑 <code>{key_value}</code>", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        await query.edit_message_text("🗑️ Delete request sent to admin. You will be notified once confirmed.")
    elif data.startswith("resetkey_"):
        key_value = data.replace("resetkey_", "")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO admin_requests (user_id, key_value, request_type, request_date)
            VALUES (?, ?, ?, ?)
        ''', (user.id, key_value, 'reset', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        cursor.execute('SELECT request_id FROM admin_requests WHERE user_id = ? AND key_value = ? AND request_type = "reset" ORDER BY request_date DESC LIMIT 1', (user.id, key_value))
        req_id = cursor.fetchone()[0]
        conn.close()
        
        keyboard = [
            [InlineKeyboardButton("✅ Reset Done", callback_data=f"reset_done_{req_id}"),
             InlineKeyboardButton("⚠️ Key Already Reset", callback_data=f"reset_already_{req_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(OWNER_ID, f"🔄 <b>Reset Request</b>\n👤 {user.first_name}\n🆔 <code>{user.id}</code>\n🔑 <code>{key_value}</code>", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        await query.edit_message_text("🔄 Reset request sent to admin. You will be notified when processed.")
    elif data.startswith("reset_done_"):
        request_id = int(data.split("_")[2])
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, key_value FROM admin_requests WHERE request_id = ?', (request_id,))
        req = cursor.fetchone()
        if req:
            user_id, key_value = req
            cursor.execute('UPDATE admin_requests SET status = "completed" WHERE request_id = ?', (request_id,))
            conn.commit()
            conn.close()
            await context.bot.send_message(user_id, f"✅ Your key <code>{key_value}</code> has been reset by admin.")
            await query.edit_message_text(f"✅ Reset confirmed for key {key_value}")
        else:
            await query.edit_message_text("❌ Request not found.")
    elif data.startswith("reset_already_"):
        request_id = int(data.split("_")[2])
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, key_value FROM admin_requests WHERE request_id = ?', (request_id,))
        req = cursor.fetchone()
        if req:
            user_id, key_value = req
            cursor.execute('UPDATE admin_requests SET status = "rejected" WHERE request_id = ?', (request_id,))
            conn.commit()
            conn.close()
            await context.bot.send_message(user_id, f"⚠️ Admin says your key <code>{key_value}</code> is already reset or invalid.")
            await query.edit_message_text(f"⚠️ Marked as already reset for {key_value}")
        else:
            await query.edit_message_text("❌ Request not found.")
    elif data.startswith("delete_confirm_"):
        request_id = int(data.split("_")[2])
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, key_value FROM admin_requests WHERE request_id = ?', (request_id,))
        req = cursor.fetchone()
        if req:
            user_id, key_value = req
            delete_key_for_user(user_id, key_value)
            cursor.execute('UPDATE admin_requests SET status = "completed" WHERE request_id = ?', (request_id,))
            conn.commit()
            conn.close()
            await context.bot.send_message(user_id, f"✅ Your key <code>{key_value}</code> has been deleted from your list.")
            await query.edit_message_text(f"🗑️ Deletion confirmed for {key_value}")
        else:
            await query.edit_message_text("❌ Request not found.")
    elif data.startswith("delete_cancel_"):
        request_id = int(data.split("_")[2])
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('UPDATE admin_requests SET status = "cancelled" WHERE request_id = ?', (request_id,))
        conn.commit()
        conn.close()
        await query.edit_message_text("❌ Deletion cancelled.")
    elif data.startswith("folder_"):
        folder_id = int(data.replace("folder_", ""))
        await show_folders(update, context, folder_id, query.message)
    elif data.startswith("product_"):
        product_id = int(data.replace("product_", ""))
        await show_product_durations(update, context, product_id, query.message)
    elif data.startswith("duration_"):
        parts = data.split("_")
        product_id = int(parts[1])
        duration = parts[2]
        amount = float(parts[3])
        await payment_with_qr(update, context, query, product_id, duration, amount)
    elif data.startswith("sendscreenshot_"):
        parts = data.split("_")
        product_id = int(parts[1])
        duration = parts[2]
        context.user_data['pending_product'] = product_id
        context.user_data['pending_duration'] = duration
        await query.edit_message_text(
            "📸 <b>SEND PAYMENT SCREENSHOT</b>\n\n"
            "Please send the payment confirmation screenshot as a photo.\n\n"
            "✅ <b>Make sure screenshot shows:</b>\n"
            "• Transaction ID\n"
            "• Amount\n"
            "• UPI ID: " + UPI_ID + "\n\n"
            "Send the photo now:",
            parse_mode=ParseMode.HTML
        )
    elif data == "admin_panel" and is_admin:
        await show_admin_panel(query)
    elif data.startswith("admin_") and is_admin:
        await handle_admin_actions(query, data, context)
    elif data.startswith("confirm_del_folder_"):
        folder_id = int(data.replace("confirm_del_folder_", ""))
        delete_folder(folder_id)
        await query.edit_message_text(f"✅ Folder #{folder_id} deleted!")
        await asyncio.sleep(1)
        await show_folders_admin(query)
    elif data.startswith("confirm_del_product_"):
        product_id = int(data.replace("confirm_del_product_", ""))
        delete_product(product_id)
        await query.edit_message_text(f"✅ Product #{product_id} deleted!")
        await asyncio.sleep(1)
        await show_products_admin(query)
    elif data.startswith("upload_apk_"):
        product_id = int(data.replace("upload_apk_", ""))
        context.user_data['upload_apk_for_product'] = product_id
        await query.edit_message_text(f"📤 Send the APK file for product ID {product_id}.\n\nPlease upload the APK file as a document.")
    elif data.startswith("remove_apk_"):
        product_id = int(data.replace("remove_apk_", ""))
        delete_product_apk(product_id)
        await query.edit_message_text(f"✅ APK file removed for product ID {product_id}.")
        await asyncio.sleep(1)
        await show_products_admin(query)

async def start_callback(query, user_id):
    user = query.from_user
    is_admin = (user.id == OWNER_ID)
    welcome_text = f"""
{BOT_LOGO} <b>{BOT_NAME}</b> {BOT_LOGO}

╔══════════════════════════════════════╗
║      🎉 <b>WELCOME BACK!</b> 🎉            ║
╚══════════════════════════════════════╝

👤 <b>Your Profile:</b>
├─ 🆔 ID: <code>{user.id}</code>
├─ 📛 Name: {user.first_name}
└─ 📱 Username: @{user.username if user.username else 'Not set'}

💳 <b>UPI ID:</b> <code>{UPI_ID}</code>

📌 <b>Use the buttons below</b>
    """
    keyboard = [
        [InlineKeyboardButton("🔑 My Keys 📋", callback_data="my_keys")],
        [InlineKeyboardButton("❌ Delete Key 🗑️", callback_data="delete_key")],
        [InlineKeyboardButton("🛒 Buy Key 💰", callback_data="browse_0")],
        [InlineKeyboardButton("🔄 Reset Key ♻️", callback_data="reset_key")]
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton("⚙️ ADMIN PANEL ⚙️", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def my_keys_callback(query, user_id):
    keys = get_user_keys(user_id)
    if not keys:
        text = "╔══════════════════════════════╗\n║      🔑 NO KEYS FOUND 🔑      ║\n╚══════════════════════════════╝\n\nYou have no approved keys yet.\nUse /buy to purchase a key."
        keyboard = [[InlineKeyboardButton("🛒 BUY NOW", callback_data="browse_0")],
                    [InlineKeyboardButton("🏠 MAIN MENU", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
        return
    
    text = "╔══════════════════════════════╗\n║      🔑 YOUR KEYS 🔑      ║\n╚══════════════════════════════╝\n\n"
    for order_id, product_name, duration, key, approved_date in keys:
        duration_name = duration.replace('1day','1 Day').replace('7days','7 Days').replace('30days','30 Days').replace('full','Full Session')
        text += f"┌────────────────────────────┐\n"
        text += f"│ 📦 {product_name}\n"
        text += f"│ 📅 {duration_name}\n"
        text += f"│ 🔑 <code>{key}</code>\n"
        text += f"│ 📅 {approved_date[:10]}\n"
        text += f"└────────────────────────────┘\n\n"
    keyboard = [[InlineKeyboardButton("🛒 BUY MORE", callback_data="browse_0")],
                [InlineKeyboardButton("🏠 MAIN MENU", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def delete_key_selection(query, user_id):
    keys = get_user_keys(user_id)
    if not keys:
        await query.edit_message_text("❌ You have no keys to delete.")
        await asyncio.sleep(2)
        await start_callback(query, user_id)
        return
    keyboard = []
    for order_id, product_name, duration, key, _ in keys:
        duration_name = duration.replace('1day','1 Day').replace('7days','7 Days').replace('30days','30 Days').replace('full','Full Session')
        display = f"{product_name} ({duration_name})"
        keyboard.append([InlineKeyboardButton(display, callback_data=f"delkey_{key}")])
    keyboard.append([InlineKeyboardButton("🔙 BACK", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Select the key you want to delete (admin will approve):", reply_markup=reply_markup)

async def reset_key_selection(query, user_id):
    keys = get_user_keys(user_id)
    if not keys:
        await query.edit_message_text("❌ You have no keys to reset.")
        await asyncio.sleep(2)
        await start_callback(query, user_id)
        return
    keyboard = []
    for order_id, product_name, duration, key, _ in keys:
        duration_name = duration.replace('1day','1 Day').replace('7days','7 Days').replace('30days','30 Days').replace('full','Full Session')
        display = f"{product_name} ({duration_name})"
        keyboard.append([InlineKeyboardButton(display, callback_data=f"resetkey_{key}")])
    keyboard.append([InlineKeyboardButton("🔙 BACK", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Select the key you want to reset (admin will be notified):", reply_markup=reply_markup)

async def show_admin_panel(query):
    text = """
╔══════════════════════════════╗
║     ⚙️ ADMIN PANEL ⚙️      ║
╚══════════════════════════════╝

Select an option:
    """
    keyboard = [
        [InlineKeyboardButton("📁 MANAGE FOLDERS", callback_data="admin_folders")],
        [InlineKeyboardButton("💰 MANAGE PRODUCTS", callback_data="admin_products")],
        [InlineKeyboardButton("🔑 MANAGE KEYS", callback_data="admin_keys")],
        [InlineKeyboardButton("📋 PENDING ORDERS", callback_data="admin_orders")],
        [InlineKeyboardButton("🏠 BACK TO MAIN", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def handle_admin_actions(query, data, context):
    if data == "admin_folders":
        await show_folders_admin(query)
    elif data == "admin_products":
        await show_products_admin(query)
    elif data == "admin_keys":
        await show_keys_admin(query)
    elif data == "admin_orders":
        await show_orders_admin(query)

async def show_folders_admin(query):
    folders = get_all_folders()
    text = "╔══════════════════════════════╗\n║     📁 MANAGE FOLDERS 📁     ║\n╚══════════════════════════════╝\n\n"
    for folder in folders:
        folder_id, name, display, parent, active = folder
        status = "✅" if active else "❌"
        parent_text = "Main" if parent == 0 else f"Inside ID:{parent}"
        text += f"{status} <b>{display}</b> (ID: {folder_id})\n   └ {name} | Parent: {parent_text}\n\n"
    text += "\n<b>Commands:</b>\n/addfolder &lt;name&gt; &lt;display&gt; &lt;parent_id&gt;\n/editfolder &lt;id&gt; &lt;new_display&gt;\n/delfolder &lt;id&gt;\n\nExample: /addfolder new_loader 'New Loader' 0"
    
    keyboard = []
    for folder in folders:
        folder_id = folder[0]
        keyboard.append([InlineKeyboardButton(f"🗑️ Delete {folder[2]}", callback_data=f"confirm_del_folder_{folder_id}")])
    keyboard.append([InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def show_products_admin(query):
    products = get_all_products()
    text = "╔══════════════════════════════╗\n║    💰 MANAGE PRODUCTS 💰    ║\n╚══════════════════════════════╝\n\n"
    for prod in products:
        prod_id, name, display, folder, p1, p7, p30, pfull, active, apk_file = prod
        status = "✅" if active else "❌"
        apk_status = "📎 APK uploaded" if apk_file else "❌ No APK"
        text += f"{status} <b>{display}</b> (ID: {prod_id})\n"
        text += f"   └ Folder: {folder}\n"
        text += f"   └ Prices: 1D:₹{p1} | 7D:₹{p7} | 30D:₹{p30} | Full:₹{pfull}\n"
        text += f"   └ {apk_status}\n\n"
    text += "\n<b>Commands:</b>\n"
    text += "/addproduct &lt;folder_id&gt; &lt;name&gt; &lt;display&gt; &lt;p1&gt; &lt;p7&gt; &lt;p30&gt; &lt;pfull&gt;\n"
    text += "/editproduct &lt;id&gt; &lt;duration&gt; &lt;price&gt;\n"
    text += "/delproduct &lt;id&gt;\n\n"
    text += "<b>APK Management (Click button below):</b>"
    
    keyboard = []
    for prod in products:
        prod_id = prod[0]
        keyboard.append([InlineKeyboardButton(f"📤 Upload APK for {prod[2]}", callback_data=f"upload_apk_{prod_id}")])
        if prod[9]:  # if APK exists
            keyboard.append([InlineKeyboardButton(f"🗑️ Remove APK from {prod[2]}", callback_data=f"remove_apk_{prod_id}")])
        keyboard.append([InlineKeyboardButton(f"🗑️ Delete {prod[2]}", callback_data=f"confirm_del_product_{prod_id}")])
    keyboard.append([InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def show_keys_admin(query):
    products = get_all_products()
    text = "╔══════════════════════════════╗\n║     🔑 MANAGE KEYS 🔑      ║\n╚══════════════════════════════╝\n\n"
    for prod in products:
        prod_id, name, display, folder, p1, p7, p30, pfull, active, apk = prod
        if active:
            text += f"<b>{display}</b> (ID: {prod_id})\n"
            keys = get_keys_for_product(prod_id)
            available = sum(1 for k in keys if not k[2])
            text += f"   └ Keys: {len(keys)} total | {available} available\n\n"
    text += "\n<b>Commands:</b>\n"
    text += "/addkey &lt;product_id&gt; &lt;duration&gt; &lt;key_value&gt;\n"
    text += "/listkeys &lt;product_id&gt;\n\n"
    text += "Example: /addkey 1 1day ABC123XYZ\n"
    text += "Durations: 1day, 7days, 30days, full"
    keyboard = [[InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def show_orders_admin(query):
    orders = get_pending_orders()
    if not orders:
        text = "╔══════════════════════════════╗\n║    📭 NO PENDING ORDERS 📭    ║\n╚══════════════════════════════╝"
    else:
        text = "╔══════════════════════════════╗\n║   📋 PENDING ORDERS 📋   ║\n╚══════════════════════════════╝\n\n"
        for order in orders:
            order_id, user_id, username, first_name, product_name, duration, amount, screenshot, date = order
            duration_name = duration.replace('1day','1 Day').replace('7days','7 Days').replace('30days','30 Days').replace('full','Full Session')
            text += f"┌────────────────────────────┐\n│ <b>ORDER #{order_id}</b>\n├────────────────────────────┤\n│ 👤 {first_name}\n│ 📱 @{username or 'No username'}\n│ 🆔 <code>{user_id}</code>\n│ 📦 {product_name}\n│ 📅 {duration_name}\n│ 💰 ₹{amount}\n│ 📅 {date[:10]}\n└────────────────────────────┘\n\n"
    text += "\n<b>Commands:</b>\n/approve &lt;order_id&gt; &lt;key&gt;\n/reject &lt;order_id&gt;\n\nExample: /approve 1 ABC123XYZ"
    keyboard = [[InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo = update.message.photo[-1]
    
    product_id = context.user_data.get('pending_product')
    duration = context.user_data.get('pending_duration')
    
    if not product_id or not duration:
        await update.message.reply_text("❌ Please start a new purchase with /buy")
        return
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT display_name FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    if not product:
        conn.close()
        await update.message.reply_text("❌ Product not found!")
        return
    product_name = product[0]
    
    if duration == '1day':
        cursor.execute('SELECT price_1day FROM products WHERE id = ?', (product_id,))
    elif duration == '7days':
        cursor.execute('SELECT price_7days FROM products WHERE id = ?', (product_id,))
    elif duration == '30days':
        cursor.execute('SELECT price_30days FROM products WHERE id = ?', (product_id,))
    else:
        cursor.execute('SELECT price_full FROM products WHERE id = ?', (product_id,))
    amount_row = cursor.fetchone()
    conn.close()
    
    if not amount_row or amount_row[0] == 0:
        await update.message.reply_text("❌ Invalid price for this duration!")
        return
    amount = amount_row[0]
    
    order_id = create_order(user.id, product_id, product_name, duration, amount)
    file_id = photo.file_id
    update_order_payment(order_id, file_id)
    
    duration_name = duration.replace('1day','1 Day').replace('7days','7 Days').replace('30days','30 Days').replace('full','Full Session')
    
    await update.message.reply_text(
        f"✅ <b>PAYMENT SCREENSHOT RECEIVED!</b>\n\n"
        f"┌────────────────────────────┐\n"
        f"│ <b>ORDER #{order_id}</b>\n"
        f"├────────────────────────────┤\n"
        f"│ 📦 {product_name}\n"
        f"│ 📅 {duration_name}\n"
        f"│ 💰 ₹{amount}\n"
        f"│ ⏳ Status: PENDING\n"
        f"└────────────────────────────┘\n\n"
        f"Your order is waiting for admin approval.\n"
        f"You will receive your key once approved.\n\n"
        f"Use /myorders to check status.",
        parse_mode=ParseMode.HTML
    )
    
    caption = f"""
🔔 <b>NEW ORDER RECEIVED!</b>

┌────────────────────────────┐
│ <b>ORDER #{order_id}</b>
├────────────────────────────┤
│ 👤 {user.first_name}
│ 📱 @{user.username or 'No username'}
│ 🆔 <code>{user.id}</code>
│ 📦 {product_name}
│ 📅 {duration_name}
│ 💰 ₹{amount}
└────────────────────────────┘

Use /approve {order_id} &lt;key&gt; to approve
Use /reject {order_id} to reject
"""
    await context.bot.send_photo(OWNER_ID, photo=file_id, caption=caption, parse_mode=ParseMode.HTML)
    
    context.user_data['pending_product'] = None
    context.user_data['pending_duration'] = None

# ==================== OWNER COMMANDS ====================
async def addfolder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command.")
        return
    try:
        args = context.args
        if len(args) < 3:
            await update.message.reply_text("Usage: /addfolder <name> <display_name> <parent_id>\n\nExample: /addfolder vip_loader 'VIP Loader' 0")
            return
        name = args[0]
        display_name = args[1]
        parent_id = int(args[2])
        if add_folder(name, display_name, parent_id):
            await update.message.reply_text(f"✅ Folder added: {display_name}")
        else:
            await update.message.reply_text("❌ Folder name already exists!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def editfolder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command.")
        return
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Usage: /editfolder <folder_id> <new_display_name>")
            return
        folder_id = int(args[0])
        display_name = ' '.join(args[1:])
        update_folder(folder_id, display_name=display_name)
        await update.message.reply_text(f"✅ Folder #{folder_id} updated to: {display_name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def delfolder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command.")
        return
    try:
        args = context.args
        if len(args) < 1:
            await update.message.reply_text("Usage: /delfolder <folder_id>")
            return
        folder_id = int(args[0])
        delete_folder(folder_id)
        await update.message.reply_text(f"✅ Folder #{folder_id} deleted!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def addproduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command.")
        return
    try:
        args = context.args
        if len(args) < 7:
            await update.message.reply_text(
                "Usage: /addproduct <folder_id> <name> <display> <price1day> <price7days> <price30days> <pricefull>\n\n"
                "Example: /addproduct 1 bgmi_key 'BGMI Key' 100 500 1200 2500"
            )
            return
        folder_id = int(args[0])
        name = args[1]
        display_name = args[2]
        price_1day = float(args[3])
        price_7days = float(args[4])
        price_30days = float(args[5])
        price_full = float(args[6])
        if add_product(folder_id, name, display_name, price_1day, price_7days, price_30days, price_full):
            await update.message.reply_text(f"✅ Product added: {display_name}\nUse Admin Panel to upload APK file.")
        else:
            await update.message.reply_text("❌ Failed to add product!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def editproduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command.")
        return
    try:
        args = context.args
        if len(args) < 3:
            await update.message.reply_text("Usage: /editproduct <product_id> <duration> <new_price>\n\nDurations: 1day, 7days, 30days, full")
            return
        product_id = int(args[0])
        duration = args[1]
        price = float(args[2])
        update_product_price(product_id, duration, price)
        await update.message.reply_text(f"✅ Product #{product_id} {duration} price updated to ₹{price}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def delproduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command.")
        return
    try:
        args = context.args
        if len(args) < 1:
            await update.message.reply_text("Usage: /delproduct <product_id>")
            return
        product_id = int(args[0])
        delete_product(product_id)
        await update.message.reply_text(f"✅ Product #{product_id} deleted!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def addkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command.")
        return
    try:
        args = context.args
        if len(args) < 3:
            await update.message.reply_text(
                "Usage: /addkey <product_id> <duration> <key_value>\n\n"
                "Durations: 1day, 7days, 30days, full\n"
                "Example: /addkey 1 1day ABC123XYZ"
            )
            return
        product_id = int(args[0])
        duration = args[1]
        key_value = args[2]
        if add_key(key_value, product_id, duration):
            await update.message.reply_text(f"✅ Key added for product #{product_id} ({duration})")
        else:
            await update.message.reply_text("❌ Key already exists!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def listkeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command.")
        return
    try:
        args = context.args
        if len(args) < 1:
            await update.message.reply_text("Usage: /listkeys <product_id>")
            return
        product_id = int(args[0])
        keys = get_keys_for_product(product_id)
        if not keys:
            await update.message.reply_text(f"📭 No keys found for product #{product_id}")
            return
        text = f"🔑 <b>Keys for Product #{product_id}:</b>\n\n"
        available = 0
        used = 0
        for key in keys:
            key_value, duration, is_used, created = key
            status = "❌ Used" if is_used else "✅ Available"
            if is_used:
                used += 1
            else:
                available += 1
            text += f"<code>{key_value}</code> - {duration} - {status}\n"
        text += f"\n<b>Summary:</b> ✅ Available: {available} | ❌ Used: {used}"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command.")
        return
    orders = get_pending_orders()
    if not orders:
        await update.message.reply_text("📭 No pending orders!")
        return
    text = "📋 <b>PENDING ORDERS:</b>\n\n"
    for order in orders:
        order_id, user_id, username, first_name, product_name, duration, amount, screenshot, date = order
        duration_name = duration.replace('1day','1 Day').replace('7days','7 Days').replace('30days','30 Days').replace('full','Full Session')
        text += f"<b>Order #{order_id}</b>\n👤 {first_name} (@{username or 'No username'})\n🆔 <code>{user_id}</code>\n📦 {product_name} ({duration_name})\n💰 ₹{amount}\n📅 {date}\n\n/approve {order_id} &lt;key&gt;\n/reject {order_id}\n" + "─" * 30 + "\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command.")
        return
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Usage: /approve <order_id> <key>")
            return
        order_id = int(args[0])
        key = args[1]
        success, user_id, apk_file_id = approve_order(order_id, key)
        if success:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT product_name, duration FROM orders WHERE order_id = ?', (order_id,))
            order = cursor.fetchone()
            conn.close()
            if order:
                product_name, duration = order
                duration_name = duration.replace('1day','1 Day').replace('7days','7 Days').replace('30days','30 Days').replace('full','Full Session')
                message = (
                    f"✅ <b>ORDER APPROVED!</b>\n\n"
                    f"┌────────────────────────────┐\n"
                    f"│ <b>ORDER #{order_id}</b>\n"
                    f"├────────────────────────────┤\n"
                    f"│ 📦 {product_name}\n"
                    f"│ 📅 {duration_name}\n"
                    f"│ 🔑 <code>{key}</code>\n"
                )
                await context.bot.send_message(user_id, message, parse_mode=ParseMode.HTML)
                # Send APK file if exists
                if apk_file_id:
                    try:
                        await context.bot.send_document(user_id, apk_file_id, caption="📲 Download APK")
                    except Exception as e:
                        await context.bot.send_message(user_id, f"⚠️ Could not send APK file. Error: {e}")
                else:
                    await context.bot.send_message(user_id, "ℹ️ No APK file attached to this product.")
                await update.message.reply_text(f"✅ Order #{order_id} approved and key sent!")
            else:
                await update.message.reply_text(f"✅ Order #{order_id} approved!")
        else:
            await update.message.reply_text("❌ Failed to approve order!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this command.")
        return
    try:
        args = context.args
        if len(args) < 1:
            await update.message.reply_text("Usage: /reject <order_id>")
            return
        order_id = int(args[0])
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM orders WHERE order_id = ?', (order_id,))
        result = cursor.fetchone()
        conn.close()
        if result:
            user_id = result[0]
            reject_order(order_id)
            await context.bot.send_message(
                user_id,
                f"❌ <b>ORDER REJECTED</b>\n\nYour order #{order_id} has been rejected.\n\nPlease make a new payment and try again.\nUse /buy to purchase again.",
                parse_mode=ParseMode.HTML
            )
            await update.message.reply_text(f"✅ Order #{order_id} rejected and user notified.")
        else:
            await update.message.reply_text("❌ Order not found!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def myorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    orders = get_user_orders(user_id)
    if not orders:
        await update.message.reply_text("📭 <b>No Orders Found</b>\n\nUse /buy to make your first purchase!", parse_mode=ParseMode.HTML)
        return
    text = "📋 <b>Your Orders:</b>\n\n"
    for order in orders:
        order_id, product_name, duration, amount, status, key, date = order
        status_icons = {'pending': '⏳ Pending', 'pending_approval': '🔄 Waiting', 'approved': '✅ Approved', 'rejected': '❌ Rejected'}
        duration_name = duration.replace('1day','1 Day').replace('7days','7 Days').replace('30days','30 Days').replace('full','Full Session')
        status_text = status_icons.get(status, status.upper())
        text += f"<b>Order #{order_id}</b>\n📦 {product_name} ({duration_name})\n💰 ₹{amount}\n📊 {status_text}\n"
        if key:
            text += f"🔑 <code>{key}</code>\n"
        text += f"📅 {date}\n" + "─" * 20 + "\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = (update.effective_user.id == OWNER_ID)
    help_text = f"""
❓ <b>HELP & SUPPORT</b>

<b>User Commands:</b>
/start - Main menu
/buy - Browse products
/myorders - Check orders
/help - This help

<b>How to Purchase:</b>
1️⃣ Click "🛒 Buy Key"
2️⃣ Browse folders
3️⃣ Select product & duration
4️⃣ Scan QR or pay to UPI: <code>{UPI_ID}</code>
5️⃣ Send screenshot
6️⃣ Wait for approval
7️⃣ Get your key + APK file (if provided by admin)

<b>My Keys</b> - View all your approved keys
<b>Delete Key</b> - Request admin to delete a key
<b>Reset Key</b> - Request admin to reset a key
    """
    if is_admin:
        help_text += """
<b>Admin Commands:</b>
📁 <b>Folders</b>
/addfolder &lt;name&gt; &lt;display&gt; &lt;parent&gt;
/editfolder &lt;id&gt; &lt;display&gt;
/delfolder &lt;id&gt;

💰 <b>Products</b>
/addproduct &lt;folder_id&gt; &lt;name&gt; &lt;display&gt; &lt;p1&gt; &lt;p7&gt; &lt;p30&gt; &lt;pfull&gt;
/editproduct &lt;id&gt; &lt;duration&gt; &lt;price&gt;
/delproduct &lt;id&gt;
Use Admin Panel to upload/remove APK files.

🔑 <b>Keys</b>
/addkey &lt;product_id&gt; &lt;duration&gt; &lt;key&gt;
/listkeys &lt;product_id&gt;

📋 <b>Orders</b>
/pending
/approve &lt;order_id&gt; &lt;key&gt;
/reject &lt;order_id&gt;

📢 <b>Broadcast</b>
/broadcast &lt;message&gt;
Reply to a message and use /broadcast to forward it

📊 <b>Utilities</b>
/stats - Bot statistics
/export_users - Get CSV of all users
/backup - Download database backup
        """
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

# Broadcast commands
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can broadcast.")
        return
    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text("Usage: /broadcast <message> or reply to a message and use /broadcast")
        return
    
    if update.message.reply_to_message:
        original = update.message.reply_to_message
        users = get_all_users()
        sent = 0
        failed = 0
        for user_id, _, _, _, _ in users:
            try:
                await original.copy(user_id)
                sent += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1
        await update.message.reply_text(f"✅ Forwarded to {sent} users. Failed: {failed}")
    else:
        message_text = ' '.join(context.args)
        users = get_all_users()
        sent = 0
        failed = 0
        for user_id, _, _, _, _ in users:
            try:
                await context.bot.send_message(user_id, message_text, parse_mode=None, disable_web_page_preview=False)
                sent += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1
        await update.message.reply_text(f"✅ Broadcast sent to {sent} users. Failed: {failed}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner.")
        return
    total_users, total_orders, total_revenue = get_stats()
    await update.message.reply_text(f"📊 <b>Bot Statistics</b>\n\n👥 Total Users: {total_users}\n📦 Total Orders: {total_orders}\n💰 Total Revenue: ₹{total_revenue}", parse_mode=ParseMode.HTML)

async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner.")
        return
    users = get_all_users()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User ID", "Username", "First Name", "Join Date", "Total Spent"])
    writer.writerows(users)
    output.seek(0)
    await update.message.reply_document(document=InputFile(output, filename="users.csv"), caption="📋 User list")

async def backup_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner.")
        return
    with open(DB_FILE, "rb") as f:
        await update.message.reply_document(document=InputFile(f, filename="panel_bot_backup.db"), caption="💾 Database backup")

# ==================== HANDLE APK UPLOAD ====================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can upload APK files.")
        return
    
    product_id = context.user_data.get('upload_apk_for_product')
    if not product_id:
        await update.message.reply_text("❌ No product selected for APK upload. Use Admin Panel -> Manage Products -> Upload APK button first.")
        return
    
    document = update.message.document
    if not document:
        await update.message.reply_text("❌ Please send a valid document (APK file).")
        return
    
    file_id = document.file_id
    file_name = document.file_name or "app.apk"
    if not file_name.endswith('.apk'):
        await update.message.reply_text("⚠️ File does not have .apk extension. Still saving, but ensure it's an APK.")
    
    set_product_apk_file(product_id, file_id)
    await update.message.reply_text(f"✅ APK file '{file_name}' uploaded successfully for product ID {product_id}.")
    context.user_data['upload_apk_for_product'] = None

# ==================== MAIN ====================
def main():
    init_database()
    application = Application.builder().token(BOT_TOKEN).build()
    
    # User commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("buy", buy))
    application.add_handler(CommandHandler("myorders", myorders))
    application.add_handler(CommandHandler("help", help_command))
    
    # Admin commands
    application.add_handler(CommandHandler("addfolder", addfolder))
    application.add_handler(CommandHandler("editfolder", editfolder))
    application.add_handler(CommandHandler("delfolder", delfolder))
    application.add_handler(CommandHandler("addproduct", addproduct))
    application.add_handler(CommandHandler("editproduct", editproduct))
    application.add_handler(CommandHandler("delproduct", delproduct))
    application.add_handler(CommandHandler("addkey", addkey))
    application.add_handler(CommandHandler("listkeys", listkeys))
    application.add_handler(CommandHandler("pending", pending))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("reject", reject))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("export_users", export_users))
    application.add_handler(CommandHandler("backup", backup_db))
    
    # Handlers
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("🤖 Bot Started!")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"💰 UPI: {UPI_ID}")
    print("✅ APK link removed, replaced with file upload system.")
    
    application.run_polling()

if __name__ == "__main__":
    main()