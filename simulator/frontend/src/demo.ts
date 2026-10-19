import type {Assignment,Coordinate,Network} from './types';
interface DemoPair {start:Coordinate;destination:Coordinate;returnRouteFeasible?:boolean}
function coordinate(value:unknown):value is Coordinate {return Array.isArray(value) && value.length===2 && value.every(number=>typeof number==='number' && Number.isFinite(number));}
/** Creates SIMULATED assignments from backend-provenanced, route-tested real OSM pairs. */
export function demoAssignments(network:Network,count:10|20,existingIds:string[]):Assignment[] {
  const source=network.metadata.demoPairs;
  if(!Array.isArray(source))throw new Error('The backend does not provide tested demo route pairs. Create trucks manually on the map.');
  const pairs=source.filter((value):value is DemoPair=>value!==null && typeof value==='object' && coordinate(value.start) && coordinate(value.destination));
  if(!pairs.length)throw new Error('No valid real-network demo pairs are available. Create trucks manually on the map.');
  if(existingIds.length+count>50)throw new Error('The first milestone supports at most 50 trucks. Reset or remove assignments before creating this demo fleet.');
  const used=new Set(existingIds),assignments:Assignment[]=[];
  for(let i=0;i<count;i++){
    const pair=pairs[i%pairs.length],reverse=Math.floor(i/pairs.length)%2===1 && pair.returnRouteFeasible===true;
    const start=reverse ? pair.destination : pair.start,destination=reverse ? pair.start : pair.destination;
    let n=1;while(used.has(`D${String(n).padStart(2,'0')}`))n++;
    const id=`D${String(n).padStart(2,'0')}`;used.add(id);
    assignments.push({id,name:`Simulated delivery ${n}`,start:{longitude:start[0],latitude:start[1]},destination:{longitude:destination[0],latitude:destination[1]},waypoints:[],maxSpeedKph:35+(i%3)*5,capacityKg:3500,loadKg:900+i*60,driverName:`Simulated driver ${id}`,priority:i%4===0 ? 'HIGH' : 'NORMAL',departureSec:i*5,deadlineSec:3600});
  }
  return assignments;
}
