import type {FeatureCollection, LineString} from 'geojson';
import type {Operations} from './operations';
export type Coordinate = [number, number];
export interface Point {longitude:number; latitude:number}
export type RoadProperties = {physicalId:string; name?:string; highway?:string; [key:string]:unknown};
export type Roads = FeatureCollection<LineString, RoadProperties>;
export interface Network {networkId:string; name:string; bbox:[number,number,number,number]; center:Coordinate; metadata:Record<string,unknown>}
export interface Route {edgeIds:string[]; geometry:Coordinate[]; distanceM:number; baseTravelSec:number; snappedStart?:Point; snappedDestination?:Point}
export interface Assignment {id:string; name:string; start:Point; destination:Point; waypoints:Point[]; capacityKg:number; loadKg:number; maxSpeedKph:number; driverName:string; priority:'NORMAL'|'HIGH'; departureSec:number; deadlineSec:number}
export interface Truck extends Assignment {route:Route; position:Coordinate; speedKph:number; remainingDistanceM:number; etaSec:number; etaKnown?:boolean; status:string; risk:{score:number;level:string;source:'RULE_BASED'}; affectedIncidentIds:string[]}
export interface Incident {id:string;type:'CLOSURE'|'SLOWDOWN';physicalId:string;severity:number;startSec:number;endSec:number;status:string;position:Coordinate}
export interface Option {action:'WAIT'|'REROUTE'|'CONTINUE';feasible:boolean;addedTravelSec:number;estimatedArrivalSec:number;totalDistanceM:number;additionalDistanceM:number;explanation:string}
export interface Recommendation {id:string;truckId:string;incidentIds:string[];riskSource:'RULE_BASED';beforeRisk:number;afterRisk:number;reason:string;options:Option[];recommendedAction:Option['action']}
export interface SimulationEvent {id:string|number;clockSec:number;type:string;message:string;truckId?:string}
export interface Kpis {totalTrucks:number;arrived:number;lateDeliveries:number;totalDelaySec:number;distanceTravelledM:number;reroutes:number;waitingTrucks:number;activeIncidents:number;completedTrips:number}
export interface State {runId?:string;status:'DRAFT'|'RUNNING'|'PAUSED'|'COMPLETED';clockSec:number;speed:number;initialClockIso:string;trucks:Truck[];incidents:Incident[];recommendations:Recommendation[];events:SimulationEvent[];kpis:Kpis;networkId:string;scenarioName:string;replaying:boolean;operations?:Operations}
export interface Scenario {id:string;name:string;createdAt:string}
export interface Health {status:'UP'|'DEGRADED';database:boolean;networkId:string;roadNodes:number;directedEdges:number;persistenceError:string}
export interface SelectedRoad {physicalId:string;name:string;position:Coordinate}
export type PickMode = 'start'|'destination'|'waypoint'|null;
