import type {Coordinate} from './types';
export interface ScreenPoint {x:number;y:number}
export interface RoadCandidate {properties:Record<string,unknown>|null;geometry:{type:string;coordinates?:unknown}}
export function segmentDistanceSquared(point:ScreenPoint,start:ScreenPoint,end:ScreenPoint):number {
  const dx=end.x-start.x,dy=end.y-start.y,lengthSquared=dx*dx+dy*dy;
  const fraction=lengthSquared===0 ? 0 : Math.max(0,Math.min(1,((point.x-start.x)*dx+(point.y-start.y)*dy)/lengthSquared));
  const x=start.x+fraction*dx,y=start.y+fraction*dy;
  return (point.x-x)**2+(point.y-y)**2;
}
function coordinate(value:unknown):value is Coordinate {return Array.isArray(value) && value.length>=2 && typeof value[0]==='number' && Number.isFinite(value[0]) && typeof value[1]==='number' && Number.isFinite(value[1]);}
/** Chooses the actual nearest rendered physical road, independent of tile/layer ordering. */
export function nearestRoad<T extends RoadCandidate>(features:T[],click:ScreenPoint,project:(coordinate:Coordinate)=>ScreenPoint):T|null {
  let best:T|null=null,bestDistance=Infinity,bestId='';
  for(const feature of features){
    const physicalId=feature.properties?.physicalId;if(physicalId===undefined || physicalId===null)continue;
    const id=String(physicalId),{type,coordinates}=feature.geometry;
    const lines=type==='LineString' ? [coordinates] : type==='MultiLineString' && Array.isArray(coordinates) ? coordinates : [];
    let distance=Infinity;
    for(const line of lines){
      if(!Array.isArray(line))continue;
      for(let i=1;i<line.length;i++){
        if(!coordinate(line[i-1]) || !coordinate(line[i]))continue;
        distance=Math.min(distance,segmentDistanceSquared(click,project(line[i-1]),project(line[i])));
      }
    }
    if(!Number.isFinite(distance))continue;
    // A consistent physicalId tie-break prevents direction copies/adjacent tile order from
    // changing selection at intersections or on perfectly overlapping geometries.
    if(distance<bestDistance-1e-8 || (Math.abs(distance-bestDistance)<=1e-8 && (!best || id<bestId))){best=feature;bestDistance=distance;bestId=id;}
  }
  return best;
}
