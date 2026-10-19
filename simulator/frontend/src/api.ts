import type {State,Network,Roads,Assignment,Route,Scenario,Option,Health} from './types';
import type {Operations,OperationalGraph,CascadeView,ResourceKind,ResourceSpec,OperationalAssignmentSpec} from './operations';
export async function request<T>(path:string, body?:unknown, method = body === undefined ? 'GET' : 'POST'):Promise<T> {
  const response = await fetch(`/api${path}`, {method,headers:body === undefined ? undefined : {'Content-Type':'application/json'},body:body === undefined ? undefined : JSON.stringify(body)});
  const content = await response.text();
  let data:unknown;
  try {data=content ? JSON.parse(content) : null;} catch {throw new Error(`Backend returned an invalid response (${response.status}). Check that the simulator service is running.`);}
  if(!response.ok) throw new Error((data as {error?:string})?.error || `Request failed (${response.status}).`);
  return data as T;
}
export const api = {
  state:()=>request<State>('/state'),health:()=>request<Health>('/health'),network:()=>request<Network>('/network'),roads:()=>request<Roads>('/network/roads'),
  addTruck:(body:Assignment)=>request<State>('/trucks',body),
  editTruck:(body:Assignment)=>request<State>(`/trucks/${encodeURIComponent(body.id)}`,body,'PUT'),
  deleteTruck:(id:string)=>request<State>(`/trucks/${encodeURIComponent(id)}`,undefined,'DELETE'),
  preview:(body:Pick<Assignment,'start'|'destination'|'waypoints'|'maxSpeedKph'>)=>request<Route>('/routes/preview',body),
  control:(action:string, extra:Record<string,number>={})=>request<State>('/control',{action,...extra}),
  incident:(body:unknown)=>request<State>('/incidents',body),resolve:(id:string)=>request<State>(`/incidents/${encodeURIComponent(id)}`,undefined,'DELETE'),
  decision:(truckId:string,recommendationId:string,action:Option['action'])=>request<State>('/decisions',{truckId,recommendationId,action}),
  scenarios:()=>request<Scenario[]>('/scenarios'),save:(name:string)=>request<Scenario>('/scenarios',{name}),
  replay:(id:string)=>request<State>(`/scenarios/${encodeURIComponent(id)}/replay`,{}),
  operations:()=>request<Operations>('/operations'),
  operationalGraph:()=>request<OperationalGraph>('/operations/graph'),
  cascade:()=>request<CascadeView>('/operations/cascade'),
  addResource:(kind:ResourceKind,spec:ResourceSpec)=>request<State>(`/operations/${kind}`,spec),
  editResource:(kind:ResourceKind,spec:ResourceSpec)=>request<State>(`/operations/${kind}/${encodeURIComponent(spec.id)}`,spec,'PUT'),
  deleteResource:(kind:ResourceKind,id:string)=>request<State>(`/operations/${kind}/${encodeURIComponent(id)}`,undefined,'DELETE'),
  assignResources:(spec:OperationalAssignmentSpec)=>request<State>('/operations/assignments',spec),
  unassignResources:(truckId:string)=>request<State>(`/operations/assignments/${encodeURIComponent(truckId)}`,undefined,'DELETE'),
  driverAvailability:(id:string,available:boolean)=>request<State>(`/operations/drivers/${encodeURIComponent(id)}/availability`,{available},'PATCH'),
};
