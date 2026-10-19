export function duration(seconds:number):string {
  if(!Number.isFinite(seconds)) return 'Unavailable';
  const s=Math.max(0,Math.round(seconds));
  if(s<60) return `${s}s`;
  if(s<3600) return `${Math.floor(s/60)}m ${s%60 ? `${s%60}s` : ''}`.trim();
  return `${Math.floor(s/3600)}h ${Math.floor(s%3600/60)}m`;
}
export function clock(seconds:number):string {const s=Math.max(0,Math.floor(seconds));return [Math.floor(s/3600),Math.floor(s/60)%60,s%60].map(n=>String(n).padStart(2,'0')).join(':');}
export function distance(meters:number):string {return meters>=1000 ? `${(meters/1000).toFixed(2)} km` : `${Math.round(meters)} m`;}
export function percent(score:number):string {return `${Math.round(Math.min(1,Math.max(0,score))*100)}%`;}
export function signedDuration(seconds:number):string {return `${seconds<0 ? '−' : '+'}${duration(Math.abs(seconds))}`;}
