"""Assemble the final Milestone 4 report from complete measured evidence; never fits a model."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'reports'
IDS=('xgb-v1','xgb-no-graph-v1','gnn-static-v1','gnn-temporal-v1')


def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
def number(value):return f'{value:,.3f}'


def main():
    model=read('models/milestone4/v1/manifest.json')
    prediction=read('reports/MILESTONE_4_PREDICTION_METRICS.json')
    policies=read('reports/MILESTONE_4_POLICY_BENCHMARK.json')
    if not policies.get('pairedExecutionComplete') or policies['runCount']!=440 or policies['caseCount']!=40:
        raise ValueError('The final report requires all 440 declared policy outcomes, not partial successes')
    expected=sha('models/milestone4/v1/manifest.json')
    if prediction['modelManifestSha256']!=expected or policies['selectionManifestSha256']!=expected:
        raise ValueError('Prediction/policy evidence does not share the exact frozen model bundle')
    metrics={(m['modelId'],m['target']):m for m in prediction['metrics'] if m['group']=='ALL'}
    policy=policies['policies']
    contrasts=policies['pairedContrasts']
    tests={name:read('reports/'+name) for name in ('milestone4_java_tests.json','milestone4_frontend_tests.json',
        'milestone4_legacy_python_tests.json','milestone4_browser_tests.json','milestone4_ml_integration.json',
        'milestone4_ml_outage.json','milestone4_ml_recovery.json','milestone4_restart_tests.json',
        'milestone4_ml_unit_tests.json','milestone4_policy_replay.json')}
    java=tests['milestone4_java_tests.json'];frontend=tests['milestone4_frontend_tests.json']
    if (not model.get('frozen') or prediction['split']!='final' or prediction['dataset']['scenarioCount']!=40
        or any(v.get('passed') is not True for k,v in tests.items() if k not in ('milestone4_java_tests.json','milestone4_frontend_tests.json'))
        or any(java[k] for k in ('failures','errors','skipped')) or frontend['numFailedTests']
        or not read('reports/milestone4_final_preservation.json')['passed']
        or not read('reports/milestone4_final_frozen_byte_audit.json')['passed']
        or not read('reports/milestone4_leakage_audit.json')['modelFittingAuthorized']):
        raise ValueError('Final publication requires passing integration, preservation, frozen-source, unit and replay evidence')
    known=next(m for m in prediction['metrics'] if m['modelId']=='xgb-v1' and m['target']=='remainingArrivalSec' and m['group']=='MATCHED_BASELINE:rule_known_operational_eta_only')
    known_ci=known['pairedLossUncertainty']
    hard=sum(p['totals']['constraintViolations'] for p in policy.values())
    fallback=sum(p['totals']['fallbackDecisions'] for p in policy.values())
    failures=sum(p['totals']['failedInferenceRequests'] for p in policy.values())
    unfinished=sum(p['totals']['unfinishedDeliveries'] for p in policy.values())
    offline={mid:{target:metrics[mid,target] for target in ('remainingArrivalSec','deliveryLate','futureImpact')} for mid in IDS}
    limitation=[
        'No observed Chennai freight labels, field intervention outcomes or calibrated freight speed/dock/driver/disruption distributions exist.',
        'Final evaluation is held-out fleet-size transfer on the same bounded Chennai network and three OD pairs; only four independent final seed clusters.',
        'Repeated snapshots are correlated; reported bootstrap intervals are descriptive and uncorrected for multiple comparisons.',
        'GNN receives additional typed-resource attributes; comparison with XGBoost is not architecture-only. No-graph XGBoost removes only three explicit graph summaries.',
        'Models learned untreated scenario trajectories; intervened candidate states may be out of distribution. Learned scores do not identify causal action effects.',
        'Temporal policy cadence differs from irregular training snapshots. Live operator advice uses a current graph and a separate three-action repertoire.',
        'Isolated policy experiments automatically execute feasible scripted interventions. Human review delay and operator acceptance are not modeled; live actions require explicit approval.',
        'Observed transport failures and complete-decision fallback remain in the main results. Unequal failure counts mean some component contrasts are as-executed system comparisons, not pure prediction-only effects.',
        'ETA residual intervals under-cover the final fleet-size domain; nominal 90% is not a guaranteed field or independent-scenario coverage claim.',
        'Timing measurements came from a shared workstation. Java heap-pool peaks exclude Python/GPU/native memory and are not simultaneous RSS.',
        'Policy order is fixed and sequential in one JVM; JIT warm-up and retained earlier outcomes can affect timing. Runtime comparisons are descriptive, not isolated hardware benchmarks.',
        'PyTorch CUDA memory peaks describe the development graph probes; a continuous peak-VRAM trace for main XGBoost fitting was not collected.',
        'OR-Tools was unavailable and a matched scheduling baseline was not attempted; B1 is not a proxy for every modern logistics platform.',
        'No combined model, RL, autonomous LLM policy, blockchain or Milestone 5 was developed.'
    ]
    evidence=['models/milestone4/v1/manifest.json','reports/MILESTONE_4_PREDICTION_METRICS.json',
        'reports/MILESTONE_4_PREDICTION_METRICS.csv','reports/MILESTONE_4_POLICY_BENCHMARK.json',
        'reports/MILESTONE_4_POLICY_BENCHMARK.csv','reports/milestone4_leakage_audit.json',
        'reports/milestone4_compute_comparison.json','reports/milestone4_final_preservation.json',
        'reports/milestone4_final_frozen_byte_audit.json','reports/milestone4_independent_results_audit.json',
        'reports/milestone4_trained_prediction_diagnostics.json',
        'reports/milestone4_resume_integration_20261019.json',
        'reports/milestone4_resume_preservation_20261019.json',
        'reports/milestone4_resume_state_comparison_20261019.json',
        'reports/milestone4_resume_verified_app_health_20261019.json',
        'reports/milestone4_pretraining_execution_events.json']
    xgb_vs_rule=contrasts['B5_XGB_V1 minus B5_RULE_V1']['slaViolationRate']
    xgb_vs_b3=contrasts['B5_XGB_V1 minus B3']['slaViolationRate']
    cf_vs_direct=contrasts['B5_XGB_CF_V1 minus B5_XGB_V1']['slaViolationRate']
    b3_sla=policy['B3']['meansPerRun']['slaViolationRate']
    any_ml_better=any(v['meansPerRun']['slaViolationRate']<b3_sla-1e-12 for mid,v in policy.items() if mid.startswith('B5_') and mid!='B5_RULE_V1')
    operational_finding=('No learned variant reduced mean SLA violations below B3 in this fixed final comparison.' if not any_ml_better
                         else 'Consult all paired contrasts; mean improvements alone do not establish reproducible or field superiority.')
    report={'schemaVersion':'cascadeshield.milestone4-results/1.0','completedAtUtc':datetime.now(timezone.utc).isoformat(),
        'status':'EXECUTED_RESEARCH_EVALUATION_COMPLETE' if hard==0 else 'PARTIAL_RELIABILITY_FAILURE',
        'provenance':'REAL_GEOGRAPHIC_DATA_PLUS_SIMULATED_OPERATIONS_AND_OUTCOMES',
        'trainedOnObservedFreight':False,'modelManifestSha256':expected,'modelVersion':model['modelVersion'],
        'developmentDataset':model['dataset'],'finalDataset':prediction['dataset'],
        'models':offline,'modelSelection':{mid:{k:v for k,v in model['models'][mid].items() if k in ('selectedEpoch','trainingSec','trainingDevice','historyFrames','hidden','cpuReloadMaximumAbsoluteDifference','peakProcessRssBytes','selection')} for mid in IDS},
        'trainingSec':model['totalTrainingSec'],'trainingHardware':model['trainingHardware'],
        'inferenceLatencyMs':prediction['inferenceLatencyMs'],'etaIntervals':prediction['etaIntervals'],
        'policyRunCount':policies['runCount'],'caseCount':40,'independentFinalSeedClusters':4,
        'policies':policy,'pairedContrasts':contrasts,'hardConstraintViolations':hard,
        'failedInferenceRequests':failures,'fallbackDecisions':fallback,'unfinishedDeliveryPolicyOutcomes':unfinished,
        'sameAlgorithmXgbMinusRuleSla':xgb_vs_rule,'fieldEffectivenessClaimed':False,
        'primarySuccessCriterionMet':False if not any_ml_better else None,
        'primaryOperationalFinding':operational_finding,
        'isolatedCounterfactualSlaGainObserved':cf_vs_direct['difference']<0,
        'tests':{name:{k:v for k,v in result.items() if k in ('passed','tests','failures','errors','skipped','passedChecks','passed_checks','numPassedTests','numFailedTests','numTotalTests')} for name,result in tests.items()},
        'limitations':limitation,'evidenceSha256':{path:sha(path) for path in evidence},
        'readinessForMilestone5':'Research integration available; field deployment and general superiority remain unvalidated. Milestone 5 not started.'}
    (R/'MILESTONE_4_RESULTS.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    lines=['# Milestone 4: executed ML and decision-impact results','',
        'Completed on 2026-10-19. All model fitting and final prediction assessment were executed before the interrupted session resumed. The remaining paired policy assessment was then executed from unchanged frozen artifacts. This report distinguishes implemented behavior from actual measurements; no field logistics result is claimed.','',
        f"**The primary prevention-success criterion was not met.** {operational_finding} B5-XGB mean SLA failures were {policy['B5_XGB_V1']['meansPerRun']['slaViolationRate']*100:.3f}% versus B3 {b3_sla*100:.3f}%; the paired difference was {xgb_vs_b3['difference']*100:+.3f} percentage points, descriptive 95% interval [{xgb_vs_b3['interval'][0]*100:+.3f}, {xgb_vs_b3['interval'][1]*100:+.3f}]. XGBoost tied B4 and its same-algorithm rule control on SLA, while its mean lateness was higher. Offline prediction gains therefore did not establish better prevention in this assessment.",'',
        '## Data and split integrity','',
        'The 18 historical tables retain 2,414,128 rows. They do not supply linked Chennai freight supervision. The ML corpus uses the authoritative simulator on the immutable real Chennai OSM network. All 86 initially recorded historical files remain byte-identical. GB, Brazil, Cambridge and other source cohorts remain separate; restricted Porto/NYC data were not used.','',
        '| Split | Scenarios | Seed groups | Truck snapshots | Actual fleet sizes |',
        '| --- | ---: | ---: | ---: | --- |',
        '| Training | 64 | 8 | 3,500 | 4 / 8 |',
        '| Validation | 24 | 3 | 1,584 | 5 / 9 |',
        '| Calibration | 24 | 3 | 1,824 | 6 / 10 |',
        '| Final | 40 | 4 | 3,837 | 7 / 11 / 12 |','',
        'Training targets use 3,055 valid remaining-road-arrival examples, 3,350 delivery-SLA examples and 3,500 future-impact examples. Final targets use 3,295 / 3,604 / 3,837 respectively. All 112 development and 40 final scenarios completed. Later truck arrival, dock delivery completion and new adverse-event onset are separate targets; unresolved labels remain masked. The 300-second resource-event target is associative and does not identify incident causation.','',
        'The first unused split proposal failed a near-duplicate audit. The revised input-only protocol separates actual fleet sizes, not administrative seed/noise fields. Exact, coarse, conservative and continuous-boundary checks passed for all 152 inputs; every development target, eligibility flag and censoring mask was independently reconstructed. Whole scenarios and related seed families stay together. Models, calibration and policy code were frozen before final outcomes were generated. Final seeds 4001-4004 are now exposed and cannot serve as fresh test data for later tuning.','',
        '## Algorithms, fitting and GPU execution','',
        'XGBoost fits separate ETA regression, SLA and future-impact classification heads, with two development-only tree configurations and separate probability/residual calibration. The no-graph variant removes the three explicit graph-summary features. Static GNN uses five actual node types, 24 hidden units, two directed relation-specific PyG message-passing layers and truck/resource heads. Temporal GNN adds per-type GRU history over at most three causal frames. No undocumented reverse edges, future schedule or rollout outcome is an ordinary inference input.','',
        f"Actual hardware: RTX 4050 Laptop, 6 GB VRAM, NVIDIA 610.74, PyTorch 2.7.1+cu118, PyG 2.7.0, XGBoost 3.1.3, Python 3.11.6, 16 GB RAM and 12 logical CPUs. Main fitting took **{model['totalTrainingSec']:.2f} s**. Six selected XGBoost heads were fitted on CUDA; all CPU reload checks passed. Static GNN selected epoch 20/24 ({model['models']['gnn-static-v1']['trainingSec']:.2f} s); temporal GNN stopped after 21 epochs and selected epoch 16 ({model['models']['gnn-temporal-v1']['trainingSec']:.2f} s). Both GNN CPU reload maximum differences were 0.0.",'',
        'Actual CPU/GPU probes showed this small workload was faster on CPU: static graph 407.6/912.7 ms, temporal 262.8/723.7 ms and XGBoost 68.4/296.5 ms (CPU/GPU). GNN main fits therefore used CPU; actual CUDA GNN probes and CUDA XGBoost fitting remain recorded. Bounded frames, gradient accumulation, early stopping, atomic checkpoints, reproducible seeds and memory records are implemented. Mixed precision was disabled for this small numerical workload. No driver/system CUDA replacement or cloud GPU service was used.','',
        '## Final prediction measurements','',
        '| Provider | ETA MAE / RMSE (s) | SLA Brier / F1 | Future-impact Brier / F1 | Mean CPU inference (ms/frame) |',
        '| --- | ---: | ---: | ---: | ---: |']
    for mid in IDS:
        a,b,c=(metrics[mid,t] for t in ('remainingArrivalSec','deliveryLate','futureImpact'))
        lines.append(f"| {mid} | {a['mae']:.3f} / {a['rmse']:.3f} | {b['brier']:.5f} / {b['f1']:.5f} | {c['brier']:.5f} / {c['f1']:.5f} | {prediction['inferenceLatencyMs'][mid]['mean']:.3f} |")
    lines+=['',
        f"XGBoost ETA improves on conditional rule ETA {metrics['rule_conditional_road_eta','remainingArrivalSec']['mae']:.3f} s on the same 3,295 rows. On the smaller known-operational-rule subset ({known['n']:,} rows), XGBoost {known['mae']:.3f} s versus rule {metrics['rule_known_operational_eta_only','remainingArrivalSec']['mae']:.3f} s gives a row-weighted difference {known['pairedLossDifference']:+.3f} s, descriptive seed-cluster 95% interval [{known_ci['lower']:+.3f}, {known_ci['upper']:+.3f}]: no clear gain there. Static GNN has lower SLA Brier than XGBoost, while both GNNs have worse ETA and future-impact error. Temporal improves static ETA but adds no isolated SLA improvement. The GNN also receives extra resource-node attributes, so this is not a pure architecture comparison.",'',
        'Nominal 90% ETA interval final coverages are XGBoost 80.52%, no-graph 80.00%, static GNN 80.06%, temporal GNN 77.51%. These intervals under-cover under fleet-size transfer. Full precision/recall, PR-AUC, ROC-AUC, confusion matrices, bias, class counts, calibration bins, per-family/severity measurements, matched-baseline comparisons and failure examples are in the prediction JSON/CSV. SLA positives 2834/3604 and impact positives 667/3837 make accuracy-only reporting inappropriate.','',
        'Separately selected [trained-provider failure examples](milestone4_trained_prediction_diagnostics.json) preserve each model/target\'s five largest errors, exact prediction-time inputs, rule baseline and later truth. Their feature importances describe fitted correlations, not causal effects. These are post-assessment diagnostics and were not used for retuning.','',
        '## Actual paired policy outcomes','',
        'All 11 declared policies ran on the identical 40 cases (440 runs), with the same five allowed road actions, maximum six decision slots and 1800-second candidate-rollout horizon. B0 deliberately takes no action. B0-B4 source is unchanged. B5 uses bounded current-knowledge candidate scoring; B5_RULE controls for the changed algorithm/objective. CF variants add executed hypothetical rollouts and consume more actual compute. Equal maximum bounds do not imply equal eligibility, realized decision counts or wall-clock budgets.','',
        '| Policy | Mean SLA failures (%) | Lateness (s/run) | Modeled cost/run | Decision compute (s/run) |',
        '| --- | ---: | ---: | ---: | ---: |']
    for mid,p in policy.items():
        v=p['meansPerRun'];lines.append(f"| {mid} | {100*v['slaViolationRate']:.3f} | {v['totalDeliveryLatenessSec']:.3f} | {v['modeledOperationalCost']:.3f} | {v['decisionComputationMs']/1000:.3f} |")
    lines+=['','Paired differences below use whole seed clusters; negative SLA differences favor the first policy. Only four clusters and no multiple-testing correction support descriptive inference.','',
        '| Paired contrast | SLA difference (percentage points) | Descriptive 95% interval |',
        '| --- | ---: | ---: |']
    for name,value in contrasts.items():
        v=value['slaViolationRate']
        mean=v['difference'];lower,upper=v['interval']
        lines.append(f'| {name} | {mean*100:.3f} | [{lower*100:.3f}, {upper*100:.3f}] |')
    lines+=['',
        f'Across all policy outcomes: **{hard} detected hard constraint violations**, **{unfinished} unfinished delivery outcomes**, **{failures} failed inference requests**, **{fallback} fallback decisions**. Constraint audits use 10-second observations alongside the movement and intervention guards; this count is not a formal proof of every intermediate state. Recovery censoring, pooled and mean SLA rates, absolute counts, per-family effects, reroutes, additional distance, modeled cost, rollouts, rejected candidates and heap-memory scope are retained in the complete policy JSON/CSV. Better offline prediction alone does not demonstrate prevention benefit; interpret B5 against B3/B4 and its same-algorithm B5_RULE control together.','',
        'All ten recorded inference failures were connection timeouts. Static GNN had two failed requests/two fallback decisions; temporal GNN one/one; counterfactual XGBoost three/three; no-graph XGBoost four/three. Direct XGBoost had none. These outcomes were retained without replacement, so unequal service failures limit pure model-component comparisons.','',
        f"Counterfactual planning shows no isolated SLA gain here: B5-XGB-CF minus direct B5-XGB is {cf_vs_direct['difference']*100:+.3f} percentage points. It adds {contrasts['B5_XGB_CF_V1 minus B5_XGB_V1']['totalDeliveryLatenessSec']['difference']:.3f} s mean lateness per run and takes {policy['B5_XGB_CF_V1']['meansPerRun']['decisionComputationMs']/1000:.3f} versus {policy['B5_XGB_V1']['meansPerRun']['decisionComputationMs']/1000:.3f} s decision computation per run. Static GNN's better offline SLA probability score did not beat XGBoost's mean policy SLA; temporal GNN had worse mean SLA outcomes than both. These conclusions concern these simulated cases, not a universal impossibility of ML or counterfactual benefit.",'',
        '## Counterfactual weakness and diagnostics','',
        'Historical M3 numbers and B0-B4 code were preserved. No original B4 baseline was retuned. Its broader action repertoire confounded full comparisons; equal-action B3/B4 previously tied. M3 traces show budget saturation, but no within-forecast SLA/lateness rank inversion. Twenty-one decisions per mode had unfinished driver-restoration forecasts whose private future restoration was unavailable to the planner.','',
        'The 16 predeclared development diagnostics cover four cases. Reference, doubled decision budget and longer 3600-second horizon each give five SLA misses and 1327.9 s total lateness; 900-second horizon gives 15 misses and 1941.0 s. Extra decision slots produced more decisions without a gain. These are development diagnostics, not final independent efficacy. Final B5_XGB_CF versus B5_XGB separates the declared CF component with matching available actions; the table and raw outcomes retain any negative result and extra compute.','',
        '## Integration, reliability and actual checks','',
        'Prediction latency above measures the CPU ModelBundle call per graph frame (411 frames per provider, containing multiple trucks); it excludes Java/HTTP transport. Separate service integration envelopes and policy measurements include end-to-end work.','',
        'The React dashboard labels rule/XGBoost/GNN predictions and simulated outcomes separately. CPU inference is read-only, validates versions/schema/graph/fingerprint/clock, and rejects invalid/future-bearing inputs. Actual outage and recovery checks passed. The operator advisor ranks copies, displays domain warnings, and uses separate request/explicit-approval/transactional-execution steps. Exact-state, paused/non-replay and one-use approval guards remain authoritative. Its three-action live interface is separate from the five-action research policy.','',
        'The isolated policy runner executes feasible interventions automatically for a controlled experiment. Human review delay and operator acceptance are not part of those simulated policy outcomes; the live application continues to require explicit operator approval. Main GNN process RSS peaks were approximately 970/980 MB; CUDA graph-probe allocated peaks were approximately 69 MB. A continuous main-XGBoost peak-VRAM trace was not collected.','',
        'Executed checks: 155 Java tests with real Chennai graph (zero failures/errors/skips); 59 frontend tests and production build; 33 legacy Python contracts; [39 ML/audit/experiment-wrapper unit tests](milestone4_ml_unit_tests.json); 8 browser checks; 13 model-service/Java integration checks; 1 outage and 13 recovery checks; 5 actual backend restart/persistence checks; [4 exact policy replays](milestone4_policy_replay.json). The separate [completion validation](milestone4_completion_validation.json) checks artifact consistency, not additional unit tests. Unit fixtures never enter training or research outcomes. The saved 13-truck completed run at 854.9 s was preserved during deployment, inference, browser and restart checks; [final application health](milestone4_final_app_health.json) confirms the running frontend, backend, database and four-model service.','',
        'The unused initial split was rejected before fitting. A stale audit gate attempt was rejected, and a binary-label dtype bug was caught by a development compute probe and corrected before main fitting. The final test launcher initially failed local module imports; its path setup was corrected and all 39 tests then passed. Failed attempts are preserved in the execution journals and are not counted as successful experiments. Frozen model/policy source and completed raw research outcomes were unchanged by the launcher correction.','',
        'On the final continuation, Docker and local services had stopped. Restart restored the same completed run, clock and fleet; [all 13 read-only inference checks passed again](milestone4_resume_integration_20261019.json), and [all 86 preserved files matched](milestone4_resume_preservation_20261019.json). The initial literal comparison with the old PowerShell state snapshot failed because 28 text fields had been decoded incorrectly in that snapshot. An explicit [strict encoding comparison](milestone4_resume_state_comparison_20261019.json) accounts for every difference; all numeric values, keys, lists and operational fields match. Neither the saved snapshot nor backend state was changed to make that comparison pass. [Current verified application health](milestone4_resume_verified_app_health_20261019.json) records all services UP with four frozen models.','',
        '## Reproduction, status and remaining limits','',
        'Use [the reproducibility guide](../docs/MILESTONE_4_REPRODUCE.md) for exact commands and environments; [the changed-file inventory](MILESTONE_4_CHANGED_FILES.md) lists reviewed source/artifact changes. The canonical project is `<research-workspace>`. Launch from that root: `powershell -ExecutionPolicy Bypass -File scripts/start_simulator.ps1 -WithML`; add `-UseMavenRelay` after Java changes. The current frozen assessment must not be reused as a new independent test after tuning.','',
        'Implemented and executed: source/label audit, leakage gates, XGBoost and static/temporal GNN fitting, calibration/reload, CPU inference/fallback, guarded UI integration, frozen prediction assessment and complete paired policy assessment. Field freight validation is blocked by missing linked operator data. OR-Tools and a combined model were not attempted. Milestone 5, RL, autonomous LLM agents and blockchain remain later work.','']
    lines += ['- '+item for item in limitation]
    lines += ['','Machine-readable evidence: [results](MILESTONE_4_RESULTS.json), [prediction metrics](MILESTONE_4_PREDICTION_METRICS.json), [policy benchmark](MILESTONE_4_POLICY_BENCHMARK.json), [independent result audit](milestone4_independent_results_audit.json), [model selection](milestone4_model_selection.json), [raw executions](milestone4_execution_log/). These are simulation-domain research results; field effectiveness and general superiority are not established.','']
    (R/'MILESTONE_4_RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'status':report['status'],'policyRuns':440,'models':len(IDS),'hardConstraintViolations':hard}))


if __name__=='__main__':main()
