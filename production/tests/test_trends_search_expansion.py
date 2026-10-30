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



if __name__=='__main__':unittest.main()
