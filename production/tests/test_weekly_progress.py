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

class FormalWeeklyTests(unittest.TestCase):
    def data(self):
        row={'title':'学习支持','observation':'同学希望获得清晰的信息。','evidence':['S1']}
        return {'current_total':20,'previous_total':10,'categories':{'课程':[12,5],'生活':[8,5]},'observed_days':7,'previous_observed_days':7,
            'evidence':[{'id':'S1','period':'current'}],
            'insights':{'schema_version':2,'headline':'本周校园观察','overview':dict(row),'signals':[dict(row)],'psychology':[dict(row)],'outlook':[dict(row)],'follow_up':['下周由教学联系老师核对信息更新时间。']}}
    def test_formal_structure_preserves_analysis_and_actions_once(self):
        report=weekly_report.build(self.data())
        self.assertEqual(report['version'],'campus-weekly-v2')
        self.assertEqual([c['title'] for c in report['chapters']],['二、重点议题与变化','三、学生心理诉求与育人分析','四、下周趋势研判与工作建议'])
        self.assertEqual(str(report).count('教学联系老师'),1)
    def test_formal_analysis_requires_current_evidence(self):
        data=self.data();data['insights']['outlook'][0]['evidence']=['unknown']
        with self.assertRaises(ValueError):weekly_report.build(data)
    def test_formal_analysis_fields_cannot_disappear(self):
        data=self.data();data['insights'].pop('psychology')
        with self.assertRaises(ValueError):weekly_report.build(data)
    def test_opening_calculates_concentration_and_comparable_growth(self):
        from CampusPulse.weekly import data_summary
        text=data_summary(self.data());self.assertIn('100.0%',text);self.assertIn('增加 10 篇',text);self.assertIn('课程',text)
        data=self.data();data['observed_days']=3
        self.assertNotIn('总采集量环比',data_summary(data));self.assertNotIn('较上周增加',data_summary(data))
    def test_grouped_citations_are_hidden_without_losing_prose(self):
        from CampusPulse.report_references import References
        text=References().clean('课程诉求[S1,S2]。归属期待【S3、S4】。保持解释[1, 2]。')
        self.assertEqual(text,'课程诉求。归属期待。保持解释。')
    def test_actual_formal_html_has_no_inline_citations_and_all_sources_at_end(self):
        from CampusPulse.weekly import report_html
        from bs4 import BeautifulSoup
        data=self.data();data.update(start=1,cutoff=2,method='test')
        data['evidence'][0].update(text='校园材料',published=1,url='https://example.invalid/1')
        data['insights']['psychology'][0]['observation']+='[S1,S1]'
        data['report']=weekly_report.build(data)
        soup=BeautifulSoup(report_html({'status':'ready','data':data}),'html.parser')
        self.assertIn('一、本周概况与数据研判',soup.select_one('.scope').get_text())
        self.assertEqual(len(soup.select('.report-body a')),0)
        self.assertNotIn('[S1',soup.select_one('.report-body').get_text())
        self.assertEqual(len(soup.select('.report-references a')),1)
        self.assertEqual(soup.select_one('.report-body').get_text().count('教学联系老师'),1)

    def test_activity_profile_preserves_incomplete_days_and_window_edges(self):
        cov=[{'ready':True} for _ in range(14)];cov[12]['ready']=False
        end=14*86400
        posts=[{'published':0,'theme':'学习'},{'published':7*86400,'theme':'学习'},{'published':12*86400,'theme':'生活'},{'published':end,'theme':'生活'}]
        rows=weekly_report.activity_profile(posts,cov,end)
        self.assertEqual(rows[0]['count'],1);self.assertEqual(rows[7]['count'],1)
        self.assertIsNone(rows[12]['count']);self.assertEqual(rows[12]['collected_count'],1)
        self.assertEqual(rows[13]['count'],0);self.assertEqual(rows[7]['period'],'current')
