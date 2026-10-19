"""Render standalone research figures from completed results without refitting models."""
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'reports'
MODELS=('xgb-v1','xgb-no-graph-v1','gnn-static-v1','gnn-temporal-v1')
LABELS=('XGBoost','XGBoost without\ngraph summaries','Static GNN','Temporal GNN')


def main():
    source=REPORTS/'MILESTONE_4_PREDICTION_METRICS.json'
    prediction=json.loads(source.read_text(encoding='utf-8'))
    policy_source=REPORTS/'MILESTONE_4_POLICY_BENCHMARK.json'
    policy=json.loads(policy_source.read_text(encoding='utf-8'))
    if not policy.get('pairedExecutionComplete'):raise ValueError('Complete paired policy evidence is required')
    out=REPORTS/'figures';out.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    metrics={(r['modelId'],r['target']):r for r in prediction['metrics'] if r['group']=='ALL'}
    figure,axes=plt.subplots(1,3,figsize=(12,4.6),layout='constrained')
    for axis,target,key,title in zip(axes,('remainingArrivalSec','deliveryLate','futureImpact'),('mae','brier','brier'),
                                   ('Remaining road arrival: MAE (s)','Delivery lateness: Brier score','New impact in 300 s: Brier score')):
        values=[metrics[mid,target][key] for mid in MODELS]
        bars=axis.bar(range(4),values,color=('#236d9f','#80abc6','#d58a39','#8b65a5'))
        axis.bar_label(bars,labels=[f'{x:.2f}' if key=='mae' else f'{x:.4f}' for x in values],padding=3,fontsize=9)
        axis.set_xticks(range(4),LABELS,rotation=25,ha='right');axis.set_title(title,fontsize=11)
        axis.set_ylim(0,max(values)*1.2);axis.grid(axis='y',alpha=.15);axis.set_axisbelow(True)
        axis.set_xlabel(f"Identical {metrics[MODELS[0],target]['n']:,} eligible truck snapshots; lower is better")
    figure.suptitle('Frozen final prediction assessment: 40 simulated scenarios, 4 seed clusters',fontsize=13)
    for extension in ('png','svg','pdf'):figure.savefig(out/f'milestone4-predictions.{extension}',dpi=180)
    plt.close(figure)
    policies=policy['policies'];ids=list(policies)
    figure,axes=plt.subplots(1,2,figsize=(13,5.8),layout='constrained')
    for axis,key,title,scale in ((axes[0],'slaViolationRate','Mean delivery SLA violation rate (%)',100),
                                (axes[1],'decisionComputationMs','Mean decision computation per policy run (s)',.001)):
        values=[policies[mid]['meansPerRun'][key]*scale for mid in ids]
        axis.barh(ids,values,color=['#236d9f' if mid.startswith('B5') else '#a1acb4' for mid in ids])
        axis.invert_yaxis();axis.set_title(title);axis.set_xlim(0,max(values)*1.22 if max(values)>0 else 1)
        for i,value in enumerate(values):axis.text(value,i,f' {value:.2f}',va='center',fontsize=9)
        axis.grid(axis='x',alpha=.15);axis.set_axisbelow(True)
    figure.suptitle('40 paired cases per policy on real Chennai geography + simulated operations',fontsize=13)
    figure.supxlabel('Equal maximum road-action repertoire and decision/rollout bounds; actual compute differs. Descriptive means; four independent seeds.')
    for extension in ('png','svg','pdf'):figure.savefig(out/f'milestone4-policies.{extension}',dpi=180)
    plt.close(figure)
    provenance={'schemaVersion':'cascadeshield.research-figures/1.0','provenance':'PLOTS_OF_EXECUTED_SIMULATED_EXPERIMENTS',
                'sourceSha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,policy_source)},
                'files':[str(p.relative_to(ROOT)).replace('\\','/') for p in sorted(out.glob('milestone4-*'))],
                'limitations':['Correlated snapshots do not equal independent trials.','Policy means summarize 40 cases grouped in four seeds; see JSON paired intervals.','No observed freight or field-effectiveness result.']}
    (REPORTS/'milestone4_figure_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'figures':len(provenance['files'])}))


if __name__=='__main__':main()
