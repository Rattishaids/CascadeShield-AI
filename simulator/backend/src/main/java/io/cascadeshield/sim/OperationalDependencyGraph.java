package io.cascadeshield.sim;

import java.util.*;
import org.jgrapht.Graph;
import org.jgrapht.graph.DirectedWeightedMultigraph;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;

/** Dependency exposure between explicitly configured simulated operational resources. */
public final class OperationalDependencyGraph {
    public static final String SCHEMA_VERSION = "cascadeshield.operational-graph/1.0";
    private static final double HORIZON = 172_800;

    public GraphView build(State state) {
        Operations ops = state.operations;
        SortedMap<String,GraphNode> nodes = new TreeMap<>();
        SortedMap<String,GraphEdge> edges = new TreeMap<>();
        Map<String,Truck> trucks = new TreeMap<>();
        Map<String,Dock> docks = new TreeMap<>();
        Map<String,Driver> drivers = new TreeMap<>();
        Map<String,Delivery> deliveries = new TreeMap<>();
        Map<String,Assignment> assignments = new TreeMap<>();
        for (Truck t : state.trucks) {
            trucks.put(t.id,t);
            node(nodes,"TRUCK",t.id,features("name",t.name,"status",t.status,"departureSec",t.departureSec,
                    "etaSec",t.etaSec,"arrivalSec",t.arrivalSec,"deadlineSec",t.deadlineSec,
                    "remainingDistanceM",t.remainingDistanceM,"loadKg",t.loadKg,"capacityKg",t.capacityKg,
                    "directTravelRisk",t.risk.score(),"etaKnown",t.etaKnown));
        }
        for (Warehouse w : ops.warehouses) node(nodes,"WAREHOUSE",w.id,features("name",w.name,
                "longitude",w.location.longitude(),"latitude",w.location.latitude(),"roadNodeId",w.nodeId,
                "dockCapacity",w.dockCapacity));
        for (Dock d : ops.docks) {
            docks.put(d.id,d);
            node(nodes,"DOCK",d.id,features("name",d.name,"warehouseId",d.warehouseId,"status",d.status,
                    "serviceSec",d.serviceSec,"openFromSec",d.openFromSec,"openUntilSec",d.openUntilSec,
                    "occupiedBy",d.occupiedBy));
        }
        for (Driver d : ops.drivers) {
            drivers.put(d.id,d);
            node(nodes,"DRIVER",d.id,features("name",d.name,"available",d.available,"status",d.status,
                    "shiftStartSec",d.shiftStartSec,"shiftEndSec",d.shiftEndSec,"dutySec",d.dutySec,
                    "occupiedBy",d.occupiedBy));
        }
        for (Delivery d : ops.deliveries) {
            deliveries.put(d.id,d);
            node(nodes,"DELIVERY",d.id,features("name",d.name,"warehouseId",d.warehouseId,"status",d.status,
                    "priority",d.priority,"deadlineSec",d.deadlineSec,"loadKg",d.loadKg,
                    "deliveredAtSec",d.deliveredAtSec,"lateSec",d.lateSec,"truckId",d.truckId));
        }
        for (Assignment a : ops.assignments) assignments.put(a.truckId,a);

        // Assignment exposure is current or forecast, ending when work actually completes.
        for (Assignment a : assignments.values()) {
            Truck t = trucks.get(a.truckId);
            if (t == null) continue;
            double from = Math.max(0,t.departureSec);
            double until = a.actualDockEndSec >= 0 ? a.actualDockEndSec
                    : Math.max(Math.max(a.predictedDockEndSec,a.reservationEndSec),t.etaSec);
            if (until <= from && a.actualDockEndSec < 0) until = HORIZON;
            String truck = id("TRUCK",a.truckId);
            Map<String,Object> f = features("assignmentStatus",a.status,"meaning","delay of truck can affect its assigned resource",
                    "reservationStartSec",a.reservationStartSec,"reservationEndSec",a.reservationEndSec,
                    "predictedDockStartSec",a.predictedDockStartSec,"predictedDockEndSec",a.predictedDockEndSec,
                    "weightSource","DOCUMENTED_RULE_BASELINE");
            Driver driver=drivers.get(a.driverId);
            double driverUntil=driver == null ? until : driverRelease(t,driver);
            edge(nodes,edges,truck,id("DRIVER",a.driverId),"ASSIGNED_DRIVER",from,driverUntil,.80,f,a.truckId);
            edge(nodes,edges,truck,id("DOCK",a.dockId),"RESERVED_DOCK",from,until,.90,f,a.truckId);
            for (String delivery : new TreeSet<>(a.deliveryIds)) edge(nodes,edges,truck,id("DELIVERY",delivery),
                    "CARRIES_DELIVERY",from,until,.95,f,a.truckId);
        }
        for (Dock d : docks.values()) edge(nodes,edges,id("DOCK",d.id),id("WAREHOUSE",d.warehouseId),
                "DOCK_AT_WAREHOUSE",0,Math.max(0,d.openUntilSec),.75,
                features("meaning","dock service exposure contributes to its configured warehouse","weightSource","DOCUMENTED_RULE_BASELINE"),d.id);
        for (Delivery d : deliveries.values()) edge(nodes,edges,id("DELIVERY",d.id),id("WAREHOUSE",d.warehouseId),
                "DELIVERY_TO_WAREHOUSE",0,d.deliveredAtSec >= 0 ? d.deliveredAtSec : HORIZON,.70,
                features("meaning","delivery lateness affects its configured destination warehouse","weightSource","DOCUMENTED_RULE_BASELINE"),d.id);

        // Runtime computes schedule consequences. A blocker truck reference never invents a new entity.
        for (Impact impact : ops.predictedImpacts) {
            if (!impact.predicted() || impact.endSec() <= state.clockSec) continue;
            double weight = clamp(.50 + .50 * Math.min(1,Math.max(0,impact.delaySec()) / 600));
            for (String resource : new TreeSet<>(impact.resourceIds())) {
                if (resource.startsWith("TRUCK:") || !nodes.containsKey(resource)) continue;
                for (String waitingTruck : new TreeSet<>(impact.truckIds())) {
                    Assignment a = assignments.get(waitingTruck);
                    if (!explicitlyLinked(resource,a,docks,deliveries)) continue;
                    edge(nodes,edges,resource,id("TRUCK",waitingTruck),impact.code(),impact.startSec(),impact.endSec(),weight,
                            features("impactId",impact.id(),"predicted",true,"delaySec",impact.delaySec(),
                                    "resourceIds",impact.resourceIds(),"meaning",impact.message(),
                                    "weightSource","DOCUMENTED_RULE_BASELINE"),impact.id());
                }
            }
        }

        // Preserve a conflict even before runtime forecasting has populated Impact records.
        // Interval ordering identifies the preceding blocker; no symmetric cross-country links exist.
        List<Assignment> ordered = new ArrayList<>(assignments.values());
        ordered.sort(Comparator.comparingDouble((Assignment a) -> projectedStart(a,trucks.get(a.truckId))).thenComparing(a -> a.truckId));
        for (int i=0;i<ordered.size();i++) for (int j=i+1;j<ordered.size();j++) {
            Assignment first=ordered.get(i), next=ordered.get(j);
            Truck ta=trucks.get(first.truckId), tb=trucks.get(next.truckId);
            if (ta == null || tb == null || "COMPLETED".equals(first.status) || "COMPLETED".equals(next.status)
                    || !ta.etaKnown || !tb.etaKnown) continue;
            if (Objects.equals(first.dockId,next.dockId) && docks.containsKey(first.dockId)) {
                Dock dock=docks.get(first.dockId);
                double firstStart=projectedStart(first,ta), firstEnd=projectedEnd(first,ta,dock);
                double wantedStart=ceilTick(Math.max(Math.max(tb.etaSec,next.reservationStartSec),Math.max(state.clockSec,dock.openFromSec)));
                double wantedEnd=ceilTick(wantedStart+dock.serviceSec);
                if (overlap(firstStart,firstEnd,wantedStart,wantedEnd) && firstEnd > state.clockSec) {
                    double delay=Math.max(0,firstEnd-wantedStart);
                    edge(nodes,edges,id("DOCK",dock.id),id("TRUCK",next.truckId),"SHARED_DOCK_CONFLICT",
                            Math.max(firstStart,wantedStart),firstEnd,clamp(.50+.50*Math.min(1,delay/600)),
                            features("blockerTruckId",first.truckId,"delaySec",delay,"predicted",true,
                                    "meaning","preceding explicit dock interval overlaps dependent reservation",
                                    "weightSource","DOCUMENTED_RULE_BASELINE"),first.truckId+"/"+next.truckId);
                }
            }
        }

        // Driver order follows departure/duty, which can differ from warehouse arrival order.
        ordered.sort(Comparator.comparingDouble((Assignment a) -> trucks.containsKey(a.truckId) ? trucks.get(a.truckId).departureSec : HORIZON).thenComparing(a -> a.truckId));
        for (int i=0;i<ordered.size();i++) for (int j=i+1;j<ordered.size();j++) {
            Assignment first=ordered.get(i),next=ordered.get(j);
            Truck ta=trucks.get(first.truckId),tb=trucks.get(next.truckId);
            if (ta == null || tb == null || ta.arrivalSec >= 0 || tb.arrivalSec >= 0
                    || !ta.etaKnown || !tb.etaKnown
                    || !Objects.equals(first.driverId,next.driverId) || !drivers.containsKey(first.driverId)) continue;
            Driver driver=drivers.get(first.driverId);
            double firstEnd=driverRelease(ta,driver),nextEnd=driverRelease(tb,driver);
            if (overlap(ta.departureSec,firstEnd,tb.departureSec,nextEnd) && firstEnd > state.clockSec) {
                double delay=Math.max(0,firstEnd-tb.departureSec);
                edge(nodes,edges,id("DRIVER",first.driverId),id("TRUCK",next.truckId),"SHARED_DRIVER_CONFLICT",
                        Math.max(ta.departureSec,tb.departureSec),Math.min(firstEnd,nextEnd),clamp(.50+.50*Math.min(1,delay/600)),
                        features("blockerTruckId",first.truckId,"delaySec",delay,"predicted",true,
                                "meaning","preceding explicit driver duty interval overlaps dependent trip",
                                "weightSource","DOCUMENTED_RULE_BASELINE"),first.truckId+"/"+next.truckId);
            }
        }

        GraphView view = new GraphView(SCHEMA_VERSION,state.clockSec,state.networkId,
                List.copyOf(nodes.values()),List.copyOf(edges.values()),"SIMULATED");
        // The actual heterogeneous dependency graph uses JGraphT; REST has a stable library-neutral DTO.
        Graph<String,GraphEdge> graph=materialize(view);
        return new GraphView(view.schemaVersion(),view.clockSec(),view.networkId(),view.nodes(),
                graph.edgeSet().stream().sorted(Comparator.comparing(GraphEdge::id)).toList(),view.provenance());
    }

    public static Graph<String,GraphEdge> materialize(GraphView view) {
        Graph<String,GraphEdge> graph=new DirectedWeightedMultigraph<>(null,null);
        view.nodes().stream().sorted(Comparator.comparing(GraphNode::id)).forEach(n -> graph.addVertex(n.id()));
        for (GraphEdge e : view.edges().stream().sorted(Comparator.comparing(GraphEdge::id)).toList()) {
            if (!graph.containsVertex(e.source()) || !graph.containsVertex(e.target()) || e.source().equals(e.target())) continue;
            if (!Double.isFinite(e.weight()) || e.weight() < 0 || e.weight() > 1)
                throw new IllegalArgumentException("Dependency weights must be finite within [0,1]");
            if (!Double.isFinite(e.validFromSec()) || !Double.isFinite(e.validUntilSec()) || e.validFromSec() < 0 || e.validUntilSec() <= e.validFromSec())
                throw new IllegalArgumentException("Dependency validity must be a nonempty finite interval");
            if (graph.addEdge(e.source(),e.target(),e)) graph.setEdgeWeight(e,e.weight());
        }
        return graph;
    }

    private static boolean explicitlyLinked(String resource,Assignment a,Map<String,Dock> docks,Map<String,Delivery> deliveries) {
        if (a == null) return false;
        if (resource.equals(id("DRIVER",a.driverId)) || resource.equals(id("DOCK",a.dockId))) return true;
        for (String delivery : a.deliveryIds) {
            if (resource.equals(id("DELIVERY",delivery))) return true;
            Delivery d=deliveries.get(delivery);
            if (d != null && resource.equals(id("WAREHOUSE",d.warehouseId))) return true;
        }
        Dock d=docks.get(a.dockId);
        return d != null && resource.equals(id("WAREHOUSE",d.warehouseId));
    }
    private static double projectedStart(Assignment a,Truck t) {
        return a.actualDockStartSec >= 0 ? a.actualDockStartSec : Math.max(a.predictedDockStartSec,
                Math.max(a.reservationStartSec,t == null ? 0 : t.etaSec));
    }
    private static double projectedEnd(Assignment a,Truck t,Dock dock) {
        return a.actualDockEndSec >= 0 ? a.actualDockEndSec
                : Math.max(a.predictedDockEndSec,projectedStart(a,t)+dock.serviceSec);
    }
    private static double driverRelease(Truck t,Driver driver) {
        return t.arrivalSec >= 0 ? t.arrivalSec : t.etaKnown ? t.etaSec : driver.shiftEndSec;
    }
    private static double ceilTick(double time) {return Math.ceil(time*10-1e-8)/10d;}
    private static boolean overlap(double a,double b,double c,double d) {return Math.max(a,c) < Math.min(b,d);}
    private static String id(String type,String resource) {return type+":"+resource;}
    private static void node(Map<String,GraphNode> nodes,String type,String resource,Map<String,Object> features) {
        nodes.put(id(type,resource),new GraphNode(id(type,resource),type,resource,features,"SIMULATED"));
    }
    private static void edge(Map<String,GraphNode> nodes,Map<String,GraphEdge> edges,String source,String target,String type,
                             double from,double until,double weight,Map<String,Object> features,String qualifier) {
        if (!nodes.containsKey(source) || !nodes.containsKey(target) || source.equals(target)
                || !Double.isFinite(from) || !Double.isFinite(until) || until <= from) return;
        String key=source+"->"+target+"|"+type+"|"+qualifier;
        edges.put(key,new GraphEdge(key,source,target,type,Math.max(0,from),until,clamp(weight),features,"SIMULATED"));
    }
    private static Map<String,Object> features(Object... pairs) {
        SortedMap<String,Object> result=new TreeMap<>();
        for (int i=0;i<pairs.length;i+=2) if (pairs[i+1] != null) result.put((String)pairs[i],pairs[i+1]);
        return Collections.unmodifiableMap(result);
    }
    private static double clamp(double n) {return Math.max(0,Math.min(1,n));}
}
