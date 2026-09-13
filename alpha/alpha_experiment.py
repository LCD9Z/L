# -*- coding: utf-8 -*-
"""Phase 18: explicit A/B strategy experiment ledger."""
import statistics

def compare_variants(variants):
    rows=[]
    for name,rets in variants.items():
        vals=[float(x) for x in rets]
        rows.append({'variant':name,'n':len(vals),'mean_return':statistics.mean(vals) if vals else None,'win_rate':sum(x>0 for x in vals)/len(vals) if vals else None})
    rows.sort(key=lambda x:(x['mean_return'] is not None,x['mean_return']),reverse=True)
    return rows
