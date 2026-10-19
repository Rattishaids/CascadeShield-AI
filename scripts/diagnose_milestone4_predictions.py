"""Post-assessment diagnostic examples for each frozen provider; never selects or refits a model."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODELS=('xgb-v1','xgb-no-graph-v1','gnn-static-v1','gnn-temporal-v1')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    path=ROOT/'reports/MILESTONE_4_PREDICTION_METRICS_rows.csv'
    grouped=defaultdict(list)
    with path.open(encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream):
            if row['modelId'] not in MODELS:continue
            row={**row,'clockSec':float(row['clockSec']),'truth':float(row['truth']),
                 'prediction':float(row['prediction']),'absoluteError':float(row['absoluteError'])}
            key=row['modelId'],row['target'];grouped[key].append(row)
            grouped[key]=sorted(grouped[key],key=lambda r:(-r['absoluteError'],r['scenarioId'],r['truckId'],r['clockSec']))[:5]
    needed={(r['scenarioId'],r['clockSec'],r['truckId']) for rows in grouped.values() for r in rows}
    inputs={};corpus=ROOT/'data/processed/milestone4/corpus_v2/final.jsonl'
    with corpus.open(encoding='utf-8-sig') as stream:
        for line in stream:
            scenario=json.loads(line)
            for frame in scenario['frames']:
                for truck in frame['trucks']:
                    key=scenario['scenarioId'],frame['clockSec'],truck['truckId']
                    if key in needed:inputs[key]={'asOfFeatures':truck['features'],'ruleBaseline':truck['baseline'],
                        'snapshotFingerprint':frame['stateFingerprint'],'labelsNotUsedForInference':True}
    diagnostics={}
    for (mid,target),rows in grouped.items():
        diagnostics.setdefault(mid,{})[target]=[{**row,**inputs[(row['scenarioId'],row['clockSec'],row['truckId'])]} for row in rows]
    manifest_path=ROOT/'models/milestone4/v1/manifest.json';manifest=json.loads(manifest_path.read_text())
    importances={mid:{target:list(config['featureImportance'].items())[:10] for target,config in manifest['models'][mid]['selection'].items()}
                 for mid in MODELS if mid.startswith('xgb')}
    report={'schemaVersion':'cascadeshield.milestone4-prediction-diagnostics/1.0',
            'provenance':'POST_ASSESSMENT_SIMULATED_OUTCOME_DIAGNOSTICS_NO_REFITTING',
            'models':diagnostics,'xgbGainImportances':importances,
            'sourcesSha256':{str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in (path,corpus,manifest_path)},
            'interpretation':['Every displayed input belongs to the exact saved prediction-time frame; the later truth remains a separate diagnostic value.',
                'Largest errors are selected separately for each provider and target; tied binary errors are resolved by scenario/truck/time for reproducibility.',
                'XGBoost gain importance describes fitted splits over correlated rule/context features; it is not causal influence or observed-traffic calibration.',
                'These final outcomes are exposed. These examples cannot be used to retune the current bundle while retaining an independent-test claim.']}
    output=ROOT/'reports/milestone4_trained_prediction_diagnostics.json'
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'providers':len(diagnostics),'examples':sum(len(rows) for targets in diagnostics.values() for rows in targets.values()),'output':str(output)}))


if __name__=='__main__':main()
