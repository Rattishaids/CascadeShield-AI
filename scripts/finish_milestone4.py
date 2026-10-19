"""Monitor the frozen assessment and run sequential verification/reporting after it completes.

This does not refit, alter a policy, reset the live fleet, or replace completed raw outcomes.
An interrupted launcher can leave this helper running; inspect its journal before restarting it.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'reports'
JOURNAL=REPORTS/'milestone4_finalization_execution.json'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def inventory():
    path=REPORTS/'MILESTONE_4_CHANGED_FILES.json';value=load(path)
    source={r['path']:r for r in value['reviewedImplementationFiles']}
    extra=('scripts/report_milestone4.py','scripts/plot_milestone4_results.py','scripts/validate_milestone4_completion.py',
           'scripts/check_milestone4_ml_tests.py','scripts/VerifyMilestone4Replay.java','scripts/finish_milestone4.py',
           'scripts/audit_milestone4_results.py')
    for name in extra:source.setdefault(name,{'path':name,'category':'Final evidence and reproducibility','reviewedStatus':'M4_ADDITION','baselineRecorded':False})
    for name,row in source.items():
        p=ROOT/name;row.update(bytes=p.stat().st_size,sha256=digest(p))
    artifacts={r['path']:r for r in value['generatedArtifacts'] if (ROOT/r['path']).is_file()}
    candidates=[*REPORTS.glob('milestone4*.json'),*REPORTS.glob('MILESTONE_4*'),
                *ROOT.glob('models/milestone4/v1/**/*'),*ROOT.glob('reports/figures/milestone4-*')]
    for p in candidates:
        if not p.is_file() or p.name in ('MILESTONE_4_CHANGED_FILES.json','MILESTONE_4_CHANGED_FILES.md','milestone4_finalization_execution.json'):continue
        name=p.relative_to(ROOT).as_posix();artifacts[name]={'path':name,'bytes':p.stat().st_size,'sha256':digest(p)}
    value.update(recordedAtUtc=datetime.now(timezone.utc).isoformat(),reviewedImplementationFileCount=len(source),
                 reviewedImplementationFiles=sorted(source.values(),key=lambda r:r['path']),
                 generatedArtifacts=sorted(artifacts.values(),key=lambda r:r['path']),
                 inProgressArtifacts={'status':'FINAL_ASSESSMENT_COMPLETE','policyRuns':440,
                                      'rawPolicyHashes':'reports/MILESTONE_4_POLICY_BENCHMARK.json','corpusHashes':'models/milestone4/v1/manifest.json'})
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    lines=['# Milestone 4 reviewed file inventory','',value['scope'],'',
           'All 86 recorded original assets remained unchanged. This inventory describes reviewed implementation work, not a reconstructed Git diff. Generated raw policy records and corpus files have complete hashes in their own manifests. Dependency environments, node_modules, caches and compiled output are excluded here.','',
           f"Reviewed implementation files: **{len(source)}**. Machine-readable bytes and SHA-256: [inventory](MILESTONE_4_CHANGED_FILES.json).",'']
    groups={}
    for row in source.values():groups.setdefault(row['category'],[]).append(row)
    for group,rows in sorted(groups.items()):
        lines+=['## '+group,'']
        for row in sorted(rows,key=lambda r:r['path']):lines.append(f"- [{row['path']}](../{row['path']}) - {row['reviewedStatus']}.")
        lines.append('')
    lines+=['## Executed artifacts','',f"{len(artifacts)} summary/model/figure artifacts are listed with exact hashes in the JSON inventory. See [final results](MILESTONE_4_RESULTS.md), [prediction evidence](MILESTONE_4_PREDICTION_METRICS.json), [all 440 policy outcome hashes](MILESTONE_4_POLICY_BENCHMARK.json), and [reproduction commands](../docs/MILESTONE_4_REPRODUCE.md).",'']
    (REPORTS/'MILESTONE_4_CHANGED_FILES.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    if JOURNAL.exists():
        old=load(JOURNAL)
        if old.get('status')=='COMPLETED':raise ValueError('Finalization already completed; inspect preserved results')
        if old.get('status')=='RUNNING':raise ValueError('A finalization journal is RUNNING; inspect its PID before any resume')
    import os
    record={'schemaVersion':'cascadeshield.milestone4-finalization/1.0','startedAtUtc':datetime.now(timezone.utc).isoformat(),
            'status':'RUNNING','pid':os.getpid(),'steps':[],'helperSha256':digest(Path(__file__)),
            'provenance':'ACTUAL_ENGINEERING_EXECUTION_NOT_MODEL_FITTING'}
    def persist():
        pending=JOURNAL.with_suffix('.pending');pending.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');pending.replace(JOURNAL)
    def run(label,command):
        row={'label':label,'command':command,'startedAtUtc':datetime.now(timezone.utc).isoformat(),'status':'RUNNING'}
        record['steps'].append(row);persist();print('START '+label,flush=True);start=time.perf_counter()
        completed=subprocess.run(command,cwd=ROOT)
        row.update(status='COMPLETED' if completed.returncode==0 else 'FAILED',returnCode=completed.returncode,elapsedSec=time.perf_counter()-start,
                   endedAtUtc=datetime.now(timezone.utc).isoformat());persist()
        if completed.returncode:raise RuntimeError(label+' failed; preserve evidence and inspect the output')
        print('DONE '+label,flush=True)
    persist()
    try:
        selection=digest(ROOT/'models/milestone4/v1/manifest.json')
        parsed={}
        while True:
            files=list((REPORTS/'milestone4_policy_raw').glob('*__*.json'))
            # CREATE_NEW raw writes may be visible before their final byte. Parse only complete records,
            # then cache immutable records; the independent summary fully validates every final outcome.
            count=0;failures=fallback=violations=0
            for path in files:
                if path not in parsed:
                    try: parsed[path]=load(path)
                    except (json.JSONDecodeError,UnicodeDecodeError): continue
                value=parsed[path]
                if value.get('selectionManifestSha256')!=selection:continue
                count+=1;summary=value['run']['finalSummary']
                failures+=summary.get('failedInferenceRequests',0);fallback+=summary.get('fallbackDecisions',0)
                violations+=value['run']['metrics']['constraintViolations']
            record['progress']={'completedPolicyRows':count,'requiredPolicyRows':440,'failedInferenceRequests':failures,'fallbackDecisions':fallback,'hardConstraintViolations':violations};persist()
            print(json.dumps(record['progress']),flush=True)
            active=subprocess.run(['docker','ps','--filter','name=cascadeshield-m4-policies-','--format','{{.Names}}'],capture_output=True,text=True,check=True).stdout.strip()
            if count==440 and not active:break
            if not active:raise RuntimeError('Policy container stopped before all 440 rows completed; resume through the frozen policy launcher')
            time.sleep(45)
        run('independent_complete_policy_summary',[sys.executable,'scripts/summarize_milestone4_policies.py'])
        if not (REPORTS/'milestone4_policy_replay.json').exists():
            command=['docker','run','--rm','--memory','2g','--cpus','4','--mount',f'type=bind,source={ROOT},target=/workspace',
                     '--mount','type=volume,source=cascadeshield_maven_cache,target=/root/.m2','-w','/workspace/simulator/backend',
                     'maven:3.9-eclipse-temurin-21','sh','-c',
                     'java -Xmx1024m -cp "$(cat target/ml-classpath.txt)" /workspace/scripts/VerifyMilestone4Replay.java /workspace /workspace/reports/milestone4_policy_replay.json']
            run('four_real_policy_determinism_reruns',command)
        run('ml_and_audit_unit_checks',[str(ROOT/'.venv-ml/Scripts/python.exe'),'scripts/check_milestone4_ml_tests.py'])
        run('research_figures',[sys.executable,'scripts/plot_milestone4_results.py'])
        run('assemble_final_report',[sys.executable,'scripts/report_milestone4.py'])
        run('cross_artifact_completion_validation',[sys.executable,'scripts/validate_milestone4_completion.py'])
        inventory()
        record.update(status='COMPLETED',endedAtUtc=datetime.now(timezone.utc).isoformat());persist()
        print('MILESTONE4_FINALIZATION_COMPLETED',flush=True)
    except BaseException as error:
        record.update(status='FAILED',error=repr(error),endedAtUtc=datetime.now(timezone.utc).isoformat());persist();raise


if __name__=='__main__':main()
