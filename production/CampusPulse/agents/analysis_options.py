"""输入栏的选择独立传入执行流程，不能因问题长度而丢失。"""
EFFORTS = {
    'auto': {'label': '自动路由', 'workflow': None, 'budget_scale': 1.0},
    'quick': {'label': '快速', 'workflow': 'lean', 'budget_scale': 0.65},
    'standard': {'label': '标准', 'workflow': 'lean_verified', 'budget_scale': 1.0},
    'deep': {'label': '深入', 'workflow': 'central_verified', 'budget_scale': 1.5},
}
PSYCHOLOGY = {
    'none': '无（不限定）',
    'custom': '自定义',
    'auto': '按议题自动匹配视角',
    'attribution': '认知归因理论与心理韧性',
    'attachment': '依恋理论与人际连接',
    'motivation': '自我决定理论与内在动机',
    'social': '群体动力学与去抑制效应',
    # 兼容历史归档
    'needs': '诉求与服务问题',
    'stress': '学习压力与支持资源',
    'conflict': '关系冲突与沟通',
    'participation': '活动参与与阻碍',
}
IDEOLOGY = {
    'none': '无（不限定）',
    'custom': '自定义',
    'auto': '按议题自动匹配立足点',
    'lideshuren': '立德树人 · 价值观涵育',
    'sanquanyuren': '三全育人 · 协同机制',
    'developmental': '发展性心理健康观',
    'narrative': '青年话语体系创新',
    # 兼容历史归档
    'evidence': '事实核查与证据缺口',
    'actions': '可执行改进清单',
    'communication': '回应与沟通方案',
    'activity': '活动执行与效果评估',
}


def normalize(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('分析选项格式不正确')
    result = {}
    for key, choices in (('thinking_effort', EFFORTS), ('psych_lens', PSYCHOLOGY), ('ideology', IDEOLOGY)):
        if key in value:
            selected = value[key]
            if not isinstance(selected, str) or selected not in choices:
                raise ValueError('无效分析选项：' + key)
            result[key] = selected
    for custom_key in ('custom_psych', 'custom_ideology'):
        if custom_key in value and value[custom_key] is not None:
            if not isinstance(value[custom_key], str):
                raise ValueError('自定义视角必须是文字')
            text = value[custom_key].strip()[:80]
            if text:
                result[custom_key] = text
    return result


def prompt(profile):
    options = profile.get('analysis_options') or {}
    lines = []
    psych_key = options.get('psych_lens')
    ideo_key = options.get('ideology')
    if psych_key == 'custom':
        if options.get('custom_psych'):
            lines.append('心理学/研究视角（教师自定义）：' + options['custom_psych'])
    elif psych_key in PSYCHOLOGY and psych_key not in ('auto', 'none'):
        lines.append(('心理学理论视角：' if psych_key in ('attribution', 'attachment', 'motivation', 'social') else '研究重点：') + PSYCHOLOGY[psych_key])
    if ideo_key == 'custom':
        if options.get('custom_ideology'):
            lines.append('思政引领/育人要求（教师自定义）：' + options['custom_ideology'])
    elif ideo_key in IDEOLOGY and ideo_key not in ('auto', 'none'):
        lines.append(('思政引领立足点：' if ideo_key in ('lideshuren', 'sanquanyuren', 'developmental', 'narrative') else '交付要求：') + IDEOLOGY[ideo_key])
    guidance = {
        'attribution': '结合认知归因理论分析学生对顺境/挫折的归因方式（内外部、稳定性、可控性），引导构建成长型思维与心理韧性。',
        'attachment': '从人际依恋与社会支持系统视角分析学生在宿舍、同伴、师生关系中的安全感与归属需求，促进健康人际连接。',
        'motivation': '运用自我决定理论（自主感、胜任感、联结感）剖析学生行为背后的内在动机与受挫点，赋能主动成长。',
        'social': '从群体动力学、从众心理与网络去抑制效应剖析校园圈层传播与情绪共振机制，引导理性表达与建设性共情。',
        'lideshuren': '立足立德树人根本任务，将解决学生实际困惑与正确世界观、人生观、价值观涵育自然融合，春风化雨、避免生硬说教。',
        'sanquanyuren': '体现全员、全过程、全方位“三全育人”理念，联动院系辅导员、心理中心、专业课教师与朋辈力量形成协同育人闭环。',
        'developmental': '秉持发展性心理健康教育观，聚焦全体学生的潜能开发、适应力提升与积极心理品质培养，不对个体作病理化诊断。',
        'narrative': '善用青年网言网语、流行梗文化与互动体验式载体实现话语转换，用学生听得懂、愿参与的方式开展心育与思政引导。',
        'needs': '区分具体诉求、受影响对象、发生场景和可核实服务问题；列出需核查的部门与信息。',
        'stress': '归纳压力来源、可提供的学校支持资源和转介条件；不对个人作诊断。',
        'conflict': '区分各方诉求与事实争议，给出沟通步骤、协商边界和升级处理条件。',
        'participation': '列出参与动机、时间成本和报名阻碍，提出可验证的活动改进假设。',
        'evidence': '输出已证实事实、原帖证据编号、未核实说法和下一步核查清单。',
        'actions': '输出行动表：建议动作、建议承接角色、执行步骤、建议时限、验收指标；未知责任部门与时限标为待确认。',
        'communication': '输出回应对象、需要解释的事实、可用回应草案、渠道与跟进节点；不得虚构学校承诺。',
        'activity': '输出活动对象、目标、执行流程、人员材料、时间预算和可观察的效果指标。',
    }
    for key in ('psych_lens', 'ideology'):
        if options.get(key) in guidance:
            lines.append('视角融合要求：' + guidance[options[key]])
    if not lines:
        return ''
    return '教师指定的理论与育人视角（用于解读现象与策划方案，不改变客观证据事实）：\n' + '\n'.join(lines) + '\n请在现象剖析、沟通话术和活动方案中自然融合上述视角，证据不足时明确标注，不推断个体诊断。\n'


def budget(base, effort):
    return max(1000, min(5400, int(base * EFFORTS[effort]['budget_scale'])))

