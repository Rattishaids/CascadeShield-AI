import {afterEach,describe,expect,it,vi} from 'vitest';
import {api,request} from './api';
afterEach(()=>vi.unstubAllGlobals());
describe('authoritative backend commands',()=>{
  it('sends operator decisions as commands without mutating a local simulation',async()=>{
    const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({status:'PAUSED'}),{status:200}));vi.stubGlobal('fetch',fetch);
    await api.decision('T01','REC-1','WAIT');
    expect(fetch).toHaveBeenCalledWith('/api/decisions',expect.objectContaining({method:'POST',body:JSON.stringify({truckId:'T01',recommendationId:'REC-1',action:'WAIT'})}));
  });
  it('preserves validation and conflict explanations from the backend',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({error:'No connected route exists between these locations.'}),{status:400})));
    await expect(request('/routes/preview',{})).rejects.toThrow('No connected route exists');
  });
  it('does not treat a development-server HTML response as simulation state',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('<html>Server unavailable</html>',{status:503})));
    await expect(api.state()).rejects.toThrow('invalid response (503)');
  });
  it('supports empty successful deletion responses and safely encodes truck IDs',async()=>{
    const fetch=vi.fn().mockResolvedValue(new Response(null,{status:204}));vi.stubGlobal('fetch',fetch);await api.deleteTruck('truck / 01');
    expect(fetch).toHaveBeenCalledWith('/api/trucks/truck%20%2F%2001',expect.objectContaining({method:'DELETE'}));
  });
});
