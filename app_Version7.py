import sqlite3
from flask import Flask, request, jsonify, session, g, send_from_directory
from flask_cors import CORS
import datetime, smtplib, threading, time, os
from email.mime.text import MIMEText

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key')
DB = 'legacy.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE, password TEXT,
                name TEXT, gender TEXT, birth TEXT, idno TEXT, nation TEXT,
                notify_days INTEGER, notify_name TEXT, notify_email TEXT, notify_relation TEXT,
                last_active TEXT, inherit_notified INTEGER DEFAULT 0
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT, account TEXT, password TEXT,
                inherit INTEGER, inheritGmail TEXT
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS communities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT, account TEXT, password TEXT,
                inherit INTEGER, inheritGmail TEXT
            )
        ''')
        db.commit()
init_db()

# ---- User Auth ----
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    db = get_db()
    try:
        db.execute('''
            INSERT INTO users (email, password, name, gender, birth, idno, nation)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (data['email'], data['password'], data['name'], data['gender'],
             data['birth'], data['idno'], data['nation']))
        db.commit()
        return jsonify({'status':'ok'})
    except sqlite3.IntegrityError:
        return jsonify({'status':'fail','msg':'Email已被註冊'})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE email=? AND password=?',
                      (data['email'], data['password'])).fetchone()
    if user:
        session['user'] = dict(user)
        db.execute('UPDATE users SET last_active=? WHERE id=?',
                   (datetime.datetime.utcnow().isoformat(), user['id']))
        db.commit()
        return jsonify({'status':'ok','user':{'email':user['email'], 'name':user['name']}})
    return jsonify({'status':'fail','msg':'帳號或密碼錯誤'})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({'status':'ok'})

def current_user():
    u = session.get('user')
    if not u: return None
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE email=?', (u['email'],)).fetchone()
    return user

@app.route('/api/whoami')
def whoami():
    u = current_user()
    if not u: return jsonify({'login':False})
    return jsonify({'login':True, 'user':{'email':u['email'],'name':u['name']}})

@app.route('/api/ping', methods=['POST'])
def ping():
    u = current_user()
    if not u: return jsonify({'status':'fail'})
    db = get_db()
    db.execute('UPDATE users SET last_active=? WHERE id=?',
               (datetime.datetime.utcnow().isoformat(), u['id']))
    db.commit()
    return jsonify({'status':'ok'})

# ---- Dashboard/繼承設定 ----
@app.route('/api/notify_setting', methods=['GET','POST'])
def notify_setting():
    u = current_user()
    if not u: return jsonify({'status':'fail','msg':'未登入'})
    db = get_db()
    if request.method == 'GET':
        return jsonify({'status':'ok',
            'notify_days': u['notify_days'] or 7,
            'notify_name': u['notify_name'] or '',
            'notify_email': u['notify_email'] or '',
            'notify_relation': u['notify_relation'] or '',
        })
    data = request.json
    db.execute('UPDATE users SET notify_days=?, notify_name=?, notify_email=?, notify_relation=?, inherit_notified=0 WHERE id=?',
                (data['notify_days'], data['notify_name'], data['notify_email'], data['notify_relation'], u['id']))
    db.commit()
    return jsonify({'status':'ok'})

# ---- 資產/社群 CRUD ----
@app.route('/api/assets', methods=['GET','POST'])
def assets():
    u = current_user()
    if not u: return jsonify([])
    db = get_db()
    if request.method=='GET':
        rows = db.execute('SELECT * FROM assets WHERE user_id=?', (u['id'],)).fetchall()
        return jsonify([dict(x) for x in rows])
    data = request.json
    db.execute('INSERT INTO assets (user_id,title,account,password,inherit,inheritGmail) VALUES (?,?,?,?,?,?)',
        (u['id'], data.get('title',''), data.get('account',''), data.get('password',''), int(data.get('inherit',False)), data.get('inheritGmail','')))
    db.commit()
    return jsonify({'status':'ok'})

@app.route('/api/assets/<int:idx>', methods=['PUT','DELETE'])
def asset_item(idx):
    u = current_user()
    if not u: return jsonify({'status':'fail'})
    db = get_db()
    if request.method=='PUT':
        data = request.json
        db.execute('UPDATE assets SET title=?,account=?,password=?,inherit=?,inheritGmail=? WHERE id=? AND user_id=?',
            (data.get('title',''), data.get('account',''), data.get('password',''), int(data.get('inherit',False)), data.get('inheritGmail',''), idx, u['id']))
        db.commit()
        return jsonify({'status':'ok'})
    else:
        db.execute('DELETE FROM assets WHERE id=? AND user_id=?', (idx, u['id']))
        db.commit()
        return jsonify({'status':'ok'})

@app.route('/api/communities', methods=['GET','POST'])
def communities():
    u = current_user()
    if not u: return jsonify([])
    db = get_db()
    if request.method=='GET':
        rows = db.execute('SELECT * FROM communities WHERE user_id=?', (u['id'],)).fetchall()
        return jsonify([dict(x) for x in rows])
    data = request.json
    db.execute('INSERT INTO communities (user_id,title,account,password,inherit,inheritGmail) VALUES (?,?,?,?,?,?)',
        (u['id'], data.get('title',''), data.get('account',''), data.get('password',''), int(data.get('inherit',False)), data.get('inheritGmail','')))
    db.commit()
    return jsonify({'status':'ok'})

@app.route('/api/communities/<int:idx>', methods=['PUT','DELETE'])
def community_item(idx):
    u = current_user()
    if not u: return jsonify({'status':'fail'})
    db = get_db()
    if request.method=='PUT':
        data = request.json
        db.execute('UPDATE communities SET title=?,account=?,password=?,inherit=?,inheritGmail=? WHERE id=? AND user_id=?',
            (data.get('title',''), data.get('account',''), data.get('password',''), int(data.get('inherit',False)), data.get('inheritGmail',''), idx, u['id']))
        db.commit()
        return jsonify({'status':'ok'})
    else:
        db.execute('DELETE FROM communities WHERE id=? AND user_id=?', (idx, u['id']))
        db.commit()
        return jsonify({'status':'ok'})

# ---- 寄信功能 ----
def send_gmail(to_email, subject, content):
    GMAIL_USER = os.environ.get('GMAIL_USER')
    GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print('Gmail credentials not set, skipping mail...')
        return
    msg = MIMEText(content, 'plain', 'utf-8')
    msg['From'] = GMAIL_USER
    msg['To'] = to_email
    msg['Subject'] = subject
    s = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    s.sendmail(GMAIL_USER, [to_email], msg.as_string())
    s.quit()

# ---- 定時後台任務 ----
def background_checker():
    while True:
        try:
            with app.app_context():
                db = get_db()
                rows = db.execute('SELECT * FROM users WHERE notify_days IS NOT NULL AND inherit_notified=0').fetchall()
                for u in rows:
                    if not u['last_active']: continue
                    days = int(u['notify_days'] or 7)
                    last = datetime.datetime.fromisoformat(u['last_active'])
                    now = datetime.datetime.utcnow()
                    delta = (now - last).days
                    if delta >= days and u['notify_email'] and u['notify_name']:
                        try:
                            send_gmail(
                                u['notify_email'],
                                "【遺產通知】提醒",
                                f"親愛的{u['notify_name']}您好，\n\n用戶{u['name']}（{u['email']}）已超過{days}天未登入本系統，請確認其狀態。\n與使用者關係：{u['notify_relation']}"
                            )
                            send_gmail(
                                u['email'],
                                "【遺產通知】提醒",
                                f"您已超過{days}天未登入本系統，請盡快登入以確認安全。"
                            )
                            db.execute('UPDATE users SET inherit_notified=1 WHERE id=?', (u['id'],))
                            db.commit()
                        except Exception as e:
                            print('Send mail fail:', e)
        except Exception as e:
            print('Background error:', e)
        time.sleep(3600)

th = threading.Thread(target=background_checker, daemon=True)
th.start()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

if __name__ == '__main__':
    app.run(debug=True)