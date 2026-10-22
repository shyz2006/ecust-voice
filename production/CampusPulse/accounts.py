"""站内账号：管理员在页面上创建的登录账号，只保存密码哈希。

.env 中的 WEB_AUTH_USERNAME / WEB_AUTH_ACCOUNTS 账号仍由服务器配置管理，这里不能修改；
站内账号不能与它们重名。version 在改密码、改角色、停用时递增，用来让旧会话失效。
"""
import re
import time
from contextlib import contextmanager

from werkzeug.security import check_password_hash, generate_password_hash

from . import storage

ROLES = ('user', 'admin')
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.\-一-鿿]{2,32}$')
PASSWORD_MIN, PASSWORD_MAX = 8, 128
_DUMMY_HASH = generate_password_hash('campus-pulse-dummy-password')
_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_accounts (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    disabled INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    created_by TEXT,
    updated_at INTEGER NOT NULL,
    last_login INTEGER
)"""
_ready = False


@contextmanager
def _conn():
    global _ready
    with storage.connect() as conn:
        if not _ready:
            conn.execute(_SCHEMA)
            _ready = True
        yield conn


def _public(row):
    return {k: row[k] for k in ('username', 'role', 'created_at', 'created_by', 'updated_at', 'last_login')} | {
        'disabled': bool(row['disabled']), 'source': 'site'}


def validate_username(username):
    if not isinstance(username, str) or not USERNAME_RE.fullmatch(username):
        raise ValueError('用户名需为2至32位，可用中英文、数字、下划线、点和短横线')


def validate_password(password):
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise ValueError(f'密码需为{PASSWORD_MIN}至{PASSWORD_MAX}位')


def validate_role(role):
    if role not in ROLES:
        raise ValueError('角色只能是管理员或普通用户')


def get(username):
    if not username:
        return None
    with _conn() as conn:
        return conn.execute('SELECT * FROM web_accounts WHERE username=?', (username,)).fetchone()


def any_active():
    with _conn() as conn:
        return conn.execute('SELECT 1 FROM web_accounts WHERE disabled=0 LIMIT 1').fetchone() is not None


def list_all():
    with _conn() as conn:
        return [_public(r) for r in conn.execute('SELECT * FROM web_accounts ORDER BY created_at')]


def verify(username, password):
    """密码正确且未停用时返回账号行；用户不存在时也做一次哈希比较，避免按耗时猜测账号。"""
    row = get(username) if isinstance(username, str) else None
    ok = check_password_hash(row['password_hash'] if row else _DUMMY_HASH, password or '')
    if not row or not ok or row['disabled']:
        return None
    with _conn() as conn:
        conn.execute('UPDATE web_accounts SET last_login=? WHERE username=?', (int(time.time()), username))
    return row


def create(username, password, role, created_by):
    validate_username(username)
    validate_password(password)
    validate_role(role)
    now = int(time.time())
    with _conn() as conn:
        if conn.execute('SELECT 1 FROM web_accounts WHERE username=?', (username,)).fetchone():
            raise ValueError('该用户名已存在')
        conn.execute('INSERT INTO web_accounts(username,password_hash,role,created_at,created_by,updated_at) VALUES(?,?,?,?,?,?)',
                     (username, generate_password_hash(password), role, now, created_by, now))
    return _public(get(username))


def update(username, password=None, role=None, disabled=None):
    row = get(username)
    if not row:
        raise LookupError('账号不存在')
    fields, values = [], []
    if password is not None:
        validate_password(password)
        fields.append('password_hash=?'); values.append(generate_password_hash(password))
    if role is not None:
        validate_role(role)
        fields.append('role=?'); values.append(role)
    if disabled is not None:
        fields.append('disabled=?'); values.append(1 if disabled else 0)
    if not fields:
        raise ValueError('没有可更新的内容')
    fields += ['version=version+1', 'updated_at=?']
    values += [int(time.time()), username]
    with _conn() as conn:
        conn.execute('UPDATE web_accounts SET ' + ','.join(fields) + ' WHERE username=?', values)
    return _public(get(username))


def delete(username):
    with _conn() as conn:
        if conn.execute('DELETE FROM web_accounts WHERE username=?', (username,)).rowcount == 0:
            raise LookupError('账号不存在')
