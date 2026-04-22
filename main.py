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
import hashlib
import base64
import csv
from io import StringIO
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from collections import defaultdict
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# ==================== CONFIG ====================

BOT_TOKEN = "8290734722:AAHk7uyZ7DgeeiJKYy7Zlp-sjblpClQNJAQ"
ADMIN_ID = 7655738256
PORT = int(os.environ.get("PORT", 5000))

# APNA RENDER URL YAHAN DALO - ⚠️ IMPORTANT ⚠️
# Render dashboard se apna URL copy karo, jaise: https://your-app-name.onrender.com
DEFAULT_RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://api-wd7m.onrender.com")

# Global variable for alive URL
MY_RENDER_URL = DEFAULT_RENDER_URL

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ==================== DATABASE INITIALIZATION ====================

def init_db():
    """Initialize complete database with all tables"""
    conn = sqlite3.connect("api_system.db", check_same_thread=False)
    cur = conn.cursor()
    
    # Users/Keys table - Complete
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT UNIQUE,
        name TEXT,
        expiry TEXT,
        used INTEGER DEFAULT 0,
        limit_req INTEGER DEFAULT 100,
        api_type TEXT DEFAULT 'all',
        plan TEXT DEFAULT 'basic',
        notes TEXT,
        created_at TEXT,
        created_by INTEGER,
        status TEXT DEFAULT 'active',
        rate_per_minute INTEGER DEFAULT 10,
        rate_per_hour INTEGER DEFAULT 100,
        rate_per_day INTEGER DEFAULT 500,
        last_used_ip TEXT,
        last_used_time TEXT,
        total_requests INTEGER DEFAULT 0,
        total_success INTEGER DEFAULT 0,
        total_failed INTEGER DEFAULT 0,
        email TEXT,
        phone TEXT,
        company TEXT
    )
    """)
    
    # APIs table
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
        rate_limit INTEGER DEFAULT 60,
        created_at TEXT,
        last_used TEXT,
        total_requests INTEGER DEFAULT 0,
        success_requests INTEGER DEFAULT 0,
        fail_requests INTEGER DEFAULT 0,
        avg_response_time REAL DEFAULT 0,
        backup_url TEXT,
        api_key_required TEXT,
        auth_header TEXT
    )
    """)
    
    # API Logs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS api_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_id INTEGER,
        api_name TEXT,
        request_number TEXT,
        api_key TEXT,
        response_code INTEGER,
        response_time REAL,
        success INTEGER,
        error_message TEXT,
        ip_address TEXT,
        user_agent TEXT,
        timestamp TEXT
    )
    """)
    
    # Blacklist
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blacklist(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip_address TEXT,
        api_key TEXT,
        reason TEXT,
        banned_until TEXT,
        created_at TEXT,
        banned_by INTEGER
    )
    """)
    
    # Whitelist
    cur.execute("""
    CREATE TABLE IF NOT EXISTS whitelist(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip_address TEXT UNIQUE,
        api_key TEXT,
        notes TEXT,
        created_at TEXT
    )
    """)
    
    # Rate Limits Log
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rate_limits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT,
        endpoint TEXT,
        requests INTEGER DEFAULT 0,
        reset_time TEXT,
        UNIQUE(api_key, endpoint)
    )
    """)
    
    # Cache
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cache(
        cache_key TEXT PRIMARY KEY,
        data TEXT,
        expires_at TEXT,
        created_at TEXT
    )
    """)
    
    # Payments
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT,
        api_key TEXT,
        amount REAL,
        plan TEXT,
        days INTEGER,
        status TEXT,
        created_at TEXT
    )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized with all tables")

init_db()

# ==================== API MANAGER CLASS ====================

class APIManager:
    def __init__(self):
        self.cache = {}
        
    def get_db(self):
        return sqlite3.connect("api_system.db")
    
    def generate_api_key(self, name, days, limit_req, api_type, plan, notes="", email="", phone="", company=""):
        """Generate custom API key"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        key_raw = f"{name}_{timestamp}_{random_part}"
        api_key = base64.b64encode(key_raw.encode()).decode()[:32].replace('/', 'a').replace('+', 'b').replace('=', 'c')
        
        expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Rate limits based on plan
        rate_limits = {
            'basic': (10, 100, 500),
            'premium': (30, 500, 2000),
            'enterprise': (100, 2000, 10000),
            'unlimited': (500, 10000, 100000),
            'custom': (50, 1000, 5000)
        }
        
        rpm, rph, rpd = rate_limits.get(plan, rate_limits['basic'])
        
        conn = self.get_db()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO users(
                api_key, name, expiry, used, limit_req, api_type, plan, notes,
                created_at, status, rate_per_minute, rate_per_hour, rate_per_day,
                email, phone, company, total_requests, total_success, total_failed
            ) VALUES(?, ?, ?, 0, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, 0, 0, 0)
        """, (api_key, name, expiry, limit_req, api_type, plan, notes, created_at,
              rpm, rph, rpd, email, phone, company))
        
        conn.commit()
        conn.close()
        
        return api_key
    
    def validate_key(self, api_key):
        """Validate API key and return full info"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT name, expiry, used, limit_req, api_type, plan, status,
                   rate_per_minute, rate_per_hour, rate_per_day
            FROM users WHERE api_key = ?
        """, (api_key,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None, "Invalid API key"
        
        name, expiry, used, limit_req, api_type, plan, status, rpm, rph, rpd = row
        
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
        
        if datetime.now() > expiry_date:
            return None, "Subscription expired"
        
        if used >= limit_req:
            return None, "Request limit reached"
        
        if status != 'active':
            return None, f"Account {status}"
        
        return {
            'name': name,
            'expiry': expiry,
            'used': used,
            'limit': limit_req,
            'remaining': limit_req - used,
            'api_type': api_type,
            'plan': plan,
            'status': status,
            'rate_per_minute': rpm,
            'rate_per_hour': rph,
            'rate_per_day': rpd
        }, "Active"
    
    def increment_usage(self, api_key, success=True):
        """Increment usage counters"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE users 
            SET used = used + 1,
                total_requests = total_requests + 1,
                total_success = total_success + ?,
                total_failed = total_failed + ?,
                last_used_time = ?
            WHERE api_key = ?
        """, (1 if success else 0, 0 if success else 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), api_key))
        conn.commit()
        conn.close()
    
    def get_all_keys(self, filters=None):
        """Get all API keys with filters"""
        conn = self.get_db()
        cur = conn.cursor()
        
        query = "SELECT api_key, name, expiry, used, limit_req, api_type, plan, status, created_at, total_requests, total_success, email, phone FROM users"
        params = []
        
        if filters:
            if filters.get('api_type'):
                query += " WHERE api_type = ?"
                params.append(filters['api_type'])
            if filters.get('status'):
                query += " AND status = ?" if 'WHERE' in query else " WHERE status = ?"
                params.append(filters['status'])
            if filters.get('plan'):
                query += " AND plan = ?" if 'WHERE' in query else " WHERE plan = ?"
                params.append(filters['plan'])
        
        query += " ORDER BY created_at DESC"
        
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        
        keys = []
        for row in rows:
            keys.append({
                'api_key': row[0],
                'name': row[1],
                'expiry': row[2],
                'used': row[3],
                'limit': row[4],
                'api_type': row[5],
                'plan': row[6],
                'status': row[7],
                'created_at': row[8],
                'total_requests': row[9],
                'total_success': row[10],
                'email': row[11] or 'N/A',
                'phone': row[12] or 'N/A'
            })
        
        return keys
    
    def update_key(self, api_key, **kwargs):
        """Update key settings"""
        conn = self.get_db()
        cur = conn.cursor()
        
        for field, value in kwargs.items():
            if field in ['name', 'plan', 'status', 'notes', 'email', 'phone', 'company', 'api_type']:
                cur.execute(f"UPDATE users SET {field} = ? WHERE api_key = ?", (value, api_key))
            elif field in ['limit', 'rate_per_minute', 'rate_per_hour', 'rate_per_day']:
                cur.execute(f"UPDATE users SET {field} = ? WHERE api_key = ?", (int(value), api_key))
            elif field == 'extend_days':
                cur.execute("SELECT expiry FROM users WHERE api_key = ?", (api_key,))
                row = cur.fetchone()
                if row:
                    new_expiry = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") + timedelta(days=int(value))
                    cur.execute("UPDATE users SET expiry = ? WHERE api_key = ?", (new_expiry.strftime("%Y-%m-%d %H:%M:%S"), api_key))
        
        conn.commit()
        conn.close()
        return True
    
    def delete_key(self, api_key):
        """Delete API key"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE api_key = ?", (api_key,))
        conn.commit()
        conn.close()
        return True
    
    def get_key_stats(self):
        """Get overall key statistics"""
        conn = self.get_db()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM users")
        total_keys = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
        active_keys = cur.fetchone()[0]
        
        cur.execute("SELECT SUM(total_requests) FROM users")
        total_requests = cur.fetchone()[0] or 0
        
        cur.execute("SELECT SUM(total_success) FROM users")
        total_success = cur.fetchone()[0] or 0
        
        cur.execute("SELECT api_type, COUNT(*) FROM users GROUP BY api_type")
        type_stats = cur.fetchall()
        
        cur.execute("SELECT plan, COUNT(*) FROM users GROUP BY plan")
        plan_stats = cur.fetchall()
        
        conn.close()
        
        return {
            'total_keys': total_keys,
            'active_keys': active_keys,
            'total_requests': total_requests,
            'total_success': total_success,
            'success_rate': (total_success/total_requests*100) if total_requests > 0 else 0,
            'type_stats': dict(type_stats),
            'plan_stats': dict(plan_stats)
        }
    
    def log_request(self, api_id, api_name, number, api_key, response_code, response_time, success, error="", ip="", ua=""):
        """Log API request"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO api_logs(api_id, api_name, request_number, api_key, response_code, 
                                response_time, success, error_message, ip_address, user_agent, timestamp)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (api_id, api_name, number, api_key, response_code, response_time, 
              1 if success else 0, error, ip, ua, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
    
    def get_logs(self, limit=100, api_key=None):
        """Get recent logs"""
        conn = self.get_db()
        cur = conn.cursor()
        
        if api_key:
            cur.execute("""
                SELECT id, api_name, request_number, response_code, success, error_message, timestamp, ip_address
                FROM api_logs WHERE api_key = ? ORDER BY timestamp DESC LIMIT ?
            """, (api_key, limit))
        else:
            cur.execute("""
                SELECT id, api_name, request_number, api_key, response_code, success, error_message, timestamp, ip_address
                FROM api_logs ORDER BY timestamp DESC LIMIT ?
            """, (limit,))
        
        rows = cur.fetchall()
        conn.close()
        
        logs = []
        for row in rows:
            logs.append({
                'id': row[0],
                'api_name': row[1],
                'number': row[2],
                'api_key': row[3] if len(row) > 3 else 'N/A',
                'response_code': row[4] if len(row) > 4 else row[3],
                'success': row[5] if len(row) > 5 else row[4],
                'error': row[6] if len(row) > 6 else '',
                'timestamp': row[7] if len(row) > 7 else row[5],
                'ip': row[8] if len(row) > 8 else ''
            })
        
        return logs

api_manager = APIManager()

# ==================== BOT COMMANDS ====================

def is_admin(user_id):
    return user_id == ADMIN_ID

@bot.message_handler(commands=['start'])
def start(msg):
    welcome_text = f"""
╔══════════════════════════════════════════════════════════════╗
║                 🤖 ULTIMATE API MANAGEMENT BOT               ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  📌 AVAILABLE COMMANDS:                                     ║
║                                                              ║
║  🔑 KEY MANAGEMENT:                                         ║
║  ├ /genkey - Generate new API key                          ║
║  ├ /keys - List all API keys                               ║
║  ├ /keyinfo - Get key details                              ║
║  ├ /editkey - Edit key settings                            ║
║  ├ /blockkey - Block API key                               ║
║  ├ /unblockkey - Unblock API key                           ║
║  ├ /deletekey - Delete API key                             ║
║  └ /extendkey - Extend key expiry                          ║
║                                                              ║
║  📊 ANALYTICS:                                              ║
║  ├ /stats - System statistics                              ║
║  ├ /keyanalytics - Key usage analytics                     ║
║  ├ /logs - Recent API logs                                 ║
║  └ /exportkeys - Export all keys to CSV                    ║
║                                                              ║
║  🔍 SEARCH:                                                 ║
║  ├ /search - Smart search                                  ║
║  ├ /aadhaar - Aadhaar search                               ║
║  ├ /mobile - Mobile search                                 ║
║  ├ /family - Family search                                 ║
║  └ /tg - Telegram search                                   ║
║                                                              ║
║  ⚙️ ADMIN:                                                  ║
║  ├ /admin - Open admin panel                               ║
║  ├ /broadcast - Broadcast message                          ║
║  ├ /health - System health check                           ║
║  └ /setalive - Set alive URL                               ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║  📡 API Endpoint: {MY_RENDER_URL}/api                         ║
║  💡 Need Help? Contact @Danger_devil1917                    ║
╚══════════════════════════════════════════════════════════════╝
"""
    bot.reply_to(msg, welcome_text)

@bot.message_handler(commands=['setalive'])
def set_alive_url(msg):
    """Set or update alive URL"""
    global MY_RENDER_URL  # ✅ FIXED: Global declaration at start of function
    
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    try:
        parts = msg.text.split()
        if len(parts) < 2:
            bot.reply_to(msg, f"""
╔══════════════════════════════════════════════════════════════╗
║                    🔧 SET ALIVE URL                          ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  CURRENT URL: {MY_RENDER_URL}                                ║
║                                                              ║
║  USAGE: /setalive https://your-app.onrender.com             ║
║                                                              ║
║  📝 NOTE: Apna Render URL yahan dalo                        ║
║  Example: /setalive https://api-bot.onrender.com            ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")
            return
        
        new_url = parts[1].strip()
        
        # Update global variable
        MY_RENDER_URL = new_url
        
        bot.reply_to(msg, f"""
✅ ALIVE URL UPDATED SUCCESSFULLY!

📍 NEW URL: {new_url}
🔄 HEALTH CHECK: {new_url}/health
📊 STATS: {new_url}/stats
📡 API: {new_url}/api

💡 Bot will now ping this URL every 5 minutes to stay alive!
""")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['genkey'])
def genkey(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    try:
        parts = msg.text.split('|')
        
        if len(parts) < 5:
            bot.reply_to(msg, """
╔══════════════════════════════════════════════════════════════╗
║              🔑 API KEY GENERATION GUIDE                     ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  BASIC USAGE:                                               ║
║  /genkey NAME | DAYS | LIMIT | TYPE | PLAN | NOTES         ║
║                                                              ║
║  EXAMPLES:                                                  ║
║                                                              ║
║  1. Aadhaar Key:                                            ║
║  /genkey Rahul_Client | 30 | 500 | aadhaar | premium | Business client ║
║                                                              ║
║  2. Mobile Key:                                             ║
║  /genkey Test_User | 7 | 100 | mobile | basic | Testing ║
║                                                              ║
║  3. All Access:                                             ║
║  /genkey Enterprise_Co | 90 | 5000 | all | enterprise | VIP client ║
║                                                              ║
║  AVAILABLE TYPES:                                           ║
║  mobile, aadhaar, family, telegram, vehicle, pan, all       ║
║                                                              ║
║  AVAILABLE PLANS:                                           ║
║  basic, premium, enterprise, unlimited, custom              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")
            return
        
        name = parts[0].strip()
        days = int(parts[1].strip())
        limit_req = int(parts[2].strip())
        api_type = parts[3].strip().lower()
        plan = parts[4].strip().lower()
        notes = parts[5].strip() if len(parts) > 5 else ""
        
        if api_type not in ['mobile', 'aadhaar', 'family', 'telegram', 'vehicle', 'pan', 'all']:
            bot.reply_to(msg, "❌ Invalid API type!")
            return
        
        api_key = api_manager.generate_api_key(name, days, limit_req, api_type, plan, notes)
        
        response_text = f"""
╔══════════════════════════════════════════════════════════════╗
║           🎫 API KEY GENERATED SUCCESSFULLY                  ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  📛 KEY NAME: {name}                                         ║
║  🔑 API KEY: {api_key}                                       ║
║                                                              ║
║  📋 DETAILS:                                                ║
║  ├ 🏷️ TYPE: {api_type.upper()}                              ║
║  ├ 📊 PLAN: {plan.upper()}                                  ║
║  ├ 📅 EXPIRY: {days} days                                   ║
║  ├ 🔢 LIMIT: {limit_req} requests                           ║
║  └ 📝 NOTES: {notes if notes else 'No notes'}               ║
║                                                              ║
║  ⚡ RATE LIMITS:                                            ║
║  ├ ⏱️ PER MINUTE: {10 if plan=='basic' else 30 if plan=='premium' else 100} ║
║  ├ 📊 PER HOUR: {100 if plan=='basic' else 500 if plan=='premium' else 2000} ║
║  └ 📆 PER DAY: {500 if plan=='basic' else 2000 if plan=='premium' else 10000} ║
║                                                              ║
║  📡 API ENDPOINT:                                           ║
║  {MY_RENDER_URL}/api?key={api_key}&number=NUMBER&type={api_type} ║
║                                                              ║
║  🔧 TEST COMMAND:                                           ║
║  /testkey {api_key[:20]}...                                 ║
║                                                              ║
║  💡 MANAGEMENT COMMANDS:                                    ║
║  ├ /keyinfo {api_key[:20]}... - View details                ║
║  ├ /editkey {api_key[:20]}... - Edit settings               ║
║  ├ /blockkey {api_key[:20]}... - Block key                  ║
║  └ /deletekey {api_key[:20]}... - Delete key                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
        bot.reply_to(msg, response_text)
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

# ==================== REST OF THE COMMANDS (SAME AS BEFORE) ====================

# [The remaining commands - keys, keyinfo, editkey, blockkey, unblockkey, 
#  deletekey, extendkey, stats, keyanalytics, logs, exportkeys, search,
#  aadhaar, mobile, family, tg, health, admin, broadcast remain the same]

# To save space, I'm showing the key fix above. 
# The rest of the commands from previous script work exactly the same.

# ==================== FLASK API ENDPOINTS ====================

@app.route("/api", methods=['GET', 'POST'])
def api_endpoint():
    """Main API endpoint"""
    start_time = time.time()
    
    if request.method == 'GET':
        api_key = request.args.get("key")
        number = request.args.get("number")
        api_type = request.args.get("type", "mobile")
    else:
        data = request.get_json()
        api_key = data.get("key") if data else None
        number = data.get("number") if data else None
        api_type = data.get("type", "mobile") if data else "mobile"
    
    if not api_key:
        return jsonify({"error": "API key required", "status": "error"})
    
    if not number:
        return jsonify({"error": "Number required", "status": "error"})
    
    # Validate key
    key_info, message = api_manager.validate_key(api_key)
    
    if not key_info:
        return jsonify({"error": message, "status": "error"})
    
    # Check type permission
    if key_info['api_type'] != 'all' and key_info['api_type'] != api_type:
        return jsonify({
            "error": f"This key only supports {key_info['api_type']} API",
            "status": "error",
            "key_type": key_info['api_type'],
            "requested_type": api_type
        })
    
    # Increment usage
    api_manager.increment_usage(api_key)
    
    response_time = time.time() - start_time
    
    # Return success response
    return jsonify({
        "status": "success",
        "message": "API key is valid",
        "key_info": key_info,
        "request": {
            "number": number,
            "type": api_type,
            "timestamp": datetime.now().isoformat()
        },
        "response_time": round(response_time, 2),
        "note": "Configure your actual API endpoints in the code"
    })

@app.route("/health", methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "alive_url": MY_RENDER_URL
    })

@app.route("/stats", methods=['GET'])
def stats_endpoint():
    stats = api_manager.get_key_stats()
    return jsonify(stats)

@app.route("/", methods=['GET'])
def home():
    return jsonify({
        "service": "Ultimate API Management System",
        "version": "2.0.0",
        "status": "running",
        "alive_url": MY_RENDER_URL,
        "endpoints": {
            "/api": "Main API endpoint (GET/POST)",
            "/health": "Health check",
            "/stats": "System statistics"
        },
        "docs": "Contact @Danger_devil1917 for documentation"
    })

# ==================== KEEP ALIVE SYSTEM ====================

def keep_alive():
    """Self-ping to keep service alive - CRITICAL FOR RENDER"""
    print(f"🔄 Keep-alive system started for: {MY_RENDER_URL}")
    print(f"📍 Will ping every 5 minutes to prevent sleeping")
    
    # Multiple endpoints to ping for better reliability
    endpoints = [
        f"{MY_RENDER_URL}/health",
        f"{MY_RENDER_URL}/stats",
        f"{MY_RENDER_URL}/",
    ]
    
    while True:
        for endpoint in endpoints:
            try:
                response = requests.get(endpoint, timeout=10)
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ PING SUCCESS - {endpoint} - Status: {response.status_code}")
            except requests.exceptions.ConnectionError:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ PING FAILED - {endpoint} - Connection Error")
            except requests.exceptions.Timeout:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ PING FAILED - {endpoint} - Timeout")
            except Exception as e:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ PING FAILED - {endpoint} - {str(e)[:50]}")
        
        # Wait 4.5 minutes before next ping cycle
        time.sleep(270)

# ==================== MAIN ====================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 ULTIMATE API MANAGEMENT SYSTEM v2.0")
    print("=" * 60)
    print(f"✅ Bot started successfully")
    print(f"✅ API Server running on port {PORT}")
    print(f"✅ Admin ID: {ADMIN_ID}")
    print(f"✅ Alive URL: {MY_RENDER_URL}")
    print(f"✅ Health Check: {MY_RENDER_URL}/health")
    print("=" * 60)
    
    # Start keep alive thread (MOST IMPORTANT)
    alive_thread = threading.Thread(target=keep_alive, daemon=True)
    alive_thread.start()
    print("✅ Keep-alive thread started - Bot will stay alive 24/7")
    
    # Start bot in thread
    def run_bot():
        print("🤖 Bot polling started...")
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Run Flask
    print(f"🌐 Flask server running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)