import unittest
from unittest.mock import patch
from CampusPulse import weekly_report,report_progress
from ReportEngine.evidence import validate_sources

class WeeklyProgressTests(unittest.TestCase):
    def data(self):
        return {'observed_days':7,'previous_observed_days':7,'evidence':[{'id':'S1','period':'current'},{'id':'S2','period':'previous'}],
            'insights':{'headline':'校园一周','signals':[{'title':'学习体验','observation':'同学希望课程安排更清晰。','comparison':'本周更关心课程安排，上周聚焦选课信息。','evidence':['S1','S2']}],'follow_up':['教学联系老师了解课程信息更新情况。']}}
    def test_weekly_composes_existing_insights_without_event_template(self):
        value=weekly_report.build(self.data())
        self.assertEqual(len(value['chapters']),2)
        self.assertNotIn('事件全景',str(value));self.assertNotIn('传播路径',str(value))
        self.assertEqual(value['chapters'][0]['sections'][0]['evidence'],['S1','S2'])
    def test_insufficient_comparison_is_omitted(self):
        data=self.data();data['previous_observed_days']=1
        self.assertEqual(len(weekly_report.build(data)['chapters']),1)
    def test_invalid_evidence_prevents_publication(self):
        data=self.data();data['insights']['signals'][0]['evidence']=['invented']
        with self.assertRaises(ValueError):weekly_report.build(data)
    def test_source_repair_identifies_bad_url_preserving_check(self):
        evidence=[{'url':'https://real.invalid/source','title':'真实资料','excerpt':'原文'}]
        with patch('ReportEngine.evidence.source_evidence',return_value=evidence):
            with self.assertRaises(ValueError) as error:validate_sources({'chapters':[{'href':'https://invented.invalid/x'}]},'task_test')
            self.assertIn('https://invented.invalid/x',str(error.exception))
            self.assertIn('https://real.invalid/source',str(error.exception))
            validate_sources({'chapters':[{'href':'https://real.invalid/source'}]},'task_test')
    def test_progress_reports_repair_and_completed_counts(self):
        events=[{'type':'stage','payload':{'section_count':5}},
            {'type':'chapter_status','payload':{'chapterId':'a','status':'completed'}},
            {'type':'chapter_status','timestamp':'now','payload':{'chapterId':'b','status':'retrying','title':'第二章','attempt':1,'error':'来源URL待修正'}}]
        result=report_progress.describe(events)
        self.assertEqual(result['completed_chapters'],1);self.assertEqual(result['total_chapters'],5)
        self.assertIn('核对来源',result['message']);self.assertIn('第2次',result['message'])
    def test_stream_eviction_does_not_erase_progress(self):
        from ReportEngine.flask_interface import ReportTask
        with patch('ReportEngine.flask_interface._broadcast_event'):
            task=ReportTask('query','report_test')
            task.publish_event('stage',{'section_count':5})
            task.publish_event('chapter_status',{'chapterId':'a','status':'completed'})
            for _ in range(1005):task.publish_event('chapter_chunk',{'chapterId':'b','delta':'draft'})
        detail=task.to_dict()['report_detail']
        self.assertEqual(detail['completed_chapters'],1);self.assertEqual(detail['total_chapters'],5)
        self.assertNotIn('draft',str(detail))
