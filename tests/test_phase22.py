import csv, tempfile, unittest
from pathlib import Path
from real_data_registry import build_manifest,audit_price_dataset
from preregistered_alpha_experiment import save,load_and_verify
from phase22_alpha_runner import run_phase22

class TestPhase22(unittest.TestCase):
    def _csv(self, d, bad=False):
        p=Path(d)/'x.csv'
        rows=[{'date':'2024-01-02','code':'000001','open':'10','high':'11','low':'9','close':'10.5','volume':'1000'}, {'date':'2024-01-03','code':'000001','open':'10.5','high':'11','low':'10','close':'10.8','volume':'1100'}]
        if bad: rows[1]['high']='9'
        with open(p,'w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
        return p
    def _spec(self,d):
        return {'name':'fixed-oos','strategy_version':'phase22','data_manifest_hashes':['x'],'oos_start':'2024-01-01','oos_end':'2024-12-31','benchmarks':['CSI300'],'entry_rules':'fixed','exit_rules':'fixed','cost_model':'fixed','alpha_gate':'phase21'}
    def test_dataset_audit(self):
        with tempfile.TemporaryDirectory() as d:
            p=self._csv(d); m=build_manifest(p,'fixture','price')
            self.assertTrue(audit_price_dataset(p,m)['passed'])
    def test_bad_dataset_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=self._csv(d,True); self.assertFalse(audit_price_dataset(p)['passed'])
    def test_prereg_hash_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'spec.json'; save(self._spec(d),p); load_and_verify(p)
            import json; x=json.loads(p.read_text()); x['spec']['name']='changed'; p.write_text(json.dumps(x))
            with self.assertRaises(ValueError): load_and_verify(p)
    def test_runner_blocks_bad_data(self):
        with tempfile.TemporaryDirectory() as d:
            csvp=self._csv(d,True); specp=Path(d)/'spec.json'; save(self._spec(d),specp)
            m=build_manifest(csvp,'fixture','price')
            r=run_phase22(specp,{'price':(csvp,m)},[])
            self.assertEqual(r['verdict'],'INCONCLUSIVE')
if __name__=='__main__': unittest.main()
