
# 脚本位于 scripts/ 下，需把项目根目录加入导入路径
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, json
from real_data_collector import acquire_universe
p=argparse.ArgumentParser(); p.add_argument('--symbols',required=True,help='comma-separated A-share codes'); p.add_argument('--start',required=True); p.add_argument('--end',required=True); p.add_argument('--out',default='real_data')
a=p.parse_args(); result=acquire_universe([x.strip() for x in a.symbols.split(',') if x.strip()],a.start,a.end,a.out); print(json.dumps(result,ensure_ascii=False,indent=2))
