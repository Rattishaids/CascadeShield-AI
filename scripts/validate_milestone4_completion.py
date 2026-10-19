"""Fail closed unless the completed Milestone 4 artifacts agree with frozen experiment evidence."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


def main():
    result={'checkedAtUtc':datetime.now(timezone.utc).isoformat(),'provenance':'ENGINEERING_ARTIFACT_VALIDATION','checks':[]}
    def check(name,condition,evidence):
        if not condition:raise ValueError(name+': '+str(evidence))
        result['checks'].append({'name':name,'passed':True,'evidence':evidence})
    try:
        model=read('models/milestone4/v1/manifest.json');digest=sha('models/milestone4/v1/manifest.json')
        check('published_model_selection_is_frozen_simulation_only',model['frozen'] and not model['trainedOnObservedFreight'],digest)
        for path,expected in model['implementationSha256'].items():check('frozen_implementation:'+path,sha(path)==expected,expected)
        for path,expected in model['artifactSha256'].items():check('model_artifact:'+path,sha('models/milestone4/v1/'+path)==expected,expected)
        check('current_protocol_matches_selection',sha('config/milestone4_protocol_v2.json')==model['protocolSha256'],model['protocolSha256'])
        check('scenario_declaration_matches_selection',sha('data/processed/milestone4/corpus_v2/generation_manifest.json')==model['generationManifestSha256'],model['generationManifestSha256'])
        for split,expected in model['sourceCorpusSha256'].items():check(split+'_corpus_unchanged',sha('data/processed/milestone4/corpus_v2/'+split+'.jsonl')==expected,expected)
        prediction=read('reports/MILESTONE_4_PREDICTION_METRICS.json');policy=read('reports/MILESTONE_4_POLICY_BENCHMARK.json')
        check('shared_selection_for_prediction_policy',prediction['modelManifestSha256']==policy['selectionManifestSha256']==digest,digest)
        check('final_prediction_examples_and_cases',prediction['split']=='final' and prediction['dataset']['scenarioCount']==40 and prediction['dataset']['truckExamples']==3837,{'cases':40,'truckSnapshots':3837})
        check('all_440_paired_policy_outcomes',policy['pairedExecutionComplete'] and policy['caseCount']==40 and policy['policyCount']==11 and policy['runCount']==440,{'cases':40,'policies':11,'rows':440})
        check('four_whole_seed_final_clusters',policy['seedClusterCount']==4,policy['uncertainty'])
        for path,expected in policy['rawOutcomeSha256'].items():
            full=path if path.startswith('reports/') else 'reports/milestone4_policy_raw/'+path
            check('raw_policy_outcome:'+path,sha(full)==expected,expected)
        freeze=read('reports/milestone4_policy_raw/policies_implementation_freeze.json')
        for path,expected in freeze['sourceAndExecutableSha256'].items():check('executed_source_or_class:'+path,sha(path)==expected,expected)
        baseline=read('reports/milestone4_preservation_manifest.json')
        for path,entry in baseline['files'].items():check('historical_preservation:'+path,sha(path)==entry['sha256'],entry['sha256'])
        for path in ('milestone4_ml_integration.json','milestone4_ml_outage.json','milestone4_ml_recovery.json',
                     'milestone4_browser_tests.json','milestone4_restart_tests.json','milestone4_legacy_python_tests.json',
                     'milestone4_ml_unit_tests.json','milestone4_policy_replay.json'):
            report=read('reports/'+path);check('executed_check_report:'+path,report.get('passed') is True,sha('reports/'+path))
        java=read('reports/milestone4_java_tests.json');frontend=read('reports/milestone4_frontend_tests.json')
        check('actual_java_suite',java['tests']==155 and java['failures']==java['errors']==java['skipped']==0,{'passed':155})
        check('actual_frontend_suite',frontend['numPassedTests']==59 and frontend['numFailedTests']==0,{'passed':59})
        figures=read('reports/milestone4_figure_provenance.json')
        check('figures_bind_current_completed_results',figures['sourceSha256']['MILESTONE_4_POLICY_BENCHMARK.json']==sha('reports/MILESTONE_4_POLICY_BENCHMARK.json'),figures['files'])
        completed=read('reports/MILESTONE_4_RESULTS.json')
        check('completion_report_agrees',completed['policyRunCount']==440 and completed['modelManifestSha256']==digest,completed['status'])
        result['passed']=True
    except Exception as error:
        result.update(passed=False,failure=repr(error));raise
    finally:
        result['passedChecks']=len(result['checks'])
        (ROOT/'reports/milestone4_completion_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'checks':result['passedChecks']}))


if __name__=='__main__':main()
