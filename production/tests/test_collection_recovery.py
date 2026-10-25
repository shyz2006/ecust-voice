import unittest,json
from unittest.mock import Mock,patch
import requests
from CampusPulse import search,collectors,pipeline
from CampusPulse.sources import campus_social

class SearchParameterTests(unittest.TestCase):
    def setUp(self):
        self.response=Mock();self.response.json.return_value={'code':200,'data':{'webPages':{'value':[{'name':'实际检索结果','url':'https://example.invalid/post','summary':'摘要'}]}}}
    def call(self,**kwargs):
        with patch.object(search.settings,'bocha_api_key','test-key'),patch.object(search.settings,'bocha_base_url','https://api.bocha.cn/v1/ai-search'),patch('utils.search_gateway.cache_get',return_value=None),patch('utils.search_gateway.try_consume',return_value=True),patch('utils.search_gateway.cache_put'),patch.object(search.requests,'post',return_value=self.response) as post:
            result=search.web_search('华理',**kwargs)
        return result,post.call_args
    def test_normal_search_does_not_require_an_include_variable(self):
        result,call=self.call();self.assertEqual(len(result),1);self.assertNotIn('include',call.kwargs['json'])
    def test_include_is_supported_and_uses_web_search_endpoint(self):
        result,call=self.call(include='xiaohongshu.com')
        self.assertTrue(call.args[0].endswith('/web-search'));self.assertEqual(call.kwargs['json']['include'],'xiaohongshu.com')
        self.assertEqual(result[0]['url'],'https://example.invalid/post')

class CollectionIsolationTests(unittest.TestCase):
    def test_new_adapter_failure_keeps_hotlists(self):
        batch={'batch_ts':123,'items':[{'source':'weibo','title':'热榜'}],'errors':{}}
        with patch.object(pipeline.collectors,'collect_hotlists',return_value=batch),patch.object(pipeline.settings,'huyou_enabled',False),patch.object(pipeline.settings,'bilibili_enabled',False),patch.object(pipeline,'get_forums',return_value=[]),patch.object(pipeline.campus_social,'collect',side_effect=TypeError('invalid signature')):
            result=pipeline._fetch_all()
        self.assertEqual(result['items'],batch['items']);self.assertIn('xiaohongshu-school',result['errors']);self.assertIn('douyin-school',result['errors'])
    def test_one_school_adapter_does_not_cancel_the_other(self):
        rows=[{'title':'华东理工大学校园讨论','snippet':'活动','url':'https://www.douyin.com/video/12345'}]
        def search_call(query,**kwargs):
            if kwargs.get('include')=='douyin.com':return rows
            raise TypeError('bad')
        with patch.object(campus_social.storage,'kv_get',return_value=None),patch.object(campus_social.storage,'kv_set'),patch.object(campus_social.search,'web_search',side_effect=search_call):
            result=campus_social.collect()
        self.assertIn('xiaohongshu-school',result['errors']);self.assertEqual(result['items'][0]['source'],'douyin-school')
    def test_malformed_cache_does_not_stop_school_searches(self):
        with patch.object(campus_social.storage,'kv_get',return_value=b'[]'),patch.object(campus_social.storage,'kv_set'),patch.object(campus_social.search,'web_search',return_value=[]) as search_call:
            result=campus_social.collect()
        self.assertEqual(search_call.call_count,6);self.assertEqual(len(result['errors']),2)
    def test_bad_hotlist_response_shape_becomes_source_error(self):
        response=Mock();response.json.return_value=['unexpected']
        with patch.object(collectors.requests,'get',return_value=response):source,items,error=collectors._fetch_source('weibo')
        self.assertEqual(items,[]);self.assertTrue(error)
    def test_temporary_http500_gets_one_retry(self):
        response=Mock();response.json.return_value={'items':[{'title':'正常恢复'}]}
        failure=requests.HTTPError(response=Mock(status_code=500))
        with patch.object(collectors.requests,'get',side_effect=[failure,response]) as get,patch.object(collectors.time,'sleep'):
            _,items,error=collectors._fetch_source('douyin')
        self.assertEqual(get.call_count,2);self.assertEqual(len(items),1);self.assertFalse(error)
    def test_permission_errors_are_not_retried(self):
        failure=requests.HTTPError(response=Mock(status_code=403))
        with patch.object(collectors.requests,'get',side_effect=failure) as get,patch.object(collectors.time,'sleep'):
            _,items,error=collectors._fetch_source('douyin')
        self.assertEqual(get.call_count,1);self.assertIn('403',error);self.assertFalse(items)
    def test_one_http500_does_not_lose_other_platform_items(self):
        response=Mock();response.json.return_value={'items':[{'title':'真实条目','url':'https://example.invalid/post'},None,{'title':123}]}
        failure=requests.HTTPError(response=Mock(status_code=500))
        def get(url,**kwargs):
            if 'id=douyin&' in url:raise failure
            return response
        with patch.object(collectors.requests,'get',side_effect=get),patch('CampusPulse.sources.xiaohongshu_hot.fetch',return_value=('xiaohongshu',[],'')):
            result=collectors.collect_hotlists(['weibo','douyin'])
        self.assertEqual(len(result['items']),1);self.assertIn('500',result['errors']['douyin'])
    def test_successful_healthy_items_reach_persistence(self):
        batch={'batch_ts':123,'items':[{'source':'weibo','title':'条目'}],'errors':{'xiaohongshu':'HTTP500'},'meta':{}}
        with patch.object(pipeline,'_fetch_all',return_value=batch),patch.object(pipeline.storage,'record_fetch') as save,patch.object(pipeline,'analyze_batch',return_value={'complete':True}):result=pipeline.run_once(use_llm=False)
        save.assert_called_once();self.assertTrue(result['complete']);self.assertIn('xiaohongshu',result['errors'])

if __name__=='__main__':unittest.main()
