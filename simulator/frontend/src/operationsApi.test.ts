import {afterEach,describe,expect,it,vi} from 'vitest';
import {api} from './api';
afterEach(()=>vi.unstubAllGlobals());
function mockFetch(){const fetch=vi.fn().mockImplementation(()=>Promise.resolve(new Response('{}',{status:200})));vi.stubGlobal('fetch',fetch);return fetch;}
describe('operational backend commands',()=>{
  it('sends explicit warehouse locations without inventing observed attributes',async()=>{const fetch=mockFetch(),warehouse={id:'W1',name:'Simulated warehouse',location:{longitude:80.27,latitude:13.07},dockCapacity:2};await api.addResource('warehouses',warehouse);expect(fetch).toHaveBeenCalledWith('/api/operations/warehouses',expect.objectContaining({method:'POST',body:JSON.stringify(warehouse)}));});
  it('sends operational dependencies and time validity exactly as configured',async()=>{const fetch=mockFetch(),assignment={truckId:'T1',driverId:'DR1',dockId:'D1',deliveryIds:['L1'],reservationStartSec:300,reservationEndSec:500};await api.assignResources(assignment);expect(fetch).toHaveBeenCalledWith('/api/operations/assignments',expect.objectContaining({method:'POST',body:JSON.stringify(assignment)}));});
  it('encodes resource IDs and uses the dedicated availability command',async()=>{const fetch=mockFetch();await api.driverAvailability('DR / 1',false);expect(fetch).toHaveBeenCalledWith('/api/operations/drivers/DR%20%2F%201/availability',expect.objectContaining({method:'PATCH',body:'{"available":false}'}));});
  it('preserves backend dock conflict errors for the resource dialog',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({error:'Dock reservation overlaps T1.'}),{status:409})));await expect(api.assignResources({truckId:'T2',driverId:'DR2',dockId:'D1',deliveryIds:['L2'],reservationStartSec:300,reservationEndSec:500})).rejects.toThrow('Dock reservation overlaps T1.');});
  it('deletes assignments through the operational API without deleting the truck',async()=>{const fetch=mockFetch();await api.unassignResources('T1');expect(fetch).toHaveBeenCalledWith('/api/operations/assignments/T1',expect.objectContaining({method:'DELETE'}));});
  it('retrieves graph and cascade values from the authoritative backend',async()=>{const fetch=mockFetch();await api.operationalGraph();await api.cascade();expect(fetch.mock.calls.map(call=>call[0])).toEqual(['/api/operations/graph','/api/operations/cascade']);});
});
