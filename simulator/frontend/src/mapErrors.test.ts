import {describe,expect,it} from 'vitest';
import {mapErrorMessage} from './mapErrors';
describe('map capability error reporting',()=>{
  it('identifies worker failure instead of falsely claiming the real road layer works',()=>{const error=mapErrorMessage('Worker failed to load. Check the URL.',undefined,false);expect(error.vectorFailure).toBe(true);expect(error.message).toContain('Road selection and route display are unavailable');expect(error.message).not.toContain('Basemap');});
  it('distinguishes raster tile failure from a functioning imported road layer',()=>{expect(mapErrorMessage('HTTP 503','osm',true)).toEqual({message:'OpenStreetMap basemap tiles unavailable. The imported real road layer remains available.',vectorFailure:false});});
  it('does not claim loaded roads before the vector source has rendered',()=>{expect(mapErrorMessage('HTTP 503','osm',false).message).toContain('still loading');});
});
