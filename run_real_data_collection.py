import argparse, json
from real_data_collector import acquire_universe
p=argparse.ArgumentParser(); p.add_argument('--symbols',required=True,help='comma-separated A-share codes'); p.add_argument('--start',required=True); p.add_argument('--end',required=True); p.add_argument('--out',default='real_data')
a=p.parse_args(); result=acquire_universe([x.strip() for x in a.symbols.split(',') if x.strip()],a.start,a.end,a.out); print(json.dumps(result,ensure_ascii=False,indent=2))
