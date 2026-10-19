import {useState} from 'react';
import {mlApi,canReviewAdvice} from './ml';
import type {MlAdvice,MlApproval,MlModelId} from './ml';
import type {State} from './types';

export default function MlAdvicePanel({state,connected,onChanged}:{state:State;connected:boolean;onChanged:()=>Promise<void>}){
  const [truck,setTruck]=useState(''),[model,setModel]=useState<MlModelId>('xgb-v1');
  const [advice,setAdvice]=useState<MlAdvice|null>(null),[approval,setApproval]=useState<MlApproval|null>(null);
  const [operator,setOperator]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const selectedTruck=state.trucks.some(t=>t.id===truck)?truck:state.trucks[0]?.id || '';
  const reviewable=canReviewAdvice(advice,state) && advice?.requestedModelId===model && advice?.selected?.truckId===selectedTruck;
  async function perform(action:()=>Promise<void>){setBusy(true);setError('');setNotice('');try{await action();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  function clear(){setAdvice(null);setApproval(null);setError('');setNotice('');}
  return <section className="ml-panel" aria-label="ML-assisted operator review">
    <div className="ml-heading"><div><span><h2>ML-assisted operator review</h2><small>Rank a copied state, review a candidate, then approve and execute separately</small></span></div></div>
    <p className="ml-method">This assistant ranks the existing Continue, Wait and Reroute actions. The isolated five-action B5 research comparison is separate. Model output cannot authorize an intervention. The backend checks the exact paused state again at every approval step.</p>
    <div className="ml-controls">
      <label>Truck<select aria-label="ML advice truck" value={selectedTruck} onChange={e=>{setTruck(e.target.value);clear();}}>{state.trucks.map(t=><option key={t.id} value={t.id}>{t.id}</option>)}</select></label>
      <label>Advisor<select aria-label="ML advisor source" value={model} onChange={e=>{setModel(e.target.value as MlModelId);clear();}}><option value="rule-v1">Rule baseline</option><option value="xgb-v1">XGBoost</option><option value="xgb-no-graph-v1">XGBoost without graph summaries</option><option value="gnn-static-v1">Static GNN</option><option value="gnn-temporal-v1">Temporal GNN (current graph)</option></select></label>
      <button className="button secondary" disabled={!connected || busy || !selectedTruck} onClick={()=>perform(async()=>{setApproval(null);setAdvice(await mlApi.advice(selectedTruck,model));})}>{busy?'Working…':'Compare operator actions'}</button>
    </div>
    {error && <p className="ml-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {advice && <><p className="ml-method">{advice.source.replaceAll('_',' ')}{advice.fallbackUsed?' · deterministic fallback':''} · snapshot +{advice.clockSec.toFixed(1)} s · {advice.latencyMs.toFixed(1)} ms. {advice.selected?`Suggested action: ${advice.selected.action}.`:'No incident-response candidate is available.'}</p>
      {!!advice.alternatives.length && <div className="ml-scroll"><table aria-label="Operator action comparison"><thead><tr><th>Action</th><th>Fixed score (lower is better)</th><th>Backend constraints</th><th>Prediction source</th></tr></thead><tbody>{advice.alternatives.map(o=><tr key={o.candidate.id}><th>{o.candidate.action}{o.candidate.id===advice.selected?.id?' · selected':''}</th><td>{o.score.toFixed(4)}</td><td>{o.validation.valid?'Feasible':'Rejected'}</td><td>{o.prediction?`${o.prediction.modelId} / ${o.prediction.modelVersion}`:'Rule score'}</td></tr>)}</tbody></table></div>}
      <div className="ml-method" role="note">{advice.warnings.map(warning=><p key={warning}>{warning}</p>)}</div>
      <details className="ml-details"><summary>Advice limitations, model outputs and candidate fingerprint</summary><pre>{JSON.stringify(advice,null,2)}</pre></details>
      {advice.selected && <div className="ml-controls">
        {!reviewable && <p className="ml-method">Pause and refresh the comparison after any state change. Replays and completed runs cannot accept operator approvals.</p>}
        <button className="button secondary" disabled={!connected || busy || !reviewable || !!approval} onClick={()=>perform(async()=>{setApproval(await mlApi.requestApproval(advice.selected!));})}>Request review for {advice.selected.action}</button>
        <label>Operator identifier<input aria-label="ML approval operator" value={operator} maxLength={100} onChange={e=>setOperator(e.target.value)} placeholder="Your local operator ID"/></label>
        <button className="button secondary" disabled={!connected || busy || !reviewable || approval?.status!=='REQUESTED' || !operator.trim()} onClick={()=>perform(async()=>{setApproval(await mlApi.approve(approval!.id,operator.trim()));})}>Explicitly approve reviewed action</button>
        <button className="button primary" disabled={!connected || busy || !reviewable || approval?.status!=='APPROVED'} onClick={()=>perform(async()=>{await mlApi.execute(approval!.id);setApproval(null);setAdvice(null);await onChanged();setNotice('The backend transaction executed the approved action. Refresh the comparison before another intervention.');})}>Execute approved action</button>
      </div>}
    </>}
  </section>;
}
