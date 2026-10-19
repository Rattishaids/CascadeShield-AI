package io.cascadeshield.sim;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;

class OperationalDependencyGraphTest {
    private final OperationalDependencyGraph builder=new OperationalDependencyGraph();

    @Test void explicitAssignmentsCreateTypedDirectedDependenciesWithSimulatedProvenance() {
        State state=fixture();
        GraphView graph=builder.build(state);
        assertEquals(7,graph.nodes().size());
        assertTrue(graph.nodes().stream().allMatch(n -> n.provenance().equals("SIMULATED")));
        assertTrue(graph.edges().stream().allMatch(e -> e.provenance().equals("SIMULATED") && e.weight() >= 0 && e.weight() <= 1));
        assertTrue(graph.edges().stream().anyMatch(e -> e.source().equals("TRUCK:T1") && e.target().equals("DRIVER:DR1") && e.type().equals("ASSIGNED_DRIVER")));
        assertTrue(graph.edges().stream().anyMatch(e -> e.source().equals("TRUCK:T1") && e.target().equals("DOCK:D1")));
        assertTrue(graph.edges().stream().anyMatch(e -> e.source().equals("TRUCK:T1") && e.target().equals("DELIVERY:L1")));
        assertTrue(graph.edges().stream().anyMatch(e -> e.source().equals("DELIVERY:L1") && e.target().equals("WAREHOUSE:W1")));
        assertEquals("cascadeshield.operational-graph/1.0",graph.schemaVersion());
        assertEquals("real-test-network",graph.networkId());
        assertTrue(OperationalDependencyGraph.materialize(graph).getType().isDirected());
        assertTrue(OperationalDependencyGraph.materialize(graph).getType().isWeighted());
    }

    @Test void sharedDockConflictRequiresActualOverlapOnSameConfiguredResource() {
        State state=fixture();
        state.trucks.get(0).etaSec=160;
        state.operations.assignments.get(0).predictedDockStartSec=160;
        state.operations.assignments.get(0).predictedDockEndSec=220;
        GraphView graph=builder.build(state);
        GraphEdge conflict=graph.edges().stream().filter(e -> e.type().equals("SHARED_DOCK_CONFLICT")).findFirst().orElseThrow();
        assertEquals("DOCK:D1",conflict.source());
        assertEquals("TRUCK:T2",conflict.target());
        assertEquals(180,conflict.validFromSec(),1e-9);
        assertEquals(220,conflict.validUntilSec(),1e-9);
        state.trucks.get(1).etaSec=300;
        state.operations.assignments.get(1).reservationStartSec=300;
        assertTrue(builder.build(state).edges().stream().noneMatch(e -> e.type().equals("SHARED_DOCK_CONFLICT")));
    }

    @Test void sharedDriverConflictUsesExplicitDutyIntervals() {
        State state=fixture();
        state.operations.assignments.get(1).driverId="DR1";
        state.trucks.get(0).etaSec=150;
        state.trucks.get(1).departureSec=120;
        assertTrue(builder.build(state).edges().stream().anyMatch(e -> e.type().equals("SHARED_DRIVER_CONFLICT") && e.target().equals("TRUCK:T2")));
        state.trucks.get(1).departureSec=300;
        assertTrue(builder.build(state).edges().stream().noneMatch(e -> e.type().equals("SHARED_DRIVER_CONFLICT")));
    }

    @Test void impactEdgesUseDependentTruckOnlyAndIgnoreInventedResourceLinks() {
        State state=fixture();
        state.operations.predictedImpacts.add(new Impact("P1","DOCK_OVERLAP",List.of("DOCK:D1","TRUCK:T1"),List.of("T2"),180,220,40,true,"computed queue","SIMULATED_PREDICTION"));
        state.operations.predictedImpacts.add(new Impact("P2","DRIVER_OVERLAP",List.of("DRIVER:DR1"),List.of("T2"),180,220,40,true,"unrelated driver","SIMULATED_PREDICTION"));
        GraphView graph=builder.build(state);
        assertTrue(graph.edges().stream().anyMatch(e -> e.type().equals("DOCK_OVERLAP") && e.source().equals("DOCK:D1") && e.target().equals("TRUCK:T2")));
        assertTrue(graph.edges().stream().noneMatch(e -> e.type().equals("DRIVER_OVERLAP")));
        assertTrue(graph.edges().stream().noneMatch(e -> e.source().equals("TRUCK:T1") && e.target().equals("TRUCK:T2")));
    }

    @Test void completedWorkClosesValidityAndStopsNewConflicts() {
        State state=fixture();
        state.clockSec=200;
        state.operations.assignments.get(0).actualDockEndSec=160;
        state.operations.assignments.get(0).status="COMPLETED";
        GraphView graph=builder.build(state);
        assertTrue(graph.edges().stream().filter(e -> e.source().equals("TRUCK:T1") && !e.type().equals("ASSIGNED_DRIVER")).allMatch(e -> e.validUntilSec() == 160));
        assertEquals(100,graph.edges().stream().filter(e -> e.source().equals("TRUCK:T1") && e.type().equals("ASSIGNED_DRIVER")).findFirst().orElseThrow().validUntilSec());
        assertTrue(graph.edges().stream().noneMatch(e -> e.type().equals("SHARED_DOCK_CONFLICT") || e.type().equals("SHARED_DRIVER_CONFLICT")));
    }

    @Test void unloadingEndIsAnOccupiedIntervalRatherThanAlreadyCompletedWork() {
        State state=fixture();state.clockSec=170;
        Truck a=state.trucks.get(0);a.arrivalSec=160;a.etaSec=160;
        Assignment assignment=state.operations.assignments.get(0);
        assignment.status="UNLOADING";assignment.actualDockStartSec=160;assignment.actualDockEndSec=220;
        state.operations.docks.get(0).occupiedBy="T1";
        assertTrue(builder.build(state).edges().stream().anyMatch(e -> e.type().equals("SHARED_DOCK_CONFLICT") && e.target().equals("TRUCK:T2")));
    }

    @Test void driverReleaseAtRoadArrivalDoesNotInventDockServiceDutyOverlap() {
        State state=fixture();state.operations.assignments.get(1).driverId="DR1";
        state.trucks.get(1).departureSec=120;
        assertTrue(builder.build(state).edges().stream().noneMatch(e -> e.type().equals("SHARED_DRIVER_CONFLICT")));
        state.trucks.get(0).arrivalSec=100;state.clockSec=130;
        assertTrue(builder.build(state).edges().stream().noneMatch(e -> e.type().equals("SHARED_DRIVER_CONFLICT")));
    }

    @Test void driverBlockerOrderFollowsDepartureWhenArrivalOrderDiffers() {
        State state=fixture();state.operations.assignments.get(1).driverId="DR1";
        state.trucks.get(0).departureSec=100;state.trucks.get(0).etaSec=150;
        state.trucks.get(1).departureSec=0;state.trucks.get(1).etaSec=200;
        GraphEdge conflict=builder.build(state).edges().stream().filter(e -> e.type().equals("SHARED_DRIVER_CONFLICT")).findFirst().orElseThrow();
        assertEquals("TRUCK:T1",conflict.target());
        assertEquals("T2",conflict.features().get("blockerTruckId"));
    }

    @Test void graphExportDoesNotDependOnInputListOrderOrHistoricalData() {
        State state=fixture();
        GraphView first=builder.build(state);
        Collections.reverse(state.trucks);
        Collections.reverse(state.operations.assignments);
        Collections.reverse(state.operations.drivers);
        assertEquals(first,builder.build(state));
        state.operations.assignments.clear();
        GraphView unassigned=builder.build(state);
        assertEquals(first.nodes().size(),unassigned.nodes().size());
        assertTrue(unassigned.edges().stream().noneMatch(e -> e.source().startsWith("TRUCK:")));
    }

    @Test void weightsAndTimeIntervalsMustBeFiniteAndBounded() {
        GraphView graph=new GraphView("test",0,"test",List.of(n("TRUCK:T1"),n("DRIVER:D1")),
                List.of(e("bad", "TRUCK:T1","DRIVER:D1",0,100,1.1)),"SIMULATED");
        assertThrows(IllegalArgumentException.class,() -> OperationalDependencyGraph.materialize(graph));
        GraphView badTime=new GraphView("test",0,"test",graph.nodes(),List.of(e("bad","TRUCK:T1","DRIVER:D1",10,10,.5)),"SIMULATED");
        assertThrows(IllegalArgumentException.class,() -> OperationalDependencyGraph.materialize(badTime));
        GraphView nan=new GraphView("test",0,"test",graph.nodes(),List.of(e("bad","TRUCK:T1","DRIVER:D1",0,100,Double.NaN)),"SIMULATED");
        assertThrows(IllegalArgumentException.class,() -> OperationalDependencyGraph.materialize(nan));
    }

    @Test void unfinishedDeliveryDestinationRemainsValidBeyondRoadTripsTwentyFourHourBound() {
        State state=fixture();state.clockSec=90_000;
        Truck truck=state.trucks.getFirst();truck.etaSec=90_010;truck.affectedIncidentIds.add("I1");truck.risk=new Risk(1,"HIGH","RULE_BASED");
        Assignment assignment=state.operations.assignments.getFirst();assignment.predictedDockStartSec=90_010;assignment.predictedDockEndSec=120_000;
        Incident incident=new Incident();incident.id="I1";incident.status="ACTIVE";incident.severity=1;incident.startSec=89_000;incident.endSec=100_000;state.incidents.add(incident);
        GraphView graph=builder.build(state);
        GraphEdge destination=graph.edges().stream().filter(e->e.source().equals("DELIVERY:L1")&&e.target().equals("WAREHOUSE:W1")).findFirst().orElseThrow();
        assertEquals(172_800,destination.validUntilSec());
        assertTrue(destination.validUntilSec()>state.clockSec);
        NodeRisk warehouse=new GraphRiskBaseline().predict(state,graph).nodeRisks().stream().filter(r->r.nodeId().equals("WAREHOUSE:W1")).findFirst().orElseThrow();
        assertTrue(warehouse.score()>0);
    }

    @Test void fractionalDependentReadyTimeDoesNotInventOverlapAtSameServiceReleaseTick() {
        State state=fixture();Dock dock=state.operations.docks.getFirst();dock.serviceSec=.14;
        Truck first=state.trucks.getFirst(),next=state.trucks.get(1);first.etaSec=10;next.etaSec=10.14;
        Assignment a=state.operations.assignments.getFirst(),b=state.operations.assignments.get(1);
        a.reservationStartSec=10;a.reservationEndSec=11;a.predictedDockStartSec=10;a.predictedDockEndSec=10.2;
        b.reservationStartSec=10.14;b.reservationEndSec=11;b.predictedDockStartSec=10.2;b.predictedDockEndSec=10.4;
        GraphView graph=builder.build(state);
        assertTrue(graph.edges().stream().noneMatch(e->e.type().equals("SHARED_DOCK_CONFLICT")));
    }

    static GraphNode n(String id) {return new GraphNode(id,id.split(":")[0],id.split(":")[1],Map.of(),"SIMULATED");}
    static GraphEdge e(String id,String source,String target,double from,double until,double weight) {return new GraphEdge(id,source,target,"TEST_DEPENDENCY",from,until,weight,Map.of(),"SIMULATED");}
    static State fixture() {
        State state=new State(); state.networkId="real-test-network";
        Truck a=new Truck(); a.id="T1";a.name="Test one";a.etaSec=100;a.departureSec=0;a.deadlineSec=1000;
        Truck b=new Truck(); b.id="T2";b.name="Test two";b.etaSec=180;b.departureSec=50;b.deadlineSec=1000;
        state.trucks.addAll(List.of(a,b));
        Warehouse w=new Warehouse(); w.id="W1";w.name="Explicit test warehouse";w.location=new Point(80.25,13.05);w.nodeId=1;w.dockCapacity=1;
        Dock d=new Dock();d.id="D1";d.warehouseId="W1";d.serviceSec=60;d.openFromSec=0;d.openUntilSec=1000;
        Driver dr1=new Driver();dr1.id="DR1";dr1.available=true;dr1.shiftEndSec=1000;
        Driver dr2=new Driver();dr2.id="DR2";dr2.available=true;dr2.shiftEndSec=1000;
        Delivery l=new Delivery();l.id="L1";l.warehouseId="W1";l.deadlineSec=1000;
        Assignment aa=new Assignment();aa.truckId="T1";aa.driverId="DR1";aa.dockId="D1";aa.deliveryIds.add("L1");aa.reservationStartSec=100;aa.reservationEndSec=160;aa.predictedDockStartSec=100;aa.predictedDockEndSec=160;
        Assignment ab=new Assignment();ab.truckId="T2";ab.driverId="DR2";ab.dockId="D1";ab.reservationStartSec=180;ab.reservationEndSec=240;ab.predictedDockStartSec=180;ab.predictedDockEndSec=240;
        state.operations.warehouses.add(w);state.operations.docks.add(d);state.operations.drivers.addAll(List.of(dr1,dr2));state.operations.deliveries.add(l);state.operations.assignments.addAll(List.of(aa,ab));
        return state;
    }
}
