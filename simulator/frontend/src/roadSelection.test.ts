import {describe,expect,it} from 'vitest';
import {nearestRoad,segmentDistanceSquared} from './roadSelection';
import type {RoadCandidate} from './roadSelection';
const project=([x,y]:[number,number])=>({x,y});
function road(id:string,coordinates:number[][]):RoadCandidate {return {properties:{physicalId:id},geometry:{type:'LineString',coordinates}};}
describe('actual clicked-road selection',()=>{
  it('selects the nearest parallel road rather than whichever road the renderer lists first',()=>{
    const farther=road('parallel-north',[[0,2],[20,2]]),nearer=road('parallel-south',[[0,8],[20,8]]);
    expect(nearestRoad([farther,nearer],{x:10,y:7},project)).toBe(nearer);
    expect(nearestRoad([nearer,farther],{x:10,y:7},project)).toBe(nearer);
  });
  it('selects the nearest part of a MultiLineString',()=>{
    const multi:RoadCandidate={properties:{physicalId:'multi'},geometry:{type:'MultiLineString',coordinates:[[[0,20],[20,20]],[[0,6],[20,6]]]}};
    expect(nearestRoad([road('other',[[0,1],[20,1]]),multi],{x:10,y:5},project)).toBe(multi);
  });
  it('breaks exact intersections consistently by physical road identifier',()=>{
    const a=road('a',[[0,5],[10,5]]),b=road('b',[[5,0],[5,10]]);
    expect(nearestRoad([b,a],{x:5,y:5},project)).toBe(a);expect(nearestRoad([a,b],{x:5,y:5},project)).toBe(a);
  });
  it('projects geographic coordinates before comparing pixel distances',()=>{
    const a=road('near',[[80,13],[80.001,13]]),b=road('far',[[80,13.002],[80.001,13.002]]);
    expect(nearestRoad([b,a],{x:5,y:1},([longitude,latitude])=>({x:(longitude-80)*10000,y:(latitude-13)*10000}))).toBe(a);
  });
  it('clamps distance to finite segment endpoints and handles degenerate segments',()=>{expect(segmentDistanceSquared({x:12,y:3},{x:0,y:0},{x:10,y:0})).toBe(13);expect(segmentDistanceSquared({x:2,y:3},{x:0,y:0},{x:0,y:0})).toBe(13);});
  it('ignores non-road or invalid geometry',()=>{expect(nearestRoad([{properties:{physicalId:'bad'},geometry:{type:'Point',coordinates:[0,0]}}],{x:0,y:0},project)).toBeNull();});
});
