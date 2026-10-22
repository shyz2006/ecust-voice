"""账号角色：管理员负责模型、检索、邮件、采集、账号与引擎；普通用户只使用校园观察与研究服务。

账号有两种来源：
- 服务器账号：.env 的 WEB_AUTH_USERNAME / WEB_AUTH_ACCOUNTS，由服务器配置管理；
- 站内账号：管理员在页面上创建，保存在 CampusPulse 数据库（CampusPulse/accounts.py）。
管理员为 WEB_ADMIN_USERS（逗号分隔；未设置时为 WEB_AUTH_USERNAME 主账号）及角色为 admin 的站内账号。
普通用户采用白名单：未列出的接口一律只对管理员开放。
"""
import hmac
import json
import os
import re

from flask import g, request, session

# 普通用户可访问的页面与接口
_USER_EXACT = {
    '/', '/login', '/logout', '/favicon.ico',
    '/api/auth/check', '/api/auth/me', '/api/account/password',
    '/pulse', '/pulse/',
    '/pulse/api/campus', '/pulse/api/campus/crisis-posts',
}
_USER_PREFIXES = ('/static/', '/pulse/poll/', '/pulse/api/revision/')

# /pulse/api/revision/ 下仍只对管理员开放的操作（发送邮件、改定时、消耗额度的手动触发）
_ADMIN_REVISION = re.compile(r'^/pulse/api/revision/(weekly/test-email|weekly/[^/]+/(send|retry)|memes/refresh)$')
_ADMIN_REVISION_POST = {'/pulse/api/revision/weekly', '/pulse/api/revision/weekly/config'}


def server_accounts():
    """.env 中配置的账号 {用户名: 密码}；格式错误的附加账号会被忽略。"""
    accounts = {os.getenv('WEB_AUTH_USERNAME', ''): os.getenv('WEB_AUTH_PASSWORD', '')}
    try:
        extra = json.loads(os.getenv('WEB_AUTH_ACCOUNTS', '{}'))
        if isinstance(extra, dict):
            accounts.update({str(k): str(v) for k, v in extra.items()})
    except json.JSONDecodeError:
        pass
    return {k: v for k, v in accounts.items() if k and v}


def admin_usernames():
    names = {name.strip() for name in os.getenv('WEB_ADMIN_USERS', '').split(',') if name.strip()}
    if not names:
        primary = os.getenv('WEB_AUTH_USERNAME', '').strip()
        if primary:
            names.add(primary)
    return names


def site_account(username):
    """站内账号行（每个请求只查一次数据库）。"""
    cache = g.setdefault('_site_accounts', {})
    if username not in cache:
        from CampusPulse import accounts
        cache[username] = accounts.get(username)
    return cache[username]


def authenticate(username, password):
    """校验登录；成功时返回写入会话的信息，失败返回 None。服务器账号优先。"""
    servers = server_accounts()
    if username in servers:
        if hmac.compare_digest(password or '', servers[username]):
            return {'source': 'server'}
        return None
    from CampusPulse import accounts
    row = accounts.verify(username, password)
    return {'source': 'site', 'version': row['version']} if row else None


def credentials_configured():
    if server_accounts():
        return True
    from CampusPulse import accounts
    return accounts.any_active()


def session_valid():
    """会话仍有效：服务器账号仍在配置中，或站内账号未停用且未改过密码/角色。"""
    if session.get('authenticated') is not True:
        return False
    username = str(session.get('username') or '')
    if not username:
        return False
    if session.get('account_source') == 'site':
        row = site_account(username)
        return bool(row) and not row['disabled'] and row['version'] == session.get('account_version')
    return username in server_accounts()


def current_username():
    return str(session.get('username')) if session_valid() else ''


def is_admin():
    username = current_username()
    if not username:
        return False
    if username in admin_usernames():
        return True
    if session.get('account_source') == 'site':
        row = site_account(username)
        return bool(row) and row['role'] == 'admin'
    return False


def role():
    return 'admin' if is_admin() else 'user'


def is_internal_request():
    """容器内回环调用（如研究流程回调 /api/report/generate）；经 nginx 的请求都带 X-Forwarded-For。"""
    return request.remote_addr in ('127.0.0.1', '::1') and not request.headers.get('X-Forwarded-For')


def user_may_access(path, method=None):
    """普通用户能否访问；method 为 None 时（nginx 子请求不带方法）只按路径判断。"""
    if path in _USER_EXACT:
        return True
    if not path.startswith(_USER_PREFIXES):
        return False
    if path.startswith('/pulse/api/revision/'):
        if _ADMIN_REVISION.match(path):
            return False
        if method == 'POST' and path in _ADMIN_REVISION_POST:
            return False
    return True
