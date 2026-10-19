package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;

/** Pure authoritative deterministic engine. Real-time scheduler only requests fixed 0.1 s ticks. */
public final class SimulationEngine {
    public static final double TICK_SEC=.1;
    private final RoadGraph graph;
    private final RuleBasedPredictionService prediction;
    private final RuleBasedPreventionService prevention;
    private final ObjectMapper mapper;
    private final OperationalRuntime operations;
    private final OperationalDependencyGraph dependencyGraph=new OperationalDependencyGraph();
    private final GraphRiskBaseline graphRisk=new GraphRiskBaseline();
    private final List<Event> pendingEvents=new ArrayList<>();
    private State state;
    private double nextRecommendationAt=0;
    public SimulationEngine(RoadGraph graph,ObjectMapper mapper){this.graph=graph;this.mapper=mapper;prediction=new RuleBasedPredictionService(graph);prevention=new RuleBasedPreventionService(graph,prediction);operations=new OperationalRuntime(graph,mapper);state=new State();state.networkId=graph.network.networkId();}
    public State raw(){return state;}
    public State snapshot(){refresh(false);return mapper.convertValue(state,State.class);}
    public List<Event> pendingEvents(){return List.copyOf(pendingEvents);}
    public List<Event> drainEvents(){List<Event> events=List.copyOf(pendingEvents);pendingEvents.clear();return events;}
    public void restore(State loaded){if(!graph.network.networkId().equals(loaded.networkId))throw new IllegalStateException("Saved state references a different road network");state=loaded;if("RUNNING".equals(state.status)){state.status="PAUSED";event("RECOVERED","Recovered persisted backend state, paused to avoid a wall-clock jump.",null,Map.of());}refresh(true);}
    public Route preview(RouteRequest request) {
        long start=graph.snap(request.start()),destination=graph.snap(request.destination());
        List<Long> via=waypoints(request.waypoints());
        if(start==destination&&via.isEmpty())throw ApiException.invalid("Start and destination snap to the same road node; choose distinct points.");
        return graph.route(start,destination,via,request.maxSpeedKph(),state.incidents,state.clockSec,0);
    }
    private List<Long> waypoints(List<Point> points){if(points==null)return List.of();if(points.size()>8)throw ApiException.invalid("At most 8 intermediate stops are supported in milestone 1.");return points.stream().map(graph::snap).toList();}
    private void editable(){if(!"DRAFT".equals(state.status)||state.clockSec>1e-7)throw ApiException.conflict("Assignments can be edited only before starting. Reset to edit the initial scenario.");}
    private void operatorCommand(){if(state.replaying)throw ApiException.conflict("Saved replay is locked for reproducibility. Reset before creating a new branch.");}
    public Truck addTruck(TruckSpec spec){editable();if(state.trucks.size()>=50)throw ApiException.invalid("This bounded demonstration supports at most 50 trucks.");if(state.trucks.stream().anyMatch(t->t.id.equals(spec.id())))throw ApiException.conflict("Truck ID already exists");Truck truck=build(spec);state.trucks.add(truck);event("TRUCK_CREATED","Created SIMULATED truck "+truck.id,truck.id,Map.of("provenance","SIMULATED"));refresh(true);return truck;}
    public Truck updateTruck(String id,TruckSpec spec){editable();if(!id.equals(spec.id()))throw ApiException.invalid("Truck ID cannot change while editing");Truck original=truck(id);Truck replacement=build(spec);Assignment assignment=OperationalRuntime.assignment(state,id);if(assignment!=null){State copy=mapper.convertValue(state,State.class);copy.trucks.set(state.trucks.indexOf(original),replacement);operations.assign(copy,new AssignmentSpec(id,assignment.driverId,assignment.dockId,assignment.deliveryIds,assignment.reservationStartSec,assignment.reservationEndSec));replacement.driverName=OperationalRuntime.driver(state,assignment.driverId).name;}state.trucks.set(state.trucks.indexOf(original),replacement);event("TRUCK_EDITED","Updated pre-departure assignment",id,Map.of());refresh(true);return replacement;}
    public void deleteTruck(String id){editable();operations.unassign(state,id);state.trucks.remove(truck(id));initialOperations();event("TRUCK_REMOVED","Removed initial assignment",id,Map.of());refresh(true);}
    private void initialOperations(){state.initialOperations=operations.configuration(state);}
    public void resource(String kind,Object body,boolean create){operatorCommand();editable();operations.upsert(state,kind,body,create);initialOperations();event("RESOURCE_CONFIGURED","Configured SIMULATED "+kind,null,Map.of("kind",kind,"provenance","SIMULATED"));refresh(true);}
    public void removeResource(String kind,String id){operatorCommand();editable();operations.remove(state,kind,id);initialOperations();event("RESOURCE_REMOVED","Removed simulated "+kind+" "+id,null,Map.of("provenance","SIMULATED"));refresh(true);}
    public void assign(AssignmentSpec request){operatorCommand();editable();operations.assign(state,request);initialOperations();event("DEPENDENCY_ASSIGNED",request.truckId()+" assigned to driver "+request.driverId()+", dock "+request.dockId()+" and deliveries "+request.deliveryIds(),request.truckId(),Map.of("assignment",request,"provenance","SIMULATED"));refresh(true);}
    public void unassign(String truckId){operatorCommand();editable();operations.unassign(state,truckId);initialOperations();event("DEPENDENCY_REMOVED","Removed operational assignment for "+truckId,truckId,Map.of());refresh(true);}
    public void availability(String id,boolean available){operatorCommand();availability(id,available,true);}
    private void availability(String id,boolean available,boolean record){Driver driver=OperationalRuntime.driver(state,id);driver.available=available;if("DRAFT".equals(state.status)&&state.clockSec==0)initialOperations();else if(record)command("DRIVER_AVAILABILITY",Map.of("id",id,"available",available));event("DRIVER_AVAILABILITY",id+" availability changed to "+available,null,Map.of("driverId",id,"available",available,"provenance","SIMULATED"));refresh(true);}
    private Truck build(TruckSpec spec) {
        if(spec.id()==null||!spec.id().matches("[A-Za-z0-9_-]{1,32}"))throw ApiException.invalid("Truck ID must contain 1–32 letters, digits, underscores or hyphens.");
        if(!Double.isFinite(spec.capacityKg())||!Double.isFinite(spec.loadKg())||spec.capacityKg()<=0||spec.loadKg()<0||spec.loadKg()>spec.capacityKg())throw ApiException.invalid("Cargo must be nonnegative and within a positive vehicle capacity.");
        if(!Double.isFinite(spec.departureSec())||!Double.isFinite(spec.deadlineSec())||spec.departureSec()<0||spec.deadlineSec()<=spec.departureSec()||spec.deadlineSec()>86400)throw ApiException.invalid("Departure/deadline must be finite seconds from simulation start, with deadline after departure and within 24 h.");
        long start=graph.snap(spec.start()),destination=graph.snap(spec.destination());List<Long> via=waypoints(spec.waypoints());
        if(start==destination&&via.isEmpty())throw ApiException.invalid("Choose different snapped start/destination nodes.");
        Route route=graph.route(start,destination,via,spec.maxSpeedKph(),List.of(),spec.departureSec(),0);
        Truck truck=new Truck();truck.id=spec.id();truck.name=spec.name()==null||spec.name().isBlank()?spec.id():spec.name().substring(0,Math.min(80,spec.name().length()));
        truck.start=graph.node(start).point();truck.destination=graph.node(destination).point();truck.startNode=start;truck.destinationNode=destination;
        truck.waypoints=spec.waypoints()==null?new ArrayList<>():new ArrayList<>(spec.waypoints());truck.remainingStops=new ArrayList<>(via);truck.remainingStops.add(destination);
        truck.capacityKg=spec.capacityKg();truck.loadKg=spec.loadKg();truck.maxSpeedKph=spec.maxSpeedKph();truck.departureSec=spec.departureSec();truck.deadlineSec=spec.deadlineSec();
        truck.driverName=spec.driverName()==null||spec.driverName().isBlank()?"Simulated driver":spec.driverName();truck.priority="HIGH".equals(spec.priority())?"HIGH":"NORMAL";
        truck.route=route;truck.position=truck.start.coordinates();truck.remainingDistanceM=route.distanceM();truck.etaSec=spec.departureSec()+route.baseTravelSec();truck.baselineArrivalSec=truck.etaSec;truck.initialAssignment=spec;return truck;
    }
    public Truck truck(String id){return state.trucks.stream().filter(t->t.id.equals(id)).findFirst().orElseThrow(()->new ApiException(404,"Truck not found: "+id));}
    public void control(ControlRequest request) {
        String action=request.action()==null?"":request.action().toUpperCase(Locale.ROOT);
        switch(action) {
            case "START" -> {if(!"DRAFT".equals(state.status))throw ApiException.conflict("Start is only available for a draft; resume or restart instead.");if(state.trucks.isEmpty())throw ApiException.invalid("Create at least one truck first.");state.status="RUNNING";event("STARTED","Simulation clock started",null,Map.of());}
            case "PAUSE" -> {if(!"RUNNING".equals(state.status))throw ApiException.conflict("Simulation is not running");state.status="PAUSED";state.trucks.forEach(t->t.speedKph=0);event("PAUSED","Simulation paused",null,Map.of());}
            case "RESUME" -> {if(!"PAUSED".equals(state.status))throw ApiException.conflict("Simulation is not paused");state.status="RUNNING";event("RESUMED","Simulation resumed",null,Map.of());}
            case "RESET" -> reset(false);
            case "RESTART" -> {reset(false);if(state.trucks.isEmpty())throw ApiException.invalid("Create at least one truck first.");state.status="RUNNING";event("STARTED","Restarted from identical assignments",null,Map.of());}
            case "SET_SPEED", "SPEED" -> {if(request.speed()==null||!List.of(1d,2d,5d,10d).contains(request.speed()))throw ApiException.invalid("Speed must be 1, 2, 5 or 10");state.speed=request.speed();event("SPEED_CHANGED","Clock rate changed to "+state.speed+"x",null,Map.of("speed",state.speed));}
            case "STEP" -> {if("RUNNING".equals(state.status))throw ApiException.conflict("Pause before stepping");if(state.trucks.isEmpty())throw ApiException.invalid("Create a truck before stepping");double seconds=request.stepSec()==null?1:request.stepSec();if(!Double.isFinite(seconds)||seconds<.1||seconds>3600||Math.abs(seconds*10-Math.rint(seconds*10))>1e-7)throw ApiException.invalid("Step must be 0.1–3600 seconds in 0.1 second increments");state.status="PAUSED";advance((int)Math.round(seconds*10));}
            default -> throw ApiException.invalid("Unknown simulation control");
        }
        refresh(true);
    }
    public void reset(boolean keepSchedule) {
        List<TruckSpec> originals=state.trucks.stream().map(t->t.initialAssignment).toList();String name=state.scenarioName;double speed=state.speed;Configuration resources=state.initialOperations;
        state=new State();state.networkId=graph.network.networkId();state.scenarioName=name;state.speed=speed;nextRecommendationAt=0;
        pendingEvents.clear();for(TruckSpec spec:originals)state.trucks.add(build(spec));operations.configure(state,resources);state.initialOperations=resources;event("RESET","Returned to initial SIMULATED assignments",null,Map.of());refresh(true);
    }
    public Incident addIncident(IncidentRequest request){operatorCommand();return addIncident(request,true);}
    private Incident addIncident(IncidentRequest request,boolean record) {
        if(!List.of("CLOSURE","SLOWDOWN").contains(request.type()))throw ApiException.invalid("Milestone 1 supports CLOSURE and SLOWDOWN incidents.");
        if(!Double.isFinite(request.severity())||request.severity()<0||request.severity()>1||!Double.isFinite(request.durationSec())||request.durationSec()<TICK_SEC||request.durationSec()>86400)throw ApiException.invalid("Severity must be 0–1 and duration 0.1–86400 seconds.");
        List<Edge> roads=graph.physicalEdges(request.physicalId());if(roads.isEmpty())throw ApiException.invalid("Select a real road segment from the prepared network");
        if(state.incidents.size()>=100)throw ApiException.invalid("At most 100 incident records per scenario are supported");
        double requestedStart=request.startSec()==null?state.clockSec:request.startSec();
        if(!Double.isFinite(requestedStart)||requestedStart<state.clockSec-1e-7)throw ApiException.invalid("Incident start must be finite and cannot precede the current simulation clock");
        double start=quantize(requestedStart),end=quantize(start+request.durationSec());
        if(!Double.isFinite(start)||!Double.isFinite(end)||Math.abs(start-requestedStart)>.050001||end-start<TICK_SEC-1e-7)throw ApiException.invalid("Incident schedule must contain at least one 0.1-second simulation tick");
        Incident incident=new Incident();incident.id="I"+String.format(Locale.ROOT,"%03d",state.nextIncidentId++);incident.type=request.type();incident.physicalId=request.physicalId();incident.severity=request.severity();incident.startSec=start;incident.endSec=end;incident.status=start>state.clockSec?"SCHEDULED":"ACTIVE";
        incident.position=graph.position(roads.getFirst(),roads.getFirst().lengthM()/2);state.incidents.add(incident);
        if(record)command("INCIDENT_ADD",Map.of("type",incident.type,"physicalId",incident.physicalId,"severity",incident.severity,"durationSec",incident.endSec-incident.startSec,"startSec",incident.startSec));
        event("INCIDENT_CREATED","Injected SIMULATED "+incident.type+" on "+(roads.getFirst().name()==null?incident.physicalId:roads.getFirst().name()),null,Map.of("incidentId",incident.id,"physicalId",incident.physicalId,"provenance","SIMULATED"));refresh(true);return incident;
    }
    public void removeIncident(String id){operatorCommand();removeIncident(id,true);}
    private void removeIncident(String id,boolean record){Incident incident=state.incidents.stream().filter(i->i.id.equals(id)).findFirst().orElseThrow(()->new ApiException(404,"Incident not found"));incident.status="RESOLVED";incident.endSec=Math.min(incident.endSec,state.clockSec);if(record)command("INCIDENT_REMOVE",Map.of("id",id));event("INCIDENT_RESOLVED","Operator resolved incident "+id,null,Map.of("incidentId",id));refresh(true);}
    public void decide(DecisionRequest request){operatorCommand();decide(request,true);}
    private void decide(DecisionRequest request,boolean record) {
        Truck truck=truck(request.truckId());refresh(true);
        Recommendation recommendation=state.recommendations.stream().filter(r->r.truckId().equals(truck.id)).findFirst().orElseThrow(()->ApiException.conflict("Truck currently has no directly affecting incident"));
        if(record&&!recommendation.id().equals(request.recommendationId()))throw ApiException.conflict("Recommendation is stale; review the current road state");
        Option option=recommendation.options().stream().filter(o->o.action().equals(request.action())&&o.feasible()).findFirst().orElseThrow(()->ApiException.invalid("Requested intervention is infeasible"));
        List<Double> before=List.copyOf(truck.position);
        switch(option.action()) {
            case "WAIT" -> {truck.approvedWaitIncidentIds=new ArrayList<>(truck.affectedIncidentIds);truck.waitUntilSec=prevention.waitUntil(state,truck);}
            case "CONTINUE" -> {truck.waitUntilSec=0;truck.approvedWaitIncidentIds.clear();}
            case "REROUTE" -> {RuleBasedPreventionService.ReroutePlan plan=prevention.reroute(state,truck);truck.route=graph.describe(plan.ids(),plan.ids().isEmpty()?truck.destination:graph.node(graph.edge(plan.ids().getFirst()).from()).point(),truck.destination,truck.maxSpeedKph);truck.edgeIndex=0;truck.offsetM=plan.offsetM();truck.waitUntilSec=0;truck.approvedWaitIncidentIds.clear();truck.reroutes++;}
            default -> throw ApiException.invalid("Unsupported action");
        }
        if(!before.equals(truck.position))throw new IllegalStateException("Intervention changed geographic position");
        if(record)command("DECISION",Map.of("truckId",truck.id,"action",option.action()));
        event("INTERVENTION_APPROVED","Operator approved "+option.action()+" for "+truck.id,truck.id,Map.of("action",option.action(),"provenance","SIMULATED","riskSource","RULE_BASED","estimatedArrivalSec",option.estimatedArrivalSec()));refresh(true);
    }
    private void command(String kind,Map<String,Object> payload){state.commandHistory.add(new ScheduledCommand(state.clockSec,state.nextSequence+1,kind,payload));}
    private void event(String type,String message,String truck,Map<String,Object> details){eventAt(state.clockSec,type,message,truck,details);}
    private void eventAt(double when,String type,String message,String truck,Map<String,Object> details){Event e=new Event(++state.nextSequence,quantize(when),type,message,truck,details);state.events.add(e);pendingEvents.add(e);if(state.events.size()>500)state.events.removeFirst();}
    private static double quantize(double value){return Math.round(value*10)/10d;}
    public void schedulerTick(){if("RUNNING".equals(state.status))advance((int)state.speed);}
    public void advance(int ticks) {
        for(int tick=0;tick<ticks;tick++) {
            applyDueCommands();double from=state.clockSec,to=quantize(from+TICK_SEC);
            for(Incident i:state.incidents)if(!"RESOLVED".equals(i.status)) {
                String next=to>=i.endSec-1e-8?"EXPIRED":to>=i.startSec-1e-8?"ACTIVE":"SCHEDULED";
                if(!next.equals(i.status)){i.status=next;eventAt(to,"INCIDENT_"+next,"Incident "+i.id+" became "+next,null,Map.of("incidentId",i.id));}
            }
            for(Truck truck:state.trucks)move(truck,from,to);
            state.clockSec=to;operations.tick(state,from,to,this::eventAt);applyDueCommands();
            if(!state.trucks.isEmpty()&&state.trucks.stream().allMatch(t->"ARRIVED".equals(t.status))&&operations.complete(state)){state.status="COMPLETED";event("COMPLETED","All SIMULATED truck trips and assigned dock deliveries completed",null,Map.of());break;}
        }
        refresh(false);
    }
    private void applyDueCommands() {
        while(state.replayCursor<state.replaySchedule.size()&&state.replaySchedule.get(state.replayCursor).clockSec()<=state.clockSec+1e-8) {
            ScheduledCommand scheduled=state.replaySchedule.get(state.replayCursor++);
            switch(scheduled.kind()) {
                case "INCIDENT_ADD" -> addIncident(mapper.convertValue(scheduled.payload(),IncidentRequest.class),false);
                case "INCIDENT_REMOVE" -> removeIncident((String)scheduled.payload().get("id"),false);
                case "DECISION" -> decide(new DecisionRequest((String)scheduled.payload().get("truckId"),(String)scheduled.payload().get("action"),null),false);
                case "DRIVER_AVAILABILITY" -> availability((String)scheduled.payload().get("id"),(Boolean)scheduled.payload().get("available"),false);
                default -> throw new IllegalStateException("Unknown saved command "+scheduled.kind());
            }
        }
    }
    private void changeStatus(Truck truck,String status,double time) {
        if(!status.equals(truck.status)) {String old=truck.status;truck.status=status;eventAt(time,"TRUCK_"+status,truck.id+" "+old+" → "+status,truck.id,Map.of("atSec",time));}
    }
    private void move(Truck truck,double from,double to) {
        truck.speedKph=0;
        if("ARRIVED".equals(truck.status)||to<=truck.departureSec+1e-8)return;
        double time=Math.max(from,truck.departureSec);
        while(time<to-1e-8&&truck.edgeIndex<truck.route.edgeIds().size()) {
            Edge edge=graph.edge(truck.route.edgeIds().get(truck.edgeIndex));boolean occupied=truck.offsetM>1e-7;
            if(!occupied&&truck.waitUntilSec>time+1e-8){truck.speedKph=0;changeStatus(truck,"WAITING",time);time=Math.min(to,truck.waitUntilSec);continue;}
            double factor=RoadGraph.speedFactor(edge.physicalId(),state.incidents,time,occupied);
            if(factor<1)for(Incident incident:state.incidents)if(incident.physicalId.equals(edge.physicalId())&&RoadGraph.active(incident,time)&&!truck.encounteredIncidentIds.contains(incident.id))truck.encounteredIncidentIds.add(incident.id);
            double boundary=Math.min(to,RoadGraph.nextBoundary(edge.physicalId(),state.incidents,time));
            if(factor==0){truck.speedKph=0;changeStatus(truck,"BLOCKED",time);time=boundary;continue;}
            if(!occupied){String constraint=operations.entryConstraint(state,truck,edge,time);if(constraint!=null){truck.speedKph=0;changeStatus(truck,constraint,time);break;}}
            double speed=Math.min(edge.speedKph(),truck.maxSpeedKph)/3.6*factor;
            double duration=Math.min(boundary-time,(edge.lengthM()-truck.offsetM)/speed);
            double distance=speed*duration;truck.offsetM+=distance;truck.distanceTravelledM+=distance;time+=duration;
            truck.speedKph=speed*3.6;changeStatus(truck,"MOVING",time);truck.position=graph.position(edge,truck.offsetM);
            if(truck.offsetM>=edge.lengthM()-1e-7) {
                truck.position=graph.node(edge.to()).point().coordinates();truck.incomingWay=edge.wayId();truck.edgeIndex++;truck.offsetM=0;
                while(!truck.remainingStops.isEmpty()&&truck.remainingStops.getFirst()==edge.to())truck.remainingStops.removeFirst();
            }
        }
        if(truck.edgeIndex>=truck.route.edgeIds().size()&&truck.arrivalSec<0){truck.arrivalSec=quantize(time);truck.speedKph=0;truck.position=truck.destination.coordinates();changeStatus(truck,"ARRIVED",truck.arrivalSec);}
    }
    public void refresh(boolean forceRecommendations) {
        boolean operationalLog=forceRecommendations||state.clockSec>=nextRecommendationAt;
        for(Truck truck:state.trucks) {
            if(!truck.approvedWaitIncidentIds.isEmpty()) {
                Set<String> approved=new HashSet<>(truck.approvedWaitIncidentIds);
                List<Incident> remaining=state.incidents.stream().filter(i->approved.contains(i.id)&&!"RESOLVED".equals(i.status)&&i.endSec>state.clockSec+1e-8).toList();
                truck.approvedWaitIncidentIds=new ArrayList<>(remaining.stream().map(i->i.id).toList());
                truck.waitUntilSec=remaining.stream().mapToDouble(i->i.endSec).max().orElse(state.clockSec);
            }
            if("ARRIVED".equals(truck.status)){truck.etaKnown=true;truck.remainingDistanceM=0;truck.etaSec=truck.arrivalSec;truck.affectedIncidentIds=new ArrayList<>();truck.risk=new Risk(0,"LOW","RULE_BASED");continue;}
            PredictionService.Estimate estimate=prediction.estimate(state,truck);truck.remainingDistanceM=estimate.remainingDistanceM();truck.etaSec=estimate.arrivalSec();truck.affectedIncidentIds=new ArrayList<>(estimate.incidentIds());truck.risk=prediction.risk(truck,truck.etaSec,prediction.baseRemaining(truck),state.clockSec);
        }
        state.trucks.stream().sorted(Comparator.comparingDouble((Truck t)->t.departureSec).thenComparing(t->t.id)).forEach(t->{t.etaSec=operations.adjustEta(state,t,t.etaSec);t.risk=prediction.risk(t,t.etaSec,prediction.baseRemaining(t),state.clockSec);});
        if(forceRecommendations||state.clockSec>=nextRecommendationAt) {
            state.recommendations=new ArrayList<>();for(Truck truck:state.trucks){Recommendation r=prevention.recommend(state,truck);if(r!=null)state.recommendations.add(r);}nextRecommendationAt=state.clockSec+1;
        }
        int arrived=0,late=0,reroutes=0,waiting=0;double delay=0,distance=0;
        for(Truck truck:state.trucks) {distance+=truck.distanceTravelledM;reroutes+=truck.reroutes;if("WAITING".equals(truck.status)||"BLOCKED".equals(truck.status))waiting++;if("ARRIVED".equals(truck.status)){arrived++;if(truck.arrivalSec>truck.deadlineSec+1e-7)late++;delay+=Math.max(0,truck.arrivalSec-truck.baselineArrivalSec);}}
        int active=(int)state.incidents.stream().filter(i->RoadGraph.active(i,state.clockSec)).count();
        state.kpis=new Kpis(state.trucks.size(),arrived,late,delay,distance,reroutes,waiting,active,arrived);
        operations.refresh(state,this::eventAt,operationalLog);
        state.operations.graph=dependencyGraph.build(state);state.operations.cascade=graphRisk.predict(state,state.operations.graph);
    }
    public Map<String,Object> scenarioConfiguration(){Map<String,Object> result=new LinkedHashMap<>();result.put("version",2);result.put("networkId",state.networkId);result.put("seed",state.randomSeed);result.put("initialClockIso",state.initialClockIso);result.put("trucks",state.trucks.stream().map(t->t.initialAssignment).toList());result.put("operations",state.initialOperations==null?operations.configuration(state):state.initialOperations);result.put("commands",List.copyOf(state.commandHistory));result.put("durationSec",state.clockSec);result.put("operationsProvenance","SIMULATED");return result;}
    @SuppressWarnings("unchecked")
    public void replay(String name,Map<String,Object> config) {
        if(!graph.network.networkId().equals(config.get("networkId")))throw ApiException.conflict("Scenario uses a different immutable network snapshot");
        state=new State();state.networkId=graph.network.networkId();state.scenarioName=name;state.status="PAUSED";state.replaying=true;pendingEvents.clear();nextRecommendationAt=0;
        for(Object spec:(List<?>)config.get("trucks"))state.trucks.add(build(mapper.convertValue(spec,TruckSpec.class)));
        Configuration resources=config.containsKey("operations")?mapper.convertValue(config.get("operations"),Configuration.class):null;operations.configure(state,resources);state.initialOperations=resources;state.randomSeed=((Number)config.getOrDefault("seed",0)).longValue();state.initialClockIso=(String)config.getOrDefault("initialClockIso",state.initialClockIso);
        for(Object command:(List<?>)config.get("commands"))state.replaySchedule.add(mapper.convertValue(command,ScheduledCommand.class));
        state.replaySchedule.sort(Comparator.comparingDouble(ScheduledCommand::clockSec).thenComparingLong(ScheduledCommand::sequence));state.commandHistory=new ArrayList<>(state.replaySchedule);
        event("REPLAY_LOADED","Loaded identical SIMULATED assignments and operator command schedule; paused at clock zero",null,Map.of("seed",0));applyDueCommands();refresh(true);
    }
}
