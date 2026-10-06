"""CNY reference costing from recorded token splits and explicitly supplied rates."""
import json
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

KEY = 'dashboard:cost-basis:v1'
FIELDS = ('input_cny_per_million', 'output_cny_per_million', 'fixed_paid_cny')


def read(conn):
    row = conn.execute('SELECT value FROM kv WHERE key=?', (KEY,)).fetchone()
    return json.loads(row[0]) if row else {}


def save(value):
    from . import storage
    if not isinstance(value, dict):
        raise ValueError('计价设置必须是对象')
    out = {}
    for k in FIELDS:
        raw = value.get(k)
        if raw is None or raw == '':
            out[k] = None
            continue
        try:
            n = Decimal(str(raw))
        except InvalidOperation:
            raise ValueError('费用必须是有效数字')
        if not n.is_finite() or n < 0 or n > 100000000:
            raise ValueError('费用必须是0至1亿元内的有限数字')
        out[k] = str(n)
    out['basis'] = str(value.get('basis') or '').strip()[:200]
    if any(out[k] is not None for k in FIELDS) and not out['basis']:
        raise ValueError('请注明服务商单价或账单依据')
    out['updated_at'] = int(time.time())
    with storage.connect() as conn:
        conn.execute('INSERT INTO kv(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     (KEY, json.dumps(out, ensure_ascii=False).encode()))
    return out


def summary(conn, usage, historical_input, historical_output, historical_split_tasks, historical_missing_tasks):
    basis = read(conn)
    ready = all(basis.get(k) is not None for k in FIELDS[:2])
    input_n = historical_input + usage['prompt_tokens']
    output_n = historical_output + usage['completion_tokens']
    model = (Decimal(input_n) * Decimal(basis[FIELDS[0]]) + Decimal(output_n) * Decimal(basis[FIELDS[1]]))/Decimal(1000000) if ready else None
    fixed = Decimal(basis['fixed_paid_cny']) if basis.get('fixed_paid_cny') is not None else None
    def money(v):
        return str(v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if v is not None else None
    return {'currency':'CNY', 'pricing':basis, 'model_estimate_cny':money(model),
            'registered_fixed_paid_cny':money(fixed), 'total_reference_cny':money(model+fixed) if model is not None and fixed is not None else None,
            'input_tokens':input_n, 'output_tokens':output_n, 'historical_split_tasks':historical_split_tasks,
            'historical_missing_tasks':historical_missing_tasks, 'unknown_usage_calls':usage['unknown_usage_calls'],
            'notes':['模型费为已记录输入/输出Token乘用户提供的统一参考单价，非服务商实付账单。',
                     '未记录用量的旧主研报、缺少usage的请求、缓存优惠与不同模型差价未计入；固定费用仅取已登记实付金额。',
                     '历史有记录的失败或草稿任务同样可能消耗Token，计入费用参考，不计为完成报告。']}
