import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import requests
from CampusPulse import search
from CampusPulse.sources import campus_social as social
from utils import search_gateway as gateway


class SchoolGatewayCacheTests(unittest.TestCase):
    def test_source_max_age_expires_before_shared_default_without_changing_other_clients(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(gateway,'DB_PATH',Path(directory)/'cache.db'),patch.object(gateway.time,'time',return_value=1000):
            gateway.cache_put('endpoint','query','noLimit',50,False,{'code':200})
            with patch.object(gateway.time,'time',return_value=1000+7*3600):
                self.assertIsNotNone(gateway.cache_get('endpoint','query','noLimit',50,False))
                self.assertIsNone(gateway.cache_get('endpoint','query','noLimit',50,False,max_age_seconds=6*3600))
                self.assertIsNone(gateway.cache_get('endpoint','query','noLimit',50,False,max_age_seconds=0))
    def test_source_limit_cannot_extend_a_shorter_global_ttl(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(gateway,'DB_PATH',Path(directory)/'cache.db'),patch.object(gateway.time,'time',return_value=1000):
            gateway.cache_put('endpoint','query','oneDay',50,False,{'code':200})
            with patch.object(gateway.time,'time',return_value=1000+3*3600):
                self.assertIsNone(gateway.cache_get('endpoint','query','oneDay',50,False,max_age_seconds=6*3600))
    def test_school_search_passes_limit_and_preserves_daily_quota_gate(self):
        with patch.object(social.search,'web_search',return_value=[]) as call:
            social.retrieve('xiaohongshu-school')
        self.assertEqual(call.call_count,4)
        self.assertTrue(all(c.kwargs['cache_max_age_seconds']==21600 for c in call.call_args_list))
        with patch.object(search.settings,'bocha_api_key','test-key'),patch('utils.search_gateway.cache_get',return_value=None) as cache,patch('utils.search_gateway.try_consume',return_value=False),patch.object(search.requests,'post') as post:
            with self.assertRaises(search.SearchUnavailable):search.web_search('query',cache_max_age_seconds=21600)
        self.assertEqual(cache.call_args.kwargs['max_age_seconds'],21600);post.assert_not_called()


class PublicShareDiscoveryTests(unittest.TestCase):
    def reply(self,status=302,location='https://www.xiaohongshu.com/explore/note123'):
        return Mock(status_code=status,headers={'Location':location})
    def test_cn_share_in_search_result_resolves_to_real_note_and_keeps_provenance(self):
        row={'title':'华理奉贤校园生活','url':'https://xhslink.cn/o/Share123','snippet':'公开笔记摘要'}
        response=self.reply()
        with patch.object(social.requests,'get',return_value=response) as get:
            found=social.expand_shared_notes([row],set(),[25.0])
        self.assertEqual(len(found),1);self.assertEqual(found[0]['url'],'https://www.xiaohongshu.com/explore/note123')
        self.assertEqual(found[0]['extra']['supporting_url'],row['url']);self.assertEqual(found[0]['extra']['discovered_via'],'public_share_link')
        self.assertFalse(get.call_args.kwargs['allow_redirects']);response.close.assert_called_once()
    def test_share_link_inside_school_excerpt_is_recovered_but_listing_page_is_not_a_note(self):
        row={'title':'华东理工大学校区分享','url':'https://example.invalid/article','snippet':'同学公开分享 https://xhslink.com/m/Share123 。'}
        with patch.object(social.requests,'get',return_value=self.reply()):found=social.expand_shared_notes([row],set(),[25.0])
        self.assertEqual(len(found),1);self.assertEqual(found[0]['extra']['supporting_url'],row['url'])
        self.assertEqual(social.parse('xiaohongshu-school',[row]),[])
    def test_unrelated_school_or_post_does_not_trigger_requests(self):
        rows=[{'title':'购物分享','url':'https://xhslink.cn/o/Share123'}, {'title':'华理 华北理工大学','url':'https://xhslink.cn/o/Share456'}]
        with patch.object(social.requests,'get') as get:self.assertFalse(social.expand_shared_notes(rows,set(),[25.0]))
        get.assert_not_called()
    def test_redirect_to_untrusted_host_or_private_address_is_not_followed(self):
        for target in ('http://127.0.0.1/private','https://xiaohongshu.com.evil.invalid/explore/note1','https://user:secret@www.xiaohongshu.com/explore/note1','https://www.xiaohongshu.com:8080/explore/note1'):
            with patch.object(social.requests,'get',return_value=self.reply(location=target)) as get:
                self.assertFalse(social.resolve_public_share('https://xhslink.cn/o/Share123',time.monotonic()+25))
            self.assertEqual(get.call_count,1)
    def test_access_denial_or_timeout_is_not_retried_or_bypassed(self):
        for status in (401,403,406,412,429):
            with patch.object(social.requests,'get',return_value=self.reply(status=status)) as get:
                self.assertFalse(social.resolve_public_share('https://xhslink.cn/o/Share123',time.monotonic()+25))
            self.assertEqual(get.call_count,1)
        with patch.object(social.requests,'get',side_effect=requests.Timeout) as get:
            self.assertFalse(social.resolve_public_share('https://xhslink.cn/o/Share123',time.monotonic()+25))
        self.assertEqual(get.call_count,1)
    def test_redirects_and_unique_share_requests_are_bounded(self):
        with patch.object(social.requests,'get',return_value=self.reply(location='/o/Another')) as get:
            self.assertFalse(social.resolve_public_share('https://xhslink.cn/o/Share123',time.monotonic()+25))
        self.assertEqual(get.call_count,3)
        rows=[{'title':'华理校园','url':'https://xhslink.cn/o/Share'+str(i)} for i in range(9)]
        with patch.object(social.requests,'get',return_value=self.reply()) as get:
            found=social.expand_shared_notes(rows+rows,set(),[25.0])
        self.assertEqual(get.call_count,4)
    def test_exhausted_budget_and_invalid_url_never_make_network_calls(self):
        with patch.object(social.requests,'get') as get:
            self.assertFalse(social.expand_shared_notes([{'title':'华理校园','url':'https://xhslink.cn/o/Share1'}],set(),[0]))
            self.assertFalse(social.resolve_public_share('file:///etc/passwd',time.monotonic()+25))
        get.assert_not_called()
    def test_shared_note_aliases_are_deduplicated_with_direct_results(self):
        direct={'title':'华理校园','url':'https://www.xiaohongshu.com/explore/note123'}
        shared={'title':'华理校园','url':'https://xhslink.cn/o/Share123'}
        with patch.object(social.search,'web_search',return_value=[direct,shared]),patch.object(social.requests,'get',return_value=self.reply()):
            found,error=social.retrieve('xiaohongshu-school')
        self.assertEqual(len(found),1);self.assertFalse(error)


if __name__=='__main__':unittest.main()
