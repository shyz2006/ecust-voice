"""Explicit browser exports, tested against a temporary database; no live account."""
import copy
import ast
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, request, session, jsonify
from urllib.parse import urlsplit
from CampusPulse import storage, xhs_browser_import as bridge
from CampusPulse.sources import campus_social as social


def payload():
    return {'format':bridge.FORMAT,'captured_at':int(time.time()),
            'page_url':'https://www.xiaohongshu.com/search_result?keyword=华理',
            'items':[{'url':'https://www.xiaohongshu.com/search_result/'+'a'*24+'?xsec_token=public-note-link&tracking=discard',
                      'title':'华理奉贤食堂体验','excerpt':'校园生活'}]}


class BrowserImportValidationTests(unittest.TestCase):
    def test_visible_card_normalized_and_unknown_stats_not_invented(self):
        notes,rejected=bridge.validate(payload())
        self.assertEqual(rejected,0)
        self.assertIn('/explore/'+'a'*24,notes[0]['url'])
        self.assertNotIn('tracking',notes[0]['url'])
        self.assertNotIn('published',notes[0])

    def test_extra_fields_including_sessions_and_client_counts_rejected(self):
        for key in ('cookies','api_key','session','username'):
            value=payload();value[key]='test'
            with self.assertRaises(ValueError):bridge.validate(value)
        for key in ('likes','published','comments','author'):
            value=payload();value['items'][0][key]=1
            with self.assertRaises(ValueError):bridge.validate(value)

    def test_other_school_or_non_note_does_not_pass(self):
        for title in ('普通穿搭','华理 华北理工大学'):
            value=payload();value['items'][0]['title']=title
            with self.assertRaises(ValueError):bridge.validate(value)
        for url in ('https://evil.invalid/explore/'+'a'*24,'http://www.xiaohongshu.com/explore/'+'a'*24,
                    'https://user:secret@www.xiaohongshu.com/explore/'+'a'*24,
                    'https://www.xiaohongshu.com:8080/explore/'+'a'*24,
                    'https://www.xiaohongshu.com/user/profile/'+'a'*24):
            value=payload();value['items'][0]['url']=url
            with self.assertRaises(ValueError):bridge.validate(value)

    def test_bad_capture_time_search_context_and_limits(self):
        for captured in (True,float('nan'),float('inf'),time.time()-8*86400,time.time()+86400):
            value=payload();value['captured_at']=captured
            with self.assertRaises(ValueError):bridge.validate(value)
        for page in ('https://www.xiaohongshu.com/explore','https://www.xiaohongshu.com/search_result?keyword=穿搭',None):
            value=payload();value['page_url']=page
            with self.assertRaises(ValueError):bridge.validate(value)
        value=payload();value['items']*=31
        with self.assertRaises(ValueError):bridge.validate(value)

    def test_dedup_by_note_id_and_partial_rejection(self):
        value=payload();other=copy.deepcopy(value['items'][0]);other['url']=other['url'].replace('search_result','explore')
        value['items'] += [other,{'url':'https://example.invalid/','title':'华理'}]
        notes,rejected=bridge.validate(value)
        self.assertEqual((len(notes),rejected),(1,1))


class BrowserImportStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'_db_path',return_value=Path(self.directory.name)/'test.db'),patch.object(storage,'_initialized',False)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.directory.cleanup()

    def test_repeat_import_updates_one_record_and_preserves_first_observation(self):
        first=bridge.save(payload(),'test-admin')
        self.assertEqual((first['added'],first['stored']),(1,1))
        stamp=bridge.items()[0]['extra']['browser_imported_at']
        second=bridge.save(payload(),'test-admin')
        self.assertEqual((second['added'],second['updated'],second['stored']),(0,1,1))
        item=bridge.items()[0]
        self.assertEqual(item['extra']['browser_imported_at'],stamp)
        self.assertEqual(item['extra']['content_kind'],'browser_card')
        self.assertIsNone(item['extra']['published']);self.assertIsNone(item['extra']['likes'])
        self.assertNotIn('imported_by',item['extra'])
        with storage.connect() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0],0)

    def test_expired_import_excluded_and_status_has_no_note_link_or_session(self):
        bridge.save(payload(),'test-admin')
        encoded=json.dumps(bridge.status())
        self.assertNotIn('public-note-link',encoded);self.assertNotIn('test-admin',encoded)
        with patch.object(bridge.time,'time',return_value=time.time()+8*86400):self.assertFalse(bridge.items())

    def test_normal_collection_merges_browser_source_with_index_by_id(self):
        bridge.save(payload(),'test-admin')
        prior=copy.deepcopy(bridge.items()[0]);prior['extra']['content_kind']='search_excerpt'
        with patch.object(social,'retrieve',return_value=([prior],'公开搜索索引未返回可核查的华理原帖')):
            result=social.collect()
        self.assertEqual(len(result['items']),1)
        self.assertEqual(result['items'][0]['extra']['content_kind'],'browser_card')
        self.assertNotIn('xiaohongshu-school',result['errors'])

    def test_scoped_token_stored_as_hash_rotation_expiry_and_revocation(self):
        with patch('utils.access.admin_usernames',return_value={'admin'}),patch('utils.access.server_accounts',return_value={'admin':'dummy'}):
            first=bridge.rotate_pair('admin')
            self.assertEqual(bridge.token_owner('Bearer '+first['token']),'admin')
            self.assertNotIn(first['token'],storage.kv_get(bridge.PAIR_KEY).decode())
            second=bridge.rotate_pair('admin')
            self.assertEqual(bridge.token_owner('Bearer '+first['token']),'')
            with patch.object(bridge.time,'time',return_value=second['expires_at']+1):self.assertEqual(bridge.token_owner('Bearer '+second['token']),'')
            bridge.revoke_pair();self.assertEqual(bridge.token_owner('Bearer '+second['token']),'')

    def test_automatic_push_deduplicates_and_limits_accidental_retry(self):
        result=bridge.auto_push(payload(),'admin');self.assertEqual(result['added'],1)
        with self.assertRaises(RuntimeError):bridge.auto_push(payload(),'admin')
        bridge.save(payload(),'admin')
        with self.assertRaises(RuntimeError):bridge.auto_push(payload(),'admin')

    def test_token_owner_must_still_be_enabled_admin(self):
        token=bridge.rotate_pair('removed-admin')['token']
        with patch('utils.access.admin_usernames',return_value=set()),patch('CampusPulse.accounts.get',return_value=None):
            self.assertFalse(bridge.token_owner('Bearer '+token))


class BrowserImportRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from CampusPulse.blueprint import pulse_bp
        cls.app=Flask(__name__);cls.app.secret_key='isolated-test-session'
        cls.app.register_blueprint(pulse_bp,url_prefix='/pulse')
    def client(self):return self.app.test_client()
    def login(self,client):
        with client.session_transaction() as session:session.update(authenticated=True,username='test-admin')
    def test_loopback_does_not_bypass_authentication_or_admin_role(self):
        client=self.client();self.assertEqual(client.post('/pulse/api/xhs-browser/import',json=payload()).status_code,401)
        self.login(client)
        with patch('CampusPulse.blueprint.access.is_admin',return_value=False):
            self.assertEqual(client.post('/pulse/api/xhs-browser/import',json=payload()).status_code,403)
    def test_origin_and_size_checks_prevent_save(self):
        client=self.client();self.login(client)
        with patch('CampusPulse.blueprint.access.is_admin',return_value=True),patch.object(bridge,'save') as save:
            self.assertEqual(client.post('/pulse/api/xhs-browser/import',json=payload(),headers={'Origin':'https://evil.invalid'}).status_code,403)
            self.assertEqual(client.post('/pulse/api/xhs-browser/import',data='x'*131073,content_type='application/json').status_code,413)
            save.assert_not_called()
    def test_valid_import_queues_refresh_and_status_not_cached(self):
        client=self.client();self.login(client)
        with patch('CampusPulse.blueprint.access.is_admin',return_value=True),patch.object(bridge,'save',return_value={'received':1}) as save,patch.object(bridge,'request_refresh') as refresh,patch.object(bridge,'status',return_value={'stored':1}):
            self.assertEqual(client.post('/pulse/api/xhs-browser/import',json=payload()).status_code,200)
            self.assertEqual(save.call_args.args[1],'test-admin');refresh.assert_called_once()
            response=client.get('/pulse/api/xhs-browser/status');self.assertEqual(response.headers['Cache-Control'],'no-store')

    def test_upload_token_does_not_require_or_grant_admin_session(self):
        client=self.client()
        with patch.object(bridge,'token_owner',return_value=''):
            self.assertEqual(client.post('/pulse/api/xhs-browser/push',json=payload()).status_code,401)
        with patch.object(bridge,'token_owner',return_value='admin'),patch.object(bridge,'auto_push',return_value={'received':1}) as upload,patch.object(bridge,'request_refresh'):
            self.assertEqual(client.get('/pulse/api/xhs-browser/ping').status_code,200)
            self.assertEqual(client.post('/pulse/api/xhs-browser/push',json=payload()).status_code,200)
            upload.assert_called_once()
            self.assertEqual(client.post('/pulse/api/xhs-browser/key',json={'action':'pair'}).status_code,401)

    def test_nginx_auth_subrequest_limits_token_to_exact_upload_paths(self):
        from unittest.mock import Mock
        tree=ast.parse((Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='auth_check');node.decorator_list=[]
        access=Mock();access.session_valid.return_value=False
        namespace={'request':request,'session':session,'jsonify':jsonify,'urlsplit':urlsplit,'access':access}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'auth-check','exec'),namespace)
        with patch.object(bridge,'token_owner',return_value='admin'):
            with self.app.test_request_context('/api/auth/check',headers={'X-Original-URI':'/pulse/api/xhs-browser/push'}):self.assertEqual(namespace['auth_check']()[1],204)
            with self.app.test_request_context('/api/auth/check',headers={'X-Original-URI':'/api/config'}):self.assertEqual(namespace['auth_check']()[1],401)


if __name__=='__main__':unittest.main()
