import unittest
from phase15_governance import review_release

class TestPhase15(unittest.TestCase):
    def base(self):
        return {
            'verdict':'PASS','issues':[], 'code_tests_passed':True,
            'data_quality':{'ok':True},
            'performance':{'max_drawdown_pct':10},
            'red_team_audit':{'ok':True,'issues':[]},
        }
    def test_ten_roles(self):
        r=review_release(self.base(), True, True, True, True, True)
        self.assertEqual(r['role_count'],10)
        self.assertEqual(r['release_verdict'],'RESEARCH_RELEASE_CANDIDATE')
    def test_lookahead_rejected(self):
        v=self.base(); v['issues']=['possible_lookahead_or_same_day_execution']; v['red_team_audit']={'ok':False,'issues':v['issues']}
        r=review_release(v, True, True, True, True, True)
        self.assertEqual(r['release_verdict'],'REJECT')
    def test_missing_evidence_holds(self):
        r=review_release(self.base())
        self.assertIn(r['release_verdict'], ('HOLD_FOR_EVIDENCE','CONDITIONAL_RESEARCH_ONLY'))

if __name__=='__main__': unittest.main()
