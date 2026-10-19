package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.OffsetDateTime;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;

/** Explicit feature allowlists prevent realized/future outcome fields leaking into model input. */
public final class GraphSnapshotExporter {
    public static final String VERSION="cascadeshield.graph-snapshot/1.0";
    public record Feature(String name,String dtype,String unit,String provenance) {}
    public record SnapshotNode(String id,String type,String resourceId,Map<String,Double> features,
                               Map<String,Boolean> availableMask,String provenance) {}
    public record SnapshotEdge(String id,String source,String target,String type,double weight,
                               double validFromSec,double validUntilSec,Map<String,Double> features,String provenance) {}
    public record Target(String nodeId,String target,double value,double atClockSec,String provenance,String source) {}
    public record SnapshotTime(double clockSec,String initialClockIso,String simulationTimestamp) {}
    public record Provenance(String geography,String operations,String predictions,String outcomeLabels,
                             String trainingStatus,Map<String,Object> networkSource) {}
    public record GraphSnapshot(String schemaVersion,SnapshotTime simulationTime,String networkId,UUID runId,
                                UUID scenarioId,long randomSeed,Map<String,List<Feature>> featureSchemas,
                                List<SnapshotNode> nodes,List<SnapshotEdge> edges,List<Target> predictions,
                                List<Target> realizedLabels,Provenance provenance) {}
    private final RoadGraph roads;private final ObjectMapper mapper;
    public GraphSnapshotExporter(RoadGraph roads,ObjectMapper mapper){this.roads=roads;this.mapper=mapper;}
    public GraphSnapshot snapshot(State source){State state=mapper.convertValue(source,State.class);List<SnapshotNode> nodes=new ArrayList<>();Map<String,List<Feature>> schemas=new TreeMap<>();Map<String,String> entityIds=new HashMap<>();
        for(GraphNode node:state.operations.graph.nodes().stream().sorted(Comparator.comparing(GraphNode::id)).toList()){
            String kind=node.type().toUpperCase(Locale.ROOT);Map<String,Double> values=features(state,kind,node.resourceId(),node.features());List<Feature> schema=schemas.computeIfAbsent(node.type(),ignored->schema(kind));Map<String,Double> filtered=new LinkedHashMap<>();Map<String,Boolean> mask=new LinkedHashMap<>();for(Feature feature:schema){Double value=values.get(feature.name());if(value!=null&&!Double.isFinite(value))value=null;filtered.put(feature.name(),value);mask.put(feature.name(),value!=null);}nodes.add(new SnapshotNode(node.id(),node.type(),node.resourceId(),Collections.unmodifiableMap(filtered),Collections.unmodifiableMap(mask),node.provenance()));entityIds.put(kind+":"+node.resourceId(),node.id());}
        List<SnapshotEdge> edges=state.operations.graph.edges().stream().sorted(Comparator.comparing(GraphEdge::id)).map(edge->new SnapshotEdge(edge.id(),edge.source(),edge.target(),edge.type(),edge.weight(),edge.validFromSec(),edge.validUntilSec(),Collections.unmodifiableMap(edgeInputs(edge.features())),edge.provenance())).toList();
        List<Target> predictions=new ArrayList<>(),labels=new ArrayList<>();for(Truck truck:state.trucks){String id=entityIds.get("TRUCK:"+truck.id);if(id==null)continue;if(truck.etaKnown)predicted(predictions,id,"estimated_arrival_sec",truck.etaSec,state.clockSec,"RULE_BASED_DIRECT_TRAVEL");predicted(predictions,id,"conditional_road_arrival_sec",truck.etaSec,state.clockSec,"RULE_BASED_DIRECT_TRAVEL_CONDITIONAL_ON_DRIVER");predicted(predictions,id,"direct_risk_score",truck.risk.score(),state.clockSec,"RULE_BASED_DIRECT_TRAVEL");if(truck.arrivalSec>=0&&truck.arrivalSec<=state.clockSec+1e-7){realized(labels,id,"arrival_sec",truck.arrivalSec,state.clockSec);realized(labels,id,"arrival_delay_sec",Math.max(0,truck.arrivalSec-truck.baselineArrivalSec),state.clockSec);}}
        for(NodeRisk risk:state.operations.cascade.nodeRisks())predicted(predictions,risk.nodeId(),"cascade_risk_score",risk.score(),state.clockSec,state.operations.cascade.provider());
        for(Assignment assignment:state.operations.assignments){String truck=entityIds.get("TRUCK:"+assignment.truckId);if(truck!=null){if(!"COMPLETED".equals(assignment.status)){predicted(predictions,truck,"estimated_dock_start_sec",assignment.predictedDockStartSec,state.clockSec,"RULE_BASED_OPERATIONAL_SCHEDULE");predicted(predictions,truck,"estimated_dock_end_sec",assignment.predictedDockEndSec,state.clockSec,"RULE_BASED_OPERATIONAL_SCHEDULE");}if(assignment.actualDockStartSec>=0)realized(labels,truck,"actual_dock_start_sec",assignment.actualDockStartSec,state.clockSec);if(assignment.actualDockEndSec>=0)realized(labels,truck,"actual_dock_end_sec",assignment.actualDockEndSec,state.clockSec);}}
        for(Delivery delivery:state.operations.deliveries){String id=entityIds.get("DELIVERY:"+delivery.id);if(id!=null&&delivery.deliveredAtSec>=0&&delivery.deliveredAtSec<=state.clockSec+1e-7){realized(labels,id,"delivered_at_sec",delivery.deliveredAtSec,state.clockSec);realized(labels,id,"delivery_lateness_sec",delivery.lateSec,state.clockSec);}}
        Comparator<Target> targetOrder=Comparator.comparing(Target::nodeId).thenComparing(Target::target);predictions.sort(targetOrder);labels.sort(targetOrder);String timestamp=OffsetDateTime.parse(state.initialClockIso).plusNanos(Math.round(state.clockSec*1_000_000_000d)).toString();Map<String,Object> network=roads.network.metadata()==null?Map.of():roads.network.metadata();return new GraphSnapshot(VERSION,new SnapshotTime(state.clockSec,state.initialClockIso,timestamp),state.networkId,state.runId,state.scenarioId,state.randomSeed,Collections.unmodifiableMap(schemas),List.copyOf(nodes),edges,List.copyOf(predictions),List.copyOf(labels),new Provenance("REAL_GEOGRAPHIC","SIMULATED","SIMULATED_PREDICTION","SIMULATED_OUTCOME","NO_TRAINED_MODEL",network));}
    private void predicted(List<Target> target,String id,String name,double value,double clock,String provider){if(Double.isFinite(value)&&value>=0)target.add(new Target(id,name,value,clock,"SIMULATED_PREDICTION",provider));}
    private void realized(List<Target> target,String id,String name,double value,double clock){boolean duration=name.endsWith("delay_sec")||name.endsWith("lateness_sec");if(Double.isFinite(value)&&value>=0&&(duration||value<=clock+1e-7))target.add(new Target(id,name,value,clock,"SIMULATED_OUTCOME","AUTHORITATIVE_SIMULATION_ENGINE"));}
    private List<Feature> schema(String type){return switch(type){
        case "TRUCK"->fields("max_speed_kph:km/h","capacity_kg:kg","load_kg:kg","current_speed_kph:km/h","distance_travelled_m:m","remaining_distance_m:m","edge_offset_m:m","departure_sec:s","deadline_sec:s","wait_until_sec:s");
        case "DRIVER"->fields("available:boolean","shift_start_sec:s","shift_end_sec:s","duty_sec:s");
        case "DOCK"->fields("service_sec:s","open_from_sec:s","open_until_sec:s");
        case "DELIVERY"->fields("load_kg:kg","deadline_sec:s","priority:ordinal");
        case "WAREHOUSE"->fields("dock_capacity:count","longitude:degrees","latitude:degrees");
        case "INCIDENT"->fields("severity:score","start_sec:s","end_sec:s","is_closure:boolean");
        case "ROAD","ROAD_SEGMENT"->fields("length_m:m","speed_kph:km/h");
        default->List.of();};}
    private List<Feature> fields(String... values){return Arrays.stream(values).map(value->{int colon=value.indexOf(':');return new Feature(value.substring(0,colon),"float64",value.substring(colon+1),"SIMULATED_INPUT");}).toList();}
    private Map<String,Double> features(State state,String type,String id,Map<String,Object> existing){Map<String,Double> values=new LinkedHashMap<>();switch(type){
        case "TRUCK"->{state.trucks.stream().filter(t->t.id.equals(id)).findFirst().ifPresent(t->{values.put("max_speed_kph",t.maxSpeedKph);values.put("capacity_kg",t.capacityKg);values.put("load_kg",t.loadKg);values.put("current_speed_kph",t.speedKph);values.put("distance_travelled_m",t.distanceTravelledM);values.put("remaining_distance_m",t.remainingDistanceM);values.put("edge_offset_m",t.offsetM);values.put("departure_sec",t.departureSec);values.put("deadline_sec",t.deadlineSec);values.put("wait_until_sec",t.waitUntilSec);});}
        case "DRIVER"->{state.operations.drivers.stream().filter(t->t.id.equals(id)).findFirst().ifPresent(t->{values.put("available",t.available?1d:0d);values.put("shift_start_sec",t.shiftStartSec);values.put("shift_end_sec",t.shiftEndSec);values.put("duty_sec",t.dutySec);});}
        case "DOCK"->{state.operations.docks.stream().filter(t->t.id.equals(id)).findFirst().ifPresent(t->{values.put("service_sec",t.serviceSec);values.put("open_from_sec",t.openFromSec);values.put("open_until_sec",t.openUntilSec);});}
        case "DELIVERY"->{state.operations.deliveries.stream().filter(t->t.id.equals(id)).findFirst().ifPresent(t->{values.put("load_kg",t.loadKg);values.put("deadline_sec",t.deadlineSec);values.put("priority",switch(t.priority==null?"NORMAL":t.priority.toUpperCase(Locale.ROOT)){case "HIGH"->2d;case "LOW"->0d;default->1d;});});}
        case "WAREHOUSE"->{state.operations.warehouses.stream().filter(t->t.id.equals(id)).findFirst().ifPresent(t->{values.put("dock_capacity",(double)t.dockCapacity);if(t.location!=null){values.put("longitude",t.location.longitude());values.put("latitude",t.location.latitude());}});}
        case "INCIDENT"->{state.incidents.stream().filter(t->t.id.equals(id)).findFirst().ifPresent(t->{values.put("severity",t.severity);values.put("start_sec",t.startSec);values.put("end_sec",t.endSec);values.put("is_closure","CLOSURE".equals(t.type)?1d:0d);});}
        case "ROAD","ROAD_SEGMENT"->{if(existing!=null){numeric(values,"length_m",existing.get("lengthM"));numeric(values,"speed_kph",existing.get("speedKph"));}}
        default->{} }return values;}
    private void numeric(Map<String,Double> out,String name,Object value){if(value instanceof Number number&&Double.isFinite(number.doubleValue()))out.put(name,number.doubleValue());}
    private Map<String,Double> edgeInputs(Map<String,Object> source){Map<String,Double> out=new TreeMap<>();if(source!=null)for(String key:List.of("reservationStartSec","reservationEndSec","serviceSec","capacityKg","loadKg"))numeric(out,key,source.get(key));return out;}
}
