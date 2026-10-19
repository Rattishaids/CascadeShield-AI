export function mapErrorMessage(message:string,sourceId:unknown,roadNetworkReady:boolean):{message:string;vectorFailure:boolean} {
  if(/worker/i.test(message))return {message:`Road rendering worker failed: ${message}. Road selection and route display are unavailable.`,vectorFailure:true};
  if(/webgl|gpu/i.test(message))return {message:`Map graphics unavailable: ${message}`,vectorFailure:true};
  if(sourceId==='osm' || /tile\.openstreetmap\.org/i.test(message))return {message:`OpenStreetMap basemap tiles unavailable. ${roadNetworkReady ? 'The imported real road layer remains available.' : 'The imported real road layer is still loading.'}`,vectorFailure:false};
  return {message:`Map rendering error: ${message}`,vectorFailure:sourceId!==undefined && sourceId!=='osm'};
}
