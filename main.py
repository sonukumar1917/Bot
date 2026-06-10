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

BOT_TOKEN = "8602100882:AAFh51ivsoHpdrLPyUbAvtNl5w9tdzKSlYo"
ADMIN_ID = 8406324025
PORT = int(os.environ.get("PORT", 5000))
MY_URL = os.environ.get("RENDER_URL", "https://api-wd7m.onrender.com")
APIS_CONFIG_FILE = "apis_config.json"
REPLACE_RULES_FILE = "replace_rules.json"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ==================== DYNAMIC REPLACE RULES ====================

def load_replace_rules():
    if os.path.exists(REPLACE_RULES_FILE):
        try:
            with open(REPLACE_RULES_FILE, 'r') as f:
                rules = json.load(f)
                print("✅ Replace rules loaded")
                return rules
        except:
            pass
    default = {}   # empty by default, you can add your own later via bot
    save_replace_rules(default)
    return default

def save_replace_rules(rules):
    try:
        with open(REPLACE_RULES_FILE, 'w') as f:
            json.dump(rules, f, indent=4)
        return True
    except:
        return False

REPLACE_RULES = load_replace_rules()

def apply_replace_rules(obj):
    """Recursively apply all find/replace rules to strings in obj"""
    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            new_key = apply_replace_rules(k)
            new_dict[new_key] = apply_replace_rules(v)
        return new_dict
    elif isinstance(obj, list):
        return [apply_replace_rules(item) for item in obj]
    elif isinstance(obj, str):
        for find, replace in REPLACE_RULES.items():
            obj = obj.replace(find, replace)
        return obj
    else:
        return obj

# ==================== DYNAMIC API STORAGE ====================

DEFAULT_APIS = {
    "mobile": [    
        {"name": "MobileAPI1", "url": "https://ownerjii-api-ayno.vercel.app/api/info?number={number}", "working": True},
    ],
    "aadhaar": [
        {"name": "AadhaarAPI1", "url": "https://devil.elementfx.com/api.php?key=DANGER&type=aadhaar_info&term={number}", "working": True},
    ],
    "family": [
        {"name": "FamilyAPI1", "url": "https://atof.onrender.com/full-search?aadhaar={number}", "working": True},
    ],
    "telegram": [
        {"name": "TelegramAPI1", "url": "https://abhigyan-codes-tg-to-number-api.onrender.com/@abhigyan_codes/userid={number}", "working": True},
    ]
}

def load_apis():
    if os.path.exists(APIS_CONFIG_FILE):
        try:
            with open(APIS_CONFIG_FILE, 'r') as f:
                apis = json.load(f)
                print("✅ APIs loaded from config file")
                return apis
        except Exception as e:
            print(f"⚠️ Error loading config: {e}, using defaults")
    print("📝 No config found, using default APIs")
    save_apis(DEFAULT_APIS)
    return DEFAULT_APIS.copy()

def save_apis(apis_dict):
    try:
        with open(APIS_CONFIG_FILE, 'w') as f:
            json.dump(apis_dict, f, indent=4)
        return True
    except Exception as e:
        print(f"❌ Failed to save APIs: {e}")
        return False

REAL_APIS = load_apis()

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

# ==================== CORE FUNCTIONS ====================

def call_real_api(number, api_type):
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
                # Apply dynamic replace rules
                data = apply_replace_rules(data)
                if data and data != {} and data != {"error": "Not found"}:
                    print(f"✅ {api['name']} success for {number}")
                    return data, api['name']
        except Exception as e:
            print(f"❌ {api['name']} failed: {str(e)[:50]}")
            continue
    return None, "All APIs failed"

def format_response(data, api_type, api_name):
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

def generate_key(name, days, limit_req, allowed_types, custom_key=None):
    if custom_key:
        api_key = custom_key
    else:
        random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        api_key = f"{name}_{random_part}"
    
    expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect("api_system.db")
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users(api_key, name, expiry, used, limit_req, allowed_types, created_at, status)
            VALUES(?, ?, ?, 0, ?, ?, ?, 'active')
        """, (api_key, name, expiry, limit_req, allowed_types, created_at))
        conn.commit()
        conn.close()
        return api_key
    except sqlite3.IntegrityError:
        conn.close()
        return None  # Duplicate key

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

# ==================== REPLACE RULES COMMANDS ====================

@bot.message_handler(commands=['addreplace'])
def add_replace_rule(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    try:
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.reply_to(msg, "❌ USAGE: /addreplace <find> <replace>\nExample: /addreplace FRAPPEASH Danger_devil1917")
            return
        find = parts[1]
        replace = parts[2]
        REPLACE_RULES[find] = replace
        save_replace_rules(REPLACE_RULES)
        bot.reply_to(msg, f"✅ Replacement rule added:\n`{find}` → `{replace}`", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['removereplace'])
def remove_replace_rule(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    try:
        parts = msg.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(msg, "❌ USAGE: /removereplace <find>\nExample: /removereplace FRAPPEASH")
            return
        find = parts[1]
        if find in REPLACE_RULES:
            del REPLACE_RULES[find]
            save_replace_rules(REPLACE_RULES)
            bot.reply_to(msg, f"✅ Removed replacement rule for `{find}`", parse_mode='Markdown')
        else:
            bot.reply_to(msg, f"❌ Rule `{find}` not found", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['listreplace'])
def list_replace_rules(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    if not REPLACE_RULES:
        bot.reply_to(msg, "📭 No replacement rules configured.")
        return
    text = "📝 **Active Replacement Rules**\n━━━━━━━━━━━━━━━━━━━━━\n"
    for find, replace in REPLACE_RULES.items():
        text += f"🔹 `{find}` → `{replace}`\n"
    bot.reply_to(msg, text, parse_mode='Markdown')

@bot.message_handler(commands=['clearreplace'])
def clear_replace_rules(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    REPLACE_RULES.clear()
    save_replace_rules(REPLACE_RULES)
    bot.reply_to(msg, "✅ All replacement rules cleared.")

# ==================== API MANAGEMENT COMMANDS ====================

@bot.message_handler(commands=['addapi'])
def add_api(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    try:
        parts = msg.text.split(maxsplit=4)
        if len(parts) < 4:
            bot.reply_to(msg, """❌ USAGE:
/addapi <type> <name> <url_template>

Example: /addapi mobile NewAPI https://example.com/api?number={number}

Placeholder {number} will be replaced with actual number.
Type must be one of: aadhaar, mobile, family, telegram""")
            return
        api_type = parts[1].lower()
        name = parts[2]
        url_template = parts[3]
        if api_type not in ['aadhaar', 'mobile', 'family', 'telegram']:
            bot.reply_to(msg, "❌ Invalid type. Use: aadhaar, mobile, family, telegram")
            return
        if '{number}' not in url_template:
            bot.reply_to(msg, "❌ URL must contain {number} placeholder")
            return
        for api in REAL_APIS.get(api_type, []):
            if api['name'] == name:
                bot.reply_to(msg, f"❌ API with name '{name}' already exists in {api_type}")
                return
        new_api = {"name": name, "url": url_template, "working": True}
        if api_type not in REAL_APIS:
            REAL_APIS[api_type] = []
        REAL_APIS[api_type].append(new_api)
        save_apis(REAL_APIS)
        bot.reply_to(msg, f"""✅ API Added Successfully!

Type: {api_type.upper()}
Name: {name}
URL: {url_template}
Status: WORKING

Use /listapis to see all APIs.""")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['removeapi'])
def remove_api(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    try:
        parts = msg.text.split()
        if len(parts) < 3:
            bot.reply_to(msg, "❌ USAGE: /removeapi <type> <name>\nExample: /removeapi mobile MobileAPI1")
            return
        api_type = parts[1].lower()
        name = parts[2]
        if api_type not in REAL_APIS:
            bot.reply_to(msg, f"❌ Type '{api_type}' not found")
            return
        original_len = len(REAL_APIS[api_type])
        REAL_APIS[api_type] = [api for api in REAL_APIS[api_type] if api['name'] != name]
        if len(REAL_APIS[api_type]) == original_len:
            bot.reply_to(msg, f"❌ API '{name}' not found in {api_type}")
            return
        save_apis(REAL_APIS)
        bot.reply_to(msg, f"✅ Removed API '{name}' from {api_type}")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['toggleapi'])
def toggle_api(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    try:
        parts = msg.text.split()
        if len(parts) < 3:
            bot.reply_to(msg, "❌ USAGE: /toggleapi <type> <name>\nExample: /toggleapi family FamilyAPI1")
            return
        api_type = parts[1].lower()
        name = parts[2]
        if api_type not in REAL_APIS:
            bot.reply_to(msg, f"❌ Type '{api_type}' not found")
            return
        for api in REAL_APIS[api_type]:
            if api['name'] == name:
                api['working'] = not api['working']
                save_apis(REAL_APIS)
                status = "WORKING" if api['working'] else "DISABLED"
                bot.reply_to(msg, f"✅ API '{name}' is now {status}")
                return
        bot.reply_to(msg, f"❌ API '{name}' not found in {api_type}")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['editapi'])
def edit_api(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    try:
        parts = msg.text.split(maxsplit=4)
        if len(parts) < 4:
            bot.reply_to(msg, """❌ USAGE:
/editapi <type> <name> <field> <new_value>

Fields: name, url
Example: /editapi aadhaar AadhaarAPI1 url https://newapi.com/{number}""")
            return
        api_type = parts[1].lower()
        name = parts[2]
        field = parts[3].lower()
        new_value = parts[4] if len(parts) > 4 else ""
        if field not in ['name', 'url']:
            bot.reply_to(msg, "❌ Only 'name' and 'url' fields can be edited")
            return
        if api_type not in REAL_APIS:
            bot.reply_to(msg, f"❌ Type '{api_type}' not found")
            return
        for api in REAL_APIS[api_type]:
            if api['name'] == name:
                if field == 'url' and '{number}' not in new_value:
                    bot.reply_to(msg, "❌ URL must contain {number} placeholder")
                    return
                old_value = api[field]
                api[field] = new_value
                save_apis(REAL_APIS)
                bot.reply_to(msg, f"✅ Updated {field} of '{name}' from\n{old_value}\nto\n{new_value}")
                return
        bot.reply_to(msg, f"❌ API '{name}' not found in {api_type}")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['listapis'])
def list_apis(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    if not REAL_APIS:
        bot.reply_to(msg, "❌ No APIs configured")
        return
    text = "📡 CONFIGURED APIS\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for api_type, apis in REAL_APIS.items():
        text += f"🔹 {api_type.upper()} ({len(apis)} APIs)\n"
        for api in apis:
            status_icon = "✅" if api['working'] else "❌"
            text += f"   {status_icon} {api['name']}\n"
            text += f"      📍 {api['url'][:999]}...\n"
        text += "\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━\nUse /addapi, /removeapi, /toggleapi, /editapi to manage"
    bot.reply_to(msg, text[:4000])

@bot.message_handler(commands=['reloadapis'])
def reload_apis(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized")
        return
    global REAL_APIS
    REAL_APIS = load_apis()
    bot.reply_to(msg, f"✅ APIs reloaded from {APIS_CONFIG_FILE}\nTotal types: {len(REAL_APIS)}")

# ==================== ORIGINAL BOT COMMANDS (unchanged logic, but using new functions) ====================

@bot.message_handler(commands=['start'])
def start(msg):
    text = f"""
╔══════════════════════════════════════════════════════════════╗
║              🔥 REAL API MANAGEMENT SYSTEM                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  🔑 GENERATE API KEY:                                       ║
║  /genkey NAME DAYS LIMIT TYPES [CUSTOM_KEY]                 ║
║                                                              ║
║  EXAMPLES:                                                  ║
║  /genkey Client1 30 500 all                                 ║
║  /genkey Client2 7 100 aadhaar,mobile MYKEY123              ║
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
║  🔧 API MANAGEMENT (ADMIN):                                 ║
║  /addapi - Add new real API                                 ║
║  /removeapi - Remove an API                                 ║
║  /toggleapi - Enable/disable API                            ║
║  /editapi - Edit API name or URL                            ║
║  /listapis - Show all APIs                                  ║
║  /reloadapis - Reload from file                             ║
║                                                              ║
║  🔄 REPLACE RULES (ADMIN):                                  ║
║  /addreplace - Add find/replace rule                        ║
║  /removereplace - Remove a rule                             ║
║  /listreplace - List all rules                              ║
║  /clearreplace - Clear all rules                            ║
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
/genkey NAME DAYS LIMIT TYPES [CUSTOM_KEY]

EXAMPLES:
/genkey Client1 30 500 all
/genkey Client2 7 100 aadhaar,mobile MYKEY123

TYPES: aadhaar, mobile, family, telegram, all
""")
            return
        
        name = parts[1]
        days = int(parts[2])
        limit_req = int(parts[3])
        allowed_types = parts[4]
        custom_key = parts[5] if len(parts) > 5 else None
        
        api_key = generate_key(name, days, limit_req, allowed_types, custom_key)
        
        if not api_key:
            bot.reply_to(msg, "❌ Failed to generate key. Maybe custom key already exists?")
            return
        
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
        text += f"   📌 {key[:999]}...\n"
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
        text += f"   🔑 {api_key[:999]}...\n"
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

🔧 API MANAGEMENT (ADMIN):
/addapi - Add real API
/removeapi - Remove API
/toggleapi - Enable/disable
/editapi - Edit API
/listapis - List all APIs
/reloadapis - Reload from file

🔄 REPLACE RULES (ADMIN):
/addreplace - Add find/replace
/removereplace - Remove rule
/listreplace - List rules
/clearreplace - Clear all
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
    print("✅ REPLACE RULES LOADED:", len(REPLACE_RULES))
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
