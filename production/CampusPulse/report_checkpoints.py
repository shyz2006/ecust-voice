"""Reuse only validated event chapters with identical research inputs."""
import hashlib
import json
import os
from pathlib import Path


class ChapterCheckpoints:
    def __init__(self, task_id, query, reports, forum_logs, template, root=None):
        from utils.task_runtime import task_output_dir
        self.task_id = task_id
        fingerprint = hashlib.sha256(json.dumps(
            {'version': 1, 'query': query, 'reports': reports, 'forum': forum_logs, 'template': template},
            sort_keys=True, ensure_ascii=False, default=str,
        ).encode()).hexdigest()
        self.root = (Path(root) if root is not None else task_output_dir(task_id, 'report')/'validated-chapters')/fingerprint

    def _path(self, chapter_id):
        return self.root/(hashlib.sha256(str(chapter_id).encode()).hexdigest()+'.json')

    def validate(self, chapter, headings):
        from .report_contract import validate_planned_ir_chapter
        from ReportEngine.evidence import validate_sources
        validate_planned_ir_chapter(chapter, headings)
        validate_sources({'chapters': [chapter]}, self.task_id)

    def load(self, chapter_id, headings):
        try:
            chapter = json.loads(self._path(chapter_id).read_text(encoding='utf-8'))
            self.validate(chapter, headings)
            return chapter
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def save(self, chapter_id, chapter, headings):
        self.validate(chapter, headings)
        path = self._path(chapter_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(chapter, ensure_ascii=False), encoding='utf-8')
        os.replace(temp, path)
