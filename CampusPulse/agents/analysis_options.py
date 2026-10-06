"""输入栏的选择独立传入执行流程，不能因问题长度而丢失。"""
EFFORTS = {
    'quick': {'label': '快速', 'workflow': 'lean', 'budget_scale': 0.65},
    'standard': {'label': '标准', 'workflow': 'lean_verified', 'budget_scale': 1.0},
    'deep': {'label': '深入', 'workflow': 'central_verified', 'budget_scale': 1.5},
}
PSYCHOLOGY = {
    'auto': '按议题选择重点',
    'needs': '诉求与服务问题',
    'stress': '学习压力与支持资源',
    'conflict': '关系冲突与沟通',
    'participation': '活动参与与阻碍',
    'attribution': '认知归因理论与心理韧性',
    'attachment': '依恋理论与人际连接',
    'motivation': '自我决定理论与内在动机',
    'social': '群体动力学与去抑制效应',
}
IDEOLOGY = {
    'evidence': '事实核查与证据缺口',
    'actions': '可执行改进清单',
    'communication': '回应与沟通方案',
    'activity': '活动执行与效果评估',
    'lideshuren': '立德树人 · 价值观涵育',
    'sanquanyuren': '三全育人 · 协同机制',
    'developmental': '发展性心理健康观',
    'narrative': '青年话语体系创新',
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
    return result


def prompt(profile):
    options = profile.get('analysis_options') or {}
    lines = []
    if options.get('psych_lens') in PSYCHOLOGY:
        lines.append(('研究重点：' if options['psych_lens'] in ('auto','needs','stress','conflict','participation') else '心理学理论视角：') + PSYCHOLOGY[options['psych_lens']])
    if options.get('ideology') in IDEOLOGY:
        lines.append(('交付要求：' if options['ideology'] in ('evidence','actions','communication','activity') else '思政引领立足点：') + IDEOLOGY[options['ideology']])
    practical = {
        'auto': '先依据原帖归纳主要问题；说明选定重点的证据，不强套理论。',
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
        if options.get(key) in practical:
            lines.append('具体交付要求：' + practical[options[key]])
    if not lines:
        return ''
    return '教师指定的分析方向（用于解释与建议，不改变证据事实）：\n' + '\n'.join(lines) + '\n请在分析和活动建议中体现指定方向，证据不足时明确标注，不推断个体诊断。\n'


def budget(base, effort):
    return max(1000, min(5400, int(base * EFFORTS[effort]['budget_scale'])))
