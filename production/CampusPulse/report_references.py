"""Keep report prose free of citation links while retaining a traceable appendix."""
import copy
import html
import re

from .report_rendering import safe_url


URL = re.compile(r'''https?://[^\s<>"'，。；！？、（）\u4e00-\u9fff]+''')
LINK = re.compile(r'(?<!!)\[([^\]\n]*)\]\(\s*<?(https?://(?:[^()\s]|\([^()\s]*\))+)\s*(?:"[^"]*")?\)')
CITATION = re.compile(r'\[(?:[A-Z]\d+|\^?\d{1,3})\]')


def plain_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ' '.join(plain_text(item) for item in value)
    if isinstance(value, dict):
        return ' '.join(plain_text(value[key]) for key in ('text', 'content', 'blocks', 'inlines', 'children', 'items') if key in value)
    return ''


class References:
    def __init__(self, catalogue=None):
        self.catalogue = catalogue or {}
        self.records = []
        self.notes = []

    def add(self, url, label=''):
        url = safe_url(url)
        if not url:
            return
        if not any(item['url'] == url for item in self.records):
            info = self.catalogue.get(url) or {}
            self.records.append({'url': url, 'label': info.get('title') or label or url, 'id': info.get('id', '')})

    @staticmethod
    def label(value):
        value = str(value or '')
        plain=re.sub(r'[*_~`]', '',value)
        return '' if safe_url(plain.strip()) or re.fullmatch(r'\s*(?:\[?(?:[A-Z]?\d+)\]?|来源|原帖|原文|参考|出处|详情|查看原帖|查看原文|保留链接|链接)\s*', plain) else value

    def note(self, value):
        text = plain_text(value).strip()
        if text and text not in self.notes:
            self.notes.append(text)
        self.gather_links(value)
        for match in URL.finditer(text):self.add(match[0].rstrip('.,;:!?)]'))

    def gather_links(self, value):
        if isinstance(value, dict):
            if value.get('type') == 'link':
                self.add(value.get('href') or value.get('value'))
            self.add(value.get('href') or value.get('url'))
            for child in value.values():
                self.gather_links(child)
        elif isinstance(value, list):
            for child in value:
                self.gather_links(child)

    def clean(self, text):
        text = str(text or '')
        # Image resources are not visible citation links; preserve their syntax.
        images = []
        def image(match):
            images.append(match[0])
            return '\x00IMAGE'+str(len(images)-1)+'\x00'
        text = re.sub(r'!\[[^\]\n]*\]\([^\n]*?\)', image, text)
        def link(match):
            self.add(match[2].rstrip('>'), match[1])
            return self.label(match[1])
        pointer=re.compile(r'(?:^|[，,；; \t])(?:详见|参见|见|查看|来源[：:])[ \t]*'+LINK.pattern,flags=re.M)
        text=pointer.sub(lambda match:(self.add(match[2].rstrip('>'),match[1]) or ''),text)
        text = LINK.sub(link, text)
        text = re.sub(r'\[(?:[A-Z]\d+|\d{1,3}|来源|原文)\]\(#[^)]*\)', '', text)
        def attributed_quote(match):
            self.note(match[1])
            return ''
        text=re.sub(r'[“「]([^”」\n]{1,500})[”」]\s*\[(?:[A-Z]\d+|\d{1,3})\]',attributed_quote,text)
        text=re.sub(r'<(https?://[^>\s]+)>',lambda match: (self.add(match[1]) or ''),text)
        def definition(match):
            self.add(match[1])
            return ''
        text = re.sub(r'^[ \t]*\[[^\]\n]+\]:\s*<?(https?://[^\s>]+)>?[^\n]*$', definition, text, flags=re.M)
        # A block quotation is a cited excerpt, so move it beside the sources.
        def quote(match):
            self.note(re.sub(r'^\s*>\s?', '', match[0], flags=re.M))
            return ''
        text = re.sub(r'^(?:[ \t]*>[^\n]*(?:\n|$))+', quote, text, flags=re.M)
        def bare(match):
            value = match[0]
            while value.endswith(('.', ',', ';', ':', '!', '?', ')', ']')):
                if value.endswith(')') and value.count('(') >= value.count(')'):
                    break
                value = value[:-1]
            self.add(value)
            return ''
        text = URL.sub(bare, text)
        text = CITATION.sub('', text)
        text = re.sub(r'[，,；;][ \t]*(?:详见|参见|见|查看)[ \t]*[。.]?$', '', text)
        text = re.sub(r'^[ \t]*(?:来源[：:]?|详见|参见|见|查看)[ \t]*[。.]?[ \t]*$', '', text, flags=re.M)
        for index, value in enumerate(images):
            text = text.replace('\x00IMAGE'+str(index)+'\x00', value)
        return text

    def document(self, document):
        """Prepare Markdown export without modifying the stored research IR."""
        def walk(value):
            if isinstance(value, list):
                return [cleaned for item in value if (cleaned := walk(item)) is not None]
            if not isinstance(value, dict):
                return value
            if value.get('type') == 'link':
                self.add(value.get('href') or value.get('value'))
                return None
            if value.get('type') == 'blockquote':
                self.note(value)
                return None
            value = dict(value)
            if any(mark.get('type') == 'link' for mark in value.get('marks', []) if isinstance(mark, dict)):
                value['text'] = self.label(value.get('text'))
            if value.get('footnotes'):
                for item in value.pop('footnotes'):
                    self.note(item)
            for key, child in value.items():
                if key in ('text', 'content', 'caption', 'title') and isinstance(child, str):
                    value[key] = self.clean(child)
                elif isinstance(child, (dict, list)):
                    value[key] = walk(child)
            return value
        return walk(copy.deepcopy(document))

    def html(self):
        e = html.escape
        if not self.records and not self.notes:
            return ''
        records = ''.join('<li'+(' id="'+e(item['id'], quote=True)+'"' if item['id'] else '')+'><p>'+e(str(item['label']))+'</p><a href="'+e(item['url'], quote=True)+'" target="_blank" rel="noopener noreferrer">'+e(item['url'])+'</a></li>' for item in self.records)
        notes = ''.join('<blockquote><p>'+e(note)+'</p></blockquote>' for note in self.notes)
        return '<section class="report-references" id="report-references"><h2>参考资料与原帖</h2>'+('<ol>'+records+'</ol>' if records else '')+notes+'</section>'

    def markdown(self):
        if not self.records and not self.notes:
            return ''
        lines = ['\n\n## 参考资料与原帖\n']
        lines += [str(index)+'. '+str(item['label'])+' — <'+item['url']+'>' for index, item in enumerate(self.records, 1)]
        lines += ['\n> '+note.replace('\n', '\n> ') for note in self.notes]
        return '\n\n'.join(lines)+'\n'
