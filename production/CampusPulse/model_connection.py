"""OpenAI-compatible connections, bounded parameter adaptation and safe diagnostics."""
from urllib.parse import urlsplit, urlunsplit
import time


def normalize_base_url(value):
    value = str(value or '').strip().rstrip('/')
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('请填写HTTP(S)接口基础地址；密钥应填写在API Key栏')
    path = parts.path.rstrip('/')
    for suffix in ('/chat/completions', '/models'):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    return urlunsplit((parts.scheme, parts.netloc, path, '', ''))


def status_code(exc):
    return getattr(exc, 'status_code', None) or getattr(getattr(exc, 'response', None), 'status_code', None)


class ProviderError(RuntimeError):
    """Retain retry classification without propagating provider payloads to logs."""
    def __init__(self, exc):
        super().__init__(safe_error(exc))
        self.status_code = status_code(exc)


def safe_error(exc):
    if isinstance(exc, ProviderError):
        return str(exc)
    code = status_code(exc)
    detail = str(getattr(exc, 'body', None) or '').lower()
    if code == 403 and any(s in detail for s in ('no longer available', 'preview has ended', 'model is deprecated')):
        return '该模型已下线或免费预览已结束（HTTP 403）。请在配置中选择其他可用模型，并测试实际调用。'
    messages = {
        401: '模型服务认证失败（HTTP 401）。请核对此接口的API Key。',
        403: '模型服务拒绝访问（HTTP 403）。请核对密钥的模型权限、服务商限制及接口地址；这不是前端按钮故障。',
        404: '模型或接口不存在（HTTP 404）。请使用服务商的OpenAI兼容基础地址和准确模型ID。',
        429: '模型服务限流或额度不足（HTTP 429）。请检查服务商额度或稍后重试。',
        400: '模型服务不接受当前参数（HTTP 400）。请检查模型ID及接口协议。',
    }
    if code in messages:
        return messages[code]
    if code and code >= 500:
        return '模型服务暂时故障（HTTP %s），请稍后重试。' % code
    if isinstance(exc, ValueError):
        return '接口地址或响应格式不正确；请核对OpenAI兼容配置。'
    if 'timeout' in type(exc).__name__.lower():
        return '模型服务连接超时，请检查网络或稍后重试。'
    return '无法连接模型服务，请检查接口地址、网络和服务商状态。'


def completion(client, **kwargs):
    """Retry only provider-confirmed unsupported parameters; never retry permission failures."""
    for attempt in range(4):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:
            if status_code(exc) != 400:
                raise
            body = getattr(exc, 'body', None)
            detail = str(body or exc).lower()
            if 'temperature' in kwargs and 'temperature' in detail and any(w in detail for w in ('unsupported', 'not support', 'only', 'not allowed')):
                kwargs.pop('temperature')
                continue
            if 'max_tokens' in kwargs and 'max_completion_tokens' in detail:
                kwargs['max_completion_tokens'] = kwargs.pop('max_tokens')
                continue
            if 'reasoning_effort' in kwargs and 'reasoning_effort' in detail and any(w in detail for w in ('unsupported', 'not support', 'unknown', 'not allowed')):
                kwargs.pop('reasoning_effort')
                continue
            raise
    raise RuntimeError('服务商反复拒绝兼容参数')


def probe(api_key, base_url, model):
    from openai import OpenAI
    if not api_key or not model:
        return {'success': False, 'message': '请填写API Key与模型ID，再测试连接。'}
    client = None
    tracked = False
    started = time.monotonic()
    try:
        kwargs = {'api_key': api_key, 'timeout': 25, 'max_retries': 0}
        normalized = normalize_base_url(base_url)
        if normalized:
            kwargs['base_url'] = normalized
        client = OpenAI(**kwargs)
        tracked = getattr(client.chat.completions.create, '_bf_usage_ledger', False)
        response = completion(client, model=model, messages=[{'role':'user','content':'请只回复OK。'}], max_tokens=24, temperature=0, timeout=25)
        from . import telemetry
        if not tracked:
            telemetry.record_response(getattr(response,'usage',None),time.monotonic()-started,engine='ConnectionTest')
        text = (response.choices[0].message.content or '').strip()
        if not text:
            return {'success': False, 'message': '接口已响应，但未返回正文；该模型需要更高输出预算或其他协议。'}
        return {'success': True, 'message': '连接测试通过：模型已实际返回正文。', 'base_url': normalized}
    except Exception as exc:
        if client is not None and not tracked:
            from . import telemetry
            telemetry.record_response(None,time.monotonic()-started,success=False,engine='ConnectionTest')
        return {'success': False, 'message': safe_error(exc), 'status_code': status_code(exc)}
    finally:
        if client is not None:
            client.close()
