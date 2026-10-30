import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from utils import topic_guard
from CampusPulse import research_brief,research


class QuotedContextTests(unittest.TestCase):
    query='南京大学蒋炎岩在课上说“没有token的学生应该立刻退学”'

    def test_named_subject_and_paraphrased_quote_remain_relevant(self):
        topic=topic_guard.subject(self.query)
        self.assertEqual(topic['quote_identity'],['蒋炎岩'])
        self.assertFalse(topic['strict'])
        self.assertTrue(topic_guard.relevant('南大副教授蒋炎岩：没有Token的CS学生，应立即退学',topic))
        self.assertFalse(topic_guard.relevant('某培训机构：没有Token的CS学生应退学',topic))
        self.assertFalse(topic_guard.relevant('蒋炎岩的学术经历与课程介绍',topic))
        query=topic_guard.search_query(self.query,topic)
        for term in ('南京大学','蒋炎岩','token','退学'):self.assertIn(term,query)
        self.assertNotIn('立刻',query)

    def test_generic_person_support_is_not_an_incident_specific_mapping(self):
        topic=topic_guard.subject('海滨大学陈明在课堂说“学生应该掌握计算机编程”')
        self.assertEqual(topic['quote_identity'],['陈明'])
        self.assertTrue(topic_guard.relevant('陈明谈学生计算机编程学习',topic))
        self.assertFalse(topic_guard.relevant('其他人谈学生计算机编程',topic))

    def test_quote_without_identity_and_explicit_confirmed_anchors_stay_strict(self):
        topic=topic_guard.subject('“鹅腿阿姨”')
        self.assertTrue(topic['strict'])
        self.assertFalse(topic_guard.relevant('数字人阿姨的新视频',topic))
        topic.update(anchors=['清华大学'],terms=['健身'])
        self.assertFalse(topic_guard.relevant('北航健身讨论',topic))

    def test_custom_scope_keeps_rechecked_preliminary_sources(self):
        source={'title':'蒋炎岩谈Token与CS学生退学讨论','snippet':'课程表达与上下文待核实','url':'https://example.com/source'}
        row={'query':self.query,'status':'ready','directions':[],'sources':[source]}
        with patch.object(research_brief,'get',return_value=row):
            brief=research_brief.exploratory('brief',self.query,'','owner')
            other=research_brief.exploratory('brief','海滨大学陈明谈学生计算机编程','','owner')
        self.assertEqual(brief['sources'],[source])
        self.assertEqual(other['sources'],[])
        self.assertTrue(brief['exploratory'])

    def test_matched_seed_avoids_a_new_search_and_clears_old_gap(self):
        source={'title':'蒋炎岩谈token与学生退学','snippet':'原始课堂表达仍需进一步核对','url':'https://example.com/source'}
        meta={'pulse_revision':2,'query':self.query,'research_brief':{'confirmed':True,'exploratory':True,'query':self.query,'sources':[source]}}
        agent=Mock();agent.state=Mock();execute=agent.execute_search_tool
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root);(directory/'research_information_gap.json').write_text('old')
            with patch('utils.task_runtime.read_task_metadata',return_value=meta),patch('utils.task_runtime.task_output_dir',return_value=directory):
                self.assertTrue(topic_guard.prepare_agent(agent,'media',self.query,'task_test'))
            self.assertFalse((directory/'research_information_gap.json').exists())
            self.assertTrue((directory/'state_topic_seed.json').exists())
            execute.assert_not_called()
            agent.state.add_paragraph.assert_called()


class PendingEngineStatusTests(unittest.TestCase):
    def test_one_gap_does_not_finish_ui_while_another_engine_is_queued(self):
        from ReportEngine import flask_interface
        meta={'task_id':'task_test','engines':{'insight':'completed','media':'failed','query':'queued'}}
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root);(directory/'research_information_gap.json').write_text('{"message":"未找到相关资料"}',encoding='utf-8')
            with patch('utils.task_runtime.task_summary',side_effect=lambda _:copy.deepcopy(meta)),patch('utils.task_runtime.task_output_dir',return_value=directory),patch.object(flask_interface,'tasks_registry',{}),patch.object(research,'_resume_jobs',{}):
                result=research.status('task_test',auto=False)
                self.assertEqual(result['status'],'running')
                meta['engines']['query']='failed'
                result=research.status('task_test',auto=False)
                self.assertEqual(result['status'],'failed')
                self.assertTrue(result['information_gap'])


if __name__=='__main__':unittest.main()
