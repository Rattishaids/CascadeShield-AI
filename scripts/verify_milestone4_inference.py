"""Read-only HTTP model/Java integration checks, preserving the operator's live fleet."""
from __future__ import annotations
import argparse
import copy
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.features import REQUEST_VERSION, RESPONSE_VERSION, FEATURE_VERSION, FEATURE_HASH, strip_labels


def request(url, body=None, expected=200):
    data = None if body is None else json.dumps(body, allow_nan=False).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urlopen(req, timeout=30) as response:
            code, content = response.status, response.read()
    except HTTPError as error:
        code, content = error.code, error.read()
    if code != expected:
        raise AssertionError(f"{url}: expected HTTP {expected}, received {code}: {content[:400]!r}")
    return json.loads(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='http://127.0.0.1:8080/api')
    parser.add_argument('--service', default='http://127.0.0.1:8090')
    parser.add_argument('--corpus', type=Path, default=ROOT/'data/processed/milestone4/corpus_v2')
    parser.add_argument('--report', type=Path, default=ROOT/'reports/milestone4_ml_integration.json')
    parser.add_argument('--outage', action='store_true', help='Check deterministic Java fallback while the model service is intentionally stopped')
    args = parser.parse_args()
    report = {'checkedAtUtc': datetime.now(timezone.utc).isoformat(), 'provenance': 'ENGINEERING_TEST_EVIDENCE',
              'checks': [], 'liveMutations': False, 'mode': 'OUTAGE' if args.outage else 'TRAINED_INFERENCE'}
    def check(name, operation):
        started = time.perf_counter()
        value = operation()
        report['checks'].append({'name': name, 'passed': True, 'elapsedSec': time.perf_counter()-started, 'evidence': value})
        return value
    before = request(args.api+'/state')
    try:
        if before['status'] == 'RUNNING':
            raise RuntimeError('Pause the operator simulation before strict immutability verification; this script will not pause it.')
        if args.outage:
            response = request(args.api+'/ml/predict', {'modelId': 'xgb-v1'})
            assert response['fallbackUsed'] and not response['stateMutated']
            assert response['prediction']['source'] == 'RULE_BASED'
            assert all(p['slaProbability'] is None and p['etaLowerSec'] is None and p['etaUpperSec'] is None
                       for p in response['prediction']['predictions'])
            check('unavailable_ml_returns_explicit_uncalibrated_rule_fallback', lambda: {'failureReason': response['failureReason']})
        else:
            catalog = check('cpu_model_service_health', lambda: request(args.service+'/health'))
            assert catalog['status'] == 'UP' and catalog['inferenceDevice'] == 'cpu'
            assert catalog['trainedOnObservedFreight'] is False
            with (args.corpus/'train.jsonl').open(encoding='utf-8-sig') as handle:
                scenario = json.loads(next(line for line in handle if line.strip()))
            frame = strip_labels(scenario['frames'][0])
            payload = {'schemaVersion': REQUEST_VERSION, 'featureSchemaVersion': FEATURE_VERSION,
                       'featureSchemaHash': FEATURE_HASH, 'networkId': catalog['networkId'],
                       'graphSha256': catalog['graphSha256'], 'stateFingerprint': frame['stateFingerprint'],
                       'frame': frame, 'history': []}
            for model in catalog['models']:
                mid = model['id']
                def infer(model_id=mid):
                    value = request(args.service+'/predict', {**payload, 'modelId': model_id})
                    assert value['schemaVersion'] == RESPONSE_VERSION and value['modelId'] == model_id
                    assert value['source'] == 'TRAINED_SIMULATION_MODEL'
                    assert value['stateFingerprint'] == frame['stateFingerprint']
                    assert {p['truckId'] for p in value['predictions']} == {t['truckId'] for t in frame['trucks']}
                    for row in value['predictions']:
                        assert row['remainingArrivalSec'] is not None and math.isfinite(row['remainingArrivalSec'])
                        assert row['etaLowerSec'] <= row['etaUpperSec']
                        assert 0 <= row['slaProbability'] <= 1 and 0 <= row['futureImpactProbability'] <= 1
                    return {'modelId': model_id, 'latencyMs': value['latencyMs'], 'trucks': len(value['predictions'])}
                check(mid+'_eligible_development_frame_http_roundtrip', infer)
                def java_infer(model_id=mid):
                    value = request(args.api+'/ml/predict', {'modelId': model_id})
                    assert not value['fallbackUsed'], value.get('failureReason')
                    assert value['prediction']['modelId'] == model_id and value['stateMutated'] is False
                    return {'modelId': model_id, 'endToEndLatencyMs': value['endToEndLatencyMs'], 'warnings': value['prediction']['warnings']}
                check(mid+'_java_validated_live_snapshot', java_infer)
            valid = {**payload, 'modelId': catalog['models'][0]['id']}
            for name, altered in [('incompatible_feature_hash', {**valid, 'featureSchemaHash':'wrong'}),
                                  ('future_target_in_frame', {**valid, 'frame':{**frame, 'labels':{'testFixtureOnly':1}}})]:
                check(name+'_rejected', lambda body=altered: request(args.service+'/predict', body, 400))
            future = copy.deepcopy(frame); future['clockSec'] += 1
            check('future_history_rejected', lambda: request(args.service+'/predict', {**valid, 'history':[future]}, 400))
            check('unsupported_java_model_rejected', lambda: request(args.api+'/ml/predict', {'modelId':'untrained-invalid-model'}, 400))
        after = request(args.api+'/state')
        assert before == after, 'Inference changed the stationary live state'
        report.update(passed=True, liveStatePreserved=True, liveRunId=before['runId'], liveClockSec=before['clockSec'], trucks=len(before['trucks']))
    except Exception as error:
        report.update(passed=False, failure=repr(error))
        raise
    finally:
        report['passedChecks'] = sum(c['passed'] for c in report['checks'])
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': report['passedChecks'], 'report': str(args.report)}))


if __name__ == '__main__':
    main()
