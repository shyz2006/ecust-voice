import json,sqlite3,tempfile,unittest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch,Mock
from flask import Flask
from CampusPulse import report_contract as contract,weekly,blueprint


def section(headings,size):
    counts=[size//len(headings)]*len(headings);counts[-1]+=size-sum(counts)
    return {'sections':[{'title':h,'content':'材'*n,'evidence':['S1']} for h,n in zip(headings,counts)]}

class ReportRepairTests(unittest.TestCase):
    def test_infeasible_checkpoint_rewinds_and_finishes(self):
        prefix=[{'title':title,**section(hs,1002)} for title,hs in contract.CHAPTERS[:4]]
        outputs=[section(contract.CHAPTERS[3][1],2200),section(contract.CHAPTERS[4][1],2800)]
        saved=[]
        with patch('CampusPulse.llm.chat_json',side_effect=outputs) as writer:
            report=contract.generate('问题',[{'id':'S1'}],resume=prefix,checkpoint=lambda c:saved.append(len(c)))
        self.assertEqual(writer.call_count,2);self.assertEqual(saved[0],3)
        self.assertEqual(report['word_count'],8006)
    def test_negated_identity_boundary_is_not_an_action_instruction(self):
        row=section(contract.CHAPTERS[-1][1],1800)
        row['sections'][-1]['content']+='严禁核查发帖人身份，也不应识别作者实名。'
        contract.validate_chapter(row,contract.CHAPTERS[-1][1],{'S1'})
    def test_identity_instruction_cannot_hide_behind_another_clause_or_double_negative(self):
        for content in ('不得猜测。建议核查发帖人身份。','不得猜测，随后核查发帖人身份。','不得不核查发帖人身份。'):
            row=section(contract.CHAPTERS[-1][1],1800);row['sections'][-1]['content']+=content
            with self.assertRaises(contract.ReportInvalid):contract.validate_chapter(row,contract.CHAPTERS[-1][1],{'S1'})
    def test_invalid_json_receives_one_bounded_chapter_repair(self):
        values=[json.JSONDecodeError('truncated','',0)]+[section(hs,1800) for _,hs in contract.CHAPTERS]
        with patch('CampusPulse.llm.chat_json',side_effect=values) as writer:
            result=contract.generate('问题',[{'id':'S1'}])
        self.assertEqual(writer.call_count,6);self.assertEqual(result['word_count'],9000)
    def test_feedback_reaches_actual_report_writer(self):
        with patch('CampusPulse.llm.chat_json',side_effect=[section(hs,1800) for _,hs in contract.CHAPTERS]) as writer:
            contract.generate('问题',[{'id':'S1'}],feedback=['删除不实结论'])
        self.assertTrue(all('删除不实结论' in c.args[1] for c in writer.call_args_list))
    def test_ir_rejects_short_total_despite_valid_chapters(self):
        doc={'chapters':[{'blocks':[{'type':'paragraph','inlines':[{'text':' '.join(hs)+'材'*1200}]}]} for _,hs in contract.CHAPTERS]}
        with self.assertRaises(contract.ReportInvalid):contract.validate_ir(doc)
        for c in doc['chapters']:c['blocks'][0]['inlines'][0]['text']+='材'*600
        self.assertTrue(8000<=contract.validate_ir(doc)<=12000)
    def test_invalid_existing_report_remains_resumable(self):
        from CampusPulse import research
        from ReportEngine import flask_interface
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'final_report_invalid.html').write_text('invalid')
            with patch('utils.task_runtime.task_summary',return_value={'engines':{'query':'completed','media':'completed','insight':'completed'}}),patch('utils.task_runtime.task_output_dir',return_value=path),patch.dict(flask_interface.tasks_registry,{},clear=True),patch.object(research,'report_html',side_effect=ValueError('正文不足')):
                result=research.status('task_test')
            self.assertEqual(result['status'],'failed');self.assertTrue(result['can_resume_report'])
    def test_final_only_resume_requests_regeneration(self):
        from CampusPulse import research
        response=Mock(status_code=200);response.json.return_value={'success':True}
        with patch('utils.research_runner.all_engines_completed',return_value=True),patch('utils.research_runner._config_port',return_value=5000),patch('utils.task_runtime.read_task_metadata',return_value={'query':'原问题'}),patch('requests.post',return_value=response) as post:
            result=research.resume_report('task_test')
        self.assertTrue(post.call_args.kwargs['json']['regenerate']);self.assertEqual(result['status'],'reporting')
    def test_cold_storage_allows_explicit_lease_transaction(self):
        from CampusPulse import storage
        with tempfile.TemporaryDirectory() as directory,patch.object(storage,'_initialized',False),patch.object(storage,'_db_path',return_value=Path(directory)/'cold.sqlite'):
            with storage.connect() as conn:
                self.assertFalse(conn.in_transaction)
                conn.execute('BEGIN IMMEDIATE')
    def test_ledger_includes_empty_xiaohongshu_sources(self):
        app=Flask(__name__)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'usage.sqlite'
            with sqlite3.connect(path) as c:c.execute('CREATE TABLE pulse_usage(ts,success,usage_known,prompt_tokens,completion_tokens)')
            @contextmanager
            def connect():
                with sqlite3.connect(path) as c:c.row_factory=sqlite3.Row;yield c
            sample={'generated_at':0,'observed_since':0,'unique_school_posts':0,'main_reports_completed':0,'recorded_tokens':0,'sources':[]}
            with app.test_request_context('/pulse/api/revision/ledger'),patch('CampusPulse.telemetry.dashboard',return_value=sample),patch.object(blueprint.storage,'connect',connect),patch.object(blueprint.access,'is_admin',return_value=False):
                body=blueprint.revision_ledger().get_json()
            sources={r['source']:r['unique'] for r in body['sources']}
            self.assertEqual(sources['xiaohongshu'],0);self.assertEqual(sources['xiaohongshu-school'],0)
            self.assertNotIn('daily_usage',body)

class WeeklyCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();path=Path(self.temp.name)/'weekly.sqlite'
        @contextmanager
        def connect():
            with sqlite3.connect(path) as c:c.row_factory=sqlite3.Row;yield c
        self.patch=patch.object(weekly.storage,'connect',connect);self.patch.start();weekly.initialize()
        evidence=[{'id':'S1','period':'current','text':'材料'}]
        data={'current_total':5,'evidence':evidence,'observed_days':3,'previous_observed_days':3}
        with connect() as c:c.execute("INSERT INTO pulse_weekly(id,cutoff,kind,created,status,data) VALUES('test',1,'preview',1,'failed',?)",(json.dumps(data),))
        self.insights={'headline':'本周观察','signals':[{'title':'学习','observation':'关注学习体验','evidence':['S1']}],'follow_up':[]}
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def test_summary_and_chapters_survive_report_failure(self):
        def fail(*args,**kwargs):kwargs['checkpoint']([{'title':'saved'}]);raise contract.ReportInvalid('报告篇幅待完善')
        def complete(*args,**kwargs):
            self.assertEqual(kwargs['resume'],[{'title':'saved'}]);return {'chapters':[]}
        with patch.object(weekly,'summarize',return_value=(self.insights,'model')) as summarize,patch.object(contract,'generate',side_effect=[None]):
            with patch.object(contract,'generate',side_effect=fail):weekly.generate('test')
            failed=weekly.get('test');self.assertEqual(failed['status'],'failed');self.assertIn('长报告生成',failed['error']);self.assertIn('insights',failed['data'])
            with patch.object(contract,'generate',side_effect=complete):weekly.generate('test')
            self.assertEqual(summarize.call_count,1);self.assertEqual(weekly.get('test')['status'],'ready')
    def test_complete_json_with_literal_newline_is_repaired_without_model(self):
        value=weekly.parse_model_json('{"content":"第一行\n第二行"}')
        self.assertEqual(value['content'],'第一行\n第二行')
        with self.assertRaises(json.JSONDecodeError):weekly.parse_model_json('{"content":"未完成')
    def test_weekly_long_report_links_all_its_evidence_and_escapes_text(self):
        data=weekly.get('test')['data']
        data.update(start=1,cutoff=2,previous_total=0,categories={},method='test',insights=self.insights,
                    report={'chapters':[{'title':'章节','sections':[{'title':'小节','content':'<script>内容</script>[S2]','evidence':['S2']}]}]})
        data['evidence']=[{'id':'S1','period':'current','text':'第一条','published':1,'url':'https://example.invalid/1'},
                          {'id':'S2','period':'current','text':'第二条','published':1,'url':'https://example.invalid/2'}]
        html=weekly.report_html({'status':'ready','data':data})
        self.assertIn('id="S2"',html);self.assertIn('href="#S2"',html)
        self.assertIn('&lt;script&gt;',html);self.assertNotIn('<script>',html)
    def test_excess_observations_are_selected_only_after_evidence_checks(self):
        data=weekly.get('test')['data']
        signals=[{'title':'待核查','observation':'资料不足','evidence':['UNKNOWN']}]
        signals += [{'title':'观察'+str(i),'observation':'关注学习体验','evidence':['S1']} for i in range(22)]
        value=weekly.select_insights({'headline':'观察','signals':signals,'follow_up':['了解诉求']*6},data)
        self.assertEqual(len(value['signals']),5);self.assertEqual(len(value['follow_up']),4)
        self.assertTrue(all(x['evidence']==['S1'] for x in value['signals']))
        weekly.validate_insights(value,data)
    def test_complete_valid_json_with_length_flag_is_accepted(self):
        from types import SimpleNamespace
        response=SimpleNamespace(choices=[SimpleNamespace(finish_reason='length',message=SimpleNamespace(content=json.dumps(self.insights)))],usage=None)
        settings=SimpleNamespace(REPORT_ENGINE_API_KEY='test',REPORT_ENGINE_BASE_URL='https://example.invalid',REPORT_ENGINE_MODEL_NAME='test')
        client=Mock()
        with patch('config.reload_settings',return_value=settings),patch('openai.OpenAI',return_value=client),patch('CampusPulse.model_connection.completion',return_value=response),patch('CampusPulse.telemetry.record_response'):
            data=weekly.get('test')['data'];result,_=weekly.summarize(data)
        self.assertEqual(result['headline'],'本周观察')
    def test_incomplete_json_with_length_flag_is_rejected(self):
        from types import SimpleNamespace
        response=SimpleNamespace(choices=[SimpleNamespace(finish_reason='length',message=SimpleNamespace(content='{"signals":['))],usage=None)
        settings=SimpleNamespace(REPORT_ENGINE_API_KEY='test',REPORT_ENGINE_BASE_URL='https://example.invalid',REPORT_ENGINE_MODEL_NAME='test')
        with patch('config.reload_settings',return_value=settings),patch('openai.OpenAI',return_value=Mock()),patch('CampusPulse.model_connection.completion',return_value=response),patch('CampusPulse.telemetry.record_response'):
            with self.assertRaisesRegex(ValueError,'截断'):weekly.summarize(weekly.get('test')['data'])
    def test_summary_validation_repair_is_bounded_and_explained(self):
        with patch.object(weekly,'summarize',side_effect=[ValueError('周报引用无法对应采集材料'),(self.insights,'model')]) as summarize,patch.object(contract,'generate',return_value={'chapters':[]}):weekly.generate('test')
        self.assertEqual(summarize.call_count,2);self.assertIn('周报引用',summarize.call_args.args[1]);self.assertEqual(weekly.get('test')['status'],'ready')

if __name__=='__main__':unittest.main()
