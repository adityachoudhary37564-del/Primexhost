# -*- coding: utf-8 -*-
import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime
import re
import sys
import logging
import psutil
import threading
import atexit
import requests

# ============================================================
# CONFIG (already filled in)
# ============================================================
TOKEN = '8892615863:AAHURJOttavY-t6a5mRWpowSmXEJHhY60j4'
OWNER_ID = 8630401564
OWNER_USERNAME = '@KievalryPrime'

# ============================================================
# PATHS
# ============================================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN)

# user_id -> {'proc','log','file','type','folder'}
running = {}

# ============================================================
# STDLIB + PIP NAME MAP (for auto-installer)
# ============================================================
STDLIB = set(getattr(sys, 'stdlib_module_names', set())) | {
    'os', 'sys', 're', 'time', 'json', 'math', 'random', 'logging', 'threading',
    'subprocess', 'zipfile', 'tempfile', 'shutil', 'sqlite3', 'datetime',
    'asyncio', 'atexit', 'pathlib', 'typing', 'collections', 'functools',
    'itertools', 'io', 'base64', 'hashlib', 'uuid', 'socket', 'http', 'urllib',
    'string', 'struct', 'copy', 'enum', 'abc', 'weakref', 'gc', 'imp', 'signal',
    'select', 'ssl', 'email', 'html', 'xml', 'csv', 'configparser', 'argparse',
    'getpass', 'platform', 'stat', 'glob', 'fnmatch', 'linecache', 'traceback',
    'warnings', 'contextlib', 'dataclasses', 'inspect', 'ast', 'tokenize',
    'pdb', 'pstats', 'profile', 'timeit', 'unittest', 'doctest', 'venv', 'pip',
}

PIP_OVERRIDES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'bs4': 'beautifulsoup4',
    'cv2': 'opencv-python',
    'pillow': 'Pillow',
    'PIL': 'Pillow',
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil',
    'sqlalchemy': 'SQLAlchemy',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'pytz': 'pytz',
    'requests': 'requests',
    'aiohttp': 'aiohttp',
    'flask': 'Flask',
    'django': 'Django',
    'numpy': 'numpy',
    'pandas': 'pandas',
    'psutil': 'psutil',
}

# ============================================================
# AUTO MODULE INSTALLER
# ============================================================

def pip_install(module_name, message):
    mod = module_name.strip().strip("'\"")
    root = mod.split('.')[0]
    if root in STDLIB:
        logger.info(f"'{mod}' is stdlib, skip install.")
        return False

    pkg = PIP_OVERRIDES.get(root, root)
    bot.reply_to(message, f"🐍 Installing missing module `{mod}` as `{pkg}`...", parse_mode='Markdown')
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--quiet', pkg],
            capture_output=True, text=True, timeout=180
        )
        if r.returncode == 0:
            bot.reply_to(message, f"✅ Installed `{pkg}`", parse_mode='Markdown')
            return True
        bot.reply_to(message,
                     f"❌ `{pkg}` install failed:\n```\n{(r.stderr or r.stdout)[:800]}\n```",
                     parse_mode='Markdown')
        return False
    except Exception as e:
        logger.error(f"pip error: {e}")
        bot.reply_to(message, f"❌ pip error: {e}")
        return False


def npm_install(module_name, folder, message):
    mod = module_name.strip().strip("'\"")
    if mod.startswith('.') or mod.startswith('/'):
        return False
    bot.reply_to(message, f"🟠 Installing missing node module `{mod}`...", parse_mode='Markdown')
    try:
        r = subprocess.run(
            ['npm', 'install', '--silent', mod],
            capture_output=True, text=True, cwd=folder, timeout=240
        )
        if r.returncode == 0:
            bot.reply_to(message, f"✅ npm installed `{mod}`", parse_mode='Markdown')
            return True
        bot.reply_to(message,
                     f"❌ npm install `{mod}` failed:\n```\n{(r.stderr or r.stdout)[:800]}\n```",
                     parse_mode='Markdown')
        return False
    except FileNotFoundError:
        bot.reply_to(message, "❌ `npm` not found. Install Node.js.")
        return False
    except Exception as e:
        logger.error(f"npm error: {e}")
        bot.reply_to(message, f"❌ npm error: {e}")
        return False


def check_and_fix_deps(file_path, file_type, folder, message):
    interpreter = [sys.executable, file_path] if file_type == 'py' else ['node', file_path]

    for attempt in range(1, 4):
        proc = None
        try:
            proc = subprocess.Popen(
                interpreter, cwd=folder,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='ignore'
            )
            try:
                out, err = proc.communicate(timeout=6)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.communicate()
                return True  # ran 6s without crashing → OK

            if proc.returncode == 0:
                return True

            # Python missing module
            if file_type == 'py':
                m = re.search(r"ModuleNotFoundError: No module named '([^']+)'", err or '')
                if m:
                    if pip_install(m.group(1), message):
                        continue
                    return False
                m = re.search(r"ImportError: cannot import name .+ from '([^']+)'", err or '')
                if m:
                    if pip_install(m.group(1), message):
                        continue
                    return False
            else:
                m = re.search(r"Cannot find module '([^']+)'", err or '')
                if m:
                    if npm_install(m.group(1), folder, message):
                        continue
                    return False

            bot.reply_to(
                message,
                f"❌ `{os.path.basename(file_path)}` crashed at startup:\n```\n{(err or out)[:1200]}\n```",
                parse_mode='Markdown'
            )
            return False

        except FileNotFoundError:
            bot.reply_to(message, f"❌ Interpreter not found: `{interpreter[0]}`")
            return False
        except Exception as e:
            logger.error(f"check_deps: {e}", exc_info=True)
            bot.reply_to(message, f"❌ Pre-check error: {e}")
            return False

    bot.reply_to(message, "❌ Could not resolve dependencies after 3 attempts.")
    return False

# ============================================================
# PROCESS MANAGEMENT
# ============================================================

def user_folder(user_id):
    f = os.path.join(UPLOAD_DIR, str(user_id))
    os.makedirs(f, exist_ok=True)
    return f


def kill_proc(user_id):
    info = running.get(user_id)
    if not info:
        return
    try:
        if info.get('log') and not info['log'].closed:
            info['log'].close()
        p = info.get('proc')
        if p and p.poll() is None:
            try:
                parent = psutil.Process(p.pid)
                for c in parent.children(recursive=True):
                    try: c.kill()
                    except: pass
                parent.kill()
            except psutil.NoSuchProcess:
                pass
    except Exception as e:
        logger.error(f"kill_proc: {e}")
    finally:
        running.pop(user_id, None)


def is_running(user_id):
    info = running.get(user_id)
    if not info:
        return False
    p = info.get('proc')
    if p and p.poll() is None:
        return True
    kill_proc(user_id)
    return False


def start_script(user_id, file_path, file_type, folder, file_name, message):
    if is_running(user_id):
        bot.reply_to(message, "⚠️ You already have a running script. Stop it from ✏️ Edit File first.")
        return

    ok = check_and_fix_deps(file_path, file_type, folder, message)
    if not ok:
        return

    log_path = os.path.join(folder, f"{os.path.splitext(file_name)[0]}.log")
    log_file = open(log_path, 'w', encoding='utf-8', errors='ignore')
    interpreter = [sys.executable, file_path] if file_type == 'py' else ['node', file_path]

    try:
        proc = subprocess.Popen(
            interpreter, cwd=folder,
            stdout=log_file, stderr=log_file,
            stdin=subprocess.PIPE, text=True,
            encoding='utf-8', errors='ignore'
        )
    except FileNotFoundError as e:
        log_file.close()
        bot.reply_to(message, f"❌ Interpreter not found: {e}")
        return
    except Exception as e:
        log_file.close()
        bot.reply_to(message, f"❌ Failed to start: {e}")
        return

    running[user_id] = {
        'proc': proc, 'log': log_file,
        'file': file_name, 'type': file_type, 'folder': folder
    }
    bot.reply_to(message, f"🚀 Running `{file_name}` (PID {proc.pid})", parse_mode='Markdown')
    logger.info(f"Started {file_name} for {user_id} PID={proc.pid}")

    def watcher():
        proc.wait()
        if running.get(user_id, {}).get('proc') is proc:
            try:
                bot.send_message(user_id, f"ℹ️ Script `{file_name}` has stopped.", parse_mode='Markdown')
            except: pass
            running.pop(user_id, None)
            try:
                if not log_file.closed: log_file.close()
            except: pass

    threading.Thread(target=watcher, daemon=True).start()

# ============================================================
# UPLOAD HANDLING
# ============================================================

def save_and_run(message, content, file_name):
    user_id = message.from_user.id
    ext = os.path.splitext(file_name)[1].lower()

    if ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Only `.py`, `.js`, or `.zip` allowed.")
        return

    folder = user_folder(user_id)
    tmp = tempfile.mkdtemp(prefix=f"u{user_id}_")

    try:
        if ext == '.zip':
            zpath = os.path.join(tmp, file_name)
            with open(zpath, 'wb') as f: f.write(content)
            with zipfile.ZipFile(zpath) as z:
                for m in z.infolist():
                    dest = os.path.abspath(os.path.join(tmp, m.filename))
                    if not dest.startswith(os.path.abspath(tmp)):
                        bot.reply_to(message, "❌ Unsafe path in ZIP.")
                        return
                z.extractall(tmp)

            items = os.listdir(tmp)
            main = None
            for pref in ('main.py', 'bot.py', 'app.py'):
                if pref in items: main = pref; break
            if not main:
                for pref in ('index.js', 'main.js', 'bot.js', 'app.js'):
                    if pref in items: main = pref; break
            if not main:
                py = [f for f in items if f.endswith('.py')]
                js = [f for f in items if f.endswith('.js')]
                if py: main = py[0]
                elif js: main = js[0]
            if not main:
                bot.reply_to(message, "❌ No `.py` or `.js` main script in ZIP.")
                return

            if 'requirements.txt' in items:
                bot.reply_to(message, "📦 Installing requirements.txt...")
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '-q',
                     '-r', os.path.join(tmp, 'requirements.txt')],
                    capture_output=True, timeout=600
                )
            if 'package.json' in items:
                bot.reply_to(message, "📦 npm install...")
                subprocess.run(['npm', 'install', '--silent'], cwd=tmp,
                               capture_output=True, timeout=600)

            for it in os.listdir(tmp):
                src = os.path.join(tmp, it)
                dst = os.path.join(folder, it)
                if os.path.isdir(dst): shutil.rmtree(dst)
                elif os.path.exists(dst): os.remove(dst)
                shutil.move(src, dst)

            file_path = os.path.join(folder, main)
            ftype = 'py' if main.endswith('.py') else 'js'
            start_script(user_id, file_path, ftype, folder, main, message)

        else:
            dest = os.path.join(folder, file_name)
            with open(dest, 'wb') as f: f.write(content)
            ftype = 'py' if ext == '.py' else 'js'
            start_script(user_id, dest, ftype, folder, file_name, message)

    except zipfile.BadZipFile:
        bot.reply_to(message, "❌ Invalid/corrupt ZIP.")
    except Exception as e:
        logger.error(f"save_and_run: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@bot.message_handler(content_types=['document'])
def on_document(message):
    doc = message.document
    if not doc.file_name:
        bot.reply_to(message, "⚠️ File has no name.")
        return
    try:
        f = bot.get_file(doc.file_id)
        data = bot.download_file(f.file_path)
        save_and_run(message, data, doc.file_name)
    except Exception as e:
        logger.error(f"download: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Download failed: {e}")

# ============================================================
# COMMANDS
# ============================================================

@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📤 Upload File"),
        types.KeyboardButton("✏️ Edit File"),
    )
    user = message.from_user
    bot.send_message(
        message.chat.id,
        f"👋 Welcome, {user.first_name}!\n\n"
        f"🆔 Your ID: `{user.id}`\n"
        f"👤 Owner: {OWNER_USERNAME}\n\n"
        "• 📤 **Upload File** — send `.py`, `.js`, or `.zip`. "
        "I'll auto-install missing modules and run it.\n"
        "• ✏️ **Edit File** — view / stop / restart / logs / delete.",
        reply_markup=markup, parse_mode='Markdown'
    )


@bot.message_handler(func=lambda m: m.text == "📤 Upload File")
def btn_upload(message):
    bot.reply_to(message,
                 "📤 Send me a `.py`, `.js`, or `.zip` file.\n"
                 "Missing modules will be installed automatically.")


@bot.message_handler(func=lambda m: m.text == "✏️ Edit File")
def btn_edit(message):
    user_id = message.from_user.id
    if is_running(user_id):
        info = running[user_id]
        fn = info['file']
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton("🔄 Restart", callback_data="act:restart"),
            types.InlineKeyboardButton("🔴 Stop", callback_data="act:stop"),
        )
        markup.row(
            types.InlineKeyboardButton("📜 Logs", callback_data="act:logs"),
            types.InlineKeyboardButton("🗑 Delete", callback_data="act:delete"),
        )
        bot.reply_to(message, f"✏️ Editing `{fn}` — 🟢 running",
                     reply_markup=markup, parse_mode='Markdown')
        return

    folder = user_folder(user_id)
    files = [f for f in os.listdir(folder) if f.endswith(('.py', '.js'))]
    if not files:
        bot.reply_to(message, "📂 No files uploaded yet. Use 📤 Upload File.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for fn in files:
        markup.add(types.InlineKeyboardButton(f"▶️ Start {fn}", callback_data=f"start:{fn}"))
    bot.reply_to(message, "📂 Your files (not running):", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    user_id = call.from_user.id
    data = call.data

    if data.startswith("start:"):
        fn = data.split(":", 1)[1]
        folder = user_folder(user_id)
        path = os.path.join(folder, fn)
        if not os.path.exists(path):
            bot.answer_callback_query(call.id, "File missing.", show_alert=True); return
        bot.answer_callback_query(call.id)
        ftype = 'py' if fn.endswith('.py') else 'js'
        start_script(user_id, path, ftype, folder, fn, call.message)
        return

    if data == "act:stop":
        if not running.get(user_id):
            bot.answer_callback_query(call.id, "Not running.", show_alert=True); return
        kill_proc(user_id)
        bot.answer_callback_query(call.id, "Stopped.")
        bot.edit_message_text("🔴 Script stopped.",
                              call.message.chat.id, call.message.message_id)
        return

    if data == "act:restart":
        info = running.get(user_id)
        if not info:
            bot.answer_callback_query(call.id, "Not running.", show_alert=True); return
        fn, folder, ftype = info['file'], info['folder'], info['type']
        kill_proc(user_id)
        bot.answer_callback_query(call.id, "Restarting...")
        path = os.path.join(folder, fn)
        start_script(user_id, path, ftype, folder, fn, call.message)
        return

    if data == "act:logs":
        info = running.get(user_id)
        if not info:
            bot.answer_callback_query(call.id, "Not running.", show_alert=True); return
        log_path = os.path.join(info['folder'],
                                f"{os.path.splitext(info['file'])[0]}.log")
        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, "No log file.", show_alert=True); return
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                txt = f.read()[-3500:] or "(empty)"
        except Exception as e:
            bot.answer_callback_query(call.id, f"Read error: {e}", show_alert=True); return
        bot.answer_callback_query(call.id)
        bot.send_message(user_id, f"📜 Logs — `{info['file']}`\n```\n{txt}\n```",
                         parse_mode='Markdown')
        return

    if data == "act:delete":
        info = running.get(user_id)
        if not info:
            bot.answer_callback_query(call.id, "Nothing to delete.", show_alert=True); return
        fn, folder = info['file'], info['folder']
        kill_proc(user_id)
        try:
            for f in [fn, os.path.splitext(fn)[0] + '.log']:
                p = os.path.join(folder, f)
                if os.path.exists(p): os.remove(p)
        except Exception as e:
            logger.error(f"delete: {e}")
        bot.answer_callback_query(call.id, "Deleted.")
        bot.edit_message_text(f"🗑 `{fn}` deleted.",
                              call.message.chat.id, call.message.message_id,
                              parse_mode='Markdown')
        return

    bot.answer_callback_query(call.id, "Unknown action.", show_alert=True)

# ============================================================
# CLEANUP
# ============================================================

def cleanup():
    logger.warning("Shutdown — killing all scripts...")
    for uid in list(running.keys()):
        kill_proc(uid)

atexit.register(cleanup)

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    print("=" * 50)
    print(f"🤖 Bot starting...")
    print(f"👤 Owner: {OWNER_ID} ({OWNER_USERNAME})")
    print(f"📁 Uploads: {UPLOAD_DIR}")
    print("=" * 50)
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except requests.exceptions.ReadTimeout:
            time.sleep(5)
        except requests.exceptions.ConnectionError:
            time.sleep(15)
        except Exception as e:
            logger.critical(f"Polling error: {e}", exc_info=True)
            time.sleep(30)
