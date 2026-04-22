import time
import telebot
import sqlite3
import random
import string
import threading
import requests
import os
import json
import base64
import csv
from io import StringIO
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

# ==================== CONFIG ====================

BOT_TOKEN = "8290734722:AAHk7uyZ7DgeeiJKYy7Zlp-sjblpClQNJAQ"
ADMIN_ID = 7655738256
PORT = int(os.environ.get("PORT", 5000))

# ⚠️ SIRF YAHAN APNA RENDER URL DALO ⚠️
MY_URL = "https://api-wd7m.onrender.com"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ==================== DATABASE ====================

def init_db():
    conn = sqlite3.connect("api_system.db", check_same_thread=False)
    cur = conn.cursor()
    
    # Users table - simple
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT UNIQUE,
        name TEXT,
        expiry TEXT,
        used INTEGER DEFAULT 0,
        limit_req INTEGER DEFAULT 100,
        notes TEXT,
        created_at TEXT,
        status TEXT DEFAULT 'active'
    )
    """)
    
    # Logs table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT,
        api_key TEXT,
        success INTEGER,
        data TEXT,
        timestamp TEXT
    )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database ready")

init_db()

# ==================== MAIN CLASS ====================

class APISystem:
    def get_db(self):
        return sqlite3.connect("api_system.db")
    
    def generate_key(self, name, days, limit_req, notes=""):
        """Generate API key"""
        random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=24))
        api_key = f"{name}_{random_part}"
        expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users(api_key, name, expiry, used, limit_req, notes, created_at, status)
            VALUES(?, ?, ?, 0, ?, ?, ?, 'active')
        """, (api_key, name, expiry, limit_req, notes, created_at))
        conn.commit()
        conn.close()
        return api_key
    
    def check_key(self, api_key):
        """Check if key is valid"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT name, expiry, used, limit_req, status FROM users WHERE api_key = ?", (api_key,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None, "INVALID_KEY"
        
        name, expiry, used, limit_req, status = row
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
        
        if datetime.now() > expiry_date:
            return None, "KEY_EXPIRED"
        if used >= limit_req:
            return None, "LIMIT_REACHED"
        if status != 'active':
            return None, "KEY_BLOCKED"
        
        return {'name': name, 'used': used, 'limit': limit_req, 'remaining': limit_req - used}, "ACTIVE"
    
    def use_key(self, api_key):
        """Increment usage"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET used = used + 1 WHERE api_key = ?", (api_key,))
        conn.commit()
        conn.close()
    
    def get_all_keys(self):
        """Get all keys"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT api_key, name, expiry, used, limit_req, notes, status, created_at FROM users ORDER BY created_at DESC")
        rows = cur.fetchall()
        conn.close()
        
        keys = []
        for row in rows:
            keys.append({
                'key': row[0],
                'name': row[1],
                'expiry': row[2],
                'used': row[3],
                'limit': row[4],
                'notes': row[5],
                'status': row[6],
                'created': row[7]
            })
        return keys
    
    def block_key(self, api_key):
        """Block a key"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'blocked' WHERE api_key = ?", (api_key,))
        conn.commit()
        conn.close()
    
    def unblock_key(self, api_key):
        """Unblock a key"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'active' WHERE api_key = ?", (api_key,))
        conn.commit()
        conn.close()
    
    def delete_key(self, api_key):
        """Delete a key"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE api_key = ?", (api_key,))
        conn.commit()
        conn.close()
    
    def extend_key(self, api_key, days):
        """Extend expiry"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT expiry FROM users WHERE api_key = ?", (api_key,))
        row = cur.fetchone()
        if row:
            new_expiry = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") + timedelta(days=days)
            cur.execute("UPDATE users SET expiry = ? WHERE api_key = ?", (new_expiry.strftime("%Y-%m-%d %H:%M:%S"), api_key))
            conn.commit()
            conn.close()
            return True
        conn.close()
        return False
    
    def get_stats(self):
        """Get system stats"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
        active = cur.fetchone()[0]
        cur.execute("SELECT SUM(used) FROM users")
        total_req = cur.fetchone()[0] or 0
        conn.close()
        return {'total': total, 'active': active, 'requests': total_req}
    
    def log_search(self, number, api_key, success, data=""):
        """Log search"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO logs(number, api_key, success, data, timestamp)
            VALUES(?, ?, ?, ?, ?)
        """, (number, api_key, 1 if success else 0, data[:500], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
    
    def get_logs(self, limit=50):
        """Get recent logs"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT number, api_key, success, timestamp FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        conn.close()
        return rows
    
    def export_keys_csv(self):
        """Export keys to CSV"""
        keys = self.get_all_keys()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['API Key', 'Name', 'Expiry', 'Used', 'Limit', 'Notes', 'Status', 'Created'])
        for key in keys:
            writer.writerow([key['key'], key['name'], key['expiry'], key['used'], key['limit'], key['notes'], key['status'], key['created']])
        return output.getvalue()

api = APISystem()

# ==================== API FUNCTIONS (AADHAAR, MOBILE, ETC) ====================

def search_aadhaar(number):
    """Aadhaar search - Replace with your actual API"""
    try:
        # Your Aadhaar API here
        # Example: response = requests.get(f"https://yourapi.com/aadhaar?number={number}")
        return {"name": "Test Name", "father": "Test Father", "address": "Test Address"}
    except:
        return None

def search_mobile(number):
    """Mobile search - Replace with your actual API"""
    try:
        # Your Mobile API here
        # Example: response = requests.get(f"https://yourapi.com/mobile?number={number}")
        return {"name": "Test User", "operator": "AIRTEL", "circle": "UP"}
    except:
        return None

def search_family(number):
    """Family search - Replace with your actual API"""
    try:
        # Your Family API here
        return {"members": ["Member1", "Member2"], "address": "Test Address"}
    except:
        return None

def search_telegram(number):
    """Telegram search - Replace with your actual API"""
    try:
        # Your Telegram API here
        return {"tg_id": number, "phone": "9876543210"}
    except:
        return None

# ==================== BOT COMMANDS ====================

def is_admin(user_id):
    return user_id == ADMIN_ID

@bot.message_handler(commands=['start'])
def start(msg):
    text = f"""
╔══════════════════════════════════════════════════╗
║           🤖 API MANAGEMENT SYSTEM               ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  🔑 KEY MANAGEMENT:                             ║
║  /genkey - Generate API key                     ║
║  /keys - List all keys                          ║
║  /info - Key details                            ║
║  /block - Block key                             ║
║  /unblock - Unblock key                         ║
║  /delete - Delete key                           ║
║  /extend - Extend expiry                        ║
║                                                  ║
║  🔍 SEARCH:                                     ║
║  /aadhaar 123456789012 - Aadhaar search         ║
║  /mobile 9876543210 - Mobile search             ║
║  /family 123456789012 - Family search           ║
║  /tg 123456789 - Telegram search                ║
║                                                  ║
║  📊 INFO:                                       ║
║  /stats - System statistics                     ║
║  /logs - Recent searches                         ║
║  /export - Export keys to CSV                   ║
║  /admin - Admin panel                           ║
║                                                  ║
║  📡 API: {MY_URL}/api?key=KEY&number=NUMBER      ║
║                                                  ║
╚══════════════════════════════════════════════════╝
"""
    bot.reply_to(msg, text)

@bot.message_handler(commands=['genkey'])
def genkey(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    try:
        parts = msg.text.split()
        if len(parts) < 4:
            bot.reply_to(msg, """
❌ GENERATE API KEY

Usage:
/genkey NAME DAYS LIMIT NOTES

Example:
/genkey Rahul_Client 30 500 "Business client"
/genkey Test_User 7 100 "Testing purpose"

Fields:
NAME - Key name (no spaces)
DAYS - Validity in days
LIMIT - Total requests allowed
NOTES - Optional description
""")
            return
        
        name = parts[1]
        days = int(parts[2])
        limit_req = int(parts[3])
        notes = ' '.join(parts[4:]) if len(parts) > 4 else ""
        
        api_key = api.generate_key(name, days, limit_req, notes)
        
        text = f"""
✅ API KEY GENERATED

━━━━━━━━━━━━━━━━━━━━━━━━━━
📛 NAME: {name}
🔑 KEY: {api_key}
📅 EXPIRY: {days} days
🔢 LIMIT: {limit_req} requests
📝 NOTES: {notes if notes else 'None'}
━━━━━━━━━━━━━━━━━━━━━━━━━━

📡 USE:
{MY_URL}/api?key={api_key}&number=9876543210

💡 SAVE THIS KEY!
"""
        bot.reply_to(msg, text)
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['keys'])
def list_keys(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    keys = api.get_all_keys()
    
    if not keys:
        bot.reply_to(msg, "❌ No keys found")
        return
    
    stats = api.get_stats()
    
    text = f"""
🔑 ALL API KEYS
━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 TOTAL: {stats['total']} keys
✅ ACTIVE: {stats['active']} keys
📈 REQUESTS: {stats['requests']}
━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
    
    for key in keys:
        expiry_date = datetime.strptime(key['expiry'], "%Y-%m-%d %H:%M:%S")
        days_left = (expiry_date - datetime.now()).days
        status_icon = "✅" if key['status'] == 'active' else "❌"
        
        text += f"{status_icon} {key['name']}\n"
        text += f"   📌 {key['key'][:35]}...\n"
        text += f"   📊 {key['used']}/{key['limit']} | ⏰ {days_left}d left\n\n"
    
    bot.reply_to(msg, text[:4000])

@bot.message_handler(commands=['info'])
def key_info(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = api.get_db()
        cur = conn.cursor()
        cur.execute("SELECT api_key, name, expiry, used, limit_req, notes, created_at, status FROM users WHERE api_key LIKE ? OR name LIKE ?", 
                   (f'%{search}%', f'%{search}%'))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            bot.reply_to(msg, "❌ Key not found")
            return
        
        key, name, expiry, used, limit_req, notes, created, status = row
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
        days_left = (expiry_date - datetime.now()).days
        percent = (used/limit_req*100) if limit_req > 0 else 0
        
        text = f"""
📊 KEY DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━

🔑 KEY: {key}
📛 NAME: {name}
🟢 STATUS: {status.upper()}

📅 CREATED: {created[:10]}
⏰ EXPIRY: {expiry[:10]} ({days_left} days left)

📊 USAGE: {used}/{limit_req} ({percent:.1f}%)

📝 NOTES: {notes if notes else 'None'}

━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 COMMANDS:
/block {key[:20]}...
/unblock {key[:20]}...
/extend {key[:20]}... 30
/delete {key[:20]}...
"""
        bot.reply_to(msg, text)
        
    except:
        bot.reply_to(msg, "❌ Usage: /info KEY_NAME_OR_KEY")

@bot.message_handler(commands=['block'])
def block_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = api.get_db()
        cur = conn.cursor()
        cur.execute("SELECT api_key, name FROM users WHERE api_key LIKE ? OR name LIKE ?", 
                   (f'%{search}%', f'%{search}%'))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            bot.reply_to(msg, "❌ Key not found")
            return
        
        api_key, name = row
        api.block_key(api_key)
        bot.reply_to(msg, f"✅ Key BLOCKED\n\nNAME: {name}\nKEY: {api_key[:30]}...")
        
    except:
        bot.reply_to(msg, "❌ Usage: /block KEY_NAME")

@bot.message_handler(commands=['unblock'])
def unblock_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = api.get_db()
        cur = conn.cursor()
        cur.execute("SELECT api_key, name FROM users WHERE api_key LIKE ? OR name LIKE ?", 
                   (f'%{search}%', f'%{search}%'))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            bot.reply_to(msg, "❌ Key not found")
            return
        
        api_key, name = row
        api.unblock_key(api_key)
        bot.reply_to(msg, f"✅ Key UNBLOCKED\n\nNAME: {name}\nKEY: {api_key[:30]}...")
        
    except:
        bot.reply_to(msg, "❌ Usage: /unblock KEY_NAME")

@bot.message_handler(commands=['delete'])
def delete_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = api.get_db()
        cur = conn.cursor()
        cur.execute("SELECT api_key, name FROM users WHERE api_key LIKE ? OR name LIKE ?", 
                   (f'%{search}%', f'%{search}%'))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            bot.reply_to(msg, "❌ Key not found")
            return
        
        api_key, name = row
        api.delete_key(api_key)
        bot.reply_to(msg, f"✅ Key DELETED\n\nNAME: {name}\nKEY: {api_key[:30]}...")
        
    except:
        bot.reply_to(msg, "❌ Usage: /delete KEY_NAME")

@bot.message_handler(commands=['extend'])
def extend_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    try:
        parts = msg.text.split()
        search = parts[1]
        days = int(parts[2]) if len(parts) > 2 else 30
        
        conn = api.get_db()
        cur = conn.cursor()
        cur.execute("SELECT api_key, name FROM users WHERE api_key LIKE ? OR name LIKE ?", 
                   (f'%{search}%', f'%{search}%'))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            bot.reply_to(msg, "❌ Key not found")
            return
        
        api_key, name = row
        if api.extend_key(api_key, days):
            bot.reply_to(msg, f"✅ Key extended by {days} days\n\nNAME: {name}")
        else:
            bot.reply_to(msg, "❌ Extension failed")
        
    except:
        bot.reply_to(msg, "❌ Usage: /extend KEY_NAME DAYS")

@bot.message_handler(commands=['stats'])
def show_stats(msg):
    stats = api.get_stats()
    keys = api.get_all_keys()
    
    expiring_soon = 0
    for key in keys:
        expiry_date = datetime.strptime(key['expiry'], "%Y-%m-%d %H:%M:%S")
        if (expiry_date - datetime.now()).days < 7:
            expiring_soon += 1
    
    text = f"""
📊 SYSTEM STATISTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━

🔑 KEYS:
├ TOTAL: {stats['total']}
├ ACTIVE: {stats['active']}
├ BLOCKED: {stats['total'] - stats['active']}
└ EXPIRING SOON: {expiring_soon}

📈 USAGE:
├ TOTAL REQUESTS: {stats['requests']}
└ AVG PER KEY: {stats['requests']/stats['total'] if stats['total'] > 0 else 0:.1f}

━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 SYSTEM: HEALTHY
📡 API: ACTIVE
💾 DATABASE: CONNECTED
"""
    bot.reply_to(msg, text)

@bot.message_handler(commands=['logs'])
def show_logs(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    logs = api.get_logs(30)
    
    if not logs:
        bot.reply_to(msg, "❌ No logs found")
        return
    
    text = "📜 RECENT LOGS\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for log in logs:
        number, api_key, success, timestamp = log
        icon = "✅" if success else "❌"
        text += f"{icon} {number}\n"
        text += f"   🔑 {api_key[:25]}...\n"
        text += f"   ⏰ {timestamp[:16]}\n\n"
    
    bot.reply_to(msg, text[:4000])

@bot.message_handler(commands=['export'])
def export_keys(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    csv_data = api.export_keys_csv()
    filename = f"keys_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    bot.send_document(msg.chat.id, 
                     (filename, csv_data.encode('utf-8')),
                     caption=f"📊 Total keys exported")

@bot.message_handler(commands=['admin'])
def admin_panel(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    stats = api.get_stats()
    
    text = f"""
🔐 ADMIN PANEL
━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 QUICK STATS:
├ KEYS: {stats['total']}
├ ACTIVE: {stats['active']}
└ REQUESTS: {stats['requests']}

🔧 QUICK ACTIONS:
/genkey - New key
/keys - List keys
/stats - Full stats
/logs - View logs
/export - Export data

📡 API STATUS:
URL: {MY_URL}/api
HEALTH: {MY_URL}/health

💡 TIPS:
• Block abuse with /block
• Extend keys with /extend
• Export data monthly
"""
    bot.reply_to(msg, text)

# ==================== SEARCH COMMANDS ====================

@bot.message_handler(commands=['aadhaar'])
def aadhaar_search(msg):
    try:
        number = msg.text.split()[1]
        if len(number) != 12 or not number.isdigit():
            bot.reply_to(msg, "❌ Invalid Aadhaar! Enter 12 digits.")
            return
        
        bot.reply_to(msg, f"🔍 Searching Aadhaar: {number}...")
        
        # Check API key from user (optional - if you want to track)
        # For now, just search
        
        result = search_aadhaar(number)
        
        if result:
            text = f"""
✅ AADHAAR DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━
📛 NAME: {result.get('name', 'N/A')}
👨 FATHER: {result.get('father', 'N/A')}
📍 ADDRESS: {result.get('address', 'N/A')}
━━━━━━━━━━━━━━━━━━━━━━━━━━
💳 Powered by @Danger_devil1917
"""
            bot.reply_to(msg, text)
            api.log_search(number, "BOT_SEARCH", True, json.dumps(result))
        else:
            bot.reply_to(msg, "❌ No data found")
            api.log_search(number, "BOT_SEARCH", False)
            
    except:
        bot.reply_to(msg, "❌ Usage: /aadhaar 123456789012")

@bot.message_handler(commands=['mobile'])
def mobile_search(msg):
    try:
        number = msg.text.split()[1]
        if len(number) != 10 or not number.isdigit():
            bot.reply_to(msg, "❌ Invalid mobile! Enter 10 digits.")
            return
        
        bot.reply_to(msg, f"🔍 Searching Mobile: {number}...")
        
        result = search_mobile(number)
        
        if result:
            text = f"""
✅ MOBILE DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━
📛 NAME: {result.get('name', 'N/A')}
📡 OPERATOR: {result.get('operator', 'N/A')}
📍 CIRCLE: {result.get('circle', 'N/A')}
━━━━━━━━━━━━━━━━━━━━━━━━━━
💳 Powered by @Danger_devil1917
"""
            bot.reply_to(msg, text)
            api.log_search(number, "BOT_SEARCH", True, json.dumps(result))
        else:
            bot.reply_to(msg, "❌ No data found")
            api.log_search(number, "BOT_SEARCH", False)
            
    except:
        bot.reply_to(msg, "❌ Usage: /mobile 9876543210")

@bot.message_handler(commands=['family'])
def family_search(msg):
    try:
        number = msg.text.split()[1]
        bot.reply_to(msg, f"🔍 Searching Family: {number}...")
        
        result = search_family(number)
        
        if result:
            text = f"""
✅ FAMILY DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 MEMBERS: {', '.join(result.get('members', ['N/A']))}
📍 ADDRESS: {result.get('address', 'N/A')}
━━━━━━━━━━━━━━━━━━━━━━━━━━
💳 Powered by @Danger_devil1917
"""
            bot.reply_to(msg, text)
            api.log_search(number, "BOT_SEARCH", True, json.dumps(result))
        else:
            bot.reply_to(msg, "❌ No data found")
            api.log_search(number, "BOT_SEARCH", False)
            
    except:
        bot.reply_to(msg, "❌ Usage: /family 123456789012")

@bot.message_handler(commands=['tg'])
def tg_search(msg):
    try:
        number = msg.text.split()[1]
        bot.reply_to(msg, f"🔍 Searching Telegram: {number}...")
        
        result = search_telegram(number)
        
        if result:
            text = f"""
✅ TELEGRAM DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━
🆔 TG ID: {result.get('tg_id', 'N/A')}
📱 PHONE: {result.get('phone', 'N/A')}
━━━━━━━━━━━━━━━━━━━━━━━━━━
💳 Powered by @Danger_devil1917
"""
            bot.reply_to(msg, text)
            api.log_search(number, "BOT_SEARCH", True, json.dumps(result))
        else:
            bot.reply_to(msg, "❌ No data found")
            api.log_search(number, "BOT_SEARCH", False)
            
    except:
        bot.reply_to(msg, "❌ Usage: /tg 123456789")

# ==================== API ENDPOINTS ====================

@app.route("/api", methods=['GET', 'POST'])
def api_endpoint():
    """Main API endpoint"""
    if request.method == 'GET':
        api_key = request.args.get("key")
        number = request.args.get("number")
    else:
        data = request.get_json()
        api_key = data.get("key") if data else None
        number = data.get("number") if data else None
    
    if not api_key:
        return jsonify({"error": "API key required"})
    
    if not number:
        return jsonify({"error": "Number required"})
    
    # Check key
    key_info, status = api.check_key(api_key)
    
    if not key_info:
        return jsonify({"error": status})
    
    # Use the key
    api.use_key(api_key)
    
    # Search based on number length
    if len(number) == 12 and number.isdigit():
        result = search_aadhaar(number)
        search_type = "aadhaar"
    elif len(number) == 10 and number.isdigit():
        result = search_mobile(number)
        search_type = "mobile"
    else:
        result = search_telegram(number)
        search_type = "telegram"
    
    if result:
        api.log_search(number, api_key, True, json.dumps(result))
        return jsonify({
            "success": True,
            "number": number,
            "type": search_type,
            "data": result,
            "key_info": key_info
        })
    else:
        api.log_search(number, api_key, False)
        return jsonify({
            "success": False,
            "error": "No data found"
        })

@app.route("/health", methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0"
    })

@app.route("/stats", methods=['GET'])
def stats_endpoint():
    stats = api.get_stats()
    return jsonify(stats)

@app.route("/", methods=['GET'])
def home():
    return jsonify({
        "service": "API Management System",
        "status": "running",
        "endpoints": {
            "/api": "Main API",
            "/health": "Health check",
            "/stats": "Statistics"
        }
    })

# ==================== KEEP ALIVE ====================

def keep_alive():
    """Keep the bot alive on Render"""
    while True:
        try:
            requests.get(f"{MY_URL}/health", timeout=10)
            print(f"✅ Keep-alive ping sent")
        except:
            pass
        time.sleep(270)

# ==================== MAIN ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 API MANAGEMENT SYSTEM STARTING")
    print("=" * 50)
    print(f"✅ Bot running")
    print(f"✅ API on port {PORT}")
    print(f"✅ Admin ID: {ADMIN_ID}")
    print(f"✅ URL: {MY_URL}")
    print("=" * 50)
    
    # Start keep alive
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start bot
    def run_bot():
        bot.infinity_polling(timeout=60)
    
    threading.Thread(target=run_bot, daemon=True).start()
    
    # Run Flask
    app.run(host="0.0.0.0", port=PORT)