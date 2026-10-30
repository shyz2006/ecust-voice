import json,tempfile,unittest,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from CampusPulse import hot_focus as focus,storage,revision

class HotFocusTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'_db_path',return_value=Path(self.temp.name)/'db.sqlite'),patch.object(storage,'_initialized',False)]
        for p in self.patches:p.start()
        with storage.connect():pass
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def item(self):return {'title':'大学开放夜间自习室','focus':'规则兜底','focus_method':'title_rule','_focus_context':'开放时间延长至晚间。'}
    def test_completed_summaries_are_reused_across_refreshes_and_platforms(self):
        row=self.item();writer=Mock(return_value={'0':'夜间自习空间的开放安排，让学生关注学习便利与校园服务之间的配合。'})
        self.assertEqual(focus.refresh([row,dict(row,platform='B站')],writer),1)
        self.assertEqual(focus.refresh([row],writer),0);self.assertEqual(writer.call_count,1)
        items=[self.item()];self.assertFalse(focus.attach(items,background=False))
        self.assertEqual(items[0]['focus_method'],'llm_summary');self.assertNotIn('_focus_context',items[0])
    def test_context_change_invalidates_summary_cache(self):
        row=self.item();writer=Mock(return_value={'0':'学校服务开放安排涉及自习便利与晚间空间管理。'})
        focus.refresh([row],writer);changed=dict(row,_focus_context='开放计划发生更新')
        focus.refresh([changed],writer);self.assertEqual(writer.call_count,2)
    def test_failed_call_has_cooldown_and_retains_existing_good_text(self):
        row=self.item();key=focus.cache_key(row)
        focus._write(key,{'focus':'已有模型概括','updated_at':1})
        writer=Mock(side_effect=ValueError('provider failed'))
        focus.refresh([row],writer);focus.refresh([row],writer)
        self.assertEqual(writer.call_count,1);self.assertEqual(focus._read(key)['focus'],'已有模型概括')
        self.assertEqual(focus._read(key)['status'],'retry')
    def test_claim_is_shared_and_atomic(self):
        key=focus.cache_key(self.item());now=int(time.time())
        self.assertTrue(focus._claim(key,now));self.assertFalse(focus._claim(key,now))
    def test_batches_cover_all_displayed_cards(self):
        items=[dict(self.item(),title='话题'+str(i)) for i in range(23)]
        calls=[]
        def writer(rows):calls.append(len(rows));return {str(i):'具体话题的简要分析与关注角度。' for i in range(len(rows))}
        self.assertEqual(focus.refresh(items,writer),23);self.assertEqual(calls,[6,6,6,5])
    def test_feed_read_only_starts_background_work(self):
        row=self.item();lock=Mock();lock.acquire.return_value=True
        with patch.object(focus,'_job_lock',lock),patch.object(focus.threading,'Thread') as thread,patch.object(focus,'model_batch') as model:
            self.assertTrue(focus.attach([row]))
            thread.return_value.start.assert_called_once();model.assert_not_called()
            self.assertIn('_focus_context',thread.call_args.kwargs['args'][0][0])
    def test_real_model_adapter_tracks_usage_and_uses_working_report_profile(self):
        from CampusPulse import model_connection,telemetry
        settings=SimpleNamespace(REPORT_ENGINE_API_KEY='test',REPORT_ENGINE_MODEL_NAME='working-report-model',REPORT_ENGINE_BASE_URL='https://example.invalid/v1')
        response=SimpleNamespace(usage=None,choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'items':[{'id':'0','focus':'夜间学习空间的安排涉及自习便利、开放时段与校园服务的配合。'}]})))])
        with patch('config.reload_settings',return_value=settings),patch('openai.OpenAI') as client,patch.object(model_connection,'completion',return_value=response) as completion,patch.object(telemetry,'record_response') as record:
            client.return_value.chat.completions.create._bf_usage_ledger=False
            result=focus.model_batch([self.item()])
        self.assertIn('0',result);self.assertEqual(completion.call_args.kwargs['model'],'working-report-model');record.assert_called_once()
    def test_enrichment_receives_only_ten_selected_cards_per_platform(self):
        now=int(time.time());rows=[{'source':'douyin','title':'校园服务'+str(i),'batch_ts':now,'rank':i+1,'extra':{'desc':'说明'}} for i in range(18)]
        seen=[]
        def attach(items):seen.extend(items);return True
        with patch.object(storage,'latest_source_batches',return_value={'douyin':now}),patch.object(storage,'recent_items',return_value=rows),patch.object(storage,'kv_prefix',return_value=[]),patch.object(storage,'latest_topics',return_value={'topics':[]}),patch.object(focus,'attach',side_effect=attach):
            value=revision._network_feed('hot',batch_ts=now)
        self.assertEqual(len(seen),10);self.assertTrue(value['focus_pending']);self.assertEqual([x['rank'] for x in value['items']],list(range(1,11)))
