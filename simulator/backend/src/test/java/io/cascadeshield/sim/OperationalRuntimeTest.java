package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;

/** Small synthetic UNIT TEST fixtures only; never acquired geography or research outcomes. */
class OperationalRuntimeTest {
    private static final ObjectMapper MAPPER=new ObjectMapper().findAndRegisterModules();
    private static final Point ORIGIN=new Point(80.2500,13.0500),MID=new Point(80.2505,13.0500),DEST=new Point(80.2510,13.0500);

    private static RoadGraph roads() {
        List<Node> nodes=List.of(new Node(1,ORIGIN.longitude(),ORIGIN.latitude()),new Node(2,MID.longitude(),MID.latitude()),new Node(3,DEST.longitude(),DEST.latitude()));
        List<Edge> edges=List.of(edge("ABf","AB",1,2,nodes),edge("ABr","AB",2,1,nodes),edge("BCf","BC",2,3,nodes),edge("BCr","BC",3,2,nodes));
        return new RoadGraph(new NetworkFile("OPERATIONAL_UNIT_TEST_ONLY","Unit fixture",List.of(13d,80d,14d,81d),nodes,edges,List.of(),Map.of("provenance","TEST_FIXTURE_ONLY")));
    }
    private static Edge edge(String id,String physical,long from,long to,List<Node> nodes) {
        return new Edge(id,physical,from,to,physical.equals("AB")?10:20,50,36,"TEST_FIXTURE_ONLY","residential",physical,
                List.of(nodes.get((int)from-1).point().coordinates(),nodes.get((int)to-1).point().coordinates()),Map.of());
    }
    private static TruckSpec truck(String id,double departure,Point start,Point destination,double capacity,double cargo) {
        return new TruckSpec(id,id,start,destination,List.of(),36,capacity,cargo,"Unassigned simulated driver","NORMAL",departure,1000);
    }
    private static SimulationEngine engine(boolean secondTruck) {
        SimulationEngine engine=new SimulationEngine(roads(),MAPPER);
        engine.addTruck(truck("A",0,ORIGIN,DEST,1000,500));
        if(secondTruck)engine.addTruck(truck("B",20,ORIGIN,DEST,1000,500));
        return engine;
    }
    private static void resources(SimulationEngine engine,double service,double shiftEnd) {
        engine.resource("warehouses",new WarehouseSpec("W1","Simulated warehouse",DEST,1),true);
        engine.resource("docks",new DockSpec("D1","Simulated receiving dock","W1",service,0,1000),true);
        engine.resource("drivers",new DriverSpec("DR1","Driver one",true,0,shiftEnd),true);
        engine.resource("drivers",new DriverSpec("DR2","Driver two",true,0,1000),true);
        engine.resource("deliveries",new DeliverySpec("L1","First delivery","W1",200,100,"NORMAL"),true);
        engine.resource("deliveries",new DeliverySpec("L2","Second delivery","W1",200,100,"HIGH"),true);
    }
    private static SimulationEngine assigned(boolean secondTruck) {
        SimulationEngine engine=engine(secondTruck);resources(engine,40,1000);
        engine.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,50));
        if(secondTruck)engine.assign(new AssignmentSpec("B","DR2","D1",List.of("L2"),50,90));
        return engine;
    }
    private static void step(SimulationEngine engine,double seconds) {engine.control(new ControlRequest("STEP",null,seconds));}
    private static Assignment assignment(SimulationEngine engine,String truck) {return OperationalRuntime.assignment(engine.raw(),truck);}
    private static Delivery delivery(SimulationEngine engine,String id) {return OperationalRuntime.delivery(engine.raw(),id);}
    private static Driver driver(SimulationEngine engine,String id) {return OperationalRuntime.driver(engine.raw(),id);}
    private static ApiException rejected(int status,Runnable action) {ApiException ex=assertThrows(ApiException.class,action::run);assertEquals(status,ex.status);return ex;}

    @Test void resourcesSupportCrudWithSnappedLocationsAndExplicitSimulatedProvenance() {
        SimulationEngine e=engine(false);
        e.resource("warehouses",new WarehouseSpec("W1","Manual facility",new Point(DEST.longitude()+.00001,DEST.latitude()),2),true);
        Warehouse w=OperationalRuntime.warehouse(e.raw(),"W1");assertEquals(3,w.nodeId);assertEquals(DEST,w.location);assertEquals("SIMULATED",w.provenance);
        e.resource("warehouses",new WarehouseSpec("W1","Renamed facility",DEST,2),false);
        assertEquals("Renamed facility",OperationalRuntime.warehouse(e.raw(),"W1").name);
        e.resource("docks",new DockSpec("D1","Dock","W1",40,0,1000),true);
        e.resource("drivers",new DriverSpec("DR1","Driver",true,0,1000),true);
        e.resource("deliveries",new DeliverySpec("L1","Cargo","W1",200,100,"HIGH"),true);
        assertEquals("SIMULATED",e.raw().operations.docks.getFirst().provenance);
        assertEquals("SIMULATED",e.raw().operations.drivers.getFirst().provenance);
        assertEquals("SIMULATED",e.raw().operations.deliveries.getFirst().provenance);
        rejected(409,()->e.removeResource("warehouses","W1"));
        e.removeResource("deliveries","L1");e.removeResource("docks","D1");e.removeResource("warehouses","W1");e.removeResource("drivers","DR1");
        assertTrue(e.raw().operations.warehouses.isEmpty());assertTrue(e.raw().operations.docks.isEmpty());assertTrue(e.raw().operations.drivers.isEmpty());assertTrue(e.raw().operations.deliveries.isEmpty());
    }

    @Test void invalidResourceIdsWindowsAndCapacityAreRejectedWithoutCreatingEntities() {
        SimulationEngine e=engine(false);
        rejected(400,()->e.resource("warehouses",new WarehouseSpec("bad/id","Bad",DEST,1),true));
        rejected(400,()->e.resource("warehouses",new WarehouseSpec("W1","Bad",DEST,0),true));
        assertTrue(e.raw().operations.warehouses.isEmpty());
        e.resource("warehouses",new WarehouseSpec("W1","Facility",DEST,1),true);
        rejected(400,()->e.resource("docks",new DockSpec("BAD","Dock","W1",40,100,10),true));
        rejected(400,()->e.resource("docks",new DockSpec("BAD","Dock","W1",Double.NaN,0,1000),true));
        e.resource("docks",new DockSpec("D1","Dock","W1",40,0,1000),true);
        rejected(400,()->e.resource("docks",new DockSpec("D2","Second","W1",40,0,1000),true));
        rejected(409,()->e.resource("warehouses",new WarehouseSpec("W1","Duplicate",DEST,1),true));
        rejected(400,()->e.resource("drivers",new DriverSpec("BAD","Driver",true,0,Double.POSITIVE_INFINITY),true));
        rejected(400,()->e.resource("deliveries",new DeliverySpec("BAD","Cargo","W1",-1,100,"NORMAL"),true));
        assertEquals(1,e.raw().operations.docks.size());assertTrue(e.raw().operations.drivers.isEmpty());assertTrue(e.raw().operations.deliveries.isEmpty());
    }

    @Test void assignmentRequiresExistingResourcesDistinctDeliveriesAndMatchingRoadDestination() {
        SimulationEngine e=engine(false);resources(e,40,1000);
        rejected(404,()->e.assign(new AssignmentSpec("A","MISSING","D1",List.of("L1"),10,50)));
        rejected(400,()->e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1","L1"),10,50)));
        rejected(400,()->e.assign(new AssignmentSpec("A","DR1","D1",List.of(),10,50)));
        rejected(400,()->e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,20)));
        e.resource("warehouses",new WarehouseSpec("W2","Different destination",ORIGIN,1),true);
        e.resource("docks",new DockSpec("D2","Other dock","W2",40,0,1000),true);
        e.resource("deliveries",new DeliverySpec("L3","Other cargo","W2",100,100,"NORMAL"),true);
        rejected(400,()->e.assign(new AssignmentSpec("A","DR1","D2",List.of("L3"),10,50)));
        rejected(400,()->e.assign(new AssignmentSpec("A","DR1","D1",List.of("L3"),10,50)));
        assertTrue(e.raw().operations.assignments.isEmpty());
    }

    @Test void rejectionPreservesExistingAssignmentAndEnforcesLoadAndSingleDeliveryOwnership() {
        SimulationEngine e=assigned(true);
        e.resource("deliveries",new DeliverySpec("HEAVY","Excess cargo","W1",501,100,"NORMAL"),true);
        Assignment before=MAPPER.convertValue(assignment(e,"A"),Assignment.class);
        rejected(400,()->e.assign(new AssignmentSpec("A","DR1","D1",List.of("HEAVY"),10,50)));
        assertEquals(MAPPER.valueToTree(before),MAPPER.valueToTree(assignment(e,"A")));
        assertEquals("A",delivery(e,"L1").truckId);assertNull(delivery(e,"HEAVY").truckId);
        rejected(409,()->e.assign(new AssignmentSpec("B","DR2","D1",List.of("L1"),50,90)));
        assertEquals("B",delivery(e,"L2").truckId);
        TruckSpec tooSmall=truck("A",0,ORIGIN,DEST,100,100);
        rejected(400,()->e.updateTruck("A",tooSmall));
        assertEquals(1000,e.truck("A").capacityKg);
        rejected(409,()->e.removeResource("drivers","DR1"));
        rejected(409,()->e.removeResource("docks","D1"));
        rejected(409,()->e.removeResource("deliveries","L1"));
    }

    @Test void baselineDriverShiftAndOverlappingDutyConstraintsRejectInvalidAssignments() {
        SimulationEngine e=engine(true);resources(e,40,9);
        rejected(400,()->e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,50)));
        e.resource("drivers",new DriverSpec("DR1","Driver",true,0,1000),false);
        e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,50));
        e.addTruck(truck("C",5,DEST,ORIGIN,1000,500));
        e.resource("warehouses",new WarehouseSpec("W2","Other endpoint",ORIGIN,1),true);
        e.resource("docks",new DockSpec("D2","Second dock","W2",40,0,1000),true);
        e.resource("deliveries",new DeliverySpec("L3","Cargo","W2",200,100,"NORMAL"),true);
        rejected(409,()->e.assign(new AssignmentSpec("C","DR1","D2",List.of("L3"),15,55)));
        rejected(400,()->e.assign(new AssignmentSpec("B","DR1","D1",List.of("L2"),50,90)));
        rejected(400,()->e.resource("drivers",new DriverSpec("DR1","Driver",true,0,9),false));
        assertEquals(1000,driver(e,"DR1").shiftEndSec);
    }

    @Test void configurationIsLockedAfterMovementAndDependenciesCanBeRemovedBeforeStart() {
        SimulationEngine e=assigned(false);e.unassign("A");
        assertNull(assignment(e,"A"));assertEquals("UNASSIGNED",delivery(e,"L1").status);assertNull(delivery(e,"L1").truckId);
        e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,50));step(e,1);
        rejected(409,()->e.unassign("A"));
        rejected(409,()->e.resource("drivers",new DriverSpec("DR3","Driver",true,0,1000),true));
        assertNotNull(assignment(e,"A"));
    }

    @Test void unavailableDriverBlocksDepartureWithUnknownEtaAndNoFabricatedArrival() {
        SimulationEngine e=assigned(false);e.availability("DR1",false);step(e,20);
        Truck truck=e.truck("A");assertEquals("DRIVER_UNAVAILABLE",truck.status);assertEquals(ORIGIN.coordinates(),truck.position);
        assertEquals(0,truck.distanceTravelledM);assertEquals(-1,truck.arrivalSec);assertFalse(truck.etaKnown);
        assertEquals(-1,assignment(e,"A").predictedDockStartSec);assertEquals(0,driver(e,"DR1").dutySec);
        assertTrue(e.raw().operations.predictedImpacts.stream().anyMatch(i -> i.code().equals("DRIVER_UNAVAILABLE")));
        assertTrue(e.raw().operations.realizedImpacts.stream().anyMatch(i -> i.code().equals("DRIVER_UNAVAILABLE") && i.provenance().equals("SIMULATED_OUTCOME")));
        e.availability("DR1",true);step(e,10);
        assertEquals(30,e.truck("A").arrivalSec,1e-8);assertTrue(e.truck("A").etaKnown);
        assertEquals(10,driver(e,"DR1").dutySec,1e-7);
    }

    @Test void driverUnavailabilityFinishesOccupiedEdgeThenHoldsAtRealNode() {
        SimulationEngine e=assigned(false);step(e,2.5);
        assertEquals(25,e.truck("A").offsetM,1e-7);
        e.availability("DR1",false);step(e,10);
        assertEquals(MID.coordinates(),e.truck("A").position);assertEquals(50,e.truck("A").distanceTravelledM,1e-7);
        assertEquals("DRIVER_UNAVAILABLE",e.truck("A").status);assertEquals(0,e.truck("A").speedKph);
        e.availability("DR1",true);step(e,5);
        assertEquals(17.5,e.truck("A").arrivalSec,1e-8);assertEquals(100,e.truck("A").distanceTravelledM,1e-7);
    }

    @Test void roadDelayCannotMakeDriverEnterEdgeThatWouldOverrunShift() {
        SimulationEngine e=engine(false);resources(e,40,12);e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,50));
        e.addIncident(new IncidentRequest("CLOSURE","BC",1,8,0d));step(e,20);
        assertEquals("SHIFT_EXHAUSTED",e.truck("A").status);assertEquals(MID.coordinates(),e.truck("A").position);
        assertEquals(50,e.truck("A").distanceTravelledM,1e-7);assertEquals(-1,e.truck("A").arrivalSec);
        assertFalse(e.truck("A").etaKnown);
        assertTrue(e.raw().operations.realizedImpacts.stream().anyMatch(i -> i.code().equals("SHIFT_EXHAUSTED")));
        assertTrue(e.raw().operations.predictedImpacts.stream().anyMatch(i -> i.code().equals("SHIFT_EXCEEDED")));
    }

    @Test void sharedDriverWaitsForActualRoadArrivalRatherThanDockCompletion() {
        SimulationEngine e=engine(false);resources(e,40,1000);
        e.addTruck(truck("B",20,DEST,ORIGIN,1000,500));
        e.resource("warehouses",new WarehouseSpec("W2","Second endpoint",ORIGIN,1),true);
        e.resource("docks",new DockSpec("D2","Other dock","W2",40,0,1000),true);
        e.resource("deliveries",new DeliverySpec("L3","Other delivery","W2",200,200,"NORMAL"),true);
        e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,50));
        e.assign(new AssignmentSpec("B","DR1","D2",List.of("L3"),30,70));
        e.addIncident(new IncidentRequest("CLOSURE","AB",1,15,0d));step(e,22);
        assertEquals("DRIVER_BUSY",e.truck("B").status);assertEquals(DEST.coordinates(),e.truck("B").position);
        assertTrue(e.raw().operations.predictedImpacts.stream().anyMatch(i -> i.code().equals("DRIVER_OVERLAP") && i.truckIds().contains("B")));
        step(e,13);
        assertEquals(25,e.truck("A").arrivalSec,1e-8);assertEquals(35,e.truck("B").arrivalSec,1e-8);
        assertEquals("UNLOADING",assignment(e,"A").status);assertTrue(e.truck("B").arrivalSec < assignment(e,"A").actualDockEndSec);
        assertNull(driver(e,"DR1").occupiedBy);
    }

    @Test void closureForecastsThenRealizesSharedDockQueueAndDeliveryLateness() {
        SimulationEngine e=assigned(true);e.addIncident(new IncidentRequest("CLOSURE","AB",1,15,0d));
        assertEquals(25,e.truck("A").etaSec,1e-8);
        assertEquals(25,assignment(e,"A").predictedDockStartSec,1e-8);assertEquals(65,assignment(e,"A").predictedDockEndSec,1e-8);
        assertEquals(65,assignment(e,"B").predictedDockStartSec,1e-8);assertEquals(105,assignment(e,"B").predictedDockEndSec,1e-8);
        assertTrue(e.raw().operations.predictedImpacts.stream().anyMatch(i -> i.code().equals("DOCK_OVERLAP") && i.truckIds().equals(List.of("B")) && Math.abs(i.delaySec()-15)<1e-8));
        assertTrue(e.raw().operations.predictedImpacts.stream().anyMatch(i -> i.code().equals("DELIVERY_DEADLINE") && i.resourceIds().contains("DELIVERY:L2") && Math.abs(i.delaySec()-5)<1e-8));
        assertTrue(e.raw().operations.realizedImpacts.isEmpty());
        step(e,50);
        assertEquals("UNLOADING",assignment(e,"A").status);assertEquals("QUEUED",assignment(e,"B").status);
        assertEquals("A",OperationalRuntime.dock(e.raw(),"D1").occupiedBy);assertEquals(30,e.truck("B").arrivalSec,1e-8);
        assertTrue(e.raw().operations.realizedImpacts.stream().anyMatch(i -> i.code().equals("DOCK_QUEUE") && i.truckIds().equals(List.of("B"))));
        assertEquals(0,e.raw().operations.kpis.delivered());
        step(e,55);
        assertEquals("COMPLETED",e.raw().status);assertEquals(105,e.raw().clockSec,1e-8);
        assertEquals(65,delivery(e,"L1").deliveredAtSec,1e-8);assertEquals(0,delivery(e,"L1").lateSec);
        assertEquals(65,assignment(e,"B").actualDockStartSec,1e-8);assertEquals(105,delivery(e,"L2").deliveredAtSec,1e-8);
        assertEquals(5,delivery(e,"L2").lateSec,1e-8);assertEquals(35,assignment(e,"B").queueSec,1e-7);
        assertEquals(2,e.raw().operations.kpis.delivered());assertEquals(1,e.raw().operations.kpis.lateDeliveries());assertEquals(5,e.raw().operations.kpis.deliveryDelaySec(),1e-8);
        assertTrue(e.raw().operations.realizedImpacts.stream().anyMatch(i -> i.code().equals("DELIVERY_LATE") && i.delaySec()==5 && i.provenance().equals("SIMULATED_OUTCOME")));
        assertTrue(e.truck("A").encounteredIncidentIds.contains("I001"));
        assertTrue(e.raw().events.stream().anyMatch(event -> event.type().equals("DOCK_SERVICE_STARTED") && event.truckId().equals("B") && event.clockSec()==65));
    }

    @Test void forecastAndCounterfactualEtaOverridesNeverMutateClockDriversOrRealizedOutcomes() {
        SimulationEngine e=assigned(true);step(e,5);
        var before=MAPPER.valueToTree(e.raw());
        List<Impact> hypothetical=OperationalRuntime.forecast(e.raw(),Map.of("A",70d));
        assertTrue(hypothetical.stream().anyMatch(i -> i.code().equals("DELIVERY_DEADLINE")));
        assertTrue(hypothetical.stream().allMatch(i -> i.predicted() && i.provenance().equals("SIMULATED_PREDICTION")));
        assertEquals(before,MAPPER.valueToTree(e.raw()));
    }

    @Test void resetRestoresInitialResourcesAndAssignmentsRatherThanCurrentAvailabilityAndOutcomes() {
        SimulationEngine e=assigned(true);step(e,1);e.availability("DR1",false);step(e,5);
        e.control(new ControlRequest("RESET",null,null));
        assertEquals("DRAFT",e.raw().status);assertEquals(0,e.raw().clockSec);
        assertTrue(driver(e,"DR1").available);assertEquals(0,driver(e,"DR1").dutySec);assertNull(driver(e,"DR1").occupiedBy);
        assertEquals("PLANNED",assignment(e,"A").status);assertEquals(-1,assignment(e,"A").actualDockStartSec);assertEquals(-1,delivery(e,"L1").deliveredAtSec);
        assertEquals(2,e.raw().operations.assignments.size());assertTrue(e.raw().operations.realizedImpacts.isEmpty());assertTrue(e.raw().commandHistory.isEmpty());
    }

    @SuppressWarnings("unchecked")
    @Test void resourceReplayIncludesRuntimeAvailabilityCommandsAndReproducesActualOutcomes() {
        SimulationEngine original=assigned(true);original.addIncident(new IncidentRequest("CLOSURE","AB",1,15,0d));
        step(original,16);original.availability("DR2",false);step(original,4);original.availability("DR2",true);step(original,85);
        assertTrue(original.raw().commandHistory.stream().anyMatch(c -> c.kind().equals("DRIVER_AVAILABILITY") && c.clockSec()==16));
        Map<String,Object> config=MAPPER.convertValue(original.scenarioConfiguration(),Map.class);
        assertEquals(2,config.get("version"));assertEquals("SIMULATED",config.get("operationsProvenance"));
        SimulationEngine replay=new SimulationEngine(roads(),MAPPER);replay.replay("Resource replay",config);step(replay,105);
        assertEquals(original.raw().clockSec,replay.raw().clockSec);assertEquals(original.raw().kpis,replay.raw().kpis);
        assertEquals(MAPPER.valueToTree(original.raw().operations),MAPPER.valueToTree(replay.raw().operations));
        for(String id:List.of("A","B")){assertEquals(original.truck(id).position,replay.truck(id).position);assertEquals(original.truck(id).arrivalSec,replay.truck(id).arrivalSec);assertEquals(original.truck(id).encounteredIncidentIds,replay.truck(id).encounteredIncidentIds);}
        rejected(409,()->replay.availability("DR1",false));
        assertTrue(replay.raw().operations.realizedImpacts.stream().allMatch(i -> !i.predicted() && i.provenance().equals("SIMULATED_OUTCOME")));
        assertTrue(replay.raw().operations.graph.nodes().stream().allMatch(n -> n.provenance().equals("SIMULATED")));
        assertEquals("SIMULATED_PREDICTION",replay.raw().operations.cascade.provenance());
    }

    @Test void priorTripBlockedBeforeDepartureDoesNotTeleportSharedDriverDownstream(){
        SimulationEngine e=engine(false);resources(e,40,1000);
        e.addTruck(truck("B",12,DEST,ORIGIN,1000,500));
        e.resource("warehouses",new WarehouseSpec("W2","Return endpoint",ORIGIN,1),true);
        e.resource("docks",new DockSpec("D2","Return dock","W2",40,0,1000),true);
        e.resource("deliveries",new DeliverySpec("L3","Return delivery","W2",200,200,"NORMAL"),true);
        e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,50));
        e.assign(new AssignmentSpec("B","DR1","D2",List.of("L3"),30,70));
        e.addIncident(new IncidentRequest("CLOSURE","AB",1,15,0d));
        assertEquals(35,e.truck("B").etaSec,1e-8);
        step(e,14);assertEquals(0,e.truck("A").distanceTravelledM);assertEquals(0,e.truck("B").distanceTravelledM);assertEquals("DRIVER_BUSY",e.truck("B").status);
        step(e,21);assertEquals(25,e.truck("A").arrivalSec);assertEquals(35,e.truck("B").arrivalSec);
    }

    @Test void fractionalServiceCannotFinishBeforeItsConfiguredDuration(){
        SimulationEngine e=engine(false);resources(e,.14,1000);e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,11));
        step(e,10.1);assertEquals("UNLOADING",assignment(e,"A").status);assertEquals(10.2,assignment(e,"A").actualDockEndSec,1e-8);
        assertEquals(-1,delivery(e,"L1").deliveredAtSec);step(e,.1);assertEquals(10.2,delivery(e,"L1").deliveredAtSec,1e-8);
    }

    @Test void completedAssignmentProjectionIsIndependentOfRefreshFrequency(){
        SimulationEngine frequent=assigned(true),coarse=assigned(true);
        frequent.addIncident(new IncidentRequest("CLOSURE","AB",1,15,0d));coarse.addIncident(new IncidentRequest("CLOSURE","AB",1,15,0d));
        for(int i=0;i<1050;i++){frequent.advance(1);frequent.snapshot();}
        coarse.advance(1050);
        assertEquals(MAPPER.valueToTree(coarse.snapshot().operations),MAPPER.valueToTree(frequent.snapshot().operations));
        assertEquals(assignment(coarse,"A").actualDockStartSec,assignment(coarse,"A").predictedDockStartSec);
    }

    @Test void tickRoundedDockServiceCannotRunBeyondFractionalClosingTime(){
        SimulationEngine e=engine(false);resources(e,.14,1000);
        e.resource("docks",new DockSpec("D1","Short opening window","W1",.14,0,11.14),false);
        e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,11));
        e.addIncident(new IncidentRequest("CLOSURE","AB",1,1,0d));
        assertEquals(11,e.truck("A").etaSec,1e-8);
        assertEquals(11.2,assignment(e,"A").predictedDockEndSec,1e-8);
        assertTrue(e.raw().operations.predictedImpacts.stream().anyMatch(i->i.code().equals("DOCK_WINDOW")&&i.endSec()>11.14));
        step(e,11.2);
        assertEquals(11,e.truck("A").arrivalSec,1e-8);
        assertEquals("QUEUED",assignment(e,"A").status);
        assertEquals(-1,assignment(e,"A").actualDockStartSec);
        assertEquals(-1,delivery(e,"L1").deliveredAtSec);
        assertNull(OperationalRuntime.dock(e.raw(),"D1").occupiedBy);
    }

    @Test void editingAssignedDockCannotInvalidateExistingReservationHoursOrService(){
        SimulationEngine e=assigned(false);var before=MAPPER.valueToTree(e.raw());
        rejected(400,()->e.resource("docks",new DockSpec("D1","Longer service","W1",41,0,1000),false));
        assertEquals(before,MAPPER.valueToTree(e.raw()));
        rejected(400,()->e.resource("docks",new DockSpec("D1","Later opening","W1",40,20,1000),false));
        assertEquals(before,MAPPER.valueToTree(e.raw()));
        rejected(400,()->e.resource("docks",new DockSpec("D1","Earlier closing","W1",40,0,49),false));
        assertEquals(before,MAPPER.valueToTree(e.raw()));
        e.resource("docks",new DockSpec("D1","Rename permitted","W1",40,0,1000),false);
        assertEquals("Rename permitted",OperationalRuntime.dock(e.raw(),"D1").name);
        assertEquals("A",delivery(e,"L1").truckId);
    }

    @Test void validThreeTripDriverChainChecksTransfersBetweenAdjacentTrips(){
        SimulationEngine e=engine(false);resources(e,40,1000);
        e.addTruck(truck("B",20,DEST,ORIGIN,1000,500));
        e.addTruck(truck("C",40,ORIGIN,DEST,1000,500));
        e.resource("warehouses",new WarehouseSpec("W2","Return endpoint",ORIGIN,1),true);
        e.resource("docks",new DockSpec("D2","Return dock","W2",40,0,1000),true);
        e.resource("deliveries",new DeliverySpec("L3","Return delivery","W2",200,200,"NORMAL"),true);
        e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,50));
        e.assign(new AssignmentSpec("B","DR1","D2",List.of("L3"),30,70));
        assertDoesNotThrow(()->e.assign(new AssignmentSpec("C","DR1","D1",List.of("L2"),90,130)));
        assertEquals(3,e.raw().operations.assignments.size());
        e.addIncident(new IncidentRequest("CLOSURE","AB",1,15,0d));step(e,130);
        assertEquals(25,e.truck("A").arrivalSec,1e-8);assertEquals(35,e.truck("B").arrivalSec,1e-8);
        assertEquals(50,e.truck("C").arrivalSec,1e-8);
        assertEquals(30,driver(e,"DR1").dutySec,1e-7);assertNull(driver(e,"DR1").occupiedBy);
        assertTrue(e.raw().operations.assignments.stream().allMatch(a->a.status.equals("COMPLETED")));
    }

    @Test void driverReadyEtaReevaluatesIncidentScheduleRatherThanAddingTwoClosureWaits(){
        SimulationEngine e=engine(false);resources(e,40,60);
        e.addTruck(truck("B",12,DEST,ORIGIN,1000,500));
        e.resource("warehouses",new WarehouseSpec("W2","Return endpoint",ORIGIN,1),true);
        e.resource("docks",new DockSpec("D2","Return dock","W2",40,0,1000),true);
        e.resource("deliveries",new DeliverySpec("L3","Return delivery","W2",200,200,"NORMAL"),true);
        e.assign(new AssignmentSpec("A","DR1","D1",List.of("L1"),10,50));
        e.assign(new AssignmentSpec("B","DR1","D2",List.of("L3"),30,70));
        e.addIncident(new IncidentRequest("CLOSURE","AB",1,30,0d));
        assertEquals(40,e.truck("A").etaSec,1e-8);
        assertEquals(50,e.truck("B").etaSec,1e-8);assertTrue(e.truck("B").etaKnown);
        assertTrue(e.truck("B").affectedIncidentIds.isEmpty());
        assertTrue(e.raw().operations.predictedImpacts.stream().anyMatch(i->i.code().equals("DRIVER_OVERLAP")&&i.truckIds().contains("B")));
        assertTrue(e.raw().operations.predictedImpacts.stream().noneMatch(i->i.code().equals("SHIFT_EXCEEDED")&&i.truckIds().contains("B")));
        step(e,50);assertEquals(40,e.truck("A").arrivalSec,1e-8);assertEquals(50,e.truck("B").arrivalSec,1e-8);
    }
}
