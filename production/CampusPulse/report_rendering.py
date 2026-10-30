"""Offline-capable event report rendering. Reading never calls an LLM."""
import html
import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

from markdown_it import MarkdownIt


def safe_url(value, image=False):
    from .source_policy import retired_url
    if not isinstance(value, str) or retired_url(value):
        return ''
    if image and re.match(r'^data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+$', value):
        return value
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme.lower() in ('http', 'https') and parsed.hostname else ''
    except ValueError:
        return ''


def esc(value):
    return html.escape(str(value or ''), quote=True)


class ReportRenderer:
    def __init__(self, references=None):
        self.references=references
        self.markdown = MarkdownIt('commonmark', {'html': False, 'breaks': True}).enable(['table', 'strikethrough'])
        self.markdown.validateLink = lambda url: bool(safe_url(url)) or url.startswith('#')
        self.charts = []
        self.has_mermaid = False
        self.sources = []
        self.markdown.renderer.rules['fence'] = self._fence

    def _fence(self, tokens, index, options, env):
        token = tokens[index]
        language = token.info.strip().lower().split(' ')[0]
        if language == 'mermaid':
            self.has_mermaid = True
            # The original diagram remains available when a diagram is invalid.
            return '<figure class="diagram"><div class="mermaid">'+esc(token.content)+'</div><details><summary>流程图文本</summary><pre>'+esc(token.content)+'</pre></details></figure>'
        if language in ('chart', 'chartjs', 'chart.js'):
            try:
                data = json.loads(token.content)
                return self.widget({'widgetType': 'chart.js/'+str(data.get('type', 'bar')), 'data': data.get('data', data)})
            except (ValueError, AttributeError):
                pass
        return '<pre><code>'+esc(token.content)+'</code></pre>'

    def text(self, value):
        value=self.references.clean(value) if self.references else str(value or '')
        return self.markdown.render(value)

    def inlines(self, runs):
        if not any(run.get('marks') for run in runs if isinstance(run, dict)):
            return self.text(''.join(str(run.get('text', '')) for run in runs if isinstance(run, dict)))
        parts = []
        for run in runs:
            if not isinstance(run, dict):
                continue
            value = str(run.get('text', ''))
            for mark in run.get('marks') or []:
                if not isinstance(mark, dict):
                    continue
                kind = mark.get('type')
                delimiter = {'bold': '**', 'strong': '**', 'italic': '*', 'em': '*', 'code': '`', 'strike': '~~'}.get(kind)
                if delimiter:
                    value = delimiter+value+delimiter
                elif kind == 'link':
                    url = safe_url(mark.get('href') or mark.get('value'))
                    if url:
                        if url not in self.sources:
                            self.sources.append(url)
                        url=url.replace('>', '%3E').replace('<', '%3C').replace('\n','').replace('\r','')
                        if self.references:
                            self.references.add(url, str(run.get('text','')))
                            value=self.references.label(value)
                        else:
                            value = '['+value.replace(']', '\\]')+'](<'+url+'>)'
            parts.append(value)
        return self.text(''.join(parts))

    def blocks(self, blocks):
        if isinstance(blocks, str):
            return self.text(blocks)
        if isinstance(blocks, dict):
            blocks = [blocks]
        return ''.join(self.block(block) for block in blocks or [])

    def block(self, block):
        if isinstance(block, str):
            return self.text(block)
        if isinstance(block, list):
            return self.blocks(block)
        if not isinstance(block, dict):
            return ''
        kind = block.get('type')
        if kind == 'paragraph':
            return self.inlines(block.get('inlines') or [{'text': block.get('text', '')}])
        if kind == 'heading':
            try:
                level = min(6, max(3, int(block.get('level', 3))))
            except (ValueError, TypeError):
                level = 3
            text=self.references.clean(block.get('text','')) if self.references else str(block.get('text',''))
            return '<h'+str(level)+'>'+self.markdown.renderInline(text)+'</h'+str(level)+'>'
        if kind in ('markdown', 'text'):
            return self.text(block.get('content') or block.get('text'))
        if kind == 'code':
            language = str(block.get('lang', block.get('language', '')))
            if language.lower() in ('md','markdown'):
                return self.text(block.get('content',''))
            return self.text('```'+language+'\n'+str(block.get('content', ''))+'\n```')
        if kind == 'list':
            tag = 'ol' if block.get('listType') == 'ordered' else 'ul'
            return '<'+tag+'>'+''.join('<li>'+self.blocks(item)+'</li>' for item in block.get('items') or [])+'</'+tag+'>'
        if kind == 'table':
            rows = []
            for row in block.get('rows') or []:
                cells = []
                for cell in row.get('cells') or []:
                    attrs = ''
                    for key in ('rowspan', 'colspan'):
                        try:
                            number = min(30, max(1, int(cell.get(key, 1))))
                        except (ValueError, TypeError):
                            number = 1
                        attrs += ' '+key+'="'+str(number)+'"'
                    cells.append('<td'+attrs+'>'+self.blocks(cell.get('blocks') or cell.get('text', ''))+'</td>')
                rows.append('<tr>'+''.join(cells)+'</tr>')
            return '<figure class="table-wrap"><table><tbody>'+''.join(rows)+'</tbody></table>'+self.caption(block)+'</figure>'
        if kind == 'widget':
            return self.widget(block)
        if kind == 'figure':
            image = block.get('img') or {}
            src = safe_url(image.get('src'), image=True)
            return '<figure>'+('<img src="'+esc(src)+'" alt="'+esc(image.get('alt'))+'">' if src else '')+self.caption(block)+'</figure>'
        if kind=='blockquote' and self.references:
            self.references.note(block)
            return ''
        if kind in ('blockquote', 'callout'):
            return '<aside>'+self.blocks(block.get('blocks') or block.get('content') or block.get('text', ''))+'</aside>'
        if kind == 'math':
            return '<pre class="formula">'+esc(block.get('latex'))+'</pre>'
        children = ''.join(self.blocks(block[key]) for key in ('blocks', 'children', 'items', 'content', 'body') if isinstance(block.get(key), (list, dict, str)))
        return children or self.text(block.get('text') or block.get('caption') or '')

    def caption(self,block):
        if self.references:
            block=dict(block,caption=self.references.clean(block.get('caption') or block.get('title') or ''))
        return '<figcaption>'+esc(block.get('caption') or block.get('title'))+'</figcaption>' if block.get('caption') or block.get('title') else ''

    def widget(self, block):
        data = block.get('data') or {}
        if not data:
            chapter_data=getattr(self,'chapter_data',{})
            if isinstance(chapter_data,dict):
                data=chapter_data.get(block.get('dataRef')) or chapter_data.get(block.get('widgetId')) or (chapter_data if 'datasets' in chapter_data else {})
        if not isinstance(data, dict):
            return '<pre>'+esc(json.dumps(data, ensure_ascii=False))+'</pre>'
        props = block.get('props') or {}
        title = props.get('title') or block.get('title') or '图表'
        if self.references:title=self.references.clean(title)
        labels = data.get('labels') or []
        datasets = data.get('datasets') or []
        if not datasets and isinstance(data.get('values'), list):
            datasets = [{'label': title, 'data': data['values']}]
        labels = [str(label) for label in labels] if isinstance(labels, list) else []
        cleaned = []
        for dataset in datasets if isinstance(datasets, list) else []:
            if not isinstance(dataset, dict) or not isinstance(dataset.get('data'), list):
                continue
            values = [v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None for v in dataset['data']]
            cleaned.append({'label': str(dataset.get('label') or title), 'data': values})
        table = '<div class="table-wrap"><table><thead><tr><th>项目</th>'+''.join('<th>'+esc(d['label'])+'</th>' for d in cleaned)+'</tr></thead><tbody>'
        count = max([len(labels)]+[len(d['data']) for d in cleaned])
        for index in range(count):
            table += '<tr><td>'+esc(labels[index] if index < len(labels) else str(index+1))+'</td>'+''.join('<td>'+esc(d['data'][index] if index < len(d['data']) and d['data'][index] is not None else '—')+'</td>' for d in cleaned)+'</tr>'
        table += '</tbody></table></div>'
        kind = str(block.get('widgetType') or '').split('/')[-1]
        chart = ''
        if cleaned and any(v is not None for d in cleaned for v in d['data']) and kind in ('bar', 'line', 'pie', 'doughnut', 'radar', 'polarArea'):
            chart_id = 'report-chart-'+str(len(self.charts))
            self.charts.append({'id': chart_id, 'type': kind, 'data': {'labels': labels or [str(i+1) for i in range(count)], 'datasets': cleaned}})
            chart = '<div class="chart-area"><canvas id="'+chart_id+'" aria-label="'+esc(title)+'" role="img"></canvas></div>'
        if not cleaned:
            # Unknown formats remain visible instead of disappearing from the report.
            table = '<pre>'+esc(json.dumps(data, ensure_ascii=False, indent=2))+'</pre>'
        return '<figure class="chart"><figcaption>'+esc(title)+'</figcaption>'+chart+('<details><summary>查看图表数据</summary>'+table+'</details>' if chart else table)+'</figure>'

    def scripts(self):
        root = Path(__file__).resolve().parent.parent/'ReportEngine/renderers/libs'
        scripts = []
        if self.charts:
            scripts.append((root/'chart.js').read_text(encoding='utf-8'))
        if self.has_mermaid:
            scripts.append((root/'mermaid-10.9.3.min.js').read_text(encoding='utf-8'))
        setup = '''window.reportReady=(async()=>{const palette=['#648bc4','#a38bc6','#7da393','#d5a36b','#c57f96','#7cabb5'];
for(const spec of CHARTS){try{spec.data.datasets.forEach((d,i)=>{d.borderColor=palette[i%palette.length];d.backgroundColor=['pie','doughnut','polarArea'].includes(spec.type)?palette:palette[i%palette.length]+'66';d.borderWidth=2;d.spanGaps=false;});new Chart(document.getElementById(spec.id),{type:spec.type,data:spec.data,options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{position:'bottom'}},scales:['bar','line'].includes(spec.type)?{y:{beginAtZero:true}}:{}}});}catch(e){document.getElementById(spec.id).closest('figure').querySelector('details').open=true;}}
if(window.mermaid){mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'neutral',flowchart:{htmlLabels:false},fontFamily:'sans-serif'});for(const node of document.querySelectorAll('.mermaid')){try{await mermaid.run({nodes:[node],suppressErrors:true});}catch(e){node.closest('figure').querySelector('details').open=true;}}}
await document.fonts.ready;window.reportRenderComplete=true;})();'''.replace('CHARTS', json.dumps(self.charts, ensure_ascii=False))
        scripts.append(setup)
        return ''.join('<script>'+re.sub(r'</script', r'<\/script', script, flags=re.I)+'</script>' for script in scripts)


STYLE = '''
*{box-sizing:border-box}body{margin:0;color:#292b32;background:#f3f0ea;font-family:"Noto Sans CJK SC","Noto Sans SC",sans-serif}.report{max-width:1000px;padding:40px 48px;margin:24px auto;background:#fffefa;border:1px solid #e5dfeb;border-radius:18px}header{font-size:12px;color:#787080;border-bottom:1px solid #e5dfeb;padding-bottom:12px}h1{font-size:27px;line-height:1.5;margin:22px 0 28px;overflow-wrap:anywhere}h2{font-size:21px;color:#56446b;margin:32px 0 18px;break-after:avoid}h3,h4{break-after:avoid}h3{font-size:17px}article{font-size:15px;line-height:1.9;overflow-wrap:anywhere}p{margin:0 0 14px;orphans:3;widows:3}.report-references{margin-top:36px;padding-top:20px;border-top:1px solid #e5dfeb}.report-references li{font-size:12px;margin:16px 0;overflow-wrap:anywhere}.report-references p{margin:0 0 4px}.report-references blockquote{font-size:12px;background:#f5f1f7;padding:12px;margin:14px 0}.source{font-size:11px;color:#68616f;margin:7px 0}a{color:#66508b;text-underline-offset:3px}li p{margin:0}li{margin:5px 0}aside{padding:14px 18px;border-left:3px solid #a38bc6;background:#f4eff9;margin:18px 0}figure{margin:22px 0}figcaption{font-size:14px;font-weight:600;margin:8px 0 12px}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.65}td,th{border:1px solid #ddd7e5;padding:9px 12px;vertical-align:top;min-width:80px}th,thead{background:#eee8f5}td p{margin:0}tbody tr:nth-child(even){background:#faf8fc}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2eff5;padding:14px;border-radius:8px;font-size:12px;line-height:1.7}code{font-family:monospace;background:#f2eff5;padding:2px 4px}pre code{padding:0}img,svg{max-width:100%;height:auto}.chart-area{height:320px;position:relative}.chart,.diagram{border:1px solid #e5dfeb;border-radius:12px;padding:18px;break-inside:avoid}summary{font-size:12px;color:#787080;cursor:pointer;margin:12px 0}.mermaid{text-align:center}footer{margin-top:30px;padding-top:14px;border-top:1px solid #e5dfeb;font-size:11px;color:#787080}@page{size:A4;margin:18mm 16mm 20mm}@media(max-width:640px){.report{margin:0;padding:24px 18px;border:0;border-radius:0}h1{font-size:23px}.chart-area{height:270px}}@media print{body{background:white}.report{max-width:none;padding:0;margin:0;border:0;border-radius:0}article{font-size:10.5pt;line-height:1.8}h1{font-size:20pt}h2{font-size:15pt}h3{font-size:12pt}.source{font-size:8pt}thead{display:table-header-group}tr,figure{break-inside:avoid}.table-wrap{overflow:visible}.chart-area{height:76mm}details[open] summary{display:none}.diagram details,.chart details{display:none}}
'''
