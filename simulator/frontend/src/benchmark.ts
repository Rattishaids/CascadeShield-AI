import {request} from './api';
import type {CascadeView,OperationalGraph} from './operations';

export type ComparisonMode='FULL'|'EQUAL_ACTIONS';
export interface BenchmarkParameters {
  profile:string;seeds:number[];truckCount:number;warehouseCount:number;docksPerWarehouse:number;
  serviceSec:number;deadlineSlackSec:number;departureGapSec:number;driverUnavailableFraction:number;
  driverRestoreSec:number;closureCount:number;rainSlowdownCount:number;severity:number;
  incidentDurationSec:number;incidentStartSec:number;simultaneousIncidents:boolean;horizonSec:number;contention:number;
  decisionIntervalSec:number;rolloutHorizonSec:number;maxDecisions:number;
}
export interface BenchmarkRequest {parameters:BenchmarkParameters;policies:string[];comparisonMode:ComparisonMode;ablations:string[]}
export interface BenchmarkPolicy {id:string;name:string;allowedActions:string[];temporalDependencies:boolean;adaptiveThreshold:boolean;counterfactualEvaluation:boolean;description?:string}
export interface BenchmarkPreset {id:string;name?:string;description?:string;parameters?:Partial<BenchmarkParameters>}
export interface BenchmarkCatalog {schemaVersion?:string;presets:BenchmarkPreset[];policies:BenchmarkPolicy[];equalActionPolicies?:BenchmarkPolicy[];ablations:{id:string;name?:string;description?:string}[];parameterSchema?:Record<string,unknown>;provenance?:string;limitations?:string[];unsupportedActions?:string[]}
export interface BenchmarkAction {id:string;type:string;truckId:string|null;waitSec:number;dockId:string|null;reservationStartSec:number;reservationEndSec:number;routeEdgeIds:string[];description:string}
export interface BenchmarkViolation {code:string;message:string;resourceIds:string[];hard:boolean}
export interface BenchmarkMetrics {
  deliveryCount:number;completedDeliveries:number;unfinishedDeliveries:number;slaViolations:number;slaViolationRate:number;
  totalDeliveryLatenessSec:number;downstreamAffectedResources:number;totalReroutes:number;travelDistanceM:number;
  signedAdditionalDistanceM:number;positiveAdditionalDistanceM:number;modeledOperationalCost:number;
  recoveryTimeSec:number;recoveryCensored:boolean;finalClockSec:number;constraintViolations:number;decisionComputationMs:number;provenance:string;
}
export interface BenchmarkAlternative {action:BenchmarkAction;feasible:boolean;score:number;metrics:BenchmarkMetrics|null;violations:BenchmarkViolation[]}
export interface BenchmarkDecision {clockSec:number;truckId:string;trigger:string;observedIncidentIds:string[];alternatives:BenchmarkAlternative[];selectedActionId:string;explanation:string;computationMs:number;knowledgeFingerprint:string}
export interface BenchmarkRun {scenarioId:string;seed:number;policyId:string;inputFingerprint:string;metrics:BenchmarkMetrics;decisions:BenchmarkDecision[];finalSummary:Record<string,unknown>;provenance:string}
export interface BenchmarkResult {schemaVersion:string;scenarios:{id:string;name:string;seed:number;profile:string;inputFingerprint:string;horizonSec:number;parameters:Record<string,unknown>;provenance:string}[];runs:BenchmarkRun[];summary:Record<string,unknown>;provenance:string}
export interface BenchmarkJob {id:string;status:string;completedRuns?:number;totalRuns?:number;progress?:number;result?:BenchmarkResult|null;error?:string|null;createdAt?:string}
export const defaultParameters:BenchmarkParameters={profile:'closure-contention',seeds:[1,2,3],truckCount:4,warehouseCount:1,docksPerWarehouse:1,serviceSec:180,deadlineSlackSec:30,departureGapSec:90,driverUnavailableFraction:0,driverRestoreSec:300,closureCount:1,rainSlowdownCount:0,severity:1,incidentDurationSec:240,incidentStartSec:10,simultaneousIncidents:true,horizonSec:2400,contention:1,decisionIntervalSec:30,rolloutHorizonSec:1800,maxDecisions:12};
export const benchmarkApi={
  catalog:()=>request<BenchmarkCatalog>('/benchmarks/catalog'),
  create:(body:BenchmarkRequest)=>request<BenchmarkJob>('/benchmarks/runs',body),
  job:(id:string)=>request<BenchmarkJob>(`/benchmarks/runs/${encodeURIComponent(id)}`),
  jobs:()=>request<BenchmarkJob[]>('/benchmarks/runs'),
};
export function benchmarkExportUrl(id:string,format:'csv'|'json'){return `/api/benchmarks/runs/${encodeURIComponent(id)}/export?format=${format}`;}
export function parseSeeds(value:string):number[]{
  if(!/^\s*\d+(?:\s*,\s*\d+)*\s*$/.test(value))throw new Error('Seeds must be comma-separated nonnegative integers.');
  const seeds=value.split(',').map(v=>Number(v.trim()));
  if(seeds.some(s=>!Number.isSafeInteger(s)))throw new Error('Each seed must be a safe integer.');
  if(seeds.some(s=>s>2147483647))throw new Error('Each seed must be between 0 and 2147483647.');
  if(seeds.length>8)throw new Error('Use at most 8 seeds per job.');
  if(new Set(seeds).size!==seeds.length)throw new Error('Use distinct seeds so repeated cases are not counted as independent observations.');
  return seeds;
}
export function jobFinished(status:string){return ['COMPLETED','FAILED','CANCELLED','INTERRUPTED'].includes(status);}
export function outcomeValue(value:number|undefined,decimals=1){return typeof value==='number' && Number.isFinite(value) ? value.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:decimals}) : 'Unavailable';}
export function recoveryLabel(metrics:BenchmarkMetrics){return `${metrics.recoveryCensored ? 'Unrecovered after ' : ''}${outcomeValue(metrics.recoveryTimeSec)} s${metrics.recoveryCensored ? ' (censored)' : ''}`;}
export function sampleSummary(values:number[]){
  const observed=values.filter(Number.isFinite),n=observed.length;
  if(!n)return {n:0,mean:null,sd:null};
  const mean=observed.reduce((sum,v)=>sum+v,0)/n;
  return {n,mean,sd:n>1 ? Math.sqrt(observed.reduce((sum,v)=>sum+(v-mean)**2,0)/(n-1)) : null};
}
export function policySummaries(runs:BenchmarkRun[]){
  const ids=[...new Set(runs.map(r=>r.policyId))].sort();
  return ids.map(id=>{const group=runs.filter(r=>r.policyId===id);return {id,n:group.length,sla:sampleSummary(group.map(r=>r.metrics.slaViolationRate)),cost:sampleSummary(group.map(r=>r.metrics.modeledOperationalCost)),lateness:sampleSummary(group.map(r=>r.metrics.totalDeliveryLatenessSec)),unfinished:group.reduce((sum,r)=>sum+r.metrics.unfinishedDeliveries,0)};});
}
export function graphFromSummary(run:BenchmarkRun,phase:'before'|'after'):{graph:OperationalGraph;cascade:CascadeView|null}|null {
  const graph=run.finalSummary[`${phase}Graph`] as OperationalGraph|undefined,cascade=run.finalSummary[`${phase}Cascade`] as CascadeView|undefined;
  return graph && Array.isArray(graph.nodes) && Array.isArray(graph.edges) ? {graph,cascade:cascade && Array.isArray(cascade.nodeRisks) ? cascade : null} : null;
}
export function graphPhaseLabel(run:BenchmarkRun,phase:'before'|'after'){
  return phase==='after' ? 'After: final outcome' : run.finalSummary.beforeGraphPhase==='FIRST_OBSERVED_DISRUPTION' ? 'Before: observed disruption' : 'Before: initial state';
}
export function scenarioInputsMatch(runs:BenchmarkRun[]){
  const fingerprints=new Map<string,string>();
  for(const run of runs){const known=fingerprints.get(run.scenarioId);if(known!==undefined && known!==run.inputFingerprint)return false;fingerprints.set(run.scenarioId,run.inputFingerprint);}
  return true;
}
export function parameterBounds(catalog:BenchmarkCatalog|null,key:string,fallback:{min:number;max:number}){
  const provided=catalog?.parameterSchema?.[key] as {min?:unknown;max?:unknown}|undefined;
  return {min:typeof provided?.min==='number' && Number.isFinite(provided.min) ? provided.min : fallback.min,max:typeof provided?.max==='number' && Number.isFinite(provided.max) ? provided.max : fallback.max};
}
