package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.security.MessageDigest;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;

/** One prediction-time feature contract shared by offline training and read-only live inference. */
public final class MlFeatureExtractor {
    public static final String VERSION="cascadeshield.ml-features/1.0";
    public static final List<String> FEATURE_NAMES=List.of("clock_sec","remaining_distance_m","max_speed_kph","current_speed_kph",
        "departure_remaining_sec","deadline_slack_sec","load_kg","capacity_kg","driver_available","driver_shift_remaining_sec",
        "driver_duty_sec","dock_service_sec","dock_open_remaining_sec","reservation_start_remaining_sec","reservation_end_remaining_sec",
        "dock_occupied","dock_queue_count","warehouse_dock_capacity","known_incident_count","route_closure_count","route_slowdown_count",
        "route_max_severity","known_incident_remaining_sec","graph_in_degree","graph_out_degree","graph_risk_score",
        "rule_road_remaining_sec","rule_dock_remaining_sec","rule_eta_known","priority_high","wait_remaining_sec","distance_speed_remaining_sec");
    public static final Set<String> DERIVED=Set.of("graph_in_degree","graph_out_degree","graph_risk_score","rule_road_remaining_sec","rule_dock_remaining_sec","rule_eta_known");
    private final RoadGraph roads; private final ObjectMapper mapper; private final CounterfactualExperimentEngine copies;
    public MlFeatureExtractor(RoadGraph roads,ObjectMapper mapper){this.roads=roads;this.mapper=mapper;copies=new CounterfactualExperimentEngine(roads,mapper);}
    public String featureSchemaHash(){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(mapper.writeValueAsBytes(FEATURE_NAMES)));}catch(Exception e){throw new IllegalStateException(e);}}
    public Map<String,Object> featureSchema(){return Map.of("schemaVersion",VERSION,"featureSchemaHash",featureSchemaHash(),"featureNames",FEATURE_NAMES,"derivedFeatureNames",DERIVED.stream().sorted().toList(),
        "missingValueEncoding","JSON null; fitted development-only imputation and missing mask","provenance","SIMULATED_INPUT_WITH_EXPLICIT_RULE_DERIVED_FEATURES");}
    /** Never returns labels, private schedules, realized outcome records or a mutable authoritative state. */
    public Map<String,Object> frame(State source){
        State s=copies.observedClone(source);Map<String,Object> result=new LinkedHashMap<>();
        result.put("schemaVersion","cascadeshield.ml-frame/1.0");result.put("featureSchemaVersion",VERSION);result.put("clockSec",s.clockSec);
        result.put("featureSchemaHash",featureSchemaHash());
        result.put("stateFingerprint",copies.fingerprint(s));result.put("networkId",s.networkId);
        @SuppressWarnings("unchecked") Map<String,Object> graph=mapper.convertValue(new GraphSnapshotExporter(roads,mapper).snapshot(s),Map.class);
        graph.put("realizedLabels",List.of());result.put("graphSnapshot",graph);
        List<Map<String,Object>> trucks=new ArrayList<>();
        for(Truck t:s.trucks.stream().sorted(Comparator.comparing(x->x.id)).toList()){
            Assignment a=OperationalRuntime.assignment(s,t.id);Driver driver=a==null?null:OperationalRuntime.driver(s,a.driverId);
            Dock dock=a==null?null:OperationalRuntime.dock(s,a.dockId);Warehouse warehouse=dock==null?null:s.operations.warehouses.stream().filter(w->w.id.equals(dock.warehouseId)).findFirst().orElse(null);
            List<String> deliveryIds=a==null?List.of():List.copyOf(a.deliveryIds);List<Delivery> deliveries=s.operations.deliveries.stream().filter(d->deliveryIds.contains(d.id)).toList();
            double deadline=deliveries.stream().mapToDouble(d->d.deadlineSec).min().orElse(t.deadlineSec);
            Set<String> remaining=new HashSet<>();if(t.route!=null)for(String id:t.route.edgeIds().subList(Math.min(t.edgeIndex,t.route.edgeIds().size()),t.route.edgeIds().size()))remaining.add(roads.edge(id).physicalId());
            List<Incident> exposed=s.incidents.stream().filter(i->RoadGraph.active(i,s.clockSec)&&remaining.contains(i.physicalId)).toList();
            double roadRemaining=Math.max(0,t.etaSec-s.clockSec);Double dockRemaining=a!=null&&a.predictedDockEndSec>=0&&(t.etaKnown||t.arrivalSec>=0)?Math.max(0,a.predictedDockEndSec-s.clockSec):null;
            Map<String,Double> f=new LinkedHashMap<>();for(String key:FEATURE_NAMES)f.put(key,null);
            f.put("clock_sec",s.clockSec);f.put("remaining_distance_m",t.remainingDistanceM);f.put("max_speed_kph",t.maxSpeedKph);f.put("current_speed_kph",t.speedKph);
            f.put("departure_remaining_sec",Math.max(0,t.departureSec-s.clockSec));f.put("deadline_slack_sec",deadline-s.clockSec);f.put("load_kg",t.loadKg);f.put("capacity_kg",t.capacityKg);
            if(driver!=null){f.put("driver_available",driver.available?1d:0d);f.put("driver_shift_remaining_sec",driver.shiftEndSec-s.clockSec);f.put("driver_duty_sec",driver.dutySec);}
            if(dock!=null){f.put("dock_service_sec",dock.serviceSec);f.put("dock_open_remaining_sec",dock.openUntilSec-s.clockSec);f.put("dock_occupied",dock.occupiedBy==null?0d:1d);f.put("dock_queue_count",(double)s.operations.assignments.stream().filter(x->x.dockId.equals(dock.id)&&"QUEUED".equals(x.status)).count());}
            if(a!=null){f.put("reservation_start_remaining_sec",a.reservationStartSec-s.clockSec);f.put("reservation_end_remaining_sec",a.reservationEndSec-s.clockSec);}
            if(warehouse!=null)f.put("warehouse_dock_capacity",(double)warehouse.dockCapacity);
            f.put("known_incident_count",(double)s.incidents.size());f.put("route_closure_count",(double)exposed.stream().filter(i->"CLOSURE".equals(i.type)).count());
            f.put("route_slowdown_count",(double)exposed.stream().filter(i->"SLOWDOWN".equals(i.type)).count());f.put("route_max_severity",exposed.stream().mapToDouble(i->i.severity).max().orElse(0));
            f.put("known_incident_remaining_sec",exposed.stream().mapToDouble(i->Math.max(0,i.endSec-s.clockSec)).max().orElse(0));String node="TRUCK:"+t.id;
            f.put("graph_in_degree",(double)s.operations.graph.edges().stream().filter(e->e.target().equals(node)&&e.validUntilSec()>s.clockSec).count());
            f.put("graph_out_degree",(double)s.operations.graph.edges().stream().filter(e->e.source().equals(node)&&e.validUntilSec()>s.clockSec).count());
            f.put("graph_risk_score",s.operations.cascade.nodeRisks().stream().filter(n->n.nodeId().equals(node)).mapToDouble(NodeRisk::score).findFirst().orElse(0));
            f.put("rule_road_remaining_sec",roadRemaining);f.put("rule_dock_remaining_sec",dockRemaining);f.put("rule_eta_known",t.etaKnown?1d:0d);
            f.put("priority_high","HIGH".equals(t.priority)?1d:0d);f.put("wait_remaining_sec",Math.max(0,t.waitUntilSec-s.clockSec));
            f.put("distance_speed_remaining_sec",t.maxSpeedKph>0?t.remainingDistanceM/(t.maxSpeedKph/3.6):null);
            Map<String,Object> baseline=new LinkedHashMap<>();baseline.put("remainingArrivalSec",t.etaKnown?roadRemaining:null);baseline.put("deliveryCompletionSec",dockRemaining==null?null:s.clockSec+dockRemaining);
            baseline.put("slackRisk",dockRemaining==null?null:(s.clockSec+dockRemaining>deadline+1e-7?1d:0d));baseline.put("graphRisk",f.get("graph_risk_score"));
            Map<String,Object> row=new LinkedHashMap<>();row.put("truckId",t.id);row.put("deliveryIds",deliveryIds);row.put("etaEligible",t.arrivalSec<0);
            row.put("deliveryEligible",!deliveries.isEmpty()&&deliveries.stream().anyMatch(d->d.deliveredAtSec<0));row.put("features",f);row.put("baseline",baseline);trucks.add(row);
        }
        result.put("trucks",trucks);result.put("provenance","SIMULATED_PREDICTION_INPUT");return result;
    }
}
