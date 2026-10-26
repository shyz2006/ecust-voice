import sqlite3,unittest
from contextlib import contextmanager
from unittest.mock import patch,Mock
from CampusPulse import pipeline,storage,revision


class CollectionAuditTests(unittest.TestCase):
    def test_failure_before_batch_insert_is_still_recorded(self):
        records=[]
        with patch.object(pipeline,'_fetch_all',side_effect=TypeError('invalid include argument')),patch.object(storage,'record_fetch') as save,patch.object(storage,'record_collection_attempt',side_effect=lambda a:records.append(dict(a))):
            result=pipeline.run_once(use_llm=False)
        save.assert_not_called();self.assertIn('error',result)
        self.assertEqual([a['status'] for a in records],['running','failed'])
        self.assertIsNone(records[-1]['batch_ts']);self.assertIn('include',records[-1]['error'])
        self.assertEqual(records[0]['id'],records[-1]['id'])

    def test_attempt_log_failure_does_not_cancel_healthy_collection(self):
        fetched={'batch_ts':100,'items':[{'source':'weibo','title':'真实条目'}],'errors':{},'meta':{}}
        with patch.object(pipeline,'_fetch_all',return_value=fetched),patch.object(storage,'record_collection_attempt',side_effect=RuntimeError('busy')),patch.object(storage,'record_fetch') as save,patch.object(pipeline,'analyze_batch',return_value={'complete':True}):
            result=pipeline.run_once(use_llm=False)
        self.assertTrue(result['complete']);save.assert_called_once()

    def test_analysis_failure_keeps_saved_batch_and_failed_attempt(self):
        records=[];fetched={'batch_ts':100,'items':[{'source':'weibo','title':'真实条目'}],'errors':{},'meta':{}}
        with patch.object(pipeline,'_fetch_all',return_value=fetched),patch.object(storage,'record_collection_attempt',side_effect=lambda a:records.append(dict(a))),patch.object(storage,'record_fetch') as save,patch.object(storage,'mark_batch_failed') as failed,patch.object(pipeline,'analyze_batch',side_effect=RuntimeError('analysis failed')):
            result=pipeline.run_once(use_llm=False)
        save.assert_called_once();failed.assert_called_once_with(100,'analysis failed')
        self.assertIn('error',result);self.assertEqual(records[-1]['status'],'failed')
        self.assertEqual(records[-1]['batch_ts'],100)

    def test_attempt_history_retains_failure_after_a_later_success(self):
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        conn.execute('CREATE TABLE kv(key TEXT PRIMARY KEY,value BLOB)')
        @contextmanager
        def connect():
            yield conn
            conn.commit()
        with patch.object(storage,'connect',connect):
            storage.record_collection_attempt({'id':1,'started_at':100,'status':'failed','error':'test'})
            storage.record_collection_attempt({'id':2,'started_at':200,'status':'complete'})
            self.assertEqual(storage.last_collection_attempt()['status'],'complete')
            self.assertEqual(len(storage.kv_prefix('collection:attempt:')),2)
        conn.close()


class StopLoop(BaseException):pass


class SchedulerResilienceTests(unittest.TestCase):
    def run_loop(self,latest,times,results,iterations):
        fake=Mock();sleeps=[]
        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps)>iterations:raise StopLoop()
        with patch.object(pipeline,'_scheduler',None),patch.object(pipeline,'logger',Mock()),patch.object(pipeline.settings,'collect_interval_min',30),patch.object(pipeline.threading,'Thread',return_value=fake) as thread,patch.object(pipeline,'recover_pending'),patch.object(storage,'latest_batch',side_effect=latest) as latest_read,patch.object(pipeline,'run_once',side_effect=results) as run,patch.object(pipeline.time,'time',side_effect=times),patch.object(pipeline.time,'sleep',side_effect=sleep):
            pipeline.start_scheduler()
            loop=thread.call_args.kwargs['target']
            with self.assertRaises(StopLoop):loop()
            self.assertEqual(latest_read.call_args.args,('complete',))
            return run.call_count

    def test_database_error_does_not_terminate_scheduler(self):
        count=self.run_loop([RuntimeError('temporary database error'),None],[1000,2000],[{}],2)
        self.assertEqual(count,1)

    def test_failed_fetch_waits_five_minutes_instead_of_retrying_each_minute(self):
        count=self.run_loop([None,None,None],[2000,2000,2100,2301],[{'error':'source failure'},{}],3)
        self.assertEqual(count,2)


class ObservationFreshnessTests(unittest.TestCase):
    def test_recomputing_overview_does_not_make_old_data_look_fresh(self):
        now=2000000;old=now-7200;rows=[{'source':'huyou-school','batch_ts':old,'title':'校园讨论','extra':{}}]
        with patch.object(revision.time,'time',return_value=now),patch.object(pipeline.settings,'collect_interval_min',30),patch.object(storage,'recent_items',return_value=rows),patch.object(storage,'kv_prefix',return_value=[]),patch.object(revision.observatory,'prepare',return_value=([],{})),patch.object(revision.campus,'_rule',return_value={'theme':'其他','crisis_level':'无'}),patch.object(revision.campus,'_filter_false_crisis',return_value='无'):
            result=revision.snapshot(force=True)
        self.assertEqual(result['generated_at'],now);self.assertEqual(result['observed_at'],old)
        self.assertEqual(result['collection_health'],'delayed')


if __name__=='__main__':unittest.main()
