import {request} from './api';

export type MlModelId='rule-v1'|'xgb-v1'|'xgb-no-graph-v1'|'gnn-static-v1'|'gnn-temporal-v1';
export interface LearnedTruckPrediction {truckId:string;remainingArrivalSec:number|null;etaLowerSec:number|null;etaUpperSec:number|null;slaProbability:number|null;futureImpactProbability:number|null}
export interface LearnedPrediction {schemaVersion:string;featureSchemaVersion:string;featureSchemaHash:string;networkId:string;graphSha256:string;modelId:string;modelVersion:string;source:string;stateFingerprint:string;clockSec:number;predictions:LearnedTruckPrediction[];calibration:Record<string,unknown>;latencyMs:number;warnings:string[];provenance:string}
export interface MlEnvelope {prediction:LearnedPrediction;requestedModelId:string;fallbackUsed:boolean;failureReason:string|null;endToEndLatencyMs:number;historicalFramesUsed:number;inputProvenance:string;stateMutated:false}
export interface MlStatus {schemaVersion:string;featureSchema:Record<string,unknown>;networkGraphSha256:string;registry:Record<string,unknown>;authority:string}
export interface MlCandidate {id:string;truckId:string;action:string;recommendationId:string;stateFingerprint:string;source:Record<string,unknown>}
export interface MlAdvice {schemaVersion:string;runId:string;requestedModelId:string;source:string;stateFingerprint:string;clockSec:number;alternatives:{candidate:MlCandidate;validation:{valid:boolean;violations:unknown[]};score:number;prediction:LearnedPrediction|null}[];selected:MlCandidate|null;fallbackUsed:boolean;warnings:string[];latencyMs:number;stateMutated:false}
export interface MlApproval {id:string;status:string;approvedBy:string|null;stateFingerprint:string}
export const mlApi={status:()=>request<MlStatus>('/ml/status'),predict:(modelId:MlModelId)=>request<MlEnvelope>('/ml/predict',{modelId}),
  advice:(truckId:string,modelId:MlModelId)=>request<MlAdvice>(`/ml/recommendations/${encodeURIComponent(truckId)}`,{modelId}),
  requestApproval:(candidate:MlCandidate)=>request<MlApproval>('/ai/approvals',candidate),
  approve:(id:string,approvedBy:string)=>request<MlApproval>(`/ai/approvals/${encodeURIComponent(id)}/approve`,{approvedBy}),
  execute:(id:string)=>request<unknown>(`/ai/approvals/${encodeURIComponent(id)}/execute`,{})};
export function canReviewAdvice(advice:MlAdvice|null,state:{runId?:string;clockSec:number;status:string;replaying:boolean}){return !!advice?.selected && advice.runId===state.runId && Math.abs(advice.clockSec-state.clockSec)<1e-8 && ['DRAFT','PAUSED'].includes(state.status) && !state.replaying;}
export function predictionProvider(value:MlEnvelope){return value.fallbackUsed ? 'Deterministic fallback' : value.prediction.source==='RULE_BASED' ? 'Rule-based prediction' : value.prediction.modelId.startsWith('gnn-') ? 'GNN prediction' : 'XGBoost prediction';}
export function probabilityLabel(value:number|null|undefined){return typeof value==='number' && Number.isFinite(value) && value>=0 && value<=1 ? `${(value*100).toFixed(1)}%` : 'Unavailable / not applicable';}
export function remainingLabel(value:number|null|undefined){return typeof value==='number' && Number.isFinite(value) && value>=0 ? `${value.toFixed(1)} s` : 'Already arrived / unavailable';}
export function intervalLabel(value:LearnedTruckPrediction){return value.etaLowerSec!==null && value.etaUpperSec!==null && Number.isFinite(value.etaLowerSec) && Number.isFinite(value.etaUpperSec) && value.etaLowerSec<=value.etaUpperSec ? `${value.etaLowerSec.toFixed(1)}–${value.etaUpperSec.toFixed(1)} s` : 'No calibrated interval';}
