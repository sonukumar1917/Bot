import time
import telebot
import sqlite3
import random
import string
import threading
import requests
import os
import json
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# ==================== CONFIG ====================

BOT_TOKEN = "8290734722:AAHk7uyZ7DgeeiJKYy7Zlp-sjblpClQNJAQ"
ADMIN_ID = 7655738256

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ==================== DATA CLASSES ====================

class APIType(Enum):
    MOBILE = "mobile"
    TG = "telegram"
    FAMILY = "family"
    AADHAAR = "aadhaar"
    VEHICLE = "vehicle"
    PAN = "pan"
    CUSTOM = "custom"

@dataclass
class APIEndpoint:
    id: int
    name: str
    url: str
    api_type: str
    method: str = "GET"
    headers: str = "{}"
    params: str = "{}"
    success_field: str = ""
    enabled: bool = True
    priority: int = 1
    timeout: int = 15
    created_at: str = ""
    last_used: str = ""
    total_requests: int = 0
    success_requests: int = 0

# ==================== DATABASE ====================

def init_db():
    """Initialize all database tables"""
    conn = sqlite3.connect("api_system.db", check_same_thread=False)
    cur = conn.cursor()
    
    # Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        api_key TEXT PRIMARY KEY,
        expiry TEXT,
        used INTEGER DEFAULT 0,
        limit_req INTEGER DEFAULT 100,
        created_at TEXT,
        created_by INTEGER,
        status TEXT DEFAULT 'active'
    )
    """)
    
    # APIs table - Main storage
    cur.execute("""
    CREATE TABLE IF NOT EXISTS apis(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        url TEXT,
        api_type TEXT,
        method TEXT DEFAULT 'GET',
        headers TEXT,
        params TEXT,
        success_field TEXT,
        enabled INTEGER DEFAULT 1,
        priority INTEGER DEFAULT 1,
        timeout INTEGER DEFAULT 15,
        created_at TEXT,
        last_used TEXT,
        total_requests INTEGER DEFAULT 0,
        success_requests INTEGER DEFAULT 0,
        fail_requests INTEGER DEFAULT 0,
        avg_response_time REAL DEFAULT 0
    )
    """)
    
    # API Groups
    cur.execute("""
    CREATE TABLE IF NOT EXISTS api_groups(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        description TEXT,
        created_at TEXT
    )
    """)
    
    # API to Group mapping
    cur.execute("""
    CREATE TABLE IF NOT EXISTS api_group_mapping(
        api_id INTEGER,
        group_id INTEGER,
        FOREIGN KEY(api_id) REFERENCES apis(id),
        FOREIGN KEY(group_id) REFERENCES api_groups(id)
    )
    """)
    
    # API Logs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS api_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_id INTEGER,
        api_name TEXT,
        request_number TEXT,
        response_code INTEGER,
        response_time REAL,
        success INTEGER,
        error_message TEXT,
        timestamp TEXT
    )
    """)
    
    # Rate limiting rules
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rate_limits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_id INTEGER,
        per_minute INTEGER DEFAULT 10,
        per_hour INTEGER DEFAULT 100,
        per_day INTEGER DEFAULT 1000,
        enabled INTEGER DEFAULT 1
    )
    """)
    
    # Load balancer config
    cur.execute("""
    CREATE TABLE IF NOT EXISTS load_balancer(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_type TEXT UNIQUE,
        strategy TEXT DEFAULT 'round_robin',
        current_index INTEGER DEFAULT 0
    )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

init_db()

# ==================== API MANAGER CLASS ====================

class APIManager:
    """Complete API Management System"""
    
    def __init__(self):
        self.cache = {}
        self.fallback_apis = {}
        
    def get_db(self):
        return sqlite3.connect("api_system.db")
    
    def add_api(self, name: str, url: str, api_type: str, **kwargs) -> bool:
        """Add new API endpoint"""
        conn = self.get_db()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                INSERT INTO apis(
                    name, url, api_type, method, headers, params,
                    success_field, enabled, priority, timeout, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, url, api_type,
                kwargs.get('method', 'GET'),
                json.dumps(kwargs.get('headers', {})),
                json.dumps(kwargs.get('params', {})),
                kwargs.get('success_field', ''),
                kwargs.get('enabled', 1),
                kwargs.get('priority', 1),
                kwargs.get('timeout', 15),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Add API Error: {e}")
            conn.close()
            return False
    
    def remove_api(self, api_id: int) -> bool:
        """Remove API endpoint"""
        conn = self.get_db()
        cur = conn.cursor()
        
        try:
            cur.execute("DELETE FROM apis WHERE id = ?", (api_id,))
            cur.execute("DELETE FROM api_logs WHERE api_id = ?", (api_id,))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False
    
    def get_all_apis(self, api_type: str = None) -> List[Dict]:
        """Get all APIs with optional type filter"""
        conn = self.get_db()
        cur = conn.cursor()
        
        if api_type:
            cur.execute("SELECT * FROM apis WHERE api_type = ? ORDER BY priority ASC", (api_type,))
        else:
            cur.execute("SELECT * FROM apis ORDER BY api_type, priority ASC")
        
        rows = cur.fetchall()
        conn.close()
        
        apis = []
        for row in rows:
            apis.append({
                'id': row[0],
                'name': row[1],
                'url': row[2],
                'api_type': row[3],
                'method': row[4],
                'headers': json.loads(row[5]) if row[5] else {},
                'params': json.loads(row[6]) if row[6] else {},
                'success_field': row[7],
                'enabled': bool(row[8]),
                'priority': row[9],
                'timeout': row[10],
                'created_at': row[11],
                'last_used': row[12],
                'total_requests': row[13],
                'success_requests': row[14]
            })
        
        return apis
    
    def update_api_status(self, api_id: int, enabled: bool) -> bool:
        """Enable/Disable API"""
        conn = self.get_db()
        cur = conn.cursor()
        
        try:
            cur.execute("UPDATE apis SET enabled = ? WHERE id = ?", (1 if enabled else 0, api_id))
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False
    
    def log_request(self, api_id: int, api_name: str, number: str, 
                    response_code: int, response_time: float, success: bool, error: str = ""):
        """Log API request for analytics"""
        conn = self.get_db()
        cur = conn.cursor()
        
        # Update API stats
        cur.execute("""
            UPDATE apis 
            SET total_requests = total_requests + 1,
                success_requests = success_requests + ?,
                fail_requests = fail_requests + ?,
                last_used = ?
            WHERE id = ?
        """, (1 if success else 0, 0 if success else 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), api_id))
        
        # Insert log
        cur.execute("""
            INSERT INTO api_logs(api_id, api_name, request_number, response_code, 
                                response_time, success, error_message, timestamp)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """, (api_id, api_name, number, response_code, response_time, 
              1 if success else 0, error, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        conn.commit()
        conn.close()
    
    def fetch_api(self, api: Dict, number: str) -> Optional[Dict]:
        """Fetch data from a single API"""
        url = api['url'].format(number=number)
        start_time = time.time()
        
        try:
            headers = api.get('headers', {})
            params = api.get('params', {})
            
            if api['method'] == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=api['timeout'])
            else:
                response = requests.post(url, headers=headers, json=params, timeout=api['timeout'])
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                
                # Check success field if specified
                if api['success_field']:
                    fields = api['success_field'].split('.')
                    success_check = data
                    for field in fields:
                        success_check = success_check.get(field, {})
                    
                    if success_check:
                        self.log_request(api['id'], api['name'], number, 
                                       response.status_code, response_time, True)
                        return data
                    else:
                        self.log_request(api['id'], api['name'], number,
                                       response.status_code, response_time, False, "Success field not found")
                else:
                    self.log_request(api['id'], api['name'], number,
                                   response.status_code, response_time, True)
                    return data
            
            self.log_request(api['id'], api['name'], number,
                           response.status_code, response_time, False, f"HTTP {response.status_code}")
                           
        except requests.Timeout:
            self.log_request(api['id'], api['name'], number, 0, time.time() - start_time, False, "Timeout")
        except Exception as e:
            self.log_request(api['id'], api['name'], number, 0, time.time() - start_time, False, str(e))
        
        return None
    
    def smart_fetch(self, number: str, api_type: str, max_retries: int = 3) -> Dict:
        """Smart fetch with fallback and load balancing"""
        apis = self.get_all_apis(api_type)
        enabled_apis = [a for a in apis if a['enabled']]
        
        if not enabled_apis:
            return {"error": f"No enabled API found for type: {api_type}"}
        
        # Sort by priority
        enabled_apis.sort(key=lambda x: x['priority'])
        
        for api in enabled_apis:
            for attempt in range(max_retries):
                result = self.fetch_api(api, number)
                if result:
                    return result
                time.sleep(0.5)
        
        return {"error": f"All APIs failed for type: {api_type}"}

# ==================== BOT COMMANDS ====================

api_manager = APIManager()

# ===== ADMIN PANEL =====

@bot.message_handler(commands=['admin'])
def admin_panel(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    
    buttons = [
        telebot.types.InlineKeyboardButton("📊 API Stats", callback_data="admin_stats"),
        telebot.types.InlineKeyboardButton("➕ Add API", callback_data="admin_add_api"),
        telebot.types.InlineKeyboardButton("📋 List APIs", callback_data="admin_list_apis"),
        telebot.types.InlineKeyboardButton("🗑️ Remove API", callback_data="admin_remove_api"),
        telebot.types.InlineKeyboardButton("🔌 Enable/Disable", callback_data="admin_toggle_api"),
        telebot.types.InlineKeyboardButton("📈 Analytics", callback_data="admin_analytics"),
        telebot.types.InlineKeyboardButton("🎫 Manage Keys", callback_data="admin_keys"),
        telebot.types.InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings"),
        telebot.types.InlineKeyboardButton("🔄 Test API", callback_data="admin_test_api"),
        telebot.types.InlineKeyboardButton("📤 Export Logs", callback_data="admin_export")
    ]
    
    for btn in buttons:
        markup.add(btn)
    
    bot.send_message(msg.chat.id, 
        "🔐 *API MANAGEMENT SYSTEM*\n\n"
        "Welcome to Advanced API Control Panel\n"
        "Manage all your APIs from here\n\n"
        f"📊 *Total APIs*: {len(api_manager.get_all_apis())}\n"
        f"✅ *Active APIs*: {len([a for a in api_manager.get_all_apis() if a['enabled']])}\n"
        f"📈 *Total Requests*: {sum(a['total_requests'] for a in api_manager.get_all_apis())}",
        parse_mode="Markdown", reply_markup=markup)

# ===== ADD API COMMAND =====

@bot.message_handler(commands=['addapi'])
def add_api_cmd(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = msg.text.split('|')
        if len(parts) < 3:
            bot.reply_to(msg, 
                "❌ *Usage:*\n"
                "`/addapi name|url|type`\n\n"
                "*Optional:*\n"
                "`|method|headers|success_field|priority|timeout`\n\n"
                "*Example:*\n"
                "`/addapi MobileAPI|https://api.com/{number}|mobile|GET|{}|data.status|1|15`",
                parse_mode="Markdown")
            return
        
        name = parts[0].strip()
        url = parts[1].strip()
        api_type = parts[2].strip()
        
        kwargs = {
            'method': parts[3].strip() if len(parts) > 3 else 'GET',
            'headers': json.loads(parts[4]) if len(parts) > 4 else {},
            'success_field': parts[5].strip() if len(parts) > 5 else '',
            'priority': int(parts[6]) if len(parts) > 6 else 1,
            'timeout': int(parts[7]) if len(parts) > 7 else 15
        }
        
        if api_manager.add_api(name, url, api_type, **kwargs):
            bot.reply_to(msg, f"✅ *API Added Successfully!*\n\n"
                           f"📛 Name: `{name}`\n"
                           f"🔗 Type: `{api_type}`\n"
                           f"⚡ Priority: `{kwargs['priority']}`",
                           parse_mode="Markdown")
        else:
            bot.reply_to(msg, "❌ Failed to add API. Name might already exist.")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

# ===== LIST APIS COMMAND =====

@bot.message_handler(commands=['listapis'])
def list_apis_cmd(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    
    apis = api_manager.get_all_apis()
    
    if not apis:
        bot.reply_to(msg, "❌ No APIs found")
        return
    
    # Group by type
    grouped = {}
    for api in apis:
        api_type = api['api_type']
        if api_type not in grouped:
            grouped[api_type] = []
        grouped[api_type].append(api)
    
    text = "📋 *ALL APIs*\n\n"
    
    for api_type, type_apis in grouped.items():
        text += f"🔹 *{api_type.upper()}* ({len(type_apis)})\n"
        for api in type_apis:
            status = "✅" if api['enabled'] else "❌"
            text += f"   {status} `{api['id']}` - {api['name']}\n"
            text += f"      📊 {api['total_requests']} reqs | 🎯 {api['success_requests']} success\n"
        text += "\n"
    
    bot.reply_to(msg, text, parse_mode="Markdown")

# ===== REMOVE API COMMAND =====

@bot.message_handler(commands=['removeapi'])
def remove_api_cmd(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    
    try:
        api_id = int(msg.text.split()[1])
        
        if api_manager.remove_api(api_id):
            bot.reply_to(msg, f"✅ API ID `{api_id}` removed successfully", parse_mode="Markdown")
        else:
            bot.reply_to(msg, "❌ Failed to remove API")
    except:
        bot.reply_to(msg, "❌ Usage: `/removeapi <api_id>`", parse_mode="Markdown")

# ===== TOGGLE API COMMAND =====

@bot.message_handler(commands=['toggleapi'])
def toggle_api_cmd(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    
    try:
        api_id = int(msg.text.split()[1])
        
        apis = api_manager.get_all_apis()
        api = next((a for a in apis if a['id'] == api_id), None)
        
        if api:
            new_status = not api['enabled']
            api_manager.update_api_status(api_id, new_status)
            status_text = "ENABLED ✅" if new_status else "DISABLED ❌"
            bot.reply_to(msg, f"✅ API `{api['name']}` is now {status_text}", parse_mode="Markdown")
        else:
            bot.reply_to(msg, "❌ API not found")
    except:
        bot.reply_to(msg, "❌ Usage: `/toggleapi <api_id>`", parse_mode="Markdown")

# ===== TEST API COMMAND =====

@bot.message_handler(commands=['testapi'])
def test_api_cmd(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = msg.text.split()
        api_id = int(parts[1])
        test_number = parts[2] if len(parts) > 2 else "9999999999"
        
        apis = api_manager.get_all_apis()
        api = next((a for a in apis if a['id'] == api_id), None)
        
        if not api:
            bot.reply_to(msg, "❌ API not found")
            return
        
        bot.reply_to(msg, f"🔄 Testing API `{api['name']}` with number `{test_number}`...", parse_mode="Markdown")
        
        result = api_manager.fetch_api(api, test_number)
        
        if result:
            bot.reply_to(msg, f"✅ *API Test Successful*\n\n"
                           f"📛 Name: `{api['name']}`\n"
                           f"📊 Response: `{json.dumps(result, indent=2)[:500]}`",
                           parse_mode="Markdown")
        else:
            bot.reply_to(msg, f"❌ *API Test Failed*\n\n"
                           f"📛 Name: `{api['name']}`\n"
                           f"Check logs for details", parse_mode="Markdown")
    except:
        bot.reply_to(msg, "❌ Usage: `/testapi <api_id> [test_number]`", parse_mode="Markdown")

# ===== API STATS COMMAND =====

@bot.message_handler(commands=['apistats'])
def api_stats_cmd(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    
    apis = api_manager.get_all_apis()
    
    text = "📊 *API STATISTICS*\n\n"
    
    for api in apis:
        success_rate = (api['success_requests'] / api['total_requests'] * 100) if api['total_requests'] > 0 else 0
        text += f"🔹 *{api['name']}* (ID: {api['id']})\n"
        text += f"   ├ Status: {'✅ Active' if api['enabled'] else '❌ Disabled'}\n"
        text += f"   ├ Type: {api['api_type']}\n"
        text += f"   ├ Requests: {api['total_requests']}\n"
        text += f"   ├ Success: {api['success_requests']}\n"
        text += f"   ├ Success Rate: {success_rate:.1f}%\n"
        text += f"   └ Last Used: {api['last_used'] or 'Never'}\n\n"
    
    bot.reply_to(msg, text, parse_mode="Markdown")

# ===== SMART SEARCH COMMAND =====

@bot.message_handler(commands=['search'])
def smart_search(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = msg.text.split()
        number = parts[1]
        api_type = parts[2] if len(parts) > 2 else "mobile"
        
        bot.reply_to(msg, f"🔍 Smart searching for `{number}` using `{api_type}` APIs...", parse_mode="Markdown")
        
        result = api_manager.smart_fetch(number, api_type)
        
        if result and 'error' not in result:
            bot.reply_to(msg, f"✅ *Search Result*\n\n```json\n{json.dumps(result, indent=2)[:1000]}\n```", parse_mode="Markdown")
        else:
            bot.reply_to(msg, f"❌ *Search Failed*\n\n{result.get('error', 'No data found')}", parse_mode="Markdown")
    except:
        bot.reply_to(msg, "❌ Usage: `/search <number> [api_type]`\n\nAvailable types: mobile, telegram, family, aadhaar", parse_mode="Markdown")

# ===== CALLBACK HANDLER =====

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    if call.data == "admin_stats":
        apis = api_manager.get_all_apis()
        total_reqs = sum(a['total_requests'] for a in apis)
        total_success = sum(a['success_requests'] for a in apis)
        
        bot.edit_message_text(
            f"📊 *SYSTEM STATISTICS*\n\n"
            f"📌 Total APIs: `{len(apis)}`\n"
            f"✅ Active: `{len([a for a in apis if a['enabled']])}`\n"
            f"📈 Total Requests: `{total_reqs}`\n"
            f"🎯 Success Rate: `{(total_success/total_reqs*100 if total_reqs>0 else 0):.1f}%`\n"
            f"💾 Database: `SQLite`\n"
            f"⚡ Load Balancer: `Active`",
            call.message.chat.id, call.message.message_id,
            parse_mode="Markdown"
        )
    
    elif call.data == "admin_list_apis":
        apis = api_manager.get_all_apis()
        text = "📋 *ALL APIs*\n\n"
        for api in apis:
            status = "✅" if api['enabled'] else "❌"
            text += f"{status} ID:`{api['id']}` | {api['name']}\n"
            text += f"   └ {api['api_type']} | {api['total_requests']} reqs\n"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "admin_analytics":
        conn = api_manager.get_db()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT api_name, COUNT(*), AVG(response_time), 
                   SUM(CASE WHEN success=1 THEN 1 ELSE 0 END)
            FROM api_logs 
            WHERE timestamp > datetime('now', '-7 days')
            GROUP BY api_name
        """)
        
        logs = cur.fetchall()
        conn.close()
        
        text = "📈 *ANALYTICS (Last 7 Days)*\n\n"
        for log in logs:
            name, count, avg_time, success = log
            text += f"🔹 {name}\n"
            text += f"   ├ Requests: {count}\n"
            text += f"   ├ Avg Time: {avg_time:.2f}s\n"
            text += f"   └ Success: {success}\n\n"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# ===== API ENDPOINT =====

@app.route("/api/v1/search")
def api_search():
    """Public API endpoint"""
    key = request.args.get("key")
    number = request.args.get("number")
    api_type = request.args.get("type", "mobile")
    
    if not key or not number:
        return jsonify({"error": "key and number required"})
    
    # Check user key
    conn = api_manager.get_db()
    cur = conn.cursor()
    cur.execute("SELECT expiry, used, limit_req, status FROM users WHERE api_key = ?", (key,))
    user = cur.fetchone()
    conn.close()
    
    if not user:
        return jsonify({"error": "invalid key"})
    
    expiry, used, limit_req, status = user
    expiry_date = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
    
    if datetime.now() > expiry_date:
        return jsonify({"error": "subscription expired"})
    
    if used >= limit_req:
        return jsonify({"error": "limit reached"})
    
    if status != "active":
        return jsonify({"error": "account inactive"})
    
    # Update usage
    conn = api_manager.get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET used = used + 1 WHERE api_key = ?", (key,))
    conn.commit()
    conn.close()
    
    # Smart fetch
    result = api_manager.smart_fetch(number, api_type)
    
    return jsonify(result)

# ===== FALLBACK API (Legacy Support) =====

@app.route("/api")
def legacy_api():
    """Legacy API endpoint"""
    key = request.args.get("key")
    number = request.args.get("number")
    
    if not key or not number:
        return jsonify({"error": "key and number required"})
    
    # Try all API types
    for api_type in ["mobile", "telegram", "family", "aadhaar"]:
        result = api_manager.smart_fetch(number, api_type)
        if result and 'error' not in result:
            return jsonify(result)
    
    return jsonify({"error": "no data found"})

# ==================== SELF PING ====================

def self_ping():
    """Keep the bot alive"""
    url = "https://api-wd7m.onrender.com?key=sleep&number=9999999999"
    while True:
        try:
            requests.get(url, timeout=10)
        except:
            pass
        time.sleep(300)

# ==================== MAIN ====================

def run_api():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

def run_bot():
    bot.infinity_polling(timeout=60, long_polling_timeout=30)

if __name__ == "__main__":
    print("🚀 API Management System Starting...")
    print("✅ Bot and API Server Active")
    
    # Auto-add default APIs
    default_apis = [
        ("MobileAPI1", "https://ayaanmods.site/mobile.php?key=annonymousmobile&term={number}", "mobile", "GET", "{}", "data", 1),
        ("TGtoNumAPI", "https://devil.elementfx.com/api.php?key=SONU&type=tg_number&term={number}", "telegram", "GET", "{}", "success", 1),
        ("FamilyAPI", "https://devil.elementfx.com/api.php?key=DANGER&type=id_family&term={number}", "family", "GET", "{}", "result.results", 2),
        ("AadhaarAPI", "https://devil.elementfx.com/api.php?key=DANGER&type=aadhaar_info&term={number}", "aadhaar", "GET", "{}", "status", 1),
    ]
    
    for name, url, api_type, method, headers, success_field, priority in default_apis:
        api_manager.add_api(name, url, api_type, method=method, headers=json.loads(headers), 
                           success_field=success_field, priority=priority)
    
    # Start threads
    threading.Thread(target=self_ping, daemon=True).start()
    threading.Thread(target=run_api, daemon=True).start()
    run_bot()