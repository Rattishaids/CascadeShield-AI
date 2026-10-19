package io.cascadeshield.sim;

import java.util.*;
import static io.cascadeshield.sim.Models.*;

/** Explicitly simulated resources. These are never historical freight records. */
public final class OpsModels {
    private OpsModels() {}
    public record WarehouseSpec(String id,String name,Point location,int dockCapacity) {}
    public record DockSpec(String id,String name,String warehouseId,double serviceSec,double openFromSec,double openUntilSec) {}
    public record DriverSpec(String id,String name,boolean available,double shiftStartSec,double shiftEndSec) {}
    public record DeliverySpec(String id,String name,String warehouseId,double loadKg,double deadlineSec,String priority) {}
    public record AssignmentSpec(String truckId,String driverId,String dockId,List<String> deliveryIds,double reservationStartSec,double reservationEndSec) {}
    public record AvailabilityRequest(Boolean available) {}
    public record Configuration(List<WarehouseSpec> warehouses,List<DockSpec> docks,List<DriverSpec> drivers,List<DeliverySpec> deliveries,List<AssignmentSpec> assignments) {}
    public static class Warehouse {public String id,name,provenance="SIMULATED";public Point location;public long nodeId;public int dockCapacity;}
    public static class Dock {public String id,name,warehouseId,status="AVAILABLE",provenance="SIMULATED";public double serviceSec,openFromSec,openUntilSec;public String occupiedBy;}
    public static class Driver {public String id,name,status="IDLE",provenance="SIMULATED";public boolean available;public double shiftStartSec,shiftEndSec,dutySec;public String occupiedBy;}
    public static class Delivery {public String id,name,warehouseId,priority,status="UNASSIGNED",provenance="SIMULATED";public double loadKg,deadlineSec,deliveredAtSec=-1,lateSec=0;public String truckId;}
    public static class Assignment {public String truckId,driverId,dockId,status="PLANNED",provenance="SIMULATED";public List<String> deliveryIds=new ArrayList<>();public double reservationStartSec,reservationEndSec,predictedDockStartSec,predictedDockEndSec,actualDockStartSec=-1,actualDockEndSec=-1,queueSec=0;}
    public record Impact(String id,String code,List<String> resourceIds,List<String> truckIds,double startSec,double endSec,double delaySec,boolean predicted,String message,String provenance) {}
    public record OpsKpis(int deliveries,int delivered,int lateDeliveries,int queuedTrucks,int unloadingTrucks,int constrainedDrivers,double deliveryDelaySec) {}
    public record GraphNode(String id,String type,String resourceId,Map<String,Object> features,String provenance) {}
    public record GraphEdge(String id,String source,String target,String type,double validFromSec,double validUntilSec,double weight,Map<String,Object> features,String provenance) {}
    public record GraphView(String schemaVersion,double clockSec,String networkId,List<GraphNode> nodes,List<GraphEdge> edges,String provenance) {}
    public record NodeRisk(String nodeId,double score,boolean direct,List<String> causeIds) {}
    public record CascadeView(String provider,double threshold,int iterations,List<NodeRisk> nodeRisks,List<String> affectedNodeIds,List<String> affectedEdgeIds,String provenance) {}
    public static class Operations {
        public List<Warehouse> warehouses=new ArrayList<>();public List<Dock> docks=new ArrayList<>();public List<Driver> drivers=new ArrayList<>();public List<Delivery> deliveries=new ArrayList<>();public List<Assignment> assignments=new ArrayList<>();
        public List<Impact> predictedImpacts=new ArrayList<>(),realizedImpacts=new ArrayList<>();
        public List<String> activeRealizedKeys=new ArrayList<>(),activePredictedKeys=new ArrayList<>();
        public GraphView graph=new GraphView("cascadeshield.operational-graph/1.0",0,"",List.of(),List.of(),"SIMULATED");
        public CascadeView cascade=new CascadeView("RULE_BASED_GRAPH_BASELINE",.35,0,List.of(),List.of(),List.of(),"SIMULATED_PREDICTION");
        public OpsKpis kpis=new OpsKpis(0,0,0,0,0,0,0);
    }
}
