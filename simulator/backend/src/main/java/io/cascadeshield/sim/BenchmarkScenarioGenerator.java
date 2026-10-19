package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;
import static io.cascadeshield.sim.BenchmarkModels.*;

/** Seeded simulated workloads on the immutable real road graph. No acquired record is changed. */
public final class BenchmarkScenarioGenerator {
    private final RoadGraph graph;
    private final ObjectMapper mapper;
    private record Pair(long start,long destination) {}
    private record Trip(String id,int warehouse,int dock,double departure,double arrival,double service,double load) {}
    private static final Set<String> KEYS=Set.of("truckCount","warehouseCount","docksPerWarehouse","serviceSec",
        "deadlineSlackSec","departureGapSec","driverUnavailableFraction","driverRestoreSec","closureCount",
        "rainSlowdownCount","severity","incidentDurationSec","incidentStartSec","simultaneousIncidents",
        "horizonSec","contention","decisionIntervalSec","rolloutHorizonSec","maxDecisions");

    public BenchmarkScenarioGenerator(RoadGraph graph,ObjectMapper mapper){this.graph=graph;this.mapper=mapper;}

    public static List<Map<String,Object>> presets(){return List.of(
        preset("closure-contention","Closure with a shared receiving dock",Map.of("truckCount",4,"warehouseCount",1,"docksPerWarehouse",1,"serviceSec",180,"closureCount",1,"rainSlowdownCount",0,"deadlineSlackSec",30,"contention",1)),
        preset("rain-multiple","Multiple closures and simulated rain slowdown",Map.of("truckCount",4,"warehouseCount",2,"docksPerWarehouse",1,"serviceSec",120,"closureCount",2,"rainSlowdownCount",2,"severity",.75,"incidentDurationSec",300)),
        preset("driver-availability","Unavailable drivers with an unannounced restoration",Map.of("truckCount",4,"warehouseCount",1,"docksPerWarehouse",2,"driverUnavailableFraction",.5,"driverRestoreSec",300,"closureCount",1,"serviceSec",120,"deadlineSlackSec",60)),
        preset("low-contention","Dispersed docks and generous delivery slack",Map.of("truckCount",4,"warehouseCount",2,"docksPerWarehouse",2,"contention",0,"serviceSec",60,"deadlineSlackSec",300,"closureCount",1)));
    }
    private static Map<String,Object> preset(String id,String name,Map<String,Object> parameters){return Map.of("id",id,"name",name,"parameters",parameters);}

    public ScenarioSpec generate(String profile,long seed,Map<String,Object> requested){
        Map<String,Object> p=new LinkedHashMap<>();
        p.put("truckCount",4);p.put("warehouseCount",1);p.put("docksPerWarehouse",1);p.put("serviceSec",180d);
        p.put("deadlineSlackSec",30d);p.put("departureGapSec",90d);p.put("driverUnavailableFraction",0d);
        p.put("driverRestoreSec",300d);p.put("closureCount",1);p.put("rainSlowdownCount",0);p.put("severity",1d);
        p.put("incidentDurationSec",240d);p.put("incidentStartSec",10d);p.put("simultaneousIncidents",true);
        p.put("horizonSec",2400d);p.put("contention",1d);p.put("decisionIntervalSec",30d);
        p.put("rolloutHorizonSec",1800d);p.put("maxDecisions",12);
        String selected=profile==null?"closure-contention":profile;
        Map<String,Object> preset=presets().stream().filter(v->v.get("id").equals(selected)).findFirst()
            .orElseThrow(()->ApiException.invalid("Unknown benchmark profile: "+selected));
        @SuppressWarnings("unchecked") Map<String,Object> defaults=(Map<String,Object>)preset.get("parameters");p.putAll(defaults);
        if(requested!=null)for(var e:requested.entrySet()){
            if(Set.of("profile","seeds","seed").contains(e.getKey()))continue;
            if(!KEYS.contains(e.getKey()))throw ApiException.invalid("Unknown benchmark parameter: "+e.getKey());p.put(e.getKey(),e.getValue());
        }
        int count=integer(p,"truckCount",2,12),warehouses=integer(p,"warehouseCount",1,3),dockCount=integer(p,"docksPerWarehouse",1,3);
        double service=number(p,"serviceSec",1,600),slack=number(p,"deadlineSlackSec",-300,1800),gap=number(p,"departureGapSec",0,600);
        double fraction=number(p,"driverUnavailableFraction",0,1),restore=number(p,"driverRestoreSec",0,3600);
        int closureCount=integer(p,"closureCount",0,3),rainCount=integer(p,"rainSlowdownCount",0,3);
        double severity=number(p,"severity",0,1),duration=number(p,"incidentDurationSec",1,1800),start=number(p,"incidentStartSec",0,1800);
        double horizon=number(p,"horizonSec",300,14400),contention=number(p,"contention",0,1);
        number(p,"decisionIntervalSec",1,300);number(p,"rolloutHorizonSec",300,3600);integer(p,"maxDecisions",1,64);
        for(String key:List.of("serviceSec","deadlineSlackSec","departureGapSec","driverRestoreSec","incidentDurationSec","incidentStartSec","horizonSec","decisionIntervalSec","rolloutHorizonSec")){
            double value=((Number)p.get(key)).doubleValue();if(Math.abs(value*10-Math.rint(value*10))>1e-7)throw ApiException.invalid(key+" must use 0.1-second increments");
        }
        Object simultaneous=p.get("simultaneousIncidents");if(!(simultaneous instanceof Boolean))throw ApiException.invalid("simultaneousIncidents must be boolean");
        if(start>=horizon||restore>horizon)throw ApiException.invalid("Incident/restoration announcement clocks must be inside the benchmark horizon");
        List<Pair> pairs=pairs();if(warehouses>pairs.size())throw ApiException.invalid("Prepared network has fewer distinct tested destination pairs than requested warehouses");
        Random random=new Random(seed);SimulationEngine engine=new SimulationEngine(graph,mapper);
        engine.raw().randomSeed=seed;engine.raw().operationsProvenance=PROVENANCE;
        engine.raw().scenarioName=selected+" seed "+seed;engine.raw().initialClockIso="2026-10-09T09:00:00+05:30";
        List<Trip> trips=new ArrayList<>();Map<String,Double> dockCursor=new HashMap<>();List<ScheduledCommand> hidden=new ArrayList<>();
        double resourceEnd=Math.min(172800,Math.max(14400,horizon+600));
        for(int w=0;w<warehouses;w++){
            Pair pair=pairs.get(w);String wid="W"+(w+1);
            engine.resource("warehouses",new WarehouseSpec(wid,"Simulated benchmark warehouse "+(w+1),graph.node(pair.destination).point(),dockCount),true);
            for(int d=0;d<dockCount;d++)engine.resource("docks",new DockSpec(dockId(w,d),"Simulated dock "+(d+1),wid,service,0,resourceEnd),true);
        }
        for(int i=0;i<count;i++){
            int w=i%warehouses,ordinal=i/warehouses;
            int d=random.nextDouble()<contention?0:ordinal%dockCount;Pair pair=pairs.get(w);
            double departure=ceil(Math.max(0,ordinal*gap+(ordinal==0?0:(random.nextDouble()-.5)*gap*.2)));
            double speed=30+random.nextInt(13),load=300+random.nextInt(201);String id="T"+(i+1);
            Truck t=engine.addTruck(new TruckSpec(id,"Simulated freight "+(i+1),graph.node(pair.start).point(),graph.node(pair.destination).point(),List.of(),speed,1000,load,"Simulated driver "+(i+1),i%3==0?"HIGH":"NORMAL",departure,86400));
            String did=dockId(w,d);double ready=ceil(t.baselineArrivalSec),reservationStart=Math.max(ready,dockCursor.getOrDefault(did,0d)),reservationEnd=ceil(reservationStart+service);
            if(reservationEnd>resourceEnd)throw ApiException.invalid("Requested service/load exceeds bounded dock window");dockCursor.put(did,reservationEnd);
            double deadline=ceil(Math.max(departure+1,reservationEnd+slack));
            engine.updateTruck(id,new TruckSpec(id,t.name,t.start,t.destination,List.of(),speed,1000,load,t.driverName,t.priority,departure,Math.min(86400,deadline)));
            boolean available=random.nextDouble()>=fraction;
            engine.resource("drivers",new DriverSpec("DR"+(i+1),"Simulated driver "+(i+1),available,0,resourceEnd),true);
            engine.resource("deliveries",new DeliverySpec("L"+(i+1),"Simulated delivery "+(i+1),"W"+(w+1),load,deadline,t.priority),true);
            engine.assign(new AssignmentSpec(id,"DR"+(i+1),did,List.of("L"+(i+1)),reservationStart,reservationEnd));
            trips.add(new Trip(id,w,d,departure,t.baselineArrivalSec,service,load));
            if(!available)hidden.add(new ScheduledCommand(ceil(restore),hidden.size()+1,"DRIVER_AVAILABILITY",Map.of("id","DR"+(i+1),"available",true)));
        }
        if(engine.raw().operations.deliveries.stream().anyMatch(d->d.deadlineSec>horizon+1e-8))throw ApiException.invalid("Outcome horizon must include every configured delivery deadline; increase horizonSec or reduce workload/service/slack");
        Set<String> selectedPhysical=new HashSet<>();
        for(int j=0;j<closureCount+rainCount;j++){
            boolean rain=j>=closureCount;Truck t=engine.truck(trips.get(j%trips.size()).id);
            String physical=incidentPhysical(t,ceil(start),j,selectedPhysical);selectedPhysical.add(physical);
            double announced=ceil(start+((Boolean)simultaneous?0:j*30));
            if(announced>=horizon)throw ApiException.invalid("Incident announcement exceeds benchmark horizon");
            hidden.add(new ScheduledCommand(announced,hidden.size()+1,"INCIDENT_ADD",Map.of("type",rain?"SLOWDOWN":"CLOSURE","physicalId",physical,"severity",severity,"durationSec",duration,"startSec",announced,"weatherAssumption",rain?"SIMULATED_RAIN_SLOWDOWN":"SIMULATED_ROAD_CLOSURE")));
        }
        hidden.sort(Comparator.comparingDouble(ScheduledCommand::clockSec).thenComparingLong(ScheduledCommand::sequence));
        engine.refresh(true);Map<String,Object> configuration=new LinkedHashMap<>(engine.scenarioConfiguration());
        configuration.put("commands",List.of());configuration.put("durationSec",0d);configuration.put("operationsProvenance",PROVENANCE);
        Map<String,Object> inputs=Map.of("configuration",configuration,"exogenousSchedule",hidden,"horizonSec",horizon,"parameters",p,"provenance",PROVENANCE);
        String fingerprint=hash(inputs);String id=selected+"-s"+seed+"-"+fingerprint.substring(0,12);
        return new ScenarioSpec(id,(String)preset.get("name")+" / seed "+seed,seed,selected,Collections.unmodifiableMap(configuration),List.copyOf(hidden),horizon,fingerprint,Collections.unmodifiableMap(p),PROVENANCE);
    }
    /** The private schedule is not loaded into the policy-visible engine. */
    public State initial(ScenarioSpec spec){
        if(!PROVENANCE.equals(spec.provenance()))throw ApiException.invalid("Benchmark requires explicit simulated-experiment provenance");
        SimulationEngine engine=new SimulationEngine(graph,mapper);Map<String,Object> config=new LinkedHashMap<>(spec.configuration());config.put("commands",List.of());
        engine.replay(spec.name(),config);State s=engine.raw();s.replaying=false;s.replaySchedule.clear();s.commandHistory.clear();s.status="PAUSED";
        s.runId=UUID.nameUUIDFromBytes((spec.inputFingerprint()+":run").getBytes(StandardCharsets.UTF_8));
        s.scenarioId=UUID.nameUUIDFromBytes(spec.id().getBytes(StandardCharsets.UTF_8));s.operationsProvenance=PROVENANCE;
        s.events.clear();s.nextSequence=0;s.randomSeed=spec.seed();engine.refresh(false);return engine.snapshot();
    }
    private String incidentPhysical(Truck t,double announce,int index,Set<String> used){
        double elapsed=t.departureSec;List<Edge> candidates=new ArrayList<>();
        for(String id:t.route.edgeIds()){
            Edge e=graph.edge(id);elapsed+=e.lengthM()/(Math.min(e.speedKph(),t.maxSpeedKph)/3.6);
            if(elapsed>announce+20&&!used.contains(e.physicalId()))candidates.add(e);
        }
        if(candidates.isEmpty())for(String id:t.route.edgeIds())if(!used.contains(graph.edge(id).physicalId()))candidates.add(graph.edge(id));
        if(candidates.isEmpty())throw ApiException.invalid("Not enough distinct real route segments for requested incidents");
        int from=Math.min(candidates.size()-1,index*3);return candidates.get(from).physicalId();
    }
    @SuppressWarnings("unchecked") private List<Pair> pairs(){
        Object value=graph.network.metadata().get("demoPairs");if(!(value instanceof List<?> list)||list.isEmpty())throw ApiException.invalid("Benchmark generation requires prepared, connected demoPairs metadata");
        List<Pair> result=new ArrayList<>();Set<Long> destinations=new HashSet<>();
        for(Object object:list){Map<String,Object> p=(Map<String,Object>)object;long start=((Number)p.get("startNodeId")).longValue(),destination=((Number)p.get("destinationNodeId")).longValue();
            graph.route(start,destination,40,List.of(),0,0);if(destinations.add(destination))result.add(new Pair(start,destination));}
        return List.copyOf(result);
    }
    private static String dockId(int warehouse,int dock){return "D"+(warehouse+1)+"_"+(dock+1);}
    private static double ceil(double seconds){return Math.ceil(seconds*10-1e-8)/10d;}
    private static double number(Map<String,Object> p,String key,double minimum,double maximum){Object raw=p.get(key);if(!(raw instanceof Number n)||!Double.isFinite(n.doubleValue())||n.doubleValue()<minimum||n.doubleValue()>maximum)throw ApiException.invalid(key+" must be finite within ["+minimum+", "+maximum+"]");double value=n.doubleValue();p.put(key,value);return value;}
    private static int integer(Map<String,Object> p,String key,int minimum,int maximum){double value=number(p,key,minimum,maximum);if(value!=Math.rint(value))throw ApiException.invalid(key+" must be an integer");p.put(key,(int)value);return (int)value;}
    public String hash(Object value){try{JsonNode tree=mapper.valueToTree(value);String json=mapper.writeValueAsString(sorted(tree));return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(json.getBytes(StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalStateException("Cannot fingerprint benchmark inputs",e);}}
    private JsonNode sorted(JsonNode node){if(node.isObject()){var result=mapper.createObjectNode();List<String> keys=new ArrayList<>();node.fieldNames().forEachRemaining(keys::add);Collections.sort(keys);for(String key:keys)result.set(key,sorted(node.get(key)));return result;}if(node.isArray()){var result=mapper.createArrayNode();node.forEach(v->result.add(sorted(v)));return result;}return node;}
}
