import {describe,expect,it} from 'vitest';
import {demoAssignments} from './demo';
import type {Network} from './types';
// Contract fixtures only: these coordinates are not acquired/evaluation data or production fallbacks.
const fixture:Network={networkId:'contract-test',name:'Contract fixture',bbox:[13,80,14,81],center:[80.5,13.5],metadata:{demoPairs:[{start:[80.1,13.1],destination:[80.2,13.2],returnRouteFeasible:true},{start:[80.3,13.3],destination:[80.4,13.4],returnRouteFeasible:false}]}};
describe('explicitly simulated demo assignment creation',()=>{
  it.each([10,20] as const)('creates %i assignments only from backend-provided tested pairs',count=>{
    const assignments=demoAssignments(fixture,count,['D01']);expect(assignments).toHaveLength(count);expect(new Set(assignments.map(assignment=>assignment.id)).size).toBe(count);
    expect(assignments[0].id).toBe('D02');expect(assignments[2].start).toEqual({longitude:80.2,latitude:13.2});expect(assignments[3].start).toEqual({longitude:80.3,latitude:13.3});
    expect(assignments.every(assignment=>assignment.name.startsWith('Simulated') && assignment.loadKg<=assignment.capacityKg && assignment.departureSec<assignment.deadlineSec)).toBe(true);
  });
  it('reports missing route metadata rather than substituting arbitrary or synthetic locations',()=>{expect(()=>demoAssignments({...fixture,metadata:{}},10,[])).toThrow('does not provide tested demo route pairs');});
  it('rejects a demo that would exceed the backend fleet limit',()=>{expect(()=>demoAssignments(fixture,20,Array.from({length:31},(_,index)=>`T${index}`))).toThrow('at most 50 trucks');});
});
