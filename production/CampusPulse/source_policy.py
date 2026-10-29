"""Retired sources stay outside active collection and public aggregation."""
from urllib.parse import urlsplit

RETIRED = frozenset(('xiaohongshu', 'xiaohongshu-school'))
RETIRED_API = '/pulse/api/xhs-browser/'


def active(source):
    return source not in RETIRED


def retired_url(value):
    try:
        host = (urlsplit(value or '').hostname or '').lower()
        return any(host == domain or host.endswith('.' + domain)
                   for domain in ('xiaohongshu.com', 'xhslink.com', 'xhslink.cn', 'rednote.com'))
    except (ValueError, TypeError):
        return False


_REMOVED = object()


def _clean(value):
    if isinstance(value, dict):
        if (isinstance(value.get('source'), str) and value['source'] in RETIRED) or value.get('platform') == '小红书':
            return _REMOVED
        if any(retired_url(value.get(key)) for key in ('url', 'link')):
            return _REMOVED
        result = {key: cleaned for key, item in value.items() if key not in RETIRED
                  and (cleaned := _clean(item)) is not _REMOVED}
        if value.get('entries') and not result.get('entries'):
            return _REMOVED
        return result
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _clean(item)) is not _REMOVED]
    if isinstance(value, str) and value in (*RETIRED, '小红书'):
        return _REMOVED
    return value


def public_payload(value):
    result = _clean(value)
    return None if result is _REMOVED else result
