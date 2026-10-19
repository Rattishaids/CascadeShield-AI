import type {Point,Truck} from './types';
import {duration} from './format';

export interface WarehouseSpec {id:string;name:string;location:Point;dockCapacity:number}
export interface DockSpec {id:string;name:string;warehouseId:string;serviceSec:number;openFromSec:number;openUntilSec:number}
export interface DriverSpec {id:string;name:string;available:boolean;shiftStartSec:number;shiftEndSec:number}
export interface DeliverySpec {id:string;name:string;warehouseId:string;loadKg:number;deadlineSec:number;priority:'NORMAL'|'HIGH'}
export interface OperationalAssignmentSpec {truckId:string;driverId:string;dockId:string;deliveryIds:string[];reservationStartSec:number;reservationEndSec:number}
export interface Warehouse extends WarehouseSpec {nodeId:number;provenance:string}
export interface Dock extends DockSpec {status:string;occupiedBy:string|null;provenance:string}
export interface Driver extends DriverSpec {status:string;dutySec:number;occupiedBy:string|null;provenance:string}
export interface Delivery extends DeliverySpec {status:string;truckId:string|null;deliveredAtSec:number;lateSec:number;provenance:string}
export interface OperationalAssignment extends OperationalAssignmentSpec {status:string;predictedDockStartSec:number;predictedDockEndSec:number;actualDockStartSec:number;actualDockEndSec:number;queueSec:number;provenance:string}
export interface GraphNode {id:string;type:string;resourceId:string;features:Record<string,unknown>;provenance:string}
export interface GraphEdge {id:string;source:string;target:string;type:string;validFromSec:number;validUntilSec:number;weight:number;features:Record<string,unknown>;provenance:string}
export interface OperationalGraph {schemaVersion:string;clockSec:number;networkId:string;nodes:GraphNode[];edges:GraphEdge[];provenance:string}
export interface NodeRisk {nodeId:string;score:number;direct:boolean;causeIds:string[]}
export interface CascadeView {provider:string;threshold:number;iterations:number;nodeRisks:NodeRisk[];affectedNodeIds:string[];affectedEdgeIds:string[];provenance:string}
export interface Impact {id:string;code:string;resourceIds:string[];truckIds:string[];startSec:number;endSec:number;delaySec:number;predicted:boolean;message:string;provenance:string}
export interface Operations {warehouses:Warehouse[];docks:Dock[];drivers:Driver[];deliveries:Delivery[];assignments:OperationalAssignment[];predictedImpacts:Impact[];realizedImpacts:Impact[];graph:OperationalGraph;cascade:CascadeView;kpis:{deliveries:number;delivered:number;lateDeliveries:number;queuedTrucks:number;unloadingTrucks:number;constrainedDrivers:number;deliveryDelaySec:number}}
export const emptyOperations:Operations={warehouses:[],docks:[],drivers:[],deliveries:[],assignments:[],predictedImpacts:[],realizedImpacts:[],graph:{schemaVersion:'cascadeshield.operational-graph/1.0',clockSec:0,networkId:'',nodes:[],edges:[],provenance:'SIMULATED'},cascade:{provider:'RULE_BASED_GRAPH_BASELINE',threshold:.35,iterations:0,nodeRisks:[],affectedNodeIds:[],affectedEdgeIds:[],provenance:'SIMULATED_PREDICTION'},kpis:{deliveries:0,delivered:0,lateDeliveries:0,queuedTrucks:0,unloadingTrucks:0,constrainedDrivers:0,deliveryDelaySec:0}};
export type ResourceKind='warehouses'|'docks'|'drivers'|'deliveries';
export type ResourceSpec=WarehouseSpec|DockSpec|DriverSpec|DeliverySpec;
export const resourceTitles:Record<ResourceKind,string>={warehouses:'Warehouses',docks:'Docks',drivers:'Drivers',deliveries:'Deliveries'};
export function deliveriesForDock(operations:Operations,dockId:string){const warehouse=operations.docks.find(d=>d.id===dockId)?.warehouseId;return operations.deliveries.filter(d=>d.warehouseId===warehouse);}
export function assignmentLoad(operations:Operations,ids:string[]){return operations.deliveries.filter(d=>ids.includes(d.id)).reduce((total,d)=>total+d.loadKg,0);}
export function warehouseMarkers(operations:Operations){return operations.warehouses.map(w=>({...w,docks:operations.docks.filter(d=>d.warehouseId===w.id)}));}
export function destinationMatches(truck:Truck|undefined,warehouse:Warehouse|undefined){return !!truck && !!warehouse && Math.abs(truck.destination.longitude-warehouse.location.longitude)<.000001 && Math.abs(truck.destination.latitude-warehouse.location.latitude)<.000001;}
export function affectedResources(operations:Operations){const risks=new Map(operations.cascade.nodeRisks.map(r=>[r.nodeId,r]));const nodes=new Map(operations.graph.nodes.map(n=>[n.id,n]));return operations.cascade.affectedNodeIds.map(id=>({id,node:nodes.get(id),risk:risks.get(id)})).sort((a,b)=>(b.risk?.score || 0)-(a.risk?.score || 0)||a.id.localeCompare(b.id));}
export function resourceSummary(kind:ResourceKind,resource:Warehouse|Dock|Driver|Delivery){
  if(kind==='warehouses'){const w=resource as Warehouse;return `${w.dockCapacity} dock capacity · ${w.location.latitude.toFixed(5)}, ${w.location.longitude.toFixed(5)}`;}
  if(kind==='docks'){const d=resource as Dock;return `${d.status.replaceAll('_',' ').toLowerCase()}${d.occupiedBy ? ` · ${d.occupiedBy}` : ''} · service ${duration(d.serviceSec)}`;}
  if(kind==='drivers'){const d=resource as Driver;return `${d.status.replaceAll('_',' ').toLowerCase()} · duty ${duration(d.dutySec)} · shift +${duration(d.shiftStartSec)}–${duration(d.shiftEndSec)}`;}
  const d=resource as Delivery;return `${d.status.replaceAll('_',' ').toLowerCase()} · ${d.loadKg} kg · deadline +${duration(d.deadlineSec)}${d.lateSec>0 ? ` · ${duration(d.lateSec)} late` : ''}`;
}
export function assignmentTiming(assignment:OperationalAssignment,truck?:Pick<Truck,'etaKnown'>){
  const predicted=truck?.etaKnown===false || assignment.predictedDockStartSec<0 || assignment.predictedDockEndSec<0
    ? 'Predicted service: unknown while arrival is constrained'
    : `Predicted service: +${duration(assignment.predictedDockStartSec)} to +${duration(assignment.predictedDockEndSec)}`;
  if(assignment.actualDockStartSec<0)return {predicted,recorded:'Recorded service: not started'};
  const started=`Recorded service: started +${duration(assignment.actualDockStartSec)}`;
  const recorded=assignment.status==='COMPLETED' && assignment.actualDockEndSec>=0
    ? `${started}; completed +${duration(assignment.actualDockEndSec)}`
    : `${started}; in progress${assignment.actualDockEndSec>=0 ? `, expected finish +${duration(assignment.actualDockEndSec)}` : ''}`;
  return {predicted,recorded};
}
