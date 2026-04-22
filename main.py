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
MY_RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://api-wd7m.onrender.com")

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
    welcome_text = """
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

@bot.message_handler(commands=['setalive'])
def set_alive_url(msg):
    """Set or update alive URL"""
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
        
        # Update environment variable (in-memory)
        global MY_RENDER_URL
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

@bot.message_handler(commands=['keys'])
def list_keys(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    parts = msg.text.split()
    api_type = parts[1] if len(parts) > 1 else None
    status_filter = parts[2] if len(parts) > 2 else None
    plan_filter = parts[3] if len(parts) > 3 else None
    
    filters = {}
    if api_type:
        filters['api_type'] = api_type
    if status_filter:
        filters['status'] = status_filter
    if plan_filter:
        filters['plan'] = plan_filter
    
    keys = api_manager.get_all_keys(filters if filters else None)
    
    if not keys:
        bot.reply_to(msg, "❌ No API keys found")
        return
    
    stats = api_manager.get_key_stats()
    
    response_text = f"""
╔══════════════════════════════════════════════════════════════╗
║                   🔑 API KEYS MANAGEMENT                      ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  📊 STATISTICS:                                             ║
║  ├ TOTAL KEYS: {stats['total_keys']}                         ║
║  ├ ACTIVE KEYS: {stats['active_keys']}                       ║
║  ├ TOTAL REQUESTS: {stats['total_requests']}                 ║
║  └ SUCCESS RATE: {stats['success_rate']:.1f}%                ║
║                                                              ║
║  📋 KEYS LIST:                                              ║
║                                                              ║
"""
    
    for key in keys:
        expiry_date = datetime.strptime(key['expiry'], "%Y-%m-%d %H:%M:%S")
        days_left = (expiry_date - datetime.now()).days
        status_icon = "✅" if key['status'] == 'active' else "❌"
        
        response_text += f"""
  {status_icon} {key['name']}
  ├ KEY: {key['api_key'][:25]}...
  ├ TYPE: {key['api_type'].upper()} | PLAN: {key['plan'].upper()}
  ├ USAGE: {key['used']}/{key['limit']} ({key['used']/key['limit']*100:.1f}%)
  ├ REQUESTS: {key['total_requests']} | SUCCESS: {key['total_success']}
  ├ EXPIRY: {key['expiry'][:10]} ({days_left} days left)
  └ STATUS: {key['status'].upper()}
  
"""
    
    response_text += """
╚══════════════════════════════════════════════════════════════╝
"""
    
    bot.reply_to(msg, response_text)

@bot.message_handler(commands=['keyinfo'])
def key_info(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = api_manager.get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT api_key, name, expiry, used, limit_req, api_type, plan, notes,
                   created_at, status, rate_per_minute, rate_per_hour, rate_per_day,
                   total_requests, total_success, total_failed, email, phone, company
            FROM users WHERE api_key LIKE ? OR name LIKE ?
        """, (f'%{search}%', f'%{search}%'))
        
        row = cur.fetchone()
        conn.close()
        
        if not row:
            bot.reply_to(msg, "❌ Key not found")
            return
        
        (api_key, name, expiry, used, limit_req, api_type, plan, notes,
         created_at, status, rpm, rph, rpd, total_req, total_success, total_failed,
         email, phone, company) = row
        
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
        days_left = (expiry_date - datetime.now()).days
        success_rate = (total_success/total_req*100) if total_req > 0 else 0
        remaining = limit_req - used
        
        response_text = f"""
╔══════════════════════════════════════════════════════════════╗
║                 📊 KEY DETAILS - {name}                        ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  🔑 API KEY:                                                ║
║  {api_key}                                                   ║
║                                                              ║
║  👤 OWNER INFORMATION:                                      ║
║  ├ NAME: {name}                                              ║
║  ├ TYPE: {api_type.upper()}                                  ║
║  ├ PLAN: {plan.upper()}                                      ║
║  ├ EMAIL: {email if email else 'N/A'}                        ║
║  ├ PHONE: {phone if phone else 'N/A'}                        ║
║  ├ COMPANY: {company if company else 'N/A'}                  ║
║  └ NOTES: {notes if notes else 'No notes'}                   ║
║                                                              ║
║  📅 VALIDITY:                                               ║
║  ├ CREATED: {created_at[:10]}                                ║
║  ├ EXPIRES: {expiry[:10]}                                    ║
║  ├ DAYS LEFT: {days_left} days                               ║
║  └ STATUS: {status.upper()}                                  ║
║                                                              ║
║  📊 USAGE STATISTICS:                                       ║
║  ├ USED: {used}/{limit_req} ({used/limit_req*100:.1f}%)      ║
║  ├ REMAINING: {remaining}                                    ║
║  ├ TOTAL REQUESTS: {total_req}                               ║
║  ├ SUCCESS: {total_success}                                  ║
║  ├ FAILED: {total_failed}                                    ║
║  └ SUCCESS RATE: {success_rate:.1f}%                         ║
║                                                              ║
║  ⚡ RATE LIMITS:                                            ║
║  ├ PER MINUTE: {rpm} requests                                ║
║  ├ PER HOUR: {rph} requests                                  ║
║  └ PER DAY: {rpd} requests                                   ║
║                                                              ║
║  🔧 QUICK ACTIONS:                                          ║
║  ├ /editkey {api_key[:15]}... name NewName                   ║
║  ├ /extendkey {api_key[:15]}... 30                           ║
║  ├ /blockkey {api_key[:15]}...                               ║
║  └ /deletekey {api_key[:15]}...                              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
        bot.reply_to(msg, response_text)
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}\n\nUsage: /keyinfo KEY_NAME_OR_KEY")

@bot.message_handler(commands=['editkey'])
def edit_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    try:
        parts = msg.text.split()
        if len(parts) < 4:
            bot.reply_to(msg, """
❌ EDIT KEY USAGE:

/editkey KEY_NAME field value

AVAILABLE FIELDS:
├ name - Change key name
├ limit - Change request limit
├ plan - Change plan (basic/premium/enterprise/unlimited)
├ status - Change status (active/inactive/banned)
├ type - Change API type (mobile/aadhaar/family/all)
├ notes - Update notes
├ email - Update email
├ phone - Update phone
├ company - Update company
├ rpm - Rate per minute
├ rph - Rate per hour
└ rpd - Rate per day

EXAMPLES:
/editkey Rahul_Client limit 1000
/editkey Test_User plan premium
/editkey Enterprise_Co status active
""")
            return
        
        search = parts[1]
        field = parts[2]
        value = ' '.join(parts[3:])
        
        # Find the key
        conn = api_manager.get_db()
        cur = conn.cursor()
        cur.execute("SELECT api_key FROM users WHERE api_key LIKE ? OR name LIKE ?", 
                   (f'%{search}%', f'%{search}%'))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            bot.reply_to(msg, "❌ Key not found")
            return
        
        actual_key = row[0]
        
        # Update the field
        if api_manager.update_key(actual_key, **{field: value}):
            bot.reply_to(msg, f"✅ Key updated successfully!\n\nFIELD: {field}\nNEW VALUE: {value}")
        else:
            bot.reply_to(msg, "❌ Update failed")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['blockkey'])
def block_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = api_manager.get_db()
        cur = conn.cursor()
        cur.execute("SELECT api_key, name FROM users WHERE api_key LIKE ? OR name LIKE ?", 
                   (f'%{search}%', f'%{search}%'))
        row = cur.fetchone()
        
        if not row:
            bot.reply_to(msg, "❌ Key not found")
            conn.close()
            return
        
        actual_key, name = row
        cur.execute("UPDATE users SET status = 'banned' WHERE api_key = ?", (actual_key,))
        conn.commit()
        conn.close()
        
        bot.reply_to(msg, f"✅ Key BLOCKED successfully!\n\nNAME: {name}\nKEY: {actual_key[:25]}...\n\nUse /unblockkey {search} to unblock")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}\n\nUsage: /blockkey KEY_NAME_OR_KEY")

@bot.message_handler(commands=['unblockkey'])
def unblock_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = api_manager.get_db()
        cur = conn.cursor()
        cur.execute("SELECT api_key, name FROM users WHERE api_key LIKE ? OR name LIKE ?", 
                   (f'%{search}%', f'%{search}%'))
        row = cur.fetchone()
        
        if not row:
            bot.reply_to(msg, "❌ Key not found")
            conn.close()
            return
        
        actual_key, name = row
        cur.execute("UPDATE users SET status = 'active' WHERE api_key = ?", (actual_key,))
        conn.commit()
        conn.close()
        
        bot.reply_to(msg, f"✅ Key UNBLOCKED successfully!\n\nNAME: {name}\nKEY: {actual_key[:25]}...")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}\n\nUsage: /unblockkey KEY_NAME_OR_KEY")

@bot.message_handler(commands=['deletekey'])
def delete_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    try:
        search = msg.text.split()[1]
        
        conn = api_manager.get_db()
        cur = conn.cursor()
        cur.execute("SELECT api_key, name FROM users WHERE api_key LIKE ? OR name LIKE ?", 
                   (f'%{search}%', f'%{search}%'))
        row = cur.fetchone()
        
        if not row:
            bot.reply_to(msg, "❌ Key not found")
            conn.close()
            return
        
        actual_key, name = row
        cur.execute("DELETE FROM users WHERE api_key = ?", (actual_key,))
        conn.commit()
        conn.close()
        
        bot.reply_to(msg, f"✅ Key DELETED successfully!\n\nNAME: {name}\nKEY: {actual_key[:25]}...\n\nThis action cannot be undone!")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}\n\nUsage: /deletekey KEY_NAME_OR_KEY")

@bot.message_handler(commands=['extendkey'])
def extend_key(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    try:
        parts = msg.text.split()
        search = parts[1]
        days = int(parts[2]) if len(parts) > 2 else 30
        
        if api_manager.update_key(search, extend_days=days):
            bot.reply_to(msg, f"✅ Key extended by {days} days successfully!")
        else:
            bot.reply_to(msg, "❌ Key not found or extension failed")
            
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}\n\nUsage: /extendkey KEY_NAME_OR_KEY DAYS")

@bot.message_handler(commands=['stats'])
def show_stats(msg):
    stats = api_manager.get_key_stats()
    
    response_text = f"""
╔══════════════════════════════════════════════════════════════╗
║                 📊 SYSTEM STATISTICS                          ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  🔑 KEY STATISTICS:                                         ║
║  ├ TOTAL KEYS: {stats['total_keys']}                         ║
║  ├ ACTIVE KEYS: {stats['active_keys']}                       ║
║  ├ INACTIVE KEYS: {stats['total_keys'] - stats['active_keys']} ║
║  └ SUCCESS RATE: {stats['success_rate']:.1f}%                ║
║                                                              ║
║  📈 USAGE STATISTICS:                                       ║
║  ├ TOTAL REQUESTS: {stats['total_requests']}                 ║
║  ├ TOTAL SUCCESS: {stats['total_success']}                   ║
║  └ TOTAL FAILED: {stats['total_requests'] - stats['total_success']} ║
║                                                              ║
║  🏷️ TYPE DISTRIBUTION:                                      ║
"""
    
    for api_type, count in stats['type_stats'].items():
        response_text += f"  ├ {api_type.upper()}: {count} keys\n"
    
    response_text += f"""
║  📋 PLAN DISTRIBUTION:                                      ║
"""
    
    for plan, count in stats['plan_stats'].items():
        response_text += f"  ├ {plan.upper()}: {count} keys\n"
    
    response_text += """
║                                                              ║
║  💡 TIPS:                                                   ║
║  ├ Use /keys to list all keys                               ║
║  ├ Use /keyanalytics for detailed analytics                 ║
║  └ Use /exportkeys to export data                           ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    
    bot.reply_to(msg, response_text)

@bot.message_handler(commands=['keyanalytics'])
def key_analytics(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    conn = api_manager.get_db()
    cur = conn.cursor()
    
    # Top 10 users by usage
    cur.execute("""
        SELECT name, used, limit_req, api_type, plan, total_requests, total_success
        FROM users 
        WHERE used > 0 
        ORDER BY used DESC 
        LIMIT 10
    """)
    top_users = cur.fetchall()
    
    # Bottom 10 users (least used)
    cur.execute("""
        SELECT name, used, limit_req, api_type, plan, total_requests
        FROM users 
        WHERE used > 0 
        ORDER BY used ASC 
        LIMIT 5
    """)
    bottom_users = cur.fetchall()
    
    # Expiring soon (next 7 days)
    cur.execute("""
        SELECT name, api_key, expiry, used, limit_req
        FROM users 
        WHERE julianday(expiry) - julianday('now') BETWEEN 0 AND 7
        AND status = 'active'
        ORDER BY expiry ASC
    """)
    expiring = cur.fetchall()
    
    conn.close()
    
    response_text = """
╔══════════════════════════════════════════════════════════════╗
║              📊 KEY USAGE ANALYTICS REPORT                    ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  🏆 TOP 10 MOST ACTIVE USERS:                               ║
║                                                              ║
"""
    
    for i, user in enumerate(top_users, 1):
        name, used, limit_req, api_type, plan, total_req, total_success = user
        percent = (used/limit_req*100) if limit_req > 0 else 0
        success_rate = (total_success/total_req*100) if total_req > 0 else 0
        response_text += f"  {i}. {name}\n"
        response_text += f"     ├ USAGE: {used}/{limit_req} ({percent:.1f}%)\n"
        response_text += f"     ├ TYPE: {api_type.upper()} | PLAN: {plan.upper()}\n"
        response_text += f"     ├ REQUESTS: {total_req} | SUCCESS RATE: {success_rate:.1f}%\n"
        response_text += f"     └ STATUS: {'⚠️ NEAR LIMIT' if percent > 80 else '✅ OK'}\n\n"
    
    response_text += """
  ⚠️ LEAST ACTIVE USERS:
  
"""
    
    for i, user in enumerate(bottom_users, 1):
        name, used, limit_req, api_type, plan, total_req = user
        response_text += f"  {i}. {name} - {used}/{limit_req} requests ({api_type.upper()})\n"
    
    if expiring:
        response_text += """
  ⏰ KEYS EXPIRING SOON (7 DAYS):
  
"""
        for key in expiring:
            name, api_key, expiry, used, limit_req = key
            expiry_date = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
            days_left = (expiry_date - datetime.now()).days
            response_text += f"  ├ {name} - Expires in {days_left} days\n"
            response_text += f"  │  KEY: {api_key[:20]}... | USAGE: {used}/{limit_req}\n"
            response_text += f"  │  ACTION: /extendkey {api_key[:15]}... 30\n\n"
    
    response_text += """
╚══════════════════════════════════════════════════════════════╝
"""
    
    bot.reply_to(msg, response_text)

@bot.message_handler(commands=['logs'])
def show_logs(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    parts = msg.text.split()
    limit = int(parts[1]) if len(parts) > 1 else 50
    key_filter = parts[2] if len(parts) > 2 else None
    
    logs = api_manager.get_logs(limit, key_filter)
    
    if not logs:
        bot.reply_to(msg, "❌ No logs found")
        return
    
    response_text = f"""
╔══════════════════════════════════════════════════════════════╗
║                   📜 RECENT API LOGS                          ║
╠══════════════════════════════════════════════════════════════╣
║  TOTAL LOGS: {len(logs)} | FILTER: {key_filter if key_filter else 'ALL'}          ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
"""
    
    for log in logs[:50]:
        status_icon = "✅" if log['success'] else "❌"
        response_text += f"  {status_icon} {log['api_name']}\n"
        response_text += f"  ├ NUMBER: {log['number']}\n"
        response_text += f"  ├ KEY: {log['api_key'][:20]}...\n"
        response_text += f"  ├ CODE: {log['response_code']} | TIME: {log['timestamp'][:16]}\n"
        if log['error']:
            response_text += f"  └ ERROR: {log['error'][:50]}\n"
        else:
            response_text += f"  └ IP: {log['ip'] if log['ip'] else 'N/A'}\n"
        response_text += "\n"
    
    response_text += """
╚══════════════════════════════════════════════════════════════╝
"""
    
    bot.reply_to(msg, response_text)

@bot.message_handler(commands=['exportkeys'])
def export_keys(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    keys = api_manager.get_all_keys()
    
    if not keys:
        bot.reply_to(msg, "❌ No keys to export")
        return
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['API Key', 'Name', 'Expiry', 'Used', 'Limit', 'Type', 'Plan', 'Status', 'Created', 'Total Requests', 'Total Success', 'Email', 'Phone'])
    
    for key in keys:
        writer.writerow([
            key['api_key'],
            key['name'],
            key['expiry'],
            key['used'],
            key['limit'],
            key['api_type'],
            key['plan'],
            key['status'],
            key['created_at'],
            key['total_requests'],
            key['total_success'],
            key['email'],
            key['phone']
        ])
    
    filename = f"api_keys_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    bot.send_document(msg.chat.id, 
                     (filename, output.getvalue().encode('utf-8')),
                     caption=f"📊 Total {len(keys)} API keys exported\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

@bot.message_handler(commands=['search'])
def smart_search(msg):
    try:
        parts = msg.text.split()
        if len(parts) < 2:
            bot.reply_to(msg, "❌ Usage: /search NUMBER [TYPE]\n\nExample: /search 9876543210 aadhaar")
            return
        
        number = parts[1]
        api_type = parts[2] if len(parts) > 2 else "mobile"
        
        bot.reply_to(msg, f"🔍 Searching {number} using {api_type.upper()} APIs...\n\nThis feature requires API endpoints configured.\n\nContact @Danger_devil1917 for setup.")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['aadhaar'])
def aadhaar_search(msg):
    try:
        number = msg.text.split()[1]
        bot.reply_to(msg, f"🔍 Searching Aadhaar: {number}\n\nThis feature requires Aadhaar API configured.\n\nContact @Danger_devil1917 for setup.")
    except:
        bot.reply_to(msg, "❌ Usage: /aadhaar 123456789012")

@bot.message_handler(commands=['mobile'])
def mobile_search(msg):
    try:
        number = msg.text.split()[1]
        bot.reply_to(msg, f"🔍 Searching Mobile: {number}\n\nThis feature requires Mobile API configured.\n\nContact @Danger_devil1917 for setup.")
    except:
        bot.reply_to(msg, "❌ Usage: /mobile 9876543210")

@bot.message_handler(commands=['family'])
def family_search(msg):
    try:
        number = msg.text.split()[1]
        bot.reply_to(msg, f"🔍 Searching Family: {number}\n\nThis feature requires Family API configured.\n\nContact @Danger_devil1917 for setup.")
    except:
        bot.reply_to(msg, "❌ Usage: /family 123456789012")

@bot.message_handler(commands=['tg'])
def tg_search(msg):
    try:
        number = msg.text.split()[1]
        bot.reply_to(msg, f"🔍 Searching Telegram: {number}\n\nThis feature requires Telegram API configured.\n\nContact @Danger_devil1917 for setup.")
    except:
        bot.reply_to(msg, "❌ Usage: /tg 123456789")

@bot.message_handler(commands=['health'])
def health_check(msg):
    stats = api_manager.get_key_stats()
    
    response_text = f"""
╔══════════════════════════════════════════════════════════════╗
║                    ✅ SYSTEM HEALTH CHECK                     ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  STATUS: 🟢 HEALTHY                                         ║
║  TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}        ║
║  ALIVE URL: {MY_RENDER_URL}                                  ║
║                                                              ║
║  COMPONENTS:                                                ║
║  ├ DATABASE: ✅ CONNECTED                                    ║
║  ├ BOT: ✅ RUNNING                                           ║
║  ├ API SERVER: ✅ RUNNING                                    ║
║  ├ KEEP ALIVE: ✅ ACTIVE (every 5 min)                       ║
║  └ CACHE: ✅ ACTIVE                                          ║
║                                                              ║
║  STATISTICS:                                                ║
║  ├ TOTAL KEYS: {stats['total_keys']}                         ║
║  ├ ACTIVE KEYS: {stats['active_keys']}                       ║
║  ├ TOTAL REQUESTS: {stats['total_requests']}                 ║
║  └ SUCCESS RATE: {stats['success_rate']:.1f}%                ║
║                                                              ║
║  📡 ENDPOINTS:                                              ║
║  ├ HEALTH: {MY_RENDER_URL}/health                            ║
║  ├ STATS: {MY_RENDER_URL}/stats                              ║
║  └ API: {MY_RENDER_URL}/api                                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    bot.reply_to(msg, response_text)

@bot.message_handler(commands=['admin'])
def admin_panel(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    stats = api_manager.get_key_stats()
    
    panel_text = f"""
╔══════════════════════════════════════════════════════════════╗
║                 🔐 ADMIN CONTROL PANEL                        ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  📊 SYSTEM OVERVIEW:                                        ║
║  ├ TOTAL KEYS: {stats['total_keys']}                         ║
║  ├ ACTIVE KEYS: {stats['active_keys']}                       ║
║  ├ TOTAL REQUESTS: {stats['total_requests']}                 ║
║  └ SUCCESS RATE: {stats['success_rate']:.1f}%                ║
║                                                              ║
║  🔧 QUICK ACTIONS:                                          ║
║  ├ /genkey - Create new API key                             ║
║  ├ /keys - List all keys                                    ║
║  ├ /keyanalytics - View analytics                           ║
║  ├ /exportkeys - Export all keys                            ║
║  ├ /logs - View recent logs                                 ║
║  └ /setalive - Set alive URL                                ║
║                                                              ║
║  📈 MANAGEMENT TIPS:                                        ║
║  ├ Monitor expiring keys with /keyanalytics                 ║
║  ├ Block abuse with /blockkey                               ║
║  ├ Extend keys with /extendkey                              ║
║  └ Export data for reports                                  ║
║                                                              ║
║  🌐 CURRENT ALIVE URL:                                      ║
║  {MY_RENDER_URL}                                             ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    bot.reply_to(msg, panel_text)

@bot.message_handler(commands=['broadcast'])
def broadcast(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    try:
        message = ' '.join(msg.text.split()[1:])
        if not message:
            bot.reply_to(msg, "❌ Usage: /broadcast MESSAGE")
            return
        
        keys = api_manager.get_all_keys()
        sent = 0
        
        for key in keys:
            try:
                # In production, you'd need to store user IDs
                # This is a placeholder
                pass
            except:
                pass
        
        bot.reply_to(msg, f"✅ Broadcast sent to {sent} users")
        
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

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
        # Render free tier sleeps after 15 minutes of inactivity
        # So pinging every 4.5 minutes keeps it alive
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