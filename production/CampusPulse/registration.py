"""校园邮箱自助注册：验证码经 Resend 发到校园邮箱，验证后创建普通用户账号。

开关与允许的邮箱后缀由管理员在“账号管理”中设置（kv: register:config:v1）。
验证码只保存哈希；按邮箱、IP 和全站限制发送频率，保护邮件额度。
"""
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
import uuid
from contextlib import contextmanager

from loguru import logger

from . import accounts, storage, weekly

CONFIG_KEY = 'register:config:v1'
DEFAULT_DOMAINS = ['mail.ecust.edu.cn', 'ecust.edu.cn']
CODE_TTL = 10 * 60
RESEND_COOLDOWN = 60
MAX_ATTEMPTS = 5
EMAIL_DAILY_LIMIT = 5
IP_HOURLY_LIMIT = 10
GLOBAL_DAILY_LIMIT = 200
COMMON_WORDS = ('password', 'passw0rd', 'qwerty', 'iloveyou', 'admin', 'ecust', 'welcome', 'abc123', 'letmein', '123123', '520520', '5201314')
SEQUENCE_RE = re.compile(r'0123|1234|2345|3456|4567|5678|6789|abcd|qwer|asdf')
DOMAIN_RE = re.compile(r'^(?=.{3,100}$)[a-z0-9-]+(\.[a-z0-9-]+)+$')
EMAIL_RE = re.compile(r'^[a-z0-9._%+\-]{1,64}@([a-z0-9-]+(\.[a-z0-9-]+)+)$')
_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_register_codes (
    email TEXT PRIMARY KEY,
    code_hash TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS web_register_sends (
    ts INTEGER NOT NULL,
    email TEXT NOT NULL,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS web_register_sends_ts ON web_register_sends(ts);
"""
_ready = False


@contextmanager
def _conn():
    global _ready
    with storage.connect() as conn:
        if not _ready:
            conn.executescript(_SCHEMA)
            _ready = True
        yield conn


def config():
    value = {'enabled': True, 'domains': list(DEFAULT_DOMAINS)}
    raw = storage.kv_get(CONFIG_KEY)
    if raw:
        value.update(json.loads(raw))
    return value


def mail_ready():
    mail = weekly.config(True)
    return bool(mail['api_key'] and mail['sender'] and mail['sender_verified'])


def public_config():
    """登录页用：只有开关和后缀。邮件服务没准备好时不显示注册入口。"""
    value = config()
    try:
        ready = mail_ready()
    except Exception:
        ready = False
    return {'enabled': bool(value['enabled'] and ready), 'domains': value['domains']}


def save_config(body):
    enabled = bool(body.get('enabled'))
    raw = body.get('domains')
    items = raw if isinstance(raw, list) else str(raw or '').replace('，', ',').split(',')
    domains = []
    for item in items:
        domain = str(item).strip().lower().lstrip('@')
        if not domain:
            continue
        if not DOMAIN_RE.fullmatch(domain):
            raise ValueError('邮箱后缀格式不正确：' + domain)
        if domain not in domains:
            domains.append(domain)
    if enabled and not domains:
        raise ValueError('开放注册时至少要填写一个邮箱后缀')
    storage.kv_set(CONFIG_KEY, json.dumps({'enabled': enabled, 'domains': domains}).encode())
    return config()


def normalize_email(value, domains):
    email = str(value or '').strip().lower()
    match = EMAIL_RE.fullmatch(email)
    if not match:
        raise ValueError('请填写正确的邮箱地址')
    if match.group(1) not in domains:
        raise ValueError('请使用校园邮箱注册（' + '、'.join('@' + d for d in domains) + '）')
    return email


def weak_password(password, username, email):
    """与登录页“力量测试机”的“弱”档一致：太常见、纯数字/连号或包含用户名、邮箱前缀。"""
    lower = password.lower()
    local = email.split('@')[0]
    if re.fullmatch(r'(.)\1+', password):
        return True
    if len(password) < 12 and (password.isdigit() or SEQUENCE_RE.search(lower)):
        return True
    if len(password) < 14 and any(word in lower for word in COMMON_WORDS):
        return True
    return (len(username) >= 3 and username.lower() in lower) or (len(local) >= 4 and local in lower)


def _code_hash(email, code):
    secret = (os.getenv('WEB_SESSION_SECRET') or 'campus-register').encode()
    return hmac.new(secret, (email + ':' + code).encode(), hashlib.sha256).hexdigest()


def _require_open():
    value = config()
    if not value['enabled']:
        raise ValueError('暂未开放注册，请联系管理员')
    return value


def send_code(email, ip):
    value = _require_open()
    email = normalize_email(email, value['domains'])
    if accounts.get_by_email(email):
        raise ValueError('该邮箱已注册，请直接登录')
    now = int(time.time())
    mail = weekly.config(True)
    if not (mail['api_key'] and mail['sender'] and mail['sender_verified']):
        raise ValueError('注册邮件服务暂未就绪，请联系管理员')
    with _conn() as conn:
        last = conn.execute('SELECT MAX(ts) t FROM web_register_sends WHERE email=?', (email,)).fetchone()['t']
        if last and now - last < RESEND_COOLDOWN:
            problem = f'请在 {RESEND_COOLDOWN - (now - last)} 秒后重新获取验证码'
        elif conn.execute('SELECT COUNT(*) n FROM web_register_sends WHERE email=? AND ts>?', (email, now - 86400)).fetchone()['n'] >= EMAIL_DAILY_LIMIT:
            problem = '该邮箱今天获取验证码的次数已用完，请明天再试'
        elif ip and conn.execute('SELECT COUNT(*) n FROM web_register_sends WHERE ip=? AND ts>?', (ip, now - 3600)).fetchone()['n'] >= IP_HOURLY_LIMIT:
            problem = '请求过于频繁，请稍后再试'
        elif conn.execute('SELECT COUNT(*) n FROM web_register_sends WHERE ts>?', (now - 86400,)).fetchone()['n'] >= GLOBAL_DAILY_LIMIT:
            problem = '今天的注册请求较多，请稍后再试或联系管理员'
        else:
            # 先记一次发送再调用邮件服务，失败也计入频率限制，防止反复刷接口
            conn.execute('INSERT INTO web_register_sends(ts,email,ip) VALUES(?,?,?)', (now, email, ip))
            problem = None
    if problem:
        raise ValueError(problem)
    code = f'{secrets.randbelow(10 ** 6):06d}'
    body = ('<div style="font-family:sans-serif;line-height:1.7;color:#29252d">'
            '<p>你好！你正在注册「华理 · 校园观察与研究」。</p>'
            f'<p style="font-size:28px;font-weight:800;letter-spacing:6px;margin:18px 0">{code}</p>'
            f'<p>验证码 {CODE_TTL // 60} 分钟内有效。如果不是你本人操作，请忽略这封邮件。</p>'
            f'<p style="color:#79727e;font-size:12px">发送至 {html.escape(email)}</p></div>')
    try:
        weekly.resend({'from': mail['sender'], 'to': [email], 'subject': '华理校园观察 · 注册验证码 ' + code, 'html': body},
                      'campus-register/' + uuid.uuid4().hex, mail['api_key'])
    except ValueError as exc:
        logger.warning(f'注册验证码发送失败：{exc}')
        raise ValueError('验证码邮件暂时发送失败，请稍后重试') from None
    with _conn() as conn:
        conn.execute('INSERT INTO web_register_codes(email,code_hash,expires_at,attempts) VALUES(?,?,?,0) '
                     'ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash,expires_at=excluded.expires_at,attempts=0',
                     (email, _code_hash(email, code), now + CODE_TTL))
    return email


def register(email, code, username, password, reserved_usernames):
    """校验验证码并创建普通用户账号；先检查用户名和密码，避免白白消耗验证码尝试次数。"""
    value = _require_open()
    email = normalize_email(email, value['domains'])
    username = str(username or '').strip()
    accounts.validate_username(username)
    accounts.validate_password(password)
    if weak_password(password, username, email):
        raise ValueError('密码太弱了，换个更长、更不常见的密码')
    if username in reserved_usernames or accounts.get(username):
        raise ValueError('该用户名已被使用，请换一个')
    if accounts.get_by_email(email):
        raise ValueError('该邮箱已注册，请直接登录')
    now = int(time.time())
    # storage.connect 只在正常退出时提交，所以先记下结果，离开 with 后再报错
    with _conn() as conn:
        row = conn.execute('SELECT * FROM web_register_codes WHERE email=?', (email,)).fetchone()
        if not row or row['expires_at'] < now:
            problem = '验证码已过期，请重新获取'
        elif row['attempts'] >= MAX_ATTEMPTS:
            problem = '验证码错误次数过多，请重新获取'
        elif not hmac.compare_digest(row['code_hash'], _code_hash(email, str(code or '').strip())):
            conn.execute('UPDATE web_register_codes SET attempts=attempts+1 WHERE email=?', (email,))
            problem = '验证码不正确'
        else:
            conn.execute('DELETE FROM web_register_codes WHERE email=?', (email,))
            problem = None
    if problem:
        raise ValueError(problem)
    item = accounts.create(username, password, 'user', '校园邮箱注册', email=email)
    logger.info(f'新用户通过校园邮箱注册：{username}')
    return accounts.get(item['username'])
