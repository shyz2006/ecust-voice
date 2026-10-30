import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from CampusPulse import report_contract as report
from CampusPulse.sources.campus_social import parse
from CampusPulse.post_identity import identifier


def chapter(headings):
    size=1800//len(headings)
    return {'sections':[{'title':h,'content':'分析材料与核查边界。'*(size//10+1),'evidence':['P1']} for h in headings]}


class ReportContract(unittest.TestCase):
    def test_five_chapters_twelve_sections_and_target_length(self):
        with patch('CampusPulse.llm.chat_json',side_effect=[chapter(h) for _,h in report.CHAPTERS]) as call:
            result=report.generate('研究问题',[{'id':'P1','text':'实际证据'}])
        self.assertEqual(call.call_count,5)
        self.assertEqual(sum(len(c['sections']) for c in result['chapters']),12)
        self.assertTrue(8000<=result['word_count']<=12000)
        self.assertEqual(len(report.as_topics(result)),5)
    def test_total_length_cannot_be_replaced_by_many_short_chapters(self):
        rows=[]
        for _,headings in report.CHAPTERS:
            rows.append({'sections':[{'title':h,'content':'材'*(1002//len(headings)),'evidence':['P1']} for h in headings]})
        with patch('CampusPulse.llm.chat_json',side_effect=rows+[rows[-1]]):
            with self.assertRaises(report.ReportInvalid):report.generate('问题',[{'id':'P1'}])
    def test_validated_checkpoint_resumes_without_regenerating_completed_chapters(self):
        first={'title':report.CHAPTERS[0][0],**chapter(report.CHAPTERS[0][1])}
        with patch('CampusPulse.llm.chat_json',side_effect=[chapter(h) for _,h in report.CHAPTERS[1:]]) as call:
            result=report.generate('问题',[{'id':'P1'}],resume=[first])
        self.assertEqual(call.call_count,4)
        self.assertEqual(len(result['chapters']),5)
    def test_empty_evidence_never_calls_model(self):
        with patch('CampusPulse.llm.chat_json') as call:
            with self.assertRaises(report.ReportInvalid):report.generate('问题',[])
        call.assert_not_called()
    def test_invalid_citation_rejected(self):
        data=chapter(report.CHAPTERS[0][1]);data['sections'][0]['content']+='[P99]'
        with self.assertRaises(report.ReportInvalid):report.validate_chapter(data,report.CHAPTERS[0][1],{'P1'})
    def test_unactionable_identity_investigation_is_rejected(self):
        data=chapter(report.CHAPTERS[-1][1])
        data['sections'][-1]['content']+='核查发帖人身份。'
        with self.assertRaises(report.ReportInvalid):report.validate_chapter(data,report.CHAPTERS[-1][1],{'P1'})
    def test_short_chapter_bounded_repair(self):
        with patch('CampusPulse.llm.chat_json',return_value={'sections':[]}) as call:
            with self.assertRaises(report.ReportInvalid):report.generate('问题',[{'id':'P1'}])
        self.assertEqual(call.call_count,2)
    def test_douyin_video_and_note(self):
        rows=[{'title':'ECUST 校园','url':'https://www.douyin.com/video/123'},
              {'title':'华理校园','url':'https://www.douyin.com/note/456'},
              {'title':'华理校园','url':'https://www.douyin.com/search/华理'}]
        self.assertEqual(len(parse('douyin-school',rows)),2)

if __name__=='__main__':unittest.main()
