"""Read-only live inference checks using the distributed models, without training corpora."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MODEL_IDS = {'xgb-v1','xgb-no-graph-v1','gnn-static-v1','gnn-temporal-v1'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api',default='http://127.0.0.1:8080/api')
    parser.add_argument('--service',default='http://127.0.0.1:8090')
    parser.add_argument('--mode',choices=('models','fallback'),default='models')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    target=args.report if args.report.is_absolute() else ROOT/args.report
    if target.exists():raise FileExistsError('Use a new report filename to preserve evidence')
    report={'checkedAtUtc':datetime.now(timezone.utc).isoformat(),'provenance':'READ_ONLY_RELEASE_ML_INTEGRATION',
            'mode':args.mode,'checks':[],'passed':False}
    def request(url,body=None,expected=200):
        req=Request(url,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=30) as response:code,value=response.status,json.load(response)
        except HTTPError as error:code,value=error.code,json.load(error)
        assert code==expected, (url,code)
        return value
    def passed(name,**evidence):report['checks'].append({'name':name,'passed':True,**evidence})
    try:
        before=request(args.api+'/state')
        assert before['status']!='RUNNING','Pause the disposable run before immutability checks'
        assert before['trucks'],'Load simulated trucks before checking inference output'
        if args.mode=='models':
            health=request(args.service+'/health')
            expected=hashlib.sha256((ROOT/'models/milestone4/v1/manifest.json').read_bytes()).hexdigest()
            assert health['status']=='UP' and health['inferenceDevice']=='cpu'
            assert health['selectionManifestSha256']==expected and not health['trainedOnObservedFreight']
            assert {m['id'] for m in health['models']}==MODEL_IDS
            passed('cpu_service_exact_frozen_manifest_and_four_model_registry',selectionManifestSha256=expected)
            for mid in sorted(MODEL_IDS):
                result=request(args.api+'/ml/predict',{'modelId':mid})
                prediction=result['prediction']
                assert not result['fallbackUsed'] and not result['stateMutated'],result.get('failureReason')
                assert prediction['modelId']==mid and prediction['source']=='TRAINED_SIMULATION_MODEL'
                assert {p['truckId'] for p in prediction['predictions']}=={t['id'] for t in before['trucks']}
                for row in prediction['predictions']:
                    for field in ('remainingArrivalSec','etaLowerSec','etaUpperSec','slaProbability','futureImpactProbability'):
                        assert row[field] is None or math.isfinite(row[field])
                    for field in ('slaProbability','futureImpactProbability'):
                        assert row[field] is None or 0<=row[field]<=1
                passed(mid+'_java_to_cpu_prediction',trucks=len(prediction['predictions']),endToEndLatencyMs=result['endToEndLatencyMs'])
            request(args.service+'/predict',{'schemaVersion':'invalid-release-contract-probe'},400)
            passed('invalid_inference_schema_is_rejected')
        else:
            result=request(args.api+'/ml/predict',{'modelId':'xgb-v1'})
            assert result['fallbackUsed'] and not result['stateMutated'] and result['failureReason']
            assert result['prediction']['source']=='RULE_BASED'
            assert all(all(p[field] is None for field in ('etaLowerSec','etaUpperSec','slaProbability','futureImpactProbability'))
                       for p in result['prediction']['predictions'])
            passed('unavailable_service_returns_labelled_rule_fallback_with_null_trained_probabilities')
        request(args.api+'/ml/predict',{'modelId':'not-a-provider'},400)
        passed('unsupported_provider_rejected')
        assert request(args.api+'/state')==before,'Inference changed authoritative state'
        passed('complete_stationary_state_preserved',runId=before['runId'],clockSec=before['clockSec'])
        report['passed']=True
    except Exception as error:
        report['failure']=repr(error)
    finally:
        report['passedChecks']=len(report['checks'])
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':report['passedChecks'],'mode':args.mode}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
