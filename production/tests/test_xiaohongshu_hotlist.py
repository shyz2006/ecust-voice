import unittest,json,time
from unittest.mock import patch,Mock
from CampusPulse.sources import xiaohongshu_hot as xhs
from CampusPulse import collectors,revision

class RednoteSourceTests(unittest.TestCase):
    def setUp(self):
        self.cache={}
        self.get=patch.object(xhs.storage,'kv_get',side_effect=lambda k:self.cache.get(k));self.get.start()
        self.put=patch.object(xhs.storage,'kv_set',side_effect=lambda k,v:self.cache.__setitem__(k,v));self.put.start()
        self.response=Mock();self.response.json.return_value={'code':200,'data':[{'title':'校园生活分享','score':'100','link':'https://example.invalid/unsafe'}]}
    def tearDown(self):self.get.stop();self.put.stop()
    def test_valid_rows_and_search_link_provenance(self):
        rows=xhs.normalize(self.response.json(),123)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['source'],'xiaohongshu')
        self.assertTrue(rows[0]['url'].startswith('https://www.xiaohongshu.com/search_result?'))
        self.assertEqual(rows[0]['extra']['link_kind'],'platform_search')
        self.assertEqual(rows[0]['extra']['provider_observed_at'],123)
    def test_duplicates_and_bad_rows_are_not_counted(self):
        payload={'code':200,'data':[None,{'title':123},{'title':''},{'title':'同一话题'},{'title':'同一话题'}]}
        self.assertEqual(len(xhs.normalize(payload,1)),1)
    def test_provider_error_cannot_become_a_valid_list(self):
        for payload in ({'code':500,'data':[{'title':'错误'}]},{'code':200,'data':[]},[]):
            with self.assertRaises(ValueError):xhs.normalize(payload,1)
    def test_success_is_cached_for_half_hour(self):
        with patch.object(xhs.requests,'get',return_value=self.response) as get:
            first=xhs.fetch();second=xhs.fetch()
        self.assertEqual(get.call_count,1);self.assertEqual(first,second)
    def test_expired_cache_fetches_again(self):
        with patch.object(xhs.requests,'get',return_value=self.response) as get:
            with patch.object(xhs.time,'time',return_value=100):xhs.fetch()
            with patch.object(xhs.time,'time',return_value=100+xhs.CACHE_SECONDS+1):xhs.fetch()
        self.assertEqual(get.call_count,2)
    def test_failure_has_short_cooldown_and_no_fake_rows(self):
        import requests
        with patch.object(xhs.requests,'get',side_effect=requests.Timeout) as get:
            result=xhs.fetch();again=xhs.fetch()
        self.assertEqual(get.call_count,2);self.assertFalse(result[1]);self.assertEqual(result,again)
    def test_transient_error_retries_once_and_caches_success(self):
        import requests
        failed=Mock();failed.status_code=503
        with patch.object(xhs.requests,'get',side_effect=[requests.HTTPError(response=failed),self.response]) as get,patch.object(xhs.time,'sleep'):
            result=xhs.fetch();again=xhs.fetch()
        self.assertEqual(get.call_count,2);self.assertTrue(result[1]);self.assertEqual(result,again)
    def test_authorization_or_quota_errors_are_not_retried(self):
        import requests
        for code in (401,403,429):
            self.cache.clear();failed=Mock();failed.status_code=code
            with patch.object(xhs.requests,'get',side_effect=requests.HTTPError(response=failed)) as get:
                result=xhs.fetch()
            self.assertEqual(get.call_count,1);self.assertFalse(result[1])
    def test_collector_uses_dedicated_source_without_newsnow(self):
        expected=('xiaohongshu',[], '测试')
        with patch.object(xhs,'fetch',return_value=expected),patch.object(collectors.requests,'get') as request:
            self.assertEqual(collectors._fetch_source('xiaohongshu'),expected)
        request.assert_not_called()
    def test_network_failure_in_xhs_does_not_cancel_other_sources(self):
        with patch.object(xhs,'fetch',side_effect=RuntimeError),patch.object(collectors.requests,'get',return_value=self.response):
            source,items,error=collectors._fetch_source('xiaohongshu')
        self.assertFalse(items);self.assertTrue(error)
    def test_youth_hotlist_has_xhs_and_keeps_ten_cards(self):
        now=int(time.time());rows=[{'source':'xiaohongshu','title':'话题'+str(i),'rank':i+1,'batch_ts':now,'url':'https://www.xiaohongshu.com/search_result?keyword='+str(i),'extra':{'link_kind':'platform_search'}} for i in range(20)]
        with patch.object(revision.storage,'latest_source_batches',return_value={'xiaohongshu':now}),patch.object(revision.storage,'recent_items',return_value=rows),patch.object(revision.storage,'kv_prefix',return_value=[]),patch.object(revision.storage,'latest_topics',return_value={'topics':[]}):
            result=revision._network_feed('hot')
        self.assertIn('小红书',result['platforms']);self.assertEqual(len(result['items']),10)
        self.assertTrue(all(x['focus'] and x['link_kind']=='platform_search' for x in result['items']))

if __name__=='__main__':unittest.main()
