# -*- coding: utf-8 -*-
"""Run an Alpha gate only after data and preregistration integrity checks."""
from alpha.alpha_survival_lab import alpha_survival_gate
from real_data_registry import audit_price_dataset
from preregistered_alpha_experiment import load_and_verify

def run_phase22(spec_path, datasets, experiments):
    spec=load_and_verify(spec_path)
    audits={name:audit_price_dataset(path, manifest=manifest) for name,(path,manifest) in datasets.items()}
    if not all(x['passed'] for x in audits.values()):
        return {'verdict':'INCONCLUSIVE','reason':'data_audit_failed','data_audits':audits}
    required=spec['spec']['benchmarks']
    gate=alpha_survival_gate(experiments,required_benchmarks=required)
    gate['data_audits']=audits; gate['preregistration_hash']=spec['sha256']
    return gate
