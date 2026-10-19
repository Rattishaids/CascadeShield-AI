import {describe,it,expect} from 'vitest';
import {clock,duration,distance,percent,signedDuration} from './format';
describe('backend state presentation',()=>{
  it('keeps the elapsed simulation clock independent of wall time',()=>{expect(clock(3661.9)).toBe('01:01:01');expect(clock(0)).toBe('00:00:00');});
  it('handles finite and unavailable route estimates',()=>{expect(duration(Infinity)).toBe('Unavailable');expect(distance(1530)).toBe('1.53 km');});
  it('bounds risk presentation',()=>{expect(percent(0.284)).toBe('28%');expect(percent(1.02)).toBe('100%');});
  it('preserves earlier arrival estimates when comparing a detour',()=>{expect(signedDuration(-120)).toBe('−2m');expect(signedDuration(60)).toBe('+1m');});
});
