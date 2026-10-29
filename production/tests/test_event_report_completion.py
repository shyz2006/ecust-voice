import json
import tempfile
import threading
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from CampusPulse import report_automation as automation
from CampusPulse import research
from CampusPulse.report_rendering import ReportRenderer


class AutomaticCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'completion.json'
        self.patches = [patch.object(automation, '_path', return_value=self.path),
                        patch('utils.task_runtime.read_task_metadata', return_value={'pulse_revision': 2, 'auto_report': True})]
        for item in self.patches:
            item.start()
    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def test_missing_report_is_submitted_without_browser_and_recovery_is_bounded(self):
        result = {'status': 'awaiting_report', 'can_resume_report': True}
        with patch.object(research, 'status', return_value=result), patch.object(research, 'resume_report') as submit:
            automation.reconcile(['task_test'], now=1000)
            automation.reconcile(['task_test'], now=1001)
            self.assertEqual(submit.call_count, 1)
            self.assertEqual(automation.state('task_test')['submissions'], 1)
            # Durable file survives an in-memory monitor restart.
            automation.reconcile(['task_test'], now=1200)
            automation.reconcile(['task_test'], now=1500)
            automation.reconcile(['task_test'], now=2500)
            self.assertEqual(submit.call_count, automation.MAX_SUBMISSIONS)
            submit.assert_called_with('task_test', automatic=True)

    def test_running_completed_and_permanent_failures_are_not_resubmitted(self):
        for result in [{'status': 'completed'}, {'status': 'reporting'},
                       {'status': 'failed', 'can_resume_report': True, 'automatic_retry_allowed': False}]:
            with patch.object(research, 'status', return_value=result), patch.object(research, 'resume_report') as submit:
                self.assertEqual(automation.reconcile(['task_test'], now=1000), [])
                submit.assert_not_called()

    def test_old_historical_tasks_do_not_start_spending_on_read_or_restart(self):
        with patch('utils.task_runtime.read_task_metadata', return_value={'pulse_revision': 2}), patch.object(research, 'status') as status:
            self.assertEqual(automation.reconcile(['task_test']), [])
            status.assert_not_called()

    def test_parallel_monitor_checks_submit_once(self):
        with patch.object(research, 'status', return_value={'status': 'failed', 'can_resume_report': True}), patch.object(research, 'resume_report') as submit:
            threads = [threading.Thread(target=automation.reconcile, args=(['task_test'], 1000)) for _ in range(5)]
            for thread in threads:thread.start()
            for thread in threads:thread.join()
            self.assertEqual(submit.call_count, 1)


class ReportRenderingTests(unittest.TestCase):
    def test_markdown_table_lists_emphasis_and_raw_html_safety(self):
        renderer = ReportRenderer()
        result = renderer.block({'type': 'paragraph', 'inlines': [{'text': '**重点**\n\n- 一项\n- 两项\n\n|议题|数量|\n|---|---|\n|校园|12|\n\n<script>alert(1)</script>\n[危险](javascript:alert(1))'}]})
        for expected in ('<strong>重点</strong>', '<ul>', '<table>', '&lt;script&gt;'):
            self.assertIn(expected, result)
        self.assertNotIn('<script>', result)
        self.assertNotIn('href="javascript:', result)

    def test_structured_table_and_inline_marks_survive(self):
        renderer = ReportRenderer()
        result = renderer.blocks([{'type': 'table', 'rows': [{'cells': [{'blocks': [{'type': 'paragraph', 'inlines': [{'text': '真实数据', 'marks': [{'type': 'bold'}, {'type': 'link', 'href': 'https://example.com/evidence'}]}]}]}]}]}])
        self.assertIn('<table>', result)
        self.assertIn('<strong>真实数据</strong>', result)
        self.assertIn('https://example.com/evidence', renderer.sources)

    def test_markdown_blocks_survive_when_a_source_link_is_an_inline_mark(self):
        renderer=ReportRenderer()
        result=renderer.inlines([{'text':'**重点**\n\n- 一项\n- 二项\n\n'}, {'text':'原始资料','marks':[{'type':'link','href':'https://example.com/source'}]}])
        self.assertIn('<ul>',result)
        self.assertIn('<strong>重点</strong>',result)
        self.assertIn('href="https://example.com/source"',result)

    def test_numeric_chart_keeps_zero_and_missing_values_with_table_fallback(self):
        renderer = ReportRenderer()
        result = renderer.widget({'widgetType': 'chart.js/line', 'data': {'labels': ['一', '二', '三'], 'datasets': [{'label': '讨论量', 'data': [0, None, 12]}]}})
        self.assertIn('<canvas', result)
        self.assertIn('<table>', result)
        self.assertEqual(renderer.charts[0]['data']['datasets'][0]['data'], [0, None, 12])
        self.assertIn('window.reportRenderComplete=true', renderer.scripts())

    def test_mermaid_and_markdown_code_blocks_are_rendered(self):
        renderer = ReportRenderer()
        result = renderer.block({'type': 'code', 'lang': 'markdown', 'content': '**说明**\n\n```mermaid\nflowchart LR\n A[检索] --> B[核对]\n```'})
        self.assertIn('<strong>说明</strong>', result)
        self.assertIn('class="mermaid"', result)
        self.assertTrue(renderer.has_mermaid)

    def test_hostile_link_and_unknown_chart_remain_safe_and_readable(self):
        renderer = ReportRenderer()
        result = renderer.inlines([{'text': '文字', 'marks': [{'type': 'link', 'href': 'javascript:alert(1)'}]}])
        self.assertNotIn('<a ', result)
        result = renderer.widget({'widgetType': 'chart.js/sankey', 'data': {'labels': ['材料'], 'datasets': [{'data': [3]}]}})
        self.assertIn('<table>', result)
        self.assertNotIn('<canvas', result)


class ReportJsonRecoveryTests(unittest.TestCase):
    def test_invalid_json_is_retried_in_same_task_instead_of_requiring_button(self):
        from ReportEngine import flask_interface as interface
        from ReportEngine.nodes.chapter_generation_node import ChapterJsonParseError
        task = Mock(research_task_id='task_test', task_id='report_test', status='running')
        task.created_at = task.updated_at = __import__('datetime').datetime.now()
        agent = Mock()
        agent.load_input_files.return_value = {'reports': {}}
        agent.generate_report.side_effect = [ChapterJsonParseError('temporary malformed JSON'), {'html_content': '<html>完成</html>'}]
        with patch.object(interface, 'task_log_context', return_value=nullcontext()), patch.object(interface, 'check_engines_ready', return_value={'ready': True, 'latest_files': {}}), patch.object(interface, '_build_task_report_config'), patch.object(interface, 'create_agent', return_value=agent), patch.object(interface, 'render_forum_log', return_value=''), patch.object(interface.time, 'sleep'):
            interface._run_report_generation(task, '校园议题')
        self.assertEqual(agent.generate_report.call_count, 2)
        task.update_status.assert_any_call('completed', 100)


class ChapterCheckpointTests(unittest.TestCase):
    def test_only_validated_chapters_with_identical_inputs_are_reused(self):
        from CampusPulse.report_checkpoints import ChapterCheckpoints
        chapter={'blocks':[{'type':'paragraph','inlines':[{'text':'资料'*850}]}]}
        with tempfile.TemporaryDirectory() as root, patch('ReportEngine.evidence.validate_sources') as validate:
            first=ChapterCheckpoints('task_test','研究问题',['原始研究材料'],'论坛讨论',['模板'],root=root)
            first.save('S1',chapter,[])
            restarted=ChapterCheckpoints('task_test','研究问题',['原始研究材料'],'论坛讨论',['模板'],root=root)
            self.assertEqual(restarted.load('S1',[]),chapter)
            changed=ChapterCheckpoints('task_test','研究问题',['新增研究材料'],'论坛讨论',['模板'],root=root)
            self.assertIsNone(changed.load('S1',[]))
            validate.assert_called()
            first._path('S1').write_text('{invalid',encoding='utf-8')
            self.assertIsNone(first.load('S1',[]))

    def test_bad_length_and_invalid_sources_never_enter_checkpoint(self):
        from CampusPulse.report_checkpoints import ChapterCheckpoints
        with tempfile.TemporaryDirectory() as root:
            checkpoint=ChapterCheckpoints('task_test','问题',[],'',[],root=root)
            with self.assertRaises(ValueError):
                checkpoint.save('S1',{'blocks':[{'type':'paragraph','inlines':[{'text':'过短'}]}]},[])
            with patch('ReportEngine.evidence.validate_sources',side_effect=ValueError('来源不符')):
                with self.assertRaises(ValueError):checkpoint.save('S1',{'blocks':[{'type':'paragraph','inlines':[{'text':'文'*1700}]}]},[])
            self.assertIsNone(checkpoint.load('S1',[]))

    def test_markdown_download_does_not_run_chart_review_or_model_calls(self):
        from ReportEngine.renderers.markdown_renderer import MarkdownRenderer
        with patch('ReportEngine.renderers.markdown_renderer.get_chart_review_service') as review:
            text=MarkdownRenderer().render({'metadata':{'title':'报告'},'chapters':[{'title':'分析','blocks':[{'type':'paragraph','inlines':[{'text':'正文'}]}]}]},review_charts=False)
        self.assertIn('正文',text)
        review.assert_not_called()


if __name__ == '__main__':
    unittest.main()
