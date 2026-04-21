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
import hmac
import base64
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import logging
# ==================== SELF PING ====================
def self_ping():
    """Keep the bot alive by pinging its own health endpoint"""
    
    # Ye URL apne actual Render app ke URL se replace karo
    # Example: https://your-bot-name.onrender.com
    YOUR_RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://api-wd7m.onrender.com")
    
    # Multiple endpoints to ping (better reliability)
    ping_endpoints = [
        f"{YOUR_RENDER_URL}/health",
        f"{YOUR_RENDER_URL}/",
        f"{YOUR_RENDER_URL}/stats"
    ]
    
    while True:
        for endpoint in ping_endpoints:
            try:
                response = requests.get(endpoint, timeout=10)
                print(f"✅ Self-ping successful: {endpoint} - Status: {response.status_code}")
            except Exception as e:
                print(f"❌ Self-ping failed: {endpoint} - Error: {e}")
        
        # Wait 5 minutes before next ping
        time.sleep(300)

# Start the ping thread
threading.Thread(target=self_ping, daemon=True).start()
# ==================== CONFIG ====================

BOT_TOKEN = "8290734722:AAHk7uyZ7DgeeiJKYy7Zlp-sjblpClQNJAQ"
ADMIN_ID = 7655738256

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== DATA CLASSES ====================

class APIType(Enum):
    MOBILE = "mobile"
    TG = "telegram"
    FAMILY = "family"
    AADHAAR = "aadhaar"
    VEHICLE = "vehicle"
    PAN = "pan"
    PASSPORT = "passport"
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
    rate_limit: int = 60
    created_at: str = ""
    last_used: str = ""
    total_requests: int = 0
    success_requests: int = 0
    fail_requests: int = 0
    avg_response_time: float = 0

# ==================== ADVANCED DATABASE ====================

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
        status TEXT DEFAULT 'active',
        plan TEXT DEFAULT 'basic',
        notes TEXT
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
        backup_url TEXT
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
    
    # API Group Mapping
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
        ip_address TEXT,
        user_agent TEXT,
        timestamp TEXT
    )
    """)
    
    # Rate Limiting
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
    
    # Blacklist
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blacklist(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip_address TEXT,
        api_key TEXT,
        reason TEXT,
        banned_until TEXT,
        created_at TEXT
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
    
    # Load Balancer
    cur.execute("""
    CREATE TABLE IF NOT EXISTS load_balancer(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_type TEXT UNIQUE,
        strategy TEXT DEFAULT 'round_robin',
        current_index INTEGER DEFAULT 0,
        last_updated TEXT
    )
    """)
    
    # Alert Rules
    cur.execute("""
    CREATE TABLE IF NOT EXISTS alert_rules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_name TEXT,
        metric TEXT,
        threshold REAL,
        condition TEXT,
        action TEXT,
        enabled INTEGER DEFAULT 1
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
    
    conn.commit()
    conn.close()
    print("✅ Database initialized with all tables")

init_db()

# ==================== ADVANCED API MANAGER ====================

class AdvancedAPIManager:
    """Complete API Management System with all features"""
    
    def __init__(self):
        self.cache = {}
        self.request_counts = defaultdict(list)
        self.alert_callbacks = []
        
    def get_db(self):
        return sqlite3.connect("api_system.db")
    
    # ========== API CRUD Operations ==========
    
    def add_api(self, name, url, api_type, **kwargs):
        """Add new API endpoint"""
        conn = self.get_db()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                INSERT INTO apis(
                    name, url, api_type, method, headers, params,
                    success_field, enabled, priority, timeout, 
                    rate_limit, created_at, backup_url
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, url, api_type,
                kwargs.get('method', 'GET'),
                json.dumps(kwargs.get('headers', {})),
                json.dumps(kwargs.get('params', {})),
                kwargs.get('success_field', ''),
                kwargs.get('enabled', 1),
                kwargs.get('priority', 1),
                kwargs.get('timeout', 15),
                kwargs.get('rate_limit', 60),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                kwargs.get('backup_url', '')
            ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Add API Error: {e}")
            conn.close()
            return False
    
    def remove_api(self, api_id):
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
    
    def update_api(self, api_id, **kwargs):
        """Update API endpoint"""
        conn = self.get_db()
        cur = conn.cursor()
        
        try:
            for key, value in kwargs.items():
                if key in ['name', 'url', 'api_type', 'method', 'success_field', 'backup_url']:
                    cur.execute(f"UPDATE apis SET {key} = ? WHERE id = ?", (value, api_id))
                elif key in ['enabled', 'priority', 'timeout', 'rate_limit']:
                    cur.execute(f"UPDATE apis SET {key} = ? WHERE id = ?", (int(value), api_id))
                elif key in ['headers', 'params']:
                    cur.execute(f"UPDATE apis SET {key} = ? WHERE id = ?", (json.dumps(value), api_id))
            
            conn.commit()
            conn.close()
            return True
        except:
            conn.close()
            return False
    
    def get_all_apis(self, api_type=None):
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
                'rate_limit': row[11],
                'created_at': row[12],
                'last_used': row[13],
                'total_requests': row[14],
                'success_requests': row[15],
                'fail_requests': row[16],
                'avg_response_time': row[17],
                'backup_url': row[18] if len(row) > 18 else ''
            })
        
        return apis
    
    def get_api_by_id(self, api_id):
        """Get API by ID"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM apis WHERE id = ?", (api_id,))
        row = cur.fetchone()
        conn.close()
        
        if row:
            return {
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
                'rate_limit': row[11],
                'created_at': row[12],
                'last_used': row[13],
                'total_requests': row[14],
                'success_requests': row[15],
                'fail_requests': row[16],
                'avg_response_time': row[17],
                'backup_url': row[18] if len(row) > 18 else ''
            }
        return None
    
    def update_api_status(self, api_id, enabled):
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
    
    def update_api_stats(self, api_id, success, response_time):
        """Update API statistics"""
        conn = self.get_db()
        cur = conn.cursor()
        
        cur.execute("""
            UPDATE apis 
            SET total_requests = total_requests + 1,
                success_requests = success_requests + ?,
                fail_requests = fail_requests + ?,
                last_used = ?,
                avg_response_time = (avg_response_time * total_requests + ?) / (total_requests + 1)
            WHERE id = ?
        """, (1 if success else 0, 0 if success else 1, 
              datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
              response_time, api_id))
        
        conn.commit()
        conn.close()
    
    # ========== User Management ==========
    
    def generate_api_key(self, days=30, limit=100, plan='basic', notes=''):
        """Generate new API key"""
        key = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users(api_key, expiry, used, limit_req, created_at, status, plan, notes)
            VALUES(?, ?, 0, ?, ?, 'active', ?, ?)
        """, (key, expiry, limit, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), plan, notes))
        conn.commit()
        conn.close()
        
        return key
    
    def validate_api_key(self, api_key):
        """Validate API key and return status"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT expiry, used, limit_req, status FROM users WHERE api_key = ?", (api_key,))
        user = cur.fetchone()
        conn.close()
        
        if not user:
            return 'invalid', None
        
        expiry, used, limit_req, status = user
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
        
        if datetime.now() > expiry_date:
            return 'expired', None
        if used >= limit_req:
            return 'limit_reached', None
        if status != 'active':
            return 'inactive', None
        
        return 'active', {'expiry': expiry, 'used': used, 'limit': limit_req}
    
    def increment_api_usage(self, api_key):
        """Increment API usage counter"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET used = used + 1 WHERE api_key = ?", (api_key,))
        conn.commit()
        conn.close()
    
    def get_all_users(self):
        """Get all API users"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT api_key, expiry, used, limit_req, status, plan, created_at FROM users")
        rows = cur.fetchall()
        conn.close()
        
        users = []
        for row in rows:
            users.append({
                'api_key': row[0],
                'expiry': row[1],
                'used': row[2],
                'limit': row[3],
                'status': row[4],
                'plan': row[5],
                'created_at': row[6]
            })
        return users
    
    def update_user_status(self, api_key, status):
        """Update user status"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = ? WHERE api_key = ?", (status, api_key))
        conn.commit()
        conn.close()
    
    def delete_user(self, api_key):
        """Delete user"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE api_key = ?", (api_key,))
        conn.commit()
        conn.close()
    
    # ========== Rate Limiting ==========
    
    def check_rate_limit(self, api_key, endpoint):
        """Check if request is within rate limit"""
        conn = self.get_db()
        cur = conn.cursor()
        
        now = datetime.now()
        reset_time = (now + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
        
        cur.execute("""
            SELECT requests, reset_time FROM rate_limits 
            WHERE api_key = ? AND endpoint = ?
        """, (api_key, endpoint))
        
        row = cur.fetchone()
        
        if not row:
            cur.execute("""
                INSERT INTO rate_limits(api_key, endpoint, requests, reset_time)
                VALUES(?, ?, 1, ?)
            """, (api_key, endpoint, reset_time))
            conn.commit()
            conn.close()
            return True, 59
        
        requests_count, reset = row
        reset_dt = datetime.strptime(reset, "%Y-%m-%d %H:%M:%S")
        
        if now > reset_dt:
            cur.execute("""
                UPDATE rate_limits SET requests = 1, reset_time = ?
                WHERE api_key = ? AND endpoint = ?
            """, (reset_time, api_key, endpoint))
            conn.commit()
            conn.close()
            return True, 59
        
        remaining = 60 - requests_count
        
        if requests_count >= 60:
            conn.close()
            return False, 0
        
        cur.execute("""
            UPDATE rate_limits SET requests = requests + 1
            WHERE api_key = ? AND endpoint = ?
        """, (api_key, endpoint))
        conn.commit()
        conn.close()
        
        return True, remaining - 1
    
    # ========== Blacklist/Whitelist ==========
    
    def add_to_blacklist(self, ip_address, api_key, reason, minutes=60):
        """Add IP or API key to blacklist"""
        conn = self.get_db()
        cur = conn.cursor()
        
        banned_until = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
        
        cur.execute("""
            INSERT OR REPLACE INTO blacklist(ip_address, api_key, reason, banned_until, created_at)
            VALUES(?, ?, ?, ?, ?)
        """, (ip_address, api_key, reason, banned_until, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        conn.commit()
        conn.close()
    
    def is_blacklisted(self, ip_address=None, api_key=None):
        """Check if IP or API key is blacklisted"""
        conn = self.get_db()
        cur = conn.cursor()
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if ip_address:
            cur.execute("""
                SELECT banned_until FROM blacklist 
                WHERE ip_address = ? AND banned_until > ?
            """, (ip_address, now))
            row = cur.fetchone()
            if row:
                conn.close()
                return True
        
        if api_key:
            cur.execute("""
                SELECT banned_until FROM blacklist 
                WHERE api_key = ? AND banned_until > ?
            """, (api_key, now))
            row = cur.fetchone()
            if row:
                conn.close()
                return True
        
        conn.close()
        return False
    
    def remove_from_blacklist(self, ip_address=None, api_key=None):
        """Remove from blacklist"""
        conn = self.get_db()
        cur = conn.cursor()
        
        if ip_address:
            cur.execute("DELETE FROM blacklist WHERE ip_address = ?", (ip_address,))
        elif api_key:
            cur.execute("DELETE FROM blacklist WHERE api_key = ?", (api_key,))
        
        conn.commit()
        conn.close()
    
    # ========== Cache Management ==========
    
    def get_cached(self, key):
        """Get cached data"""
        conn = self.get_db()
        cur = conn.cursor()
        
        cur.execute("SELECT data, expires_at FROM cache WHERE cache_key = ?", (key,))
        row = cur.fetchone()
        conn.close()
        
        if row:
            data, expires_at = row
            if datetime.now() < datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S"):
                return json.loads(data)
        
        return None
    
    def set_cache(self, key, data, ttl_seconds=300):
        """Cache data with TTL"""
        conn = self.get_db()
        cur = conn.cursor()
        
        expires_at = (datetime.now() + timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%d %H:%M:%S")
        
        cur.execute("""
            INSERT OR REPLACE INTO cache(cache_key, data, expires_at, created_at)
            VALUES(?, ?, ?, ?)
        """, (key, json.dumps(data), expires_at, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        conn.commit()
        conn.close()
    
    # ========== API Fetch with Smart Logic ==========
    
    def fetch_api(self, api, number):
        """Fetch data from a single API with backup support"""
        url = api['url'].format(number=number)
        start_time = time.time()
        
        try:
            headers = api.get('headers', {})
            headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            
            if api['method'] == 'GET':
                response = requests.get(url, headers=headers, timeout=api['timeout'], verify=False)
            else:
                response = requests.post(url, headers=headers, timeout=api['timeout'], verify=False)
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                self.update_api_stats(api['id'], True, response_time)
                self.log_request(api['id'], api['name'], number, response.status_code, response_time, True)
                return data
            
            # Try backup URL if available
            if api.get('backup_url'):
                backup_url = api['backup_url'].format(number=number)
                response = requests.get(backup_url, headers=headers, timeout=api['timeout'], verify=False)
                if response.status_code == 200:
                    data = response.json()
                    self.update_api_stats(api['id'], True, response_time)
                    self.log_request(api['id'], api['name'], number, response.status_code, response_time, True)
                    return data
            
            self.update_api_stats(api['id'], False, response_time)
            self.log_request(api['id'], api['name'], number, response.status_code, response_time, False, f"HTTP {response.status_code}")
                           
        except Exception as e:
            response_time = time.time() - start_time
            self.update_api_stats(api['id'], False, response_time)
            self.log_request(api['id'], api['name'], number, 0, response_time, False, str(e)[:100])
        
        return None
    
    def log_request(self, api_id, api_name, number, response_code, response_time, success, error=""):
        """Log API request"""
        conn = self.get_db()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO api_logs(api_id, api_name, request_number, response_code, 
                                response_time, success, error_message, timestamp)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """, (api_id, api_name, number, response_code, response_time, 
              1 if success else 0, error, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        conn.commit()
        conn.close()
    
    def smart_fetch(self, number, api_type, use_cache=True):
        """Smart fetch with caching, fallback, and load balancing"""
        
        # Check cache first
        if use_cache:
            cache_key = f"{api_type}:{number}"
            cached_data = self.get_cached(cache_key)
            if cached_data:
                logger.info(f"Cache hit for {number} ({api_type})")
                return cached_data
        
        # Get enabled APIs
        apis = self.get_all_apis(api_type)
        enabled_apis = [a for a in apis if a['enabled']]
        
        if not enabled_apis:
            return {"error": f"No enabled API found for type: {api_type}"}
        
        # Sort by priority
        enabled_apis.sort(key=lambda x: x['priority'])
        
        # Try each API
        for api in enabled_apis:
            result = self.fetch_api(api, number)
            if result:
                # Cache successful result
                if use_cache:
                    self.set_cache(cache_key, result, ttl_seconds=300)
                return result
        
        return {"error": f"All APIs failed for type: {api_type}"}
    
    # ========== Statistics & Analytics ==========
    
    def get_system_stats(self):
        """Get complete system statistics"""
        apis = self.get_all_apis()
        users = self.get_all_users()
        
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM api_logs WHERE timestamp > datetime('now', '-24 hours')")
        last_24h = cur.fetchone()[0]
        conn.close()
        
        return {
            'total_apis': len(apis),
            'active_apis': len([a for a in apis if a['enabled']]),
            'total_requests': sum(a['total_requests'] for a in apis),
            'total_success': sum(a['success_requests'] for a in apis),
            'total_users': len(users),
            'active_users': len([u for u in users if u['status'] == 'active']),
            'requests_24h': last_24h,
            'success_rate': (sum(a['success_requests'] for a in apis) / sum(a['total_requests'] for a in apis) * 100) if sum(a['total_requests'] for a in apis) > 0 else 0
        }
    
    def get_api_logs(self, limit=100):
        """Get recent API logs"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, api_name, request_number, response_code, success, error_message, timestamp
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
                'response_code': row[3],
                'success': bool(row[4]),
                'error': row[5],
                'timestamp': row[6]
            })
        return logs
    
    def clear_logs(self, days=30):
        """Clear old logs"""
        conn = self.get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM api_logs WHERE timestamp < datetime('now', ?)", (f'-{days} days',))
        conn.commit()
        conn.close()

api_manager = AdvancedAPIManager()

# ==================== ADVANCED BOT COMMANDS ====================

def is_admin(user_id):
    return user_id == ADMIN_ID

# Main Admin Panel
@bot.message_handler(commands=['admin'])
def admin_panel(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Unauthorized access")
        return
    
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    
    buttons = [
        # API Management
        telebot.types.InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard"),
        telebot.types.InlineKeyboardButton("➕ Add API", callback_data="admin_add_api"),
        telebot.types.InlineKeyboardButton("📋 List APIs", callback_data="admin_list_apis"),
        telebot.types.InlineKeyboardButton("✏️ Edit API", callback_data="admin_edit_api"),
        telebot.types.InlineKeyboardButton("🗑️ Remove API", callback_data="admin_remove_api"),
        telebot.types.InlineKeyboardButton("🔌 Toggle API", callback_data="admin_toggle_api"),
        
        # User Management
        telebot.types.InlineKeyboardButton("👥 Users", callback_data="admin_users"),
        telebot.types.InlineKeyboardButton("🎫 Generate Key", callback_data="admin_genkey"),
        telebot.types.InlineKeyboardButton("📝 List Keys", callback_data="admin_list_keys"),
        telebot.types.InlineKeyboardButton("🔑 Edit Key", callback_data="admin_edit_key"),
        
        # Security
        telebot.types.InlineKeyboardButton("🚫 Blacklist", callback_data="admin_blacklist"),
        telebot.types.InlineKeyboardButton("✅ Whitelist", callback_data="admin_whitelist"),
        
        # Analytics
        telebot.types.InlineKeyboardButton("📈 Analytics", callback_data="admin_analytics"),
        telebot.types.InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
        telebot.types.InlineKeyboardButton("📜 Logs", callback_data="admin_logs"),
        
        # System
        telebot.types.InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings"),
        telebot.types.InlineKeyboardButton("🔄 Backup", callback_data="admin_backup"),
        telebot.types.InlineKeyboardButton("📤 Export", callback_data="admin_export"),
        telebot.types.InlineKeyboardButton("🧹 Clear Cache", callback_data="admin_clear_cache"),
        
        # Testing
        telebot.types.InlineKeyboardButton("🔍 Test API", callback_data="admin_test_api"),
        telebot.types.InlineKeyboardButton("🚀 Smart Search", callback_data="admin_smart_search"),
    ]
    
    for btn in buttons:
        markup.add(btn)
    
    stats = api_manager.get_system_stats()
    
    bot.send_message(msg.chat.id, 
        f"🔐 ADVANCED API MANAGEMENT SYSTEM\n\n"
        f"📊 System Status:\n"
        f"├ APIs: {stats['total_apis']} total, {stats['active_apis']} active\n"
        f"├ Users: {stats['total_users']} total, {stats['active_users']} active\n"
        f"├ Requests: {stats['total_requests']} total, {stats['requests_24h']} last 24h\n"
        f"└ Success Rate: {stats['success_rate']:.1f}%\n\n"
        f"Select an option below:",
        reply_markup=markup)

@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, 
        "🤖 ULTIMATE API MANAGEMENT BOT\n\n"
        "📌 Available Commands:\n\n"
        "🔹 API Management:\n"
        "  /addapi - Add new API endpoint\n"
        "  /listapis - List all APIs\n"
        "  /delapi - Delete API\n"
        "  /toggleapi - Enable/Disable API\n"
        "  /editapi - Edit API settings\n"
        "  /testapi - Test API endpoint\n\n"
        "🔹 User Management:\n"
        "  /genkey - Generate API key\n"
        "  /keys - List all keys\n"
        "  /delkey - Delete API key\n"
        "  /editkey - Edit key settings\n\n"
        "🔹 Search:\n"
        "  /search - Smart search\n"
        "  /mobile - Mobile number search\n"
        "  /aadhaar - Aadhaar search\n"
        "  /family - Family search\n"
        "  /tg - Telegram ID search\n\n"
        "🔹 System:\n"
        "  /stats - System statistics\n"
        "  /logs - Recent logs\n"
        "  /health - Health check\n"
        "  /admin - Admin panel\n\n"
        "📡 API Endpoint:\n"
        "  GET /api?key=YOUR_KEY&number=NUMBER&type=TYPE\n\n"
        "💡 Need help? Contact @Danger_devil1917")

@bot.message_handler(commands=['search'])
def smart_search(msg):
    try:
        parts = msg.text.split()
        if len(parts) < 2:
            bot.reply_to(msg, "❌ Usage: /search NUMBER\n\nExample: /search 9876543210")
            return
        
        number = parts[1]
        api_type = parts[2] if len(parts) > 2 else "mobile"
        
        bot.reply_to(msg, f"🔍 Smart searching for {number} using {api_type} APIs...")
        
        result = api_manager.smart_fetch(number, api_type)
        
        if result and 'error' not in result:
            bot.reply_to(msg, f"✅ RESULT FOUND\n\n{json.dumps(result, indent=2)[:3000]}")
        else:
            bot.reply_to(msg, f"❌ No data found for {number}\n\nError: {result.get('error', 'Unknown')}")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['mobile'])
def mobile_search(msg):
    try:
        number = msg.text.split()[1]
        bot.reply_to(msg, f"🔍 Searching mobile: {number}")
        result = api_manager.smart_fetch(number, 'mobile')
        if result and 'error' not in result:
            bot.reply_to(msg, f"✅ Mobile Data\n\n{json.dumps(result, indent=2)[:2000]}")
        else:
            bot.reply_to(msg, f"❌ No data found")
    except:
        bot.reply_to(msg, "❌ Usage: /mobile 9876543210")

@bot.message_handler(commands=['aadhaar'])
def aadhaar_search(msg):
    try:
        number = msg.text.split()[1]
        bot.reply_to(msg, f"🔍 Searching Aadhaar: {number}")
        result = api_manager.smart_fetch(number, 'aadhaar')
        if result and 'error' not in result:
            bot.reply_to(msg, f"✅ Aadhaar Data\n\n{json.dumps(result, indent=2)[:2000]}")
        else:
            bot.reply_to(msg, f"❌ No data found")
    except:
        bot.reply_to(msg, "❌ Usage: /aadhaar 123456789012")

@bot.message_handler(commands=['family'])
def family_search(msg):
    try:
        number = msg.text.split()[1]
        bot.reply_to(msg, f"🔍 Searching Family: {number}")
        result = api_manager.smart_fetch(number, 'family')
        if result and 'error' not in result:
            bot.reply_to(msg, f"✅ Family Data\n\n{json.dumps(result, indent=2)[:2000]}")
        else:
            bot.reply_to(msg, f"❌ No data found")
    except:
        bot.reply_to(msg, "❌ Usage: /family 123456789012")

@bot.message_handler(commands=['tg'])
def tg_search(msg):
    try:
        number = msg.text.split()[1]
        bot.reply_to(msg, f"🔍 Searching Telegram: {number}")
        result = api_manager.smart_fetch(number, 'telegram')
        if result and 'error' not in result:
            bot.reply_to(msg, f"✅ Telegram Data\n\n{json.dumps(result, indent=2)[:2000]}")
        else:
            bot.reply_to(msg, f"❌ No data found")
    except:
        bot.reply_to(msg, "❌ Usage: /tg 123456789")

@bot.message_handler(commands=['addapi'])
def add_api_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split('|')
        if len(parts) < 3:
            bot.reply_to(msg, 
                "❌ USAGE:\n"
                "/addapi name|url|type\n\n"
                "OPTIONAL:\n"
                "|method|priority|timeout|rate_limit\n\n"
                "EXAMPLE:\n"
                "/addapi MobileAPI|https://api.com/{number}|mobile|GET|1|15|60")
            return
        
        name = parts[0].strip()
        url = parts[1].strip()
        api_type = parts[2].strip()
        method = parts[3].strip() if len(parts) > 3 else 'GET'
        priority = int(parts[4]) if len(parts) > 4 else 1
        timeout = int(parts[5]) if len(parts) > 5 else 15
        rate_limit = int(parts[6]) if len(parts) > 6 else 60
        
        if api_manager.add_api(name, url, api_type, method=method, priority=priority, timeout=timeout, rate_limit=rate_limit):
            bot.reply_to(msg, f"✅ API ADDED\n\nName: {name}\nType: {api_type}\nURL: {url}\nPriority: {priority}\nTimeout: {timeout}s\nRate Limit: {rate_limit}/min")
        else:
            bot.reply_to(msg, "❌ Failed to add API. Name might exist.")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['listapis'])
def list_apis_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    
    apis = api_manager.get_all_apis()
    
    if not apis:
        bot.reply_to(msg, "❌ No APIs found")
        return
    
    text = "📋 ALL APIs\n\n"
    for api in apis:
        status = "✅ ACTIVE" if api['enabled'] else "❌ DISABLED"
        text += f"ID: {api['id']}\n"
        text += f"Name: {api['name']}\n"
        text += f"Type: {api['api_type']}\n"
        text += f"Status: {status}\n"
        text += f"Requests: {api['total_requests']} (Success: {api['success_requests']})\n"
        text += f"Priority: {api['priority']} | Timeout: {api['timeout']}s\n"
        text += "-------------------\n"
    
    bot.reply_to(msg, text[:4000])

@bot.message_handler(commands=['delapi'])
def del_api_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        api_id = int(msg.text.split()[1])
        if api_manager.remove_api(api_id):
            bot.reply_to(msg, f"✅ API ID {api_id} deleted")
        else:
            bot.reply_to(msg, "❌ Failed to delete")
    except:
        bot.reply_to(msg, "❌ Usage: /delapi API_ID")

@bot.message_handler(commands=['toggleapi'])
def toggle_api_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        api_id = int(msg.text.split()[1])
        api = api_manager.get_api_by_id(api_id)
        if api:
            new_status = not api['enabled']
            api_manager.update_api_status(api_id, new_status)
            bot.reply_to(msg, f"✅ API {api['name']} is now {'ENABLED' if new_status else 'DISABLED'}")
        else:
            bot.reply_to(msg, "❌ API not found")
    except:
        bot.reply_to(msg, "❌ Usage: /toggleapi API_ID")

@bot.message_handler(commands=['editapi'])
def edit_api_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split('|')
        if len(parts) < 2:
            bot.reply_to(msg, "❌ Usage: /editapi API_ID|field|value\n\nFields: name, url, type, method, priority, timeout, rate_limit, enabled")
            return
        
        api_id = int(parts[0].strip())
        field = parts[1].strip()
        value = parts[2].strip()
        
        if field == 'enabled':
            value = value.lower() == 'true' or value == '1'
        elif field in ['priority', 'timeout', 'rate_limit']:
            value = int(value)
        
        if api_manager.update_api(api_id, **{field: value}):
            bot.reply_to(msg, f"✅ API {api_id} updated: {field} = {value}")
        else:
            bot.reply_to(msg, "❌ Update failed")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['testapi'])
def test_api_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        api_id = int(parts[1])
        test_number = parts[2] if len(parts) > 2 else "9999999999"
        
        api = api_manager.get_api_by_id(api_id)
        if not api:
            bot.reply_to(msg, "❌ API not found")
            return
        
        bot.reply_to(msg, f"🔄 Testing {api['name']} with {test_number}...")
        
        result = api_manager.fetch_api(api, test_number)
        
        if result:
            bot.reply_to(msg, f"✅ TEST SUCCESSFUL\n\nResponse:\n{json.dumps(result, indent=2)[:2000]}")
        else:
            bot.reply_to(msg, f"❌ TEST FAILED\n\nAPI: {api['name']}\nCheck logs for details")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['genkey'])
def genkey_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        days = int(parts[1]) if len(parts) > 1 else 30
        limit = int(parts[2]) if len(parts) > 2 else 100
        plan = parts[3] if len(parts) > 3 else 'basic'
        
        key = api_manager.generate_api_key(days, limit, plan)
        
        bot.reply_to(msg, 
            f"🎫 NEW API KEY GENERATED\n\n"
            f"Key: {key}\n"
            f"Expiry: {days} days\n"
            f"Limit: {limit} requests\n"
            f"Plan: {plan}\n\n"
            f"Usage: https://your-domain.onrender.com/api?key={key}&number=9876543210")
    except:
        bot.reply_to(msg, "❌ Usage: /genkey [days] [limit] [plan]\n\nExample: /genkey 30 100 premium")

@bot.message_handler(commands=['keys'])
def keys_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    
    users = api_manager.get_all_users()
    
    if not users:
        bot.reply_to(msg, "❌ No API keys found")
        return
    
    text = "📋 API KEYS\n\n"
    for user in users:
        text += f"Key: {user['api_key'][:16]}...\n"
        text += f"Expiry: {user['expiry']}\n"
        text += f"Usage: {user['used']}/{user['limit']}\n"
        text += f"Status: {user['status']} | Plan: {user['plan']}\n"
        text += "-------------------\n"
    
    bot.reply_to(msg, text[:4000])

@bot.message_handler(commands=['delkey'])
def delkey_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        key = msg.text.split()[1]
        api_manager.delete_user(key)
        bot.reply_to(msg, f"✅ API key deleted")
    except:
        bot.reply_to(msg, "❌ Usage: /delkey API_KEY")

@bot.message_handler(commands=['editkey'])
def editkey_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        parts = msg.text.split()
        key = parts[1]
        field = parts[2]
        value = parts[3]
        
        if field == 'status':
            api_manager.update_user_status(key, value)
            bot.reply_to(msg, f"✅ Key {key[:16]}... status updated to {value}")
        else:
            bot.reply_to(msg, "❌ Fields: status (active/inactive)")
    except:
        bot.reply_to(msg, "❌ Usage: /editkey API_KEY status active/inactive")

@bot.message_handler(commands=['stats'])
def stats_cmd(msg):
    stats = api_manager.get_system_stats()
    
    bot.reply_to(msg,
        f"📊 SYSTEM STATISTICS\n\n"
        f"APIs:\n"
        f"├ Total: {stats['total_apis']}\n"
        f"├ Active: {stats['active_apis']}\n"
        f"└ Success Rate: {stats['success_rate']:.1f}%\n\n"
        f"Requests:\n"
        f"├ Total: {stats['total_requests']}\n"
        f"└ Last 24h: {stats['requests_24h']}\n\n"
        f"Users:\n"
        f"├ Total: {stats['total_users']}\n"
        f"└ Active: {stats['active_users']}")

@bot.message_handler(commands=['logs'])
def logs_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    
    logs = api_manager.get_api_logs(50)
    
    if not logs:
        bot.reply_to(msg, "No logs found")
        return
    
    text = "📜 RECENT LOGS\n\n"
    for log in logs:
        status = "✅" if log['success'] else "❌"
        text += f"{status} {log['api_name']} - {log['number']}\n"
        text += f"   Code: {log['response_code']} | {log['timestamp'][:16]}\n"
    
    bot.reply_to(msg, text[:4000])

@bot.message_handler(commands=['health'])
def health_cmd(msg):
    stats = api_manager.get_system_stats()
    bot.reply_to(msg,
        f"✅ SYSTEM HEALTHY\n\n"
        f"Uptime: Active\n"
        f"APIs: {stats['active_apis']}/{stats['total_apis']} active\n"
        f"Database: Connected\n"
        f"Cache: Active\n"
        f"Rate Limiter: Active")

# ==================== CALLBACK HANDLER ====================

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Unauthorized")
        return
    
    if call.data == "admin_dashboard":
        stats = api_manager.get_system_stats()
        bot.edit_message_text(
            f"📊 DASHBOARD\n\n"
            f"📌 APIs: {stats['total_apis']} ({stats['active_apis']} active)\n"
            f"📈 Requests: {stats['total_requests']} total, {stats['requests_24h']} today\n"
            f"👥 Users: {stats['total_users']} ({stats['active_users']} active)\n"
            f"✅ Success Rate: {stats['success_rate']:.1f}%\n"
            f"💾 Cache: Active\n"
            f"🛡️ Rate Limiter: Active",
            call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_list_apis":
        apis = api_manager.get_all_apis()
        if not apis:
            bot.edit_message_text("No APIs found", call.message.chat.id, call.message.message_id)
            return
        
        text = "📋 ALL APIS\n\n"
        for api in apis[:20]:
            status = "✅" if api['enabled'] else "❌"
            text += f"{status} ID:{api['id']} | {api['name']}\n"
            text += f"   Type: {api['api_type']} | Reqs: {api['total_requests']}\n\n"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_stats":
        stats = api_manager.get_system_stats()
        bot.edit_message_text(
            f"📊 SYSTEM STATISTICS\n\n"
            f"APIs: {stats['total_apis']}\n"
            f"Active APIs: {stats['active_apis']}\n"
            f"Total Requests: {stats['total_requests']}\n"
            f"Success Rate: {stats['success_rate']:.1f}%\n"
            f"Requests (24h): {stats['requests_24h']}\n"
            f"Total Users: {stats['total_users']}\n"
            f"Active Users: {stats['active_users']}",
            call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_users":
        users = api_manager.get_all_users()
        if not users:
            bot.edit_message_text("No users found", call.message.chat.id, call.message.message_id)
            return
        
        text = "👥 USERS\n\n"
        for user in users[:15]:
            text += f"Key: {user['api_key'][:16]}...\n"
            text += f"Plan: {user['plan']} | Used: {user['used']}/{user['limit']}\n"
            text += f"Status: {user['status']} | Exp: {user['expiry'][:10]}\n"
            text += "-------------------\n"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_genkey":
        key = api_manager.generate_api_key(30, 100, 'premium')
        bot.edit_message_text(
            f"🎫 NEW API KEY\n\nKey: {key}\nExpiry: 30 days\nLimit: 100 requests\nPlan: Premium",
            call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_list_keys":
        users = api_manager.get_all_users()
        if not users:
            bot.edit_message_text("No keys found", call.message.chat.id, call.message.message_id)
            return
        
        text = "🔑 API KEYS\n\n"
        for user in users[:15]:
            text += f"{user['api_key'][:20]}... | {user['status']}\n"
            text += f"  Used: {user['used']}/{user['limit']} | Exp: {user['expiry'][:10]}\n\n"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_analytics":
        logs = api_manager.get_api_logs(100)
        if not logs:
            bot.edit_message_text("No analytics data", call.message.chat.id, call.message.message_id)
            return
        
        # Group by API
        api_stats = {}
        for log in logs:
            name = log['api_name']
            if name not in api_stats:
                api_stats[name] = {'total': 0, 'success': 0}
            api_stats[name]['total'] += 1
            if log['success']:
                api_stats[name]['success'] += 1
        
        text = "📈 ANALYTICS (Last 100 requests)\n\n"
        for name, stats in api_stats.items():
            rate = (stats['success']/stats['total']*100) if stats['total'] > 0 else 0
            text += f"📌 {name}\n"
            text += f"   Requests: {stats['total']}\n"
            text += f"   Success Rate: {rate:.1f}%\n\n"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_logs":
        logs = api_manager.get_api_logs(30)
        if not logs:
            bot.edit_message_text("No logs", call.message.chat.id, call.message.message_id)
            return
        
        text = "📜 RECENT LOGS\n\n"
        for log in logs[:15]:
            status = "✅" if log['success'] else "❌"
            text += f"{status} {log['api_name']}\n"
            text += f"   {log['number']} | {log['timestamp'][:16]}\n"
            if log['error']:
                text += f"   Error: {log['error'][:50]}\n"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_clear_cache":
        # Clear in-memory and database cache
        api_manager.cache = {}
        bot.edit_message_text("✅ Cache cleared successfully", call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_backup":
        # Create backup
        backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        data = {
            'apis': api_manager.get_all_apis(),
            'users': api_manager.get_all_users(),
            'timestamp': datetime.now().isoformat()
        }
        
        with open(backup_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        bot.edit_message_text(f"✅ Backup created: {backup_file}", call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_export":
        logs = api_manager.get_api_logs(500)
        export_file = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(export_file, 'w') as f:
            json.dump(logs, f, indent=2)
        
        bot.edit_message_text(f"✅ Exported {len(logs)} logs to {export_file}", call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_settings":
        bot.edit_message_text(
            "⚙️ SYSTEM SETTINGS\n\n"
            "Current Configuration:\n"
            "├ Cache TTL: 300 seconds\n"
            "├ Rate Limit: 60/min per key\n"
            "├ Max Timeout: 30 seconds\n"
            "├ Log Retention: 30 days\n"
            "└ Backup: Manual\n\n"
            "Use commands to modify settings:\n"
            "/setcache [seconds]\n"
            "/setratelimit [limit]\n"
            "/settimeout [seconds]",
            call.message.chat.id, call.message.message_id)
    
    elif call.data == "admin_smart_search":
        bot.edit_message_text(
            "🔍 SMART SEARCH\n\n"
            "Use: /search NUMBER [TYPE]\n\n"
            "Types available:\n"
            "├ mobile - Phone number lookup\n"
            "├ aadhaar - Aadhaar card info\n"
            "├ family - Family details\n"
            "└ telegram - Telegram ID lookup\n\n"
            "Example: /search 9876543210 mobile",
            call.message.chat.id, call.message.message_id)

# ==================== FLASK API ENDPOINTS ====================

@app.route("/api", methods=['GET', 'POST'])
def api_endpoint():
    """Main API endpoint"""
    start_time = time.time()
    
    # Get client IP
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    
    # Parse request
    if request.method == 'GET':
        key = request.args.get("key")
        number = request.args.get("number")
        api_type = request.args.get("type", "mobile")
    else:
        data = request.get_json()
        key = data.get("key") if data else None
        number = data.get("number") if data else None
        api_type = data.get("type", "mobile") if data else "mobile"
    
    # Validate required parameters
    if not key:
        return jsonify({"error": "API key required", "status": "error"})
    
    if not number:
        return jsonify({"error": "Number required", "status": "error"})
    
    # Check blacklist
    if api_manager.is_blacklisted(ip_address=client_ip) or api_manager.is_blacklisted(api_key=key):
        return jsonify({"error": "Your IP or API key is blacklisted", "status": "error"})
    
    # Validate API key
    status, user_info = api_manager.validate_api_key(key)
    
    if status == 'invalid':
        return jsonify({"error": "Invalid API key", "status": "error"})
    if status == 'expired':
        return jsonify({"error": "Subscription expired", "status": "error"})
    if status == 'limit_reached':
        return jsonify({"error": "Request limit reached", "status": "error"})
    if status == 'inactive':
        return jsonify({"error": "Account inactive", "status": "error"})
    
    # Check rate limit
    allowed, remaining = api_manager.check_rate_limit(key, api_type)
    if not allowed:
        return jsonify({"error": "Rate limit exceeded. Try again later.", "status": "error", "retry_after": 60})
    
    # Process request
    result = api_manager.smart_fetch(number, api_type)
    
    # Increment usage
    api_manager.increment_api_usage(key)
    
    # Add metadata
    response_time = time.time() - start_time
    result['metadata'] = {
        'status': 'success' if 'error' not in result else 'error',
        'response_time': round(response_time, 2),
        'rate_limit_remaining': remaining,
        'api_type': api_type,
        'timestamp': datetime.now().isoformat()
    }
    
    return jsonify(result)

@app.route("/api/v2/info", methods=['GET'])
def api_v2_info():
    """API v2 with more features"""
    key = request.args.get("key")
    number = request.args.get("number")
    
    if not key or not number:
        return jsonify({"error": "key and number required"})
    
    # Validate key
    status, _ = api_manager.validate_api_key(key)
    if status != 'active':
        return jsonify({"error": f"Invalid key: {status}"})
    
    # Fetch from all types
    results = {}
    for api_type in ['mobile', 'aadhaar', 'family', 'telegram']:
        result = api_manager.smart_fetch(number, api_type)
        if result and 'error' not in result:
            results[api_type] = result
    
    return jsonify({
        "number": number,
        "results": results,
        "total_found": len(results),
        "timestamp": datetime.now().isoformat()
    })

@app.route("/api/v2/bulk", methods=['POST'])
def api_v2_bulk():
    """Bulk API endpoint"""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "JSON data required"})
    
    key = data.get("key")
    numbers = data.get("numbers", [])
    api_type = data.get("type", "mobile")
    
    if not key or not numbers:
        return jsonify({"error": "key and numbers array required"})
    
    # Validate key
    status, _ = api_manager.validate_api_key(key)
    if status != 'active':
        return jsonify({"error": f"Invalid key: {status}"})
    
    # Process each number
    results = {}
    for number in numbers[:10]:  # Max 10 per request
        results[number] = api_manager.smart_fetch(number, api_type)
        api_manager.increment_api_usage(key)
    
    return jsonify({
        "total": len(results),
        "results": results,
        "timestamp": datetime.now().isoformat()
    })

@app.route("/stats", methods=['GET'])
def stats_endpoint():
    """Public stats endpoint"""
    stats = api_manager.get_system_stats()
    return jsonify(stats)

@app.route("/health", methods=['GET'])
def health_endpoint():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    })

@app.route("/", methods=['GET'])
def home():
    """Home page"""
    return jsonify({
        "service": "Ultimate API Management System",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "GET /api": "Main API endpoint",
            "GET /api/v2/info": "Enhanced API with all types",
            "POST /api/v2/bulk": "Bulk API requests",
            "GET /stats": "System statistics",
            "GET /health": "Health check"
        },
        "docs": "Contact @Danger_devil1917 for documentation"
    })

# ==================== INITIALIZATION ====================

def add_default_apis():
    """Add default APIs if none exist"""
    if len(api_manager.get_all_apis()) == 0:
        logger.info("Adding default APIs...")
        
        default_apis = [
            ("MobileAPI", "https://ayaanmods.site/mobile.php?key=annonymousmobile&term={number}", "mobile", "GET", 1, 15, 60),
            ("AadhaarAPI", "https://devil.elementfx.com/api.php?key=DANGER&type=aadhaar_info&term={number}", "aadhaar", "GET", 1, 15, 60),
            ("FamilyAPI", "https://devil.elementfx.com/api.php?key=DANGER&type=id_family&term={number}", "family", "GET", 2, 20, 30),
            ("TGAPI", "https://devil.elementfx.com/api.php?key=SONU&type=tg_number&term={number}", "telegram", "GET", 1, 15, 60),
        ]
        
        for name, url, api_type, method, priority, timeout, rate_limit in default_apis:
            api_manager.add_api(name, url, api_type, method=method, priority=priority, timeout=timeout, rate_limit=rate_limit)
        
        logger.info("Default APIs added successfully")

def run_bot():
    """Run bot in thread"""
    logger.info("🤖 Bot started...")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)

# ==================== MAIN ====================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 ULTIMATE API MANAGEMENT SYSTEM v2.0")
    print("=" * 60)
    
    add_default_apis()
    
    port = int(os.environ.get("PORT", 5000))
    
    # Start bot thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    logger.info(f"🌐 API Server running on port {port}")
    logger.info(f"📡 Bot is active")
    logger.info("=" * 60)
    
    # Run Flask
    app.run(host="0.0.0.0", port=port)