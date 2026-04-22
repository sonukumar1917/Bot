import time
import telebot
import sqlite3
import random
import string
import threading
import requests
import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

# ==================== CONFIG ====================

BOT_TOKEN = "8290734722:AAHk7uyZ7DgeeiJKYy7Zlp-sjblpClQNJAQ"
ADMIN_ID = 7655738256
PORT = int(os.environ.get("PORT", 5000))
MY_URL = os.environ.get("RENDER_URL", "https://api-wd7m.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ==================== REAL APIS (YAHI DALO) ====================

REAL_APIS = {
    "mobile": [    
        {"name": "MobileAPI1", "url": "https://ownerjii-api-ayno.vercel.app/api/info?number={number}", "working": True},
    ],
    "aadhaar": [
        {"name": "AadhaarAPI1", "url": "https://devil.elementfx.com/api.php?key=DANGER&type=aadhaar_info&term={number}", "working": True},
    ],
    "family": [
        {"name": "FamilyAPI1", "url": "https://devil.elementfx.com/api.php?key=DANGER&type=id_family&term={number}", "working": True},
    ],
    "telegram": [
        {"name": "TelegramAPI1", "url": "https://devil.elementfx.com/api.php?key=SONU&type=tg_number&term={number}", "working": True},
    ]
}

# ==================== DATABASE ====================

def init_db():
    conn = sqlite3.connect("api_system.db", check_same_thread=False)
    cur = conn.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT UNIQUE,
        name TEXT,
        expiry TEXT,
        used INTEGER DEFAULT 0,
        limit_req INTEGER DEFAULT 100,
        allowed_types TEXT DEFAULT 'all',
        created_at TEXT,
        status TEXT DEFAULT 'active'
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT,
        search_type TEXT,
        number TEXT,
        success INTEGER,
        response TEXT,
        timestamp TEXT
    )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database ready")

init_db()

# ==================== FUNCTIONS ====================

def call_real_api(number, api_type):
    """Call real APIs and get data"""
    
    if api_type not in REAL_APIS:
        return None, "No API found for this type"
    
    for api in REAL_APIS[api_type]:
        if not api['working']:
            continue
        
        url = api['url'].format(number=number)
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if data is valid
                if data and data != {} and data != {"error": "Not found"}:
                    print(f"✅ {api['name']} success for {number}")
                    return data, api['name']
                    
        except Exception as e:
            print(f"❌ {api['name']} failed: {str(e)[:50]}")
            continue
    
    return None, "All APIs failed"

def format_response(data, api_type, api_name):
    """Format data beautifully"""
    
    if not data:
        return "❌ No data found"
    
    lines = []
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📡 {api_type.upper()} REPORT")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"👑 Provider : @Danger_devil1917")
    lines.append(f"📡 API Used : {api_name}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    if isinstance(data, dict):
        # Check if data has results or records
        if "results" in data:
            for idx, record in enumerate(data["results"], 1):
                lines.append(f"┌── 📍 RECORD {idx} ──")
                for key, value in record.items():
                    if value and str(value) not in ['null', 'None', '']:
                        lines.append(f"│ {key.upper()}: {value}")
                lines.append("└──────────────────────────────────────────────────")
                lines.append("")
        elif "result" in data:
            for key, value in data["result"].items():
                if value and str(value) not in ['null', 'None', '']:
                    lines.append(f"│ {key.upper()}: {value}")
        else:
            for key, value in data.items():
                if key not in ['status', 'message']:
                    if value and str(value) not in ['null', 'None', '']:
                        lines.append(f"│ {key.upper()}: {value}")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💳 Powered by @Danger_devil1917")
    
    return "\n".join(lines)

def generate_key(name, days, limit_req, allowed_types):
    random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    api_key = f"{name}_{random_part}"
    expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect("api_system.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users(api_key, name, expiry, used, limit_req, allowed_types, created_at, status)
        VALUES(?, ?, ?, 0, ?, ?, ?, 'active')
    """, (api_key, name, expiry, limit_req, allowed_types, created_at))
    conn.commit()
    conn.close()
    return api_key

def check_key(api_key, req_type):
    conn = sqlite3.connect("api_system.db")
    cur = conn.cursor()
    cur.execute("SELECT name, expiry, used, limit_req, allowed_types, status FROM users WHERE api_key = ?", (api_key,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return None, "INVALID_KEY"
    
    name, expiry, used, limit_req, allowed_types, status = row
    expiry_date = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
    
    if datetime.now() > expiry_date:
        return None, "KEY_EXPIRED"
    if used >= limit_req:
        return None, "LIMIT_REACHED"
    if status != 'active':
        return None, "KEY_BLOCKED"
    
    if allowed_types != 'all' and req_type not in allowed_types.split(','):
        return None, f"NO_ACCESS_TO_{req_type}"
    
    return {'name': name, 'used': used, 'limit': limit_req, 'remaining': limit_req - used, 'allowed': allowed_types}, "ACTIVE"

def use_key(api_key):
    conn = sqlite3.connect("api_system.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET used = used + 1 WHERE api_key = ?", (api_key,))
    conn.commit()
    conn.close()

def log_search(api_key, search_type, number, success, response=""):
    conn = sqlite3.connect("api_system.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO logs(api_key, search_type, number, success, response, timestamp)
        VALUES(?, ?, ?, ?, ?, ?)
    """, (api_key, search_type, number, 1 if success else 0, response[:500], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def is_admin(user_id):
    return user_id == ADMIN_ID

# ==================== BOT COMMANDS ====================

@bot.message_handler(commands=['start'])
def start(msg):
    text = f"""
╔══════════════════════════════════════════════════════════════╗
║              🔥 REAL API MANAGEMENT SYSTEM                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  🔑 GENERATE API KEY:                                       ║
║  /genkey NAME DAYS LIMIT TYPES                              ║
║                                                              ║
║  EXAMPLES:                                                  ║
║  /genkey Client1 30 500 aadhaar,mobile                      ║
║  /genkey Client2 7 100 all                                  ║
║  /genkey Client3 90 1000 family,telegram                    ║
║                                                              ║
║  TYPES: aadhaar, mobile, family, telegram, all              ║
║                                                              ║
║  🔍 SEARCH (KEY LAGAO):                                     ║
║  /aadhaar KEY NUMBER                                        ║
║  /mobile KEY NUMBER                                         ║
║  /family KEY NUMBER                                         ║
║  /tg KEY NUMBER                                             ║
║                                                              ║
║  📋 MANAGE KEYS:                                            ║
║  /keys - List all keys                                      ║
║  /info KEY - Key details                                    ║
║  /block KEY - Block key                                     ║
║  /unblock KEY - Unblock key                                 ║
║  /delete KEY - Delete key                                   ║
║  /extend KEY DAYS - Extend expiry                           ║
║                                                              ║
║  📊 INFO:                                                   ║
║  /stats - System stats                                      ║
║  /logs - Recent searches                                    ║
║  /admin - Admin panel                                       ║
║                                                              ║
║  📡 API ENDPOINT:                                           ║
║  {MY_URL}/api?key=KEY&number=NUMBER&type=TYPE               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    bot.reply_to(msg, text)

@bot.message_handler(commands=['genkey'])
def genkey(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    try:
        parts = msg.text.split()
        if len(parts) < 5:
            bot.reply_to(msg, """
❌ USAGE:
/genkey NAME DAYS LIMIT TYPES

EXAMPLES:
/genkey Client1 30 500 aadhaar,mobile
/genkey Client2 7 100 all
/genkey Client3 90 1000 family,telegram

TYPES: aadhaar, mobile, family, telegram, all
""")
            return
        
        name = parts[1]
        days = int(parts[2])
        limit_req = int(parts[3])
        allowed_types = parts[4]
        
        api_key = generate_key(name, days, limit_req, allowed_types)
        
        text = f"""
✅ API KEY GENERATED
━━━━━━━━━━━━━━━━━━━━━━━━━━
📛 NAME: {name}
🔑 KEY: {api_key}
📅 EXPIRY: {days} days
🔢 LIMIT: {limit_req} requests
🏷️ ACCESS: {allowed_types.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 SEARCH COMMANDS:
/aadhaar {api_key} 123456789012
/mobile {api_key} 9876543210
/family {api_key} 123456789012
/tg {api_key} 123456789

📡 API: {MY_URL}/api?key={api_key}&number=9876543210&type=mobile

💡 SAVE THIS KEY!
"""
        bot.reply_to(msg, text)
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['aadhaar'])
def aadhaar_search(msg):
    try:
        parts = msg.text.split()
        if len(parts) < 3:
            bot.reply_to(msg, "❌ Usage: /aadhaar API_KEY 12_DIGIT_NUMBER\n\nExample: /aadhaar YourKey 123456789012")
            return
        
        api_key = parts[1]
        number = parts[2]
        
        if len(number) != 12 or not number.isdigit():
            bot.reply_to(msg, "❌ Invalid Aadhaar! Enter 12 digits.")
            return
        
        key_info, status = check_key(api_key, "aadhaar")
        
        if not key_info:
            if status == "INVALID_KEY":
                bot.reply_to(msg, "❌ Invalid API key")
            elif status == "KEY_EXPIRED":
                bot.reply_to(msg, "❌ Key expired on " + datetime.now().strftime("%Y-%m-%d"))
            elif status == "LIMIT_REACHED":
                bot.reply_to(msg, "❌ Request limit reached")
            elif status == "KEY_BLOCKED":
                bot.reply_to(msg, "❌ Key is blocked")
            elif "NO_ACCESS" in status:
                bot.reply_to(msg, f"❌ This key cannot access aadhaar. Allowed: {key_info['allowed'] if key_info else 'unknown'}")
            else:
                bot.reply_to(msg, f"❌ {status}")
            return
        
        bot.reply_to(msg, f"🔍 Searching Aadhaar: {number}...")
        
        result, api_used = call_real_api(number, "aadhaar")
        
        if result:
            use_key(api_key)
            log_search(api_key, "aadhaar", number, True, json.dumps(result)[:500])
            
            formatted = format_response(result, "AADHAAR", api_used)
            formatted += f"\n\n📊 Remaining: {key_info['remaining'] - 1}/{key_info['limit']}"
            
            bot.reply_to(msg, formatted)
        else:
            log_search(api_key, "aadhaar", number, False)
            bot.reply_to(msg, f"❌ No Aadhaar data found for {number}\n\n📊 Remaining: {key_info['remaining']}/{key_info['limit']}")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['mobile'])
def mobile_search(msg):
    try:
        parts = msg.text.split()
        if len(parts) < 3:
            bot.reply_to(msg, "❌ Usage: /mobile API_KEY 10_DIGIT_NUMBER\n\nExample: /mobile YourKey 9876543210")
            return
        
        api_key = parts[1]
        number = parts[2]
        
        if len(number) != 10 or not number.isdigit():
            bot.reply_to(msg, "❌ Invalid mobile! Enter 10 digits.")
            return
        
        key_info, status = check_key(api_key, "mobile")
        
        if not key_info:
            bot.reply_to(msg, f"❌ {status}")
            return
        
        bot.reply_to(msg, f"🔍 Searching Mobile: {number}...")
        
        result, api_used = call_real_api(number, "mobile")
        
        if result:
            use_key(api_key)
            log_search(api_key, "mobile", number, True, json.dumps(result)[:500])
            
            formatted = format_response(result, "MOBILE", api_used)
            formatted += f"\n\n📊 Remaining: {key_info['remaining'] - 1}/{key_info['limit']}"
            
            bot.reply_to(msg, formatted)
        else:
            log_search(api_key, "mobile", number, False)
            bot.reply_to(msg, f"❌ No mobile data found for {number}\n\n📊 Remaining: {key_info['remaining']}/{key_info['limit']}")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['family'])
def family_search(msg):
    try:
        parts = msg.text.split()
        if len(parts) < 3:
            bot.reply_to(msg, "❌ Usage: /family API_KEY 12_DIGIT_NUMBER\n\nExample: /family YourKey 123456789012")
            return
        
        api_key = parts[1]
        number = parts[2]
        
        key_info, status = check_key(api_key, "family")
        
        if not key_info:
            bot.reply_to(msg, f"❌ {status}")
            return
        
        bot.reply_to(msg, f"🔍 Searching Family: {number}...")
        
        result, api_used = call_real_api(number, "family")
        
        if result:
            use_key(api_key)
            log_search(api_key, "family", number, True, json.dumps(result)[:500])
            
            formatted = format_response(result, "FAMILY", api_used)
            formatted += f"\n\n📊 Remaining: {key_info['remaining'] - 1}/{key_info['limit']}"
            
            bot.reply_to(msg, formatted)
        else:
            log_search(api_key, "family", number, False)
            bot.reply_to(msg, f"❌ No family data found for {number}\n\n📊 Remaining: {key_info['remaining']}/{key_info['limit']}")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['tg'])
def tg_search(msg):
    try:
        parts = msg.text.split()
        if len(parts) < 3:
            bot.reply_to(msg, "❌ Usage: /tg API_KEY TELEGRAM_ID\n\nExample: /tg YourKey 123456789")
            return
        
        api_key = parts[1]
        number = parts[2]
        
        key_info, status = check_key(api_key, "telegram")
        
        if not key_info:
            bot.reply_to(msg, f"❌ {status}")
            return
        
        bot.reply_to(msg, f"🔍 Searching Telegram: {number}...")
        
        result, api_used = call_real_api(number, "telegram")
        
        if result:
            use_key(api_key)
            log_search(api_key, "telegram", number, True, json.dumps(result)[:500])
            
            formatted = format_response(result, "TELEGRAM", api_used)
            formatted += f"\n\n📊 Remaining: {key_info['remaining'] - 1}/{key_info['limit']}"
            
            bot.reply_to(msg, formatted)
        else:
            log_search(api_key, "telegram", number, False)
            bot.reply_to(msg, f"❌ No telegram data found for {number}\n\n📊 Remaining: {key_info['remaining']}/{key_info['limit']}")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['keys'])
def list_keys(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    conn = sqlite3.connect("api_system.db")
    cur = conn.cursor()
    cur.execute("SELECT api_key, name, expiry, used, limit_req, allowed_types, status FROM users ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(msg, "❌ No keys found")
        return
    
    text = "🔑 ALL API KEYS\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for row in rows:
        key, name, expiry, used, limit_req, types, status = row
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
        days_left = (expiry_date - datetime.now()).days
        status_icon = "✅" if status == 'active' else "❌"
        
        text += f"{status_icon} {name}\n"
        text += f"   📌 {key[:99]}...\n"
        text += f"   🏷️ {types.upper()} | 📊 {used}/{limit_req} | ⏰ {days_left}d left\n\n"
    
    bot.reply_to(msg, text[:4000])

@bot.message_handler(commands=['info'])
def key_info(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = sqlite3.connect("api_system.db")
        cur = conn.cursor()
        cur.execute("SELECT api_key, name, expiry, used, limit_req, allowed_types, created_at, status FROM users WHERE api_key LIKE ? OR name LIKE ?", 
                   (f'%{search}%', f'%{search}%'))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            bot.reply_to(msg, "❌ Key not found")
            return
        
        key, name, expiry, used, limit_req, types, created, status = row
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
        days_left = (expiry_date - datetime.now()).days
        
        text = f"""
📊 KEY DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━

🔑 KEY: {key}
📛 NAME: {name}
🟢 STATUS: {status.upper()}
🏷️ ACCESS: {types.upper()}

📅 CREATED: {created[:10]}
⏰ EXPIRY: {expiry[:10]} ({days_left} days left)

📊 USAGE: {used}/{limit_req} ({used/limit_req*100:.1f}%)

━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 COMMANDS:
/block {key[:20]}
/unblock {key[:20]}
/extend {key[:20]} 30
/delete {key[:20]}
"""
        bot.reply_to(msg, text)
        
    except:
        bot.reply_to(msg, "❌ Usage: /info KEY_NAME")

@bot.message_handler(commands=['block'])
def block_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = sqlite3.connect("api_system.db")
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'blocked' WHERE api_key LIKE ? OR name LIKE ?", (f'%{search}%', f'%{search}%'))
        conn.commit()
        conn.close()
        
        bot.reply_to(msg, f"✅ Key blocked: {search}")
    except:
        bot.reply_to(msg, "❌ Usage: /block KEY_NAME")

@bot.message_handler(commands=['unblock'])
def unblock_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = sqlite3.connect("api_system.db")
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'active' WHERE api_key LIKE ? OR name LIKE ?", (f'%{search}%', f'%{search}%'))
        conn.commit()
        conn.close()
        
        bot.reply_to(msg, f"✅ Key unblocked: {search}")
    except:
        bot.reply_to(msg, "❌ Usage: /unblock KEY_NAME")

@bot.message_handler(commands=['delete'])
def delete_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = sqlite3.connect("api_system.db")
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE api_key LIKE ? OR name LIKE ?", (f'%{search}%', f'%{search}%'))
        conn.commit()
        conn.close()
        
        bot.reply_to(msg, f"✅ Key deleted: {search}")
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
        
        conn = sqlite3.connect("api_system.db")
        cur = conn.cursor()
        cur.execute("SELECT expiry FROM users WHERE api_key LIKE ? OR name LIKE ?", (f'%{search}%', f'%{search}%'))
        row = cur.fetchone()
        
        if row:
            new_expiry = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") + timedelta(days=days)
            cur.execute("UPDATE users SET expiry = ? WHERE api_key LIKE ? OR name LIKE ?", 
                       (new_expiry.strftime("%Y-%m-%d %H:%M:%S"), f'%{search}%', f'%{search}%'))
            conn.commit()
            bot.reply_to(msg, f"✅ Key extended by {days} days")
        else:
            bot.reply_to(msg, "❌ Key not found")
        
        conn.close()
    except:
        bot.reply_to(msg, "❌ Usage: /extend KEY_NAME DAYS")

@bot.message_handler(commands=['stats'])
def show_stats(msg):
    conn = sqlite3.connect("api_system.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
    active = cur.fetchone()[0]
    cur.execute("SELECT SUM(used) FROM users")
    total_req = cur.fetchone()[0] or 0
    conn.close()
    
    text = f"""
📊 SYSTEM STATISTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━

🔑 KEYS:
├ TOTAL: {total}
├ ACTIVE: {active}
└ TOTAL REQUESTS: {total_req}

📡 REAL APIS:
├ MOBILE: {len(REAL_APIS.get('mobile', []))} APIs
├ AADHAAR: {len(REAL_APIS.get('aadhaar', []))} APIs
├ FAMILY: {len(REAL_APIS.get('family', []))} APIs
└ TELEGRAM: {len(REAL_APIS.get('telegram', []))} APIs

━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 SYSTEM: HEALTHY
📡 BOT: RUNNING
💾 DATABASE: CONNECTED
"""
    bot.reply_to(msg, text)

@bot.message_handler(commands=['logs'])
def show_logs(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    conn = sqlite3.connect("api_system.db")
    cur = conn.cursor()
    cur.execute("SELECT api_key, search_type, number, success, timestamp FROM logs ORDER BY timestamp DESC LIMIT 30")
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(msg, "❌ No logs found")
        return
    
    text = "📜 RECENT SEARCHES\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for row in rows:
        api_key, search_type, number, success, timestamp = row
        icon = "✅" if success else "❌"
        text += f"{icon} {search_type.upper()} - {number}\n"
        text += f"   🔑 {api_key[:99]}...\n"
        text += f"   ⏰ {timestamp[:16]}\n\n"
    
    bot.reply_to(msg, text[:4000])

@bot.message_handler(commands=['admin'])
def admin_panel(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    
    conn = sqlite3.connect("api_system.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
    active = cur.fetchone()[0]
    conn.close()
    
    text = f"""
🔐 ADMIN PANEL
━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 STATS:
├ KEYS: {total}
├ ACTIVE: {active}
└ APIS: {len(REAL_APIS)} types

🔧 QUICK ACTIONS:

🔑 KEY MANAGEMENT:
/genkey - Generate key
/keys - List keys
/block - Block key
/unblock - Unblock key
/extend - Extend expiry
/delete - Delete key

🔍 SEARCH COMMANDS:
/aadhaar KEY NUMBER
/mobile KEY NUMBER
/family KEY NUMBER
/tg KEY NUMBER

📡 API: {MY_URL}/api?key=KEY&number=NUMBER&type=TYPE
"""
    bot.reply_to(msg, text)

# ==================== API ENDPOINT ====================

@app.route("/api", methods=['GET'])
def api_endpoint():
    api_key = request.args.get("key")
    number = request.args.get("number")
    api_type = request.args.get("type", "mobile")
    
    if not api_key:
        return jsonify({"error": "API key required"})
    
    if not number:
        return jsonify({"error": "Number required"})
    
    if api_type not in ['aadhaar', 'mobile', 'family', 'telegram']:
        return jsonify({"error": "Invalid type. Use: aadhaar, mobile, family, telegram"})
    
    key_info, status = check_key(api_key, api_type)
    
    if not key_info:
        return jsonify({"error": status})
    
    result, api_used = call_real_api(number, api_type)
    
    if result:
        use_key(api_key)
        log_search(api_key, api_type, number, True, json.dumps(result)[:500])
        
        return jsonify({
            "success": True,
            "key": key_info['name'],
            "remaining": key_info['remaining'] - 1,
            "limit": key_info['limit'],
            "type": api_type,
            "api_used": api_used,
            "data": result
        })
    else:
        log_search(api_key, api_type, number, False)
        return jsonify({"success": False, "error": "No data found"})

@app.route("/health", methods=['GET'])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route("/", methods=['GET'])
def home():
    return jsonify({"service": "API Management System", "status": "running"})

# ==================== KEEP ALIVE ====================

def keep_alive():
    while True:
        try:
            requests.get(f"{MY_URL}/health", timeout=10)
        except:
            pass
        time.sleep(270)

# ==================== MAIN ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🔥 REAL API SYSTEM STARTING")
    print("=" * 50)
    print("✅ REAL APIS LOADED:")
    for k, v in REAL_APIS.items():
        print(f"   📡 {k.upper()}: {len(v)} APIs")
    print(f"✅ Bot running")
    print(f"✅ API on port {PORT}")
    print("=" * 50)
    
    threading.Thread(target=keep_alive, daemon=True).start()
    
    def run_bot():
        bot.infinity_polling(timeout=60)
    
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)