import time
import telebot
import sqlite3
import random
import string
import threading
import requests
import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

# ===== CONFIG =====

BOT_TOKEN = "8290734722:AAGJ7yf9Kuh1IPGPNu_SQxg_BG3OftE9lUw"
ADMIN_ID = 7655738256

REAL_API = "https://ownerjii-api-ayno.vercel.app/api/info?number={}"  # Yaha real API lagao

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
# ===== SELF PING =====
def self_ping():
    url = "https://api-wd7m.onrender.com/api?key=sleep&number=9999999999"

    while True:
        try:
            r = requests.get(url)
            print("Ping Success:", r.status_code)
        except Exception as e:
            print("Ping Failed:", e)

        time.sleep(300)
# ===== DATABASE =====

def init_db():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        api_key TEXT,
        expiry TEXT,
        used INTEGER,
        limit_req INTEGER
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ===== KEY GENERATOR =====

def generate_key():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=30))

# ===== CHECK KEY =====

def check_key(key):

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT expiry,used,limit_req FROM users WHERE api_key=?", (key,))
    data = cur.fetchone()

    if not data:
        conn.close()
        return "invalid"

    expiry, used, limit_req = data
    expiry = datetime.strptime(expiry, "%Y-%m-%d")

    if datetime.now() > expiry:
        conn.close()
        return "expired"

    if used >= limit_req:
        conn.close()
        return "limit"

    cur.execute("UPDATE users SET used=? WHERE api_key=?", (used + 1, key))
    conn.commit()
    conn.close()

    return "active"

# ===== API SERVER =====

@app.route("/api")

def api():

    key = request.args.get("key")
    number = request.args.get("number")

    if not key:
        return jsonify({"error":"API key required"})

    if not number:
        return jsonify({"error":"number required"})

    status = check_key(key)

    if status == "invalid":
        return jsonify({"error":"invalid key"})

    if status == "expired":
        return jsonify({"error":"subscription expired"})

    if status == "limit":
        return jsonify({"error":"request limit reached"})

    # ===== REAL API REQUEST =====

    try:
        r = requests.get(REAL_API.format(number), timeout=10)
        return jsonify(r.json())

    except:
        return jsonify({"error":"real api failed"})

# ===== TELEGRAM BOT =====

@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg,"✅ API ADMIN PANEL ACTIVE")

# ===== GENKEY =====

@bot.message_handler(commands=['genkey'])
def genkey(msg):

    if msg.from_user.id != ADMIN_ID:
        return

    try:
        days = int(msg.text.split()[1])
        limit_req = int(msg.text.split()[2])
    except:
        bot.reply_to(msg,"Use:\n/genkey days limit")
        return

    key = generate_key()
    expiry = (datetime.now()+timedelta(days=days)).strftime("%Y-%m-%d")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("INSERT INTO users VALUES(?,?,?,?)",(key,expiry,0,limit_req))

    conn.commit()
    conn.close()

    bot.reply_to(msg,f"""
NEW API KEY

Key:
{key}

Expiry:
{expiry}

Limit:
{limit_req}
""")

# ===== ADD MANUAL KEY =====

@bot.message_handler(commands=['addkey'])
def addkey(msg):

    if msg.from_user.id != ADMIN_ID:
        return

    try:
        key = msg.text.split()[1]
        days = int(msg.text.split()[2])
        limit_req = int(msg.text.split()[3])
    except:
        bot.reply_to(msg,"Use:\n/addkey key days limit")
        return

    expiry = (datetime.now()+timedelta(days=days)).strftime("%Y-%m-%d")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("INSERT INTO users VALUES(?,?,?,?)",(key,expiry,0,limit_req))

    conn.commit()
    conn.close()

    bot.reply_to(msg,"Manual key added")

# ===== KEYS LIST =====

@bot.message_handler(commands=['keys'])
def keys(msg):

    if msg.from_user.id != ADMIN_ID:
        return

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT * FROM users")
    data = cur.fetchall()

    text = "API KEYS\n\n"

    for k,e,u,l in data:

        text += f"""
KEY: {k}
Expiry: {e}
Usage: {u}/{l}

"""

    conn.close()

    bot.reply_to(msg,text)

# ===== DELETE KEY =====

@bot.message_handler(commands=['delkey'])
def delkey(msg):

    if msg.from_user.id != ADMIN_ID:
        return

    try:
        key = msg.text.split()[1]
    except:
        return

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("DELETE FROM users WHERE api_key=?", (key,))
    conn.commit()
    conn.close()

    bot.reply_to(msg,"Key deleted")

# ===== KEY INFO =====

@bot.message_handler(commands=['info'])
def info(msg):

    if msg.from_user.id != ADMIN_ID:
        return

    try:
        key = msg.text.split()[1]
    except:
        return

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE api_key=?", (key,))
    data = cur.fetchone()
    conn.close()

    if not data:
        bot.reply_to(msg,"Key not found")
        return

    k,e,u,l = data

    bot.reply_to(msg,f"""
KEY INFO

Key:
{k}

Expiry:
{e}

Usage:
{u}/{l}
""")

# ===== RUN SERVER =====

def run_api():
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)

def run_bot():
    bot.infinity_polling()
threading.Thread(target=self_ping).start()
threading.Thread(target=run_api).start()
run_bot()