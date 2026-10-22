"""账号角色：管理员负责模型、检索、邮件、采集与引擎；普通用户只使用校园观察与研究服务。

管理员名单来自 WEB_ADMIN_USERS（逗号分隔）；未设置时，WEB_AUTH_USERNAME 主账号为管理员，
WEB_AUTH_ACCOUNTS 中的附加账号为普通用户。普通用户采用白名单：未列出的接口一律只对管理员开放。
"""
import os
import re

from flask import request, session

# 普通用户可访问的页面与接口
_USER_EXACT = {
    '/', '/login', '/logout', '/favicon.ico',
    '/api/auth/check', '/api/auth/me',
    '/pulse', '/pulse/',
    '/pulse/api/campus', '/pulse/api/campus/crisis-posts',
}
_USER_PREFIXES = ('/static/', '/pulse/poll/', '/pulse/api/revision/')

# /pulse/api/revision/ 下仍只对管理员开放的操作（发送邮件、改定时、消耗额度的手动触发）
_ADMIN_REVISION = re.compile(r'^/pulse/api/revision/(weekly/test-email|weekly/[^/]+/(send|retry)|memes/refresh)$')
_ADMIN_REVISION_POST = {'/pulse/api/revision/weekly', '/pulse/api/revision/weekly/config'}


def admin_usernames():
    names = {name.strip() for name in os.getenv('WEB_ADMIN_USERS', '').split(',') if name.strip()}
    if not names:
        primary = os.getenv('WEB_AUTH_USERNAME', '').strip()
        if primary:
            names.add(primary)
    return names


def current_username():
    if session.get('authenticated') is not True:
        return ''
    return str(session.get('username') or '')


def is_admin():
    username = current_username()
    return bool(username) and username in admin_usernames()


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
