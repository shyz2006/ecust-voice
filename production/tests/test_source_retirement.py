import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from flask import Flask, request, session, jsonify, redirect

from CampusPulse import storage, telemetry, revision, observatory, pipeline, collectors, source_policy
from CampusPulse.sources import campus_social


class RetirementTests(unittest.TestCase):
    def test_collection_and_all_visible_source_lists_exclude_retired_sources(self):
        self.assertNotIn('xiaohongshu', revision.HOT_PLATFORMS)
        for names in (observatory.SOURCES, pipeline.FORUM_SOURCES, campus_social.PLATFORMS):
            self.assertNotIn('xiaohongshu-school', names)
        with patch.object(collectors,'_fetch_source',return_value=('weibo',[],'')) as fetch:
            collectors.collect_hotlists(['xiaohongshu','weibo','xiaohongshu-school'])
        self.assertEqual([call.args[0] for call in fetch.call_args_list],['weibo'])
        with patch.object(collectors.requests,'get') as get:
            self.assertEqual(collectors._fetch_source('xiaohongshu'),('xiaohongshu',[],''))
            get.assert_not_called()

    def test_old_environment_source_setting_cannot_reenable_retired_sources(self):
        from CampusPulse.config import PulseSettings
        with patch.dict('os.environ',{'PULSE_SOURCES':'xiaohongshu,weibo,xiaohongshu-school'}):
            self.assertEqual(PulseSettings().sources,['weibo'])

    def test_payload_retirement_preserves_null_semantics_and_other_platforms(self):
        data={'delta':None,'platforms':['小红书','B站'],'source_errors':{'xiaohongshu':'failed','douyin':'timeout'},
              'items':[{'source':'xiaohongshu','title':'old'},{'source':'weibo','title':'active'}]}
        result=source_policy.public_payload(data)
        self.assertIn('delta',result);self.assertIsNone(result['delta'])
        self.assertEqual(result['platforms'],['B站']);self.assertEqual(result['source_errors'],{'douyin':'timeout'})
        self.assertEqual(result['items'],[{'source':'weibo','title':'active'}])
        self.assertIsNone(source_policy.public_payload({'entries':[{'source':'xiaohongshu','title':'old'}]}))

    def test_retired_domain_entries_and_links_are_removed(self):
        for host in ('www.xiaohongshu.com','xhslink.cn','xhslink.com','sub.rednote.com'):
            self.assertIsNone(source_policy.public_payload({'url':'https://'+host+'/note','title':'old'}))
        self.assertFalse(source_policy.retired_url('https://xiaohongshu.com.example.invalid/note'))

    def test_feed_defensively_ignores_retired_history_even_if_reader_returns_it(self):
        rows=[{'source':'xiaohongshu','title':'old','batch_ts':123,'rank':1,'extra':{}}]
        with patch.object(revision.storage,'latest_source_batches',return_value={}),patch.object(revision.storage,'recent_items',return_value=rows),patch.object(revision.storage,'kv_prefix',return_value=[]),patch.object(revision.storage,'latest_topics',return_value={'topics':[]}):
            result=revision._network_feed('hot')
        self.assertFalse(result['items']);self.assertNotIn('小红书',result['platforms'])

    def test_retired_extension_calls_are_gone_including_unauthenticated_calls(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='enforce_account_role');node.decorator_list=[]
        namespace={'request':request,'session':session,'jsonify':jsonify,'redirect':redirect,'access':Mock()}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'role-guard','exec'),namespace)
        app=Flask(__name__);app.secret_key='test'
        for route in ('push','ping','key','import','status'):
            with app.test_request_context('/pulse/api/xhs-browser/'+route,method='POST'):
                self.assertEqual(namespace['enforce_account_role']()[1],410)

    def test_templates_and_active_js_have_no_feature_or_download_reference(self):
        root=Path(__file__).resolve().parents[1]
        for path in ('templates/index.html','CampusPulse/templates/pulse.html','static/js/campus-review.js'):
            text=(root/path).read_text(encoding='utf-8')
            for word in ('小红书','xiaohongshu','campus-xhs','CampusXhs'):
                self.assertNotIn(word,text,path)
        self.assertFalse((root/'static/downloads/ecust-xhs-browser-helper.zip').exists())


class RetiredStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'_db_path',return_value=Path(self.directory.name)/'test.db'),patch.object(storage,'_initialized',False)]
        for p in self.patches:p.start()
        with storage.connect():pass
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.directory.cleanup()

    def test_history_reader_excludes_retired_rows_without_erasing_archive(self):
        with storage.connect() as conn:
            for src in ('weibo','xiaohongshu','xiaohongshu-school'):
                conn.execute('INSERT INTO snapshots(batch_ts,source,rank,title,url,extra) VALUES (100,?,1,?,NULL,?)',(src,src,'{}'))
        self.assertEqual([x['source'] for x in storage.recent_items(['weibo','xiaohongshu','xiaohongshu-school'],0)],['weibo'])
        self.assertEqual(storage.latest_source_batches(['xiaohongshu'],0),{})
        self.assertEqual(len(storage.load_batch_items(100)),3)

    def test_historical_ledger_totals_exclude_removed_platform(self):
        values={'observations':30,'unique_items':9,'school_observations':17,'unique_school_posts':6,
                'observations:xiaohongshu':10,'observations:xiaohongshu-school':15,'observations:weibo':5,
                'unique:xiaohongshu':3,'unique:xiaohongshu-school':4,'unique:weibo':2}
        with storage.connect() as conn:
            for k,v in values.items():conn.execute('INSERT OR REPLACE INTO pulse_ledger VALUES (?,?)',(k,v))
        with patch.object(telemetry,'sync_main_reports'),patch('CampusPulse.costs.summary',return_value={}),patch('CampusPulse.issues.usage',return_value={'briefs_completed':0}):
            result=telemetry.dashboard()
        self.assertEqual(result['observations'],5);self.assertEqual(result['unique_items'],2)
        self.assertEqual(result['school_observations'],2);self.assertEqual(result['unique_school_posts'],2)
        self.assertEqual([s['source'] for s in result['sources']],['weibo'])


if __name__=='__main__':unittest.main()
