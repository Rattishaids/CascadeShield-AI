package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static io.cascadeshield.sim.Models.*;
import static org.junit.jupiter.api.Assertions.*;

/** TESTONLY abstract fixtures for previously reproduced state-machine bugs. */
class SimulationEngineRegressionTest {
    private static final ObjectMapper MAPPER=new ObjectMapper().findAndRegisterModules();
    private static Node n(long id){return new Node(id,80.25+id*.0001,13.06);}
    private static Edge e(String id,long from,long to,long way,double metres){
        return new Edge(id,id,from,to,way,metres,36,"TESTONLY","residential","TESTONLY",
            List.of(n(from).point().coordinates(),n(to).point().coordinates()),Map.of("testOnly",true));
    }
    private static RoadGraph graph(List<Edge> edges,List<Restriction> restrictions){
        return new RoadGraph(new NetworkFile("TESTONLY","Never an acquired/research dataset",
            List.of(13d,80d,14d,81d),List.of(n(1),n(2),n(3),n(4),n(5)),edges,restrictions,Map.of("testOnly",true)));
    }
    private static RoadGraph simple(double firstLength){
        return graph(List.of(e("first",1,2,10,firstLength),e("second",2,3,20,100)),List.of());
    }
    private static SimulationEngine engine(RoadGraph graph){
        SimulationEngine engine=new SimulationEngine(graph,MAPPER);
        engine.addTruck(new TruckSpec("T1","TESTONLY",n(1).point(),n(3).point(),List.of(),
            36,100,50,"TESTONLY","NORMAL",0,500));
        return engine;
    }
    private static void step(SimulationEngine engine,double seconds){engine.control(new ControlRequest("STEP",null,seconds));}
    private static void approve(SimulationEngine engine,String action){
        engine.decide(new DecisionRequest("T1",action,engine.raw().recommendations.getFirst().id()));
    }

    @Test void resolvingApprovedWaitsRetainsOnlyOtherOriginalIncidentDependencies(){
        SimulationEngine engine=engine(simple(100));
        Incident first=engine.addIncident(new IncidentRequest("CLOSURE","first",1,100,null));
        Incident second=engine.addIncident(new IncidentRequest("CLOSURE","first",1,200,null));
        approve(engine,"WAIT");
        assertEquals(List.of(first.id,second.id),engine.truck("T1").approvedWaitIncidentIds);
        assertEquals(200,engine.truck("T1").waitUntilSec);
        step(engine,1);
        engine.removeIncident(second.id);
        assertEquals(List.of(first.id),engine.truck("T1").approvedWaitIncidentIds);
        assertEquals(100,engine.truck("T1").waitUntilSec);
        assertEquals("WAITING",engine.truck("T1").status);
        engine.removeIncident(first.id);
        assertTrue(engine.truck("T1").approvedWaitIncidentIds.isEmpty());
        assertEquals(1,engine.truck("T1").waitUntilSec);
        assertEquals(21,engine.truck("T1").etaSec,1e-9);
        step(engine,.1);
        assertEquals("MOVING",engine.truck("T1").status);
        assertEquals(1,engine.truck("T1").distanceTravelledM,1e-7);
    }

    @Test void naturalExpiryAndReplayReleaseTheSameApprovedWait(){
        SimulationEngine original=engine(simple(100));
        Incident first=original.addIncident(new IncidentRequest("CLOSURE","first",1,100,null));
        Incident second=original.addIncident(new IncidentRequest("CLOSURE","first",1,200,null));
        approve(original,"WAIT");
        step(original,1);
        original.removeIncident(second.id);
        original.removeIncident(first.id);
        step(original,30);
        assertEquals(21,original.truck("T1").arrivalSec,1e-9);
        @SuppressWarnings("unchecked")
        Map<String,Object> configuration=MAPPER.convertValue(original.scenarioConfiguration(),Map.class);
        SimulationEngine replay=new SimulationEngine(simple(100),MAPPER);
        replay.replay("TESTONLY wait-resolution replay",configuration);
        step(replay,40);
        assertEquals(original.truck("T1").arrivalSec,replay.truck("T1").arrivalSec);
        assertEquals(original.raw().kpis,replay.raw().kpis);
        assertEquals(original.truck("T1").incomingWay,replay.truck("T1").incomingWay);

        SimulationEngine expires=engine(simple(100));
        expires.addIncident(new IncidentRequest("CLOSURE","first",1,.5,null));
        approve(expires,"WAIT");
        step(expires,.6);
        assertTrue(expires.truck("T1").approvedWaitIncidentIds.isEmpty());
        assertEquals(1,expires.truck("T1").distanceTravelledM,1e-7);
    }

    @Test void repeatedJunctionReroutesAndRecoveryPreserveActualIncomingWay(){
        RoadGraph graph=graph(List.of(e("approach",1,2,10,1),e("forbidden",2,3,20,1),
            e("preferred",2,5,50,10),e("preferred-exit",5,3,60,10),
            e("detour",2,4,30,20),e("detour-exit",4,3,40,20)),
            List.of(new Restriction(10,2,20,"no_right_turn")));
        SimulationEngine engine=engine(graph);
        step(engine,.1);
        assertEquals(10,engine.truck("T1").incomingWay);
        engine.addIncident(new IncidentRequest("CLOSURE","preferred",1,100,null));
        approve(engine,"REROUTE");
        assertEquals(List.of("detour","detour-exit"),engine.truck("T1").route.edgeIds());
        assertEquals(0,engine.truck("T1").edgeIndex);
        assertEquals(10,engine.truck("T1").incomingWay);
        SimulationEngine recovered=new SimulationEngine(graph,MAPPER);
        recovered.restore(MAPPER.convertValue(engine.raw(),State.class));
        recovered.addIncident(new IncidentRequest("CLOSURE","detour",1,100,null));
        Option reroute=recovered.raw().recommendations.getFirst().options().stream()
            .filter(option->option.action().equals("REROUTE")).findFirst().orElseThrow();
        assertFalse(reroute.feasible(),"Forbidden shortcut must stay forbidden after route replacement");
        assertThrows(ApiException.class,()->approve(recovered,"REROUTE"));
        assertEquals(List.of("detour","detour-exit"),recovered.truck("T1").route.edgeIds());
        assertEquals(n(2).point().coordinates(),recovered.truck("T1").position);
    }

    @Test void incidentRawTimesAreValidatedBeforeQuantization(){
        SimulationEngine engine=engine(simple(100));
        for(double invalid:List.of(Double.NaN,Double.POSITIVE_INFINITY,Double.NEGATIVE_INFINITY,Double.MAX_VALUE)){
            assertThrows(ApiException.class,()->engine.addIncident(new IncidentRequest("CLOSURE","first",1,1,invalid)));
        }
        for(double tooShort:List.of(.001,.01,.049,.05,.099)){
            assertThrows(ApiException.class,()->engine.addIncident(new IncidentRequest("CLOSURE","first",1,tooShort,null)));
        }
        assertTrue(engine.raw().incidents.isEmpty());
        Incident accepted=engine.addIncident(new IncidentRequest("CLOSURE","first",1,.1,.05));
        assertEquals(.1,accepted.startSec,1e-9);
        assertEquals(.2,accepted.endSec,1e-9);
    }

    @Test void blockedAndWaitingSpeedIsZeroWithinTheSameTickAsEdgeExit(){
        SimulationEngine blocked=engine(simple(.5));
        blocked.addIncident(new IncidentRequest("CLOSURE","second",1,100,null));
        step(blocked,.1);
        assertEquals("BLOCKED",blocked.truck("T1").status);
        assertEquals(0,blocked.truck("T1").speedKph);
        assertEquals(.5,blocked.truck("T1").distanceTravelledM,1e-9);

        SimulationEngine nodeWait=engine(simple(1.5));
        step(nodeWait,.1);
        nodeWait.addIncident(new IncidentRequest("CLOSURE","second",1,100,null));
        approve(nodeWait,"WAIT");
        step(nodeWait,.1); // Completes first edge at 0.15 s, then waits during the same tick.
        assertEquals("WAITING",nodeWait.truck("T1").status);
        assertEquals(0,nodeWait.truck("T1").speedKph);
        assertEquals(n(2).point().coordinates(),nodeWait.truck("T1").position);
    }
}
