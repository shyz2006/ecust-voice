import copy
import unittest
from unittest.mock import patch

from CampusPulse import research,weekly
from CampusPulse.report_references import References
from CampusPulse.report_rendering import ReportRenderer


class DeferredReferencesTests(unittest.TestCase):
    def test_markdown_bare_links_citations_and_quotes_move_to_appendix(self):
        references=References()
        renderer=ReportRenderer(references=references)
        body=renderer.text('分析结论[S1]。参考[报道](https://example.com/a_(b))。\n\nhttps://example.com/b\n\n> 同学的原始表达\n\n“我希望增加座位”[S2]')
        self.assertNotIn('href=',body)
        self.assertNotIn('https://',body)
        self.assertNotIn('[S1]',body)
        self.assertNotIn('同学的原始表达',body)
        self.assertNotIn('我希望增加座位',body)
        self.assertIn('分析结论',body)
        appendix=references.html()
        for value in ['https://example.com/a_(b)','https://example.com/b','同学的原始表达','我希望增加座位']:
            self.assertIn(value,appendix)

    def test_event_report_has_one_final_appendix_across_chapters(self):
        url='https://example.com/evidence'
        paragraph={'type':'paragraph','inlines':[{'text':'保留分析。'}, {'text':'查看原帖','marks':[{'type':'link','href':url}]}]}
        doc={'chapters':[{'title':'第一章','blocks':[paragraph],'footnotes':[{'text':'原始资料说明','href':url}]},{'title':'第二章','blocks':[paragraph]}]}
        original=copy.deepcopy(doc)
        html=research.render_document(doc,'研究问题',{url:{'title':'正式来源'}})
        body,appendix=html.split('<section class="report-references"',1)
        self.assertNotIn('href=',body)
        self.assertNotIn('查看原帖',body)
        self.assertNotIn('原始资料说明',body)
        self.assertEqual(appendix.count('href="'+url+'"'),1)
        self.assertIn('原始资料说明',appendix)
        self.assertEqual(doc,original)

    def test_markdown_export_keeps_urls_only_in_final_references(self):
        url='https://example.com/evidence'
        doc={'chapters':[{'title':'分析','blocks':[{'type':'paragraph','inlines':[{'text':'正文 **重点** [报道]('+url+') [S1]'}]}]}]}
        with patch.object(research,'report_document',return_value=doc),patch('utils.task_runtime.read_task_metadata',return_value={'query':'研究问题'}),patch('ReportEngine.evidence.source_evidence',return_value=[{'url':url,'title':'来源'}]):
            text=research.markdown('task_test')
        body,appendix=text.split('## 参考资料与原帖',1)
        self.assertNotIn(url,body)
        self.assertNotIn('[S1]',body)
        self.assertIn(url,appendix)

    def test_images_and_analysis_formatting_are_retained(self):
        renderer=ReportRenderer(references=References())
        result=renderer.text('**重点**\n\n- 一项\n\n![图表](https://example.com/chart.png)')
        self.assertIn('<strong>重点</strong>',result)
        self.assertIn('<ul>',result)
        self.assertIn('<img src="https://example.com/chart.png"',result)


class WeeklyOpeningTests(unittest.TestCase):
    def data(self):
        return {'start':1,'cutoff':604801,'current_total':20,'previous_total':15,'observed_days':7,'previous_observed_days':7,
                'categories':{'课程':[10,5],'生活':[6,7],'实践':[4,3]},'method':'按帖子标识去重',
                'insights':{'headline':'本周观察','signals':[{'title':'学习体验','observation':'课程讨论[S1]，见[原帖](https://example.com/post)。','evidence':['S1']}],'follow_up':['了解具体诉求']},
                'evidence':[{'id':'S1','period':'current','text':'同学的原始帖子','published':5,'url':'https://example.com/post'}]}

    def test_weekly_starts_with_programmatic_counts_and_defers_all_links(self):
        data=self.data();html=weekly.report_html({'status':'ready','data':data})
        body,appendix=html.split('<section class="report-references"',1)
        self.assertLess(body.index('本周数据概览'),body.index('class="report-body"'))
        for value in ['20 篇','3 类议题','课程（10篇）','增加 5 篇']:
            self.assertIn(value,body)
        self.assertNotIn('href=',body)
        self.assertNotIn('https://',body)
        self.assertNotIn('[S1]',body)
        self.assertNotIn('同学的原始帖子',body)
        self.assertNotIn('见原帖',body)
        self.assertIn('同学的原始帖子',appendix)
        self.assertEqual(appendix.count('href="https://example.com/post"'),1)

    def test_partial_coverage_does_not_claim_full_week_growth(self):
        data=self.data();data['observed_days']=3
        text=weekly.data_summary(data)
        self.assertIn('20 篇',text)
        self.assertIn('3/7',text)
        self.assertNotIn('较上周',text)

    def test_long_weekly_report_also_moves_embedded_and_declared_sources(self):
        data=self.data();data['report']={'chapters':[{'title':'长报告','sections':[{'title':'讨论','content':'分析[S1]，资料 https://example.com/extra','evidence':['S1']}]}]}
        html=weekly.report_html({'status':'ready','data':data})
        body,appendix=html.split('<section class="report-references"',1)
        self.assertNotIn('https://',body)
        self.assertNotIn('[S1]',body)
        self.assertIn('https://example.com/post',appendix)
        self.assertIn('https://example.com/extra',appendix)


if __name__=='__main__':unittest.main()
