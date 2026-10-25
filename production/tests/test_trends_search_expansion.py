import time,unittest
from unittest.mock import patch
from CampusPulse import revision,search
from CampusPulse.sources import campus_social

DAY=86400

def points(values):
    return [{'ts':1000000+i*DAY,'observed':v is not None,'new_posts':v,'posts':v if v is not None else 7} for i,v in enumerate(values)]


class TrendWindowTests(unittest.TestCase):
    def test_latest_complete_pair_survives_recent_outage(self):
        series=points([5,8,9,None,None]);result=revision.window_comparison(series)
        self.assertEqual(result['value'],1);self.assertEqual(result['basis'],'latest_complete')
        self.assertEqual(result['current'],9);self.assertEqual(result['previous'],8)
        self.assertEqual(result['end'],series[2]['ts']+DAY)
        self.assertIsNone(series[-1]['new_posts'])
    def test_current_complete_pair_is_preferred(self):
        result=revision.window_comparison(points([3,8,6]))
        self.assertEqual(result['value'],-2);self.assertEqual(result['basis'],'current')
    def test_isolated_observations_cannot_be_a_daily_comparison(self):
        self.assertIsNone(revision.window_comparison(points([4,None,9]))['value'])
        separated=points([4,9]);separated[1]['ts']+=DAY
        self.assertIsNone(revision.window_comparison(separated)['value'])
    def test_zero_counts_are_valid_when_windows_are_complete(self):
        self.assertEqual(revision.window_comparison(points([0,0]))['value'],0)
        self.assertEqual(revision.count_reference(points([0,0,0]))['value'],0)
    def test_reference_excludes_partial_counts_and_marks_its_age(self):
        series=points([10,20,30,40,None,None]);result=revision.count_reference(series)
        self.assertEqual(result['value'],25);self.assertEqual(result['windows'],4)
        self.assertEqual(result['lag_windows'],2);self.assertEqual(result['as_of'],series[3]['ts']+DAY)
        self.assertEqual(result['target_end'],series[-1]['ts']+2*DAY)
        self.assertGreater(result['upper']-result['value'],result['mae'])
    def test_reference_requires_three_observed_windows(self):
        result=revision.count_reference(points([2,5,None,None]))
        self.assertIsNone(result['value']);self.assertIsNone(result['lower'])
        self.assertIsNone(revision.count_reference([])['value'])


def note(n=1,alias='explore'):
    return {'title':'华东理工大学校园分享','snippet':'奉贤校区的学习生活',
            'url':'https://www.xiaohongshu.com/'+alias+'/'+str(n)}


class SchoolSearchExpansionTests(unittest.TestCase):
    def test_four_bounded_queries_merge_duplicate_note_aliases(self):
        with patch.object(campus_social.search,'web_search',return_value=[note(1),note(1,'discovery/item'),note(2)]) as call:
            found,error=campus_social.retrieve('xiaohongshu-school')
        self.assertEqual(len(found),2);self.assertFalse(error);self.assertEqual(call.call_count,4)
        self.assertTrue(all(c.kwargs['count']==50 and c.kwargs['plain'] for c in call.call_args_list))
        self.assertEqual(len(found[0]['extra']['search_queries']),4)
    def test_search_pool_is_bounded_at_one_hundred_distinct_notes(self):
        def results(query,**kwargs):
            offset=0 if query=='华东理工大学' else 50
            return [note(i+offset) for i in range(50)]
        with patch.object(campus_social.search,'web_search',side_effect=results) as call:
            found,error=campus_social.retrieve('xiaohongshu-school')
        self.assertEqual(len(found),100);self.assertEqual(call.call_count,2)
        self.assertEqual(found[-1]['rank'],100)
    def test_landing_pages_and_other_schools_are_not_counted(self):
        wrong=[{'title':'华东理工大学','url':'https://www.xiaohongshu.com/'},
               {'title':'华理 华北理工大学','url':note()['url']},
               {'title':'华东理工大学','url':'https://pgy.xiaohongshu.com/explore/123'},
               {'title':'华东理工大学','url':note()['url']+'/comments'}]
        self.assertEqual(campus_social.parse('xiaohongshu-school',wrong),[])
    def test_plain_http_index_link_is_upgraded_after_validation(self):
        row=note();row['url']=row['url'].replace('https:','http:')
        self.assertTrue(campus_social.parse('xiaohongshu-school',[row])[0]['url'].startswith('https:'))
    def test_one_query_failure_keeps_other_queries_results(self):
        with patch.object(campus_social.search,'web_search',side_effect=[RuntimeError(),[note(1)],[note(2)],[note(3)]]):
            found,error=campus_social.retrieve('xiaohongshu-school')
        self.assertEqual(len(found),3);self.assertIn('部分',error)
    def test_quota_failure_does_not_spend_more_queries(self):
        with patch.object(campus_social.search,'web_search',side_effect=search.SearchUnavailable()) as call:
            found,error=campus_social.retrieve('xiaohongshu-school')
        self.assertEqual(call.call_count,1);self.assertFalse(found);self.assertTrue(error)


class RecentHotPoolTests(unittest.TestCase):
    def test_expired_latest_batch_is_not_described_as_recent(self):
        now=int(time.time());old=now-2*DAY
        rows=[{'source':'xiaohongshu','title':'旧话题','batch_ts':old,'rank':1,'extra':{}}]
        with patch.object(revision.storage,'latest_source_batches',return_value={'xiaohongshu':old}),patch.object(revision.storage,'recent_items',return_value=rows),patch.object(revision.storage,'kv_prefix',return_value=[]),patch.object(revision.storage,'latest_topics',return_value={'topics':[]}):
            result=revision._network_feed('hot')
        self.assertEqual(result['candidate_counts'].get('小红书',0),0);self.assertEqual(result['items'],[])

    def test_recent_topics_are_retained_deduplicated_and_not_scored_as_current(self):
        now=int(time.time())
        def row(title,ts,rank):return {'source':'xiaohongshu','title':title,'batch_ts':ts,'rank':rank,'url':note()['url'],'extra':{'link_kind':'platform_search'}}
        rows=[row('新话题'+str(i),now,i+1) for i in range(8)]
        rows += [row('旧话题'+str(i),now-3600,i+1) for i in range(4)]
        rows += [row('新话题0',now-3600,1),row('过期话题',now-2*DAY,1)]
        with patch.object(revision.storage,'latest_source_batches',return_value={'xiaohongshu':now}),patch.object(revision.storage,'recent_items',return_value=rows),patch.object(revision.storage,'kv_prefix',return_value=[]),patch.object(revision.storage,'latest_topics',return_value={'topics':[]}):
            result=revision._network_feed('hot')
        self.assertEqual(result['candidate_counts']['小红书'],12);self.assertEqual(len(result['items']),10)
        self.assertTrue(all(not x['recent_topic'] for x in result['items'][:8]))
        self.assertTrue(all(x['recent_topic'] and x['signal'] is None for x in result['items'][8:]))
        self.assertEqual(next(x for x in result['items'] if x['title']=='新话题0')['ts'],now)


if __name__=='__main__':unittest.main()
