import {useEffect,useRef,useState} from 'react';
import {Map,Marker,Popup,NavigationControl,AttributionControl,GeoJSONSource,setWorkerUrl} from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type {FeatureCollection,Feature,LineString,Point as GeoPoint} from 'geojson';
import {Crosshair,Layers,Navigation,MapPin} from 'lucide-react';
import type {Network,Roads,Truck,Incident,Coordinate,SelectedRoad,PickMode,Point,Route} from './types';
import {distance} from './format';
import {mapErrorMessage} from './mapErrors';
import {nearestRoad} from './roadSelection';
import type {Operations} from './operations';
import {warehouseMarkers} from './operations';

// MapLibre v6 requires explicit worker bundling; the default sibling URL fails after Vite optimization.
setWorkerUrl(workerUrl);

interface Props {network:Network;roads:Roads;trucks:Truck[];incidents:Incident[];operations?:Operations;selectedTruck:string|null;selectedRoad:SelectedRoad|null;pickMode:PickMode;draftStart:Point|null;draftDestination:Point|null;draftWaypoints:Point[];preview:Route|null;onPick:(point:Point)=>void;onRoad:(road:SelectedRoad)=>void;onTruck:(id:string)=>void}
const empty:FeatureCollection={type:'FeatureCollection',features:[]};
function endpoint(point:Point,label:string,color:string):Feature<GeoPoint>{return {type:'Feature',properties:{label,color},geometry:{type:'Point',coordinates:[point.longitude,point.latitude]}};}
export default function NetworkMap(props:Props) {
  const host=useRef<HTMLDivElement>(null), map=useRef<Map|null>(null), markers=useRef(new globalThis.Map<string,Marker>()), latest=useRef(props);
  const sourceCache=useRef(new globalThis.Map<string,string>());
  const resourceMarkers=useRef(new globalThis.Map<string,Marker>());
  latest.current=props;
  const [loaded,setLoaded]=useState(false),[base,setBase]=useState(true),[mapWarning,setMapWarning]=useState(''),[vectorReady,setVectorReady]=useState(false),[roadCount,setRoadCount]=useState(0),[routeCount,setRouteCount]=useState(0);
  const vectorReadyRef=useRef(false);
  useEffect(()=>{
    if(!host.current) return;
    sourceCache.current.clear();
    let instance:Map;
    try {
      instance=new Map({container:host.current,center:props.network.center,zoom:13.1,minZoom:9,maxZoom:19,attributionControl:false,
        style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>'}},layers:[{id:'background',type:'background',paint:{'background-color':'#111e2b'}},{id:'osm-basemap',type:'raster',source:'osm',paint:{'raster-saturation':-0.95,'raster-brightness-max':0.36,'raster-brightness-min':0.09,'raster-contrast':0.1}}]}});
    } catch(error){setMapWarning(`Map initialization failed: ${error instanceof Error ? error.message : String(error)}. WebGL is required.`);return;}
    map.current=instance;
    instance.addControl(new NavigationControl({showCompass:false}),'bottom-right');
    instance.addControl(new AttributionControl({compact:true}),'bottom-left');
    instance.on('error',event=>{const sourceId=(event as unknown as {sourceId?:unknown}).sourceId;const failure=mapErrorMessage(event.error?.message || 'Unknown map error',sourceId,vectorReadyRef.current);setMapWarning(failure.message);if(failure.vectorFailure){vectorReadyRef.current=false;setVectorReady(false);}});
    instance.on('load',()=>{
      instance.addSource('roads',{type:'geojson',data:latest.current.roads});
      instance.addLayer({id:'road-network',type:'line',source:'roads',paint:{'line-color':'#769bab','line-opacity':0.38,'line-width':['interpolate',['linear'],['zoom'],11,0.8,16,2]}});
      instance.addLayer({id:'road-hit',type:'line',source:'roads',paint:{'line-color':'#ffffff','line-opacity':0,'line-width':14}});
      instance.addLayer({id:'incident-roads',type:'line',source:'roads',filter:['in',['get','physicalId'],['literal',[]]],paint:{'line-color':'#f5a64b','line-width':6,'line-opacity':0.95}});
      instance.addLayer({id:'selected-road',type:'line',source:'roads',filter:['==',['get','physicalId'],''],paint:{'line-color':'#ffca75','line-width':7,'line-opacity':0.9}});
      instance.addSource('routes',{type:'geojson',data:empty});
      instance.addLayer({id:'fleet-routes',type:'line',source:'routes',paint:{'line-color':['case',['==',['get','selected'],true],'#4fe6cc','#67bdb4'],'line-width':['case',['==',['get','selected'],true],4.5,2.2],'line-opacity':['case',['==',['get','selected'],true],0.98,0.28]}});
      instance.addSource('preview',{type:'geojson',data:empty});
      instance.addLayer({id:'preview-route',type:'line',source:'preview',paint:{'line-color':'#66e7d0','line-width':5,'line-dasharray':[2,1]}});
      instance.addSource('endpoints',{type:'geojson',data:empty});
      instance.addLayer({id:'assignment-endpoints',type:'circle',source:'endpoints',paint:{'circle-radius':7,'circle-color':['get','color'],'circle-stroke-width':3,'circle-stroke-color':'#10212b'}});
      instance.addSource('incidents',{type:'geojson',data:empty});
      instance.addLayer({id:'incident-points',type:'circle',source:'incidents',paint:{'circle-radius':10,'circle-color':'#f7b25d','circle-stroke-width':5,'circle-stroke-color':'rgba(247,178,93,0.3)'}});
      instance.on('click',event=>{
        if(latest.current.pickMode){latest.current.onPick({longitude:event.lngLat.lng,latitude:event.lngLat.lat});return;}
        const features=instance.queryRenderedFeatures([[event.point.x-6,event.point.y-6],[event.point.x+6,event.point.y+6]],{layers:['road-hit']});
        const road=nearestRoad(features,event.point,coordinate=>instance.project(coordinate));
        if(road)latest.current.onRoad({physicalId:String(road.properties.physicalId),name:String(road.properties.name || road.properties.highway || 'Unnamed road'),position:[event.lngLat.lng,event.lngLat.lat]});
      });
      instance.on('mousemove',event=>{instance.getCanvas().style.cursor=latest.current.pickMode ? 'crosshair' : instance.queryRenderedFeatures(event.point,{layers:['road-hit']}).length ? 'pointer' : '';});
      instance.fitBounds([[props.network.bbox[1],props.network.bbox[0]],[props.network.bbox[3],props.network.bbox[2]]],{padding:46,duration:0});
      // A Map load event proves only raster/style initialization. Confirm the actual worker-backed
      // vector layers contain rendered real geometries before enabling selection/readiness checks.
      let lastInspection=0;
      function inspectVectors(){
        if(instance.getLayer('road-hit') && instance.isSourceLoaded('roads')){
          const count=instance.queryRenderedFeatures(undefined,{layers:['road-hit']}).length;setRoadCount(count);
          if(count>0 && !vectorReadyRef.current){vectorReadyRef.current=true;setVectorReady(true);}
        }
        if(instance.getLayer('fleet-routes') && instance.isSourceLoaded('routes'))setRouteCount(instance.queryRenderedFeatures(undefined,{layers:['fleet-routes']}).length);
      }
      instance.on('render',()=>{if(performance.now()-lastInspection<250)return;lastInspection=performance.now();inspectVectors();});
      instance.on('idle',inspectVectors);
      setLoaded(true);
    });
    const observer=new ResizeObserver(()=>instance.resize());observer.observe(host.current);
    return ()=>{observer.disconnect();markers.current.forEach(marker=>marker.remove());markers.current.clear();resourceMarkers.current.forEach(marker=>marker.remove());resourceMarkers.current.clear();instance.remove();map.current=null;setLoaded(false);vectorReadyRef.current=false;setVectorReady(false);};
  },[props.network.networkId]);

  useEffect(()=>{
    const instance=map.current;if(!loaded || !instance)return;
    function updateSource(id:string,data:FeatureCollection){
      const signature=JSON.stringify(data);
      if(sourceCache.current.get(id)===signature)return;
      (instance!.getSource(id) as GeoJSONSource).setData(data);sourceCache.current.set(id,signature);
    }
    function updateFilter(id:string,filter:Parameters<Map['setFilter']>[1]){
      const signature=JSON.stringify(filter);
      if(sourceCache.current.get(id)===signature)return;
      instance!.setFilter(id,filter);sourceCache.current.set(id,signature);
    }
    const routes:FeatureCollection<LineString>={type:'FeatureCollection',features:props.trucks.filter(t=>t.route?.geometry?.length>1).map(t=>({type:'Feature',properties:{id:t.id,selected:t.id===props.selectedTruck},geometry:{type:'LineString',coordinates:t.route.geometry}}))};
    updateSource('routes',routes);
    updateSource('preview',props.preview ? {type:'FeatureCollection',features:[{type:'Feature',properties:{},geometry:{type:'LineString',coordinates:props.preview.geometry}}]} : empty);
    updateFilter('selected-road',['==',['get','physicalId'],props.selectedRoad?.physicalId || '']);
    updateFilter('incident-roads',['in',['get','physicalId'],['literal',props.incidents.filter(i=>i.status==='ACTIVE').map(i=>i.physicalId)]]);
    updateSource('incidents',{type:'FeatureCollection',features:props.incidents.filter(i=>i.status==='ACTIVE').map(i=>({type:'Feature',properties:{id:i.id},geometry:{type:'Point',coordinates:i.position}}))});
    const selected=props.trucks.find(t=>t.id===props.selectedTruck);
    const points=[];
    const start=props.draftStart || selected?.start,destination=props.draftDestination || selected?.destination;
    if(start)points.push(endpoint(start,'Start','#4fe6cc'));if(destination)points.push(endpoint(destination,'Destination','#b6a0fc'));
    props.draftWaypoints.forEach(point=>points.push(endpoint(point,'Waypoint','#ffffff')));
    updateSource('endpoints',{type:'FeatureCollection',features:points});
    const ids=new Set(props.trucks.map(t=>t.id));
    markers.current.forEach((marker,id)=>{if(!ids.has(id)){marker.remove();markers.current.delete(id);}});
    props.trucks.forEach(truck=>{
      let marker=markers.current.get(truck.id);
      if(!marker){
        const element=document.createElement('button');element.type='button';element.className='vehicle-marker';element.setAttribute('aria-label',`Select truck ${truck.id}`);
        const icon=document.createElement('span');icon.className='vehicle-pin';icon.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2 5h12v12H2zM14 9h4l4 4v4h-8M5 17a2 2 0 1 0 4 0M16 17a2 2 0 1 0 4 0"/></svg>';
        const label=document.createElement('span');label.className='vehicle-label';label.textContent=truck.id;element.append(icon,label);
        element.addEventListener('click',event=>{event.stopPropagation();const current=latest.current.trucks.find(t=>t.id===truck.id);if(latest.current.pickMode && current)latest.current.onPick({longitude:current.position[0],latitude:current.position[1]});else latest.current.onTruck(truck.id);});
        marker=new Marker({element,anchor:'center'}).setLngLat(truck.position).addTo(instance);markers.current.set(truck.id,marker);
      }
      marker.setLngLat(truck.position);const element=marker.getElement();
      element.classList.toggle('selected',truck.id===props.selectedTruck);element.classList.toggle('at-risk',truck.affectedIncidentIds.length>0);element.classList.toggle('arrived',truck.status==='ARRIVED');
      element.title=`${truck.name} · ${truck.status.toLowerCase()} · ${Math.round(truck.speedKph)} km/h · ${distance(truck.remainingDistanceM)} remaining`;
    });
  },[props.trucks,props.incidents,props.selectedTruck,props.selectedRoad,props.preview,props.draftStart,props.draftDestination,props.draftWaypoints,loaded]);

  useEffect(()=>{
    const instance=map.current;if(!loaded || !instance)return;
    const warehouseData=props.operations ? warehouseMarkers(props.operations) : [],ids=new Set(warehouseData.map(w=>w.id));
    resourceMarkers.current.forEach((marker,id)=>{if(!ids.has(id)){marker.remove();resourceMarkers.current.delete(id);}});
    const affected=new Set(props.operations?.cascade.affectedNodeIds || []);
    warehouseData.forEach(warehouse=>{
      let marker=resourceMarkers.current.get(warehouse.id);
      if(!marker){
        const element=document.createElement('button');element.type='button';element.className='warehouse-marker';
        const icon=document.createElement('span');icon.className='warehouse-pin';icon.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 10L12 4l9 6v10H3zM8 20v-7h8v7M7 10h10"/></svg>';
        const label=document.createElement('span');label.className='warehouse-label';const docks=document.createElement('span');docks.className='dock-marker-label';element.append(icon,label,docks);
        element.addEventListener('click',event=>{event.stopPropagation();if(latest.current.pickMode){event.stopImmediatePropagation();const current=latest.current.operations?.warehouses.find(w=>w.id===warehouse.id);if(current)latest.current.onPick(current.location);}});
        marker=new Marker({element,anchor:'bottom'}).setLngLat([warehouse.location.longitude,warehouse.location.latitude]).addTo(instance);resourceMarkers.current.set(warehouse.id,marker);
      }
      const element=marker.getElement();marker.setLngLat([warehouse.location.longitude,warehouse.location.latitude]);
      element.querySelector('.warehouse-label')!.textContent=warehouse.id;
      element.querySelector('.dock-marker-label')!.textContent=warehouse.docks.length ? warehouse.docks.map(d=>`${d.id} ${d.status.toLowerCase()}`).join(' · ') : 'No docks';
      element.classList.toggle('at-risk',affected.has(`WAREHOUSE:${warehouse.id}`) || warehouse.docks.some(d=>affected.has(`DOCK:${d.id}`)));
      element.setAttribute('aria-label',`Simulated warehouse ${warehouse.id}; docks ${warehouse.docks.map(d=>d.id).join(', ') || 'none'}`);
      const text=`SIMULATED warehouse ${warehouse.id}: ${warehouse.name}. ${warehouse.docks.map(d=>`Dock ${d.id}: ${d.status.toLowerCase()}${d.occupiedBy ? ` by ${d.occupiedBy}` : ''}; service ${d.serviceSec} seconds.`).join(' ')} Docks are located at their warehouse. Not an observed freight facility.`;
      element.title=text;
      const popup=marker.getPopup();if(popup)popup.setText(text);else marker.setPopup(new Popup({offset:20,maxWidth:'280px'}).setText(text));
    });
  },[props.operations,loaded]);

  function fit(){map.current?.fitBounds([[props.network.bbox[1],props.network.bbox[0]],[props.network.bbox[3],props.network.bbox[2]]],{padding:55,duration:600});}
  function focus(){const truck=props.trucks.find(t=>t.id===props.selectedTruck);if(truck)map.current?.flyTo({center:truck.position,zoom:15,duration:500});}
  function toggleBase(){if(loaded){map.current?.setLayoutProperty('osm-basemap','visibility',base ? 'none' : 'visible');setBase(!base);}}
  return <div className="map-wrap" data-road-network-ready={vectorReady} data-road-feature-count={roadCount} data-route-feature-count={routeCount}><div className="map-canvas" ref={host}/><div className="map-heading"><span className="live-dot"/><div><strong title={props.network.name}>{props.network.name.replace(/\s+real OSM roads.*$/i,'') || 'Chennai'}</strong><small>Real geography. Simulated operations.</small></div><span className="map-area">OSM NETWORK</span></div>
    <div className="map-tools"><button className="icon-button" onClick={fit} title="Fit network" aria-label="Fit road network"><Crosshair size={17}/></button><button className="icon-button" onClick={focus} disabled={!props.selectedTruck} title="Locate selected truck" aria-label="Locate selected truck"><Navigation size={17}/></button><button className={`icon-button ${!base ? 'active' : ''}`} onClick={toggleBase} title="Toggle basemap" aria-label="Toggle OpenStreetMap basemap"><Layers size={17}/></button></div>
    {props.pickMode && <div className="map-instruction"><MapPin size={17}/><span>Click the map to choose a {props.pickMode === 'waypoint' ? 'delivery stop' : props.pickMode}. The backend snaps it to a connected road.</span></div>}
    {mapWarning && <div className="map-warning">{mapWarning}</div>}
    <div className="map-legend"><span><i className="legend-route"/>Planned route</span><span><i className="legend-truck"/>Simulated truck</span><span><i className="legend-warehouse"/>Warehouse / docks</span><span><i className="legend-incident"/>Injected disruption</span></div>
    {!props.pickMode && <div className="map-hint">Click a road segment to inject a disruption</div>}
  </div>;
}
