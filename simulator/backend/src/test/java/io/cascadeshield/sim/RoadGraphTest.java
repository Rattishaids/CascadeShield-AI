package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assumptions;
import static io.cascadeshield.sim.Models.*;
import static org.junit.jupiter.api.Assertions.*;

/** Tiny TESTONLY contract fixtures are never research data or acquired geography. */
class RoadGraphTest {
    private static Node n(long id, double x, double y) {
        return new Node(id, 80.25 + x * 0.001, 13.06 + y * 0.001);
    }

    private static Edge e(String id, String physical, Node from, Node to, long way, double metres) {
        return new Edge(id, physical, from.id(), to.id(), way, metres, 36,
            "TESTONLY_ASSUMPTION", "residential", "TESTONLY road",
            List.of(from.point().coordinates(), to.point().coordinates()), Map.of("testOnly", true));
    }

    private static NetworkFile network(List<Node> nodes, List<Edge> edges, List<Restriction> restrictions) {
        return new NetworkFile("TESTONLY", "Abstract routing contract fixture; never research data",
            List.of(13.0, 80.2, 13.1, 80.3), nodes, edges, restrictions,
            Map.of("dataClass", "TESTONLY", "researchData", false));
    }

    /** Directed diamond includes a tempting shortcut forbidden by an only-turn. */
    private static NetworkFile directedTurns() {
        Node a=n(1,0,0), b=n(2,1,0), c=n(3,2,0), d=n(4,1,1), shortcut=n(5,2,1);
        return network(List.of(a,b,c,d,shortcut), List.of(
            e("approach","p10",a,b,10,100),
            e("forbidden-right","p20",b,c,20,100),
            e("legal-detour","p30",b,d,30,100),
            e("mandatory-exit","p40",d,c,40,100),
            e("forbidden-shortcut","p60",d,shortcut,60,10),
            e("shortcut-exit","p70",shortcut,c,70,10)),
            List.of(new Restriction(10,2,20,"no_right_turn"),
                    new Restriction(30,4,40,"only_straight_on")));
    }

    /** Each physical segment has two directions and a genuine longer alternate path. */
    private static NetworkFile bidirectionalDetour() {
        Node a=n(1,0,0), b=n(2,1,0), c=n(3,0.5,1);
        return network(List.of(a,b,c), List.of(
            e("direct:f","direct",a,b,10,100), e("direct:r","direct",b,a,10,100),
            e("detour-a:f","detour-a",a,c,20,120), e("detour-a:r","detour-a",c,a,20,120),
            e("detour-b:f","detour-b",c,b,30,120), e("detour-b:r","detour-b",b,c,30,120)), List.of());
    }

    /** Two separated components; a coordinate near either component still snaps locally. */
    private static NetworkFile disconnected() {
        Node a=n(1,0,0), b=n(2,1,0), c=n(3,0,4), d=n(4,1,4);
        return network(List.of(a,b,c,d), List.of(
            e("component-a","pa",a,b,10,100),
            e("component-b","pb",c,d,20,100)), List.of());
    }

    private static Incident incident(String type,double severity,double start,double end) {
        Incident result=new Incident();
        result.id="TESTONLY-incident";
        result.type=type;
        result.physicalId="direct";
        result.severity=severity;
        result.startSec=start;
        result.endSec=end;
        result.status="ACTIVE";
        return result;
    }

    @Test void respectsDirectedEdgesAndNoAndOnlyTurnRestrictions() {
        RoadGraph graph=new RoadGraph(directedTurns());
        Route route=graph.route(1,3,36,List.of(),0,-1);
        assertEquals(List.of("approach","legal-detour","mandatory-exit"),route.edgeIds());
        assertEquals(300,route.distanceM(),1e-9);
        assertEquals(30,route.baseTravelSec(),1e-9);
        ApiException error=assertThrows(ApiException.class,()->graph.route(3,1,36,List.of(),0,-1));
        assertFalse(error.getMessage().isBlank(),"An impossible directed route must explain the failure");
    }

    @Test void incomingWayAndWaypointBoundaryPreserveTurnConstraints() {
        RoadGraph graph=new RoadGraph(directedTurns());
        assertEquals(List.of("forbidden-right"),graph.route(2,3,36,List.of(),0,-1).edgeIds());
        assertEquals(List.of("legal-detour","mandatory-exit"),
            graph.route(2,3,36,List.of(),0,10).edgeIds());
        assertEquals(List.of("approach","legal-detour","mandatory-exit"),
            graph.route(1,3,List.of(2L),36,List.of(),0,-1).edgeIds());
    }

    @Test void geometryIsContinuousAndUsesActualEdgeEndpoints() {
        RoadGraph graph=new RoadGraph(directedTurns());
        Route route=graph.route(1,3,36,List.of(),0,-1);
        assertConnectedGeometry(graph,route);
        assertEquals(graph.node(1).point(),route.snappedStart());
        assertEquals(graph.node(3).point(),route.snappedDestination());
        assertEquals(List.of(graph.node(1).point().coordinates(),graph.node(2).point().coordinates(),
            graph.node(4).point().coordinates(),graph.node(3).point().coordinates()),route.geometry());
    }

    @Test void closureBlocksBothDirectionsOfPhysicalRoadAndExpires() {
        RoadGraph graph=new RoadGraph(bidirectionalDetour());
        Incident closure=incident("CLOSURE",1,0,30);
        for (long[] pair : List.of(new long[]{1,2},new long[]{2,1})) {
            Route open=graph.route(pair[0],pair[1],36,List.of(),10,-1);
            assertEquals(100,open.distanceM(),1e-9);
            Route closed=graph.route(pair[0],pair[1],36,List.of(closure),10,-1);
            assertEquals(240,closed.distanceM(),1e-9);
            assertTrue(closed.edgeIds().stream().noneMatch(id->graph.edge(id).physicalId().equals("direct")));
            assertConnectedGeometry(graph,closed);
            Route expired=graph.route(pair[0],pair[1],36,List.of(closure),31,-1);
            assertEquals(100,expired.distanceM(),1e-9);
        }
    }

    @Test void strongerSlowdownChangesRoutingAndVehicleSpeedIsRespected() {
        RoadGraph graph=new RoadGraph(bidirectionalDetour());
        Route normal=graph.route(1,2,36,List.of(),0,-1);
        Route mild=graph.route(1,2,36,List.of(incident("SLOWDOWN",0.1,0,300)),0,-1);
        Route severe=graph.route(1,2,36,List.of(incident("SLOWDOWN",0.9,0,300)),0,-1);
        assertEquals(List.of("direct:f"),mild.edgeIds());
        assertEquals(List.of("detour-a:f","detour-b:f"),severe.edgeIds());
        // Route descriptor keeps baseline travel; conditioned traversal is separate.
        assertEquals(normal.baseTravelSec(),mild.baseTravelSec(),1e-9);
        Edge direct=graph.edge("direct:f");
        double mildCost=RoadGraph.traversalSeconds(direct,100,36,List.of(incident("SLOWDOWN",0.1,0,300)),0,false,false);
        double severeCost=RoadGraph.traversalSeconds(direct,100,36,List.of(incident("SLOWDOWN",0.9,0,300)),0,false,false);
        assertTrue(mildCost>normal.baseTravelSec());
        assertTrue(severeCost>mildCost);
        Route slowVehicle=graph.route(1,2,18,List.of(),0,-1);
        assertEquals(2*normal.baseTravelSec(),slowVehicle.baseTravelSec(),1e-9);
    }

    @Test void disconnectedLocationsFailClearlyAndFarawayClicksCannotSnap() {
        RoadGraph graph=new RoadGraph(disconnected());
        ApiException error=assertThrows(ApiException.class,()->graph.route(1,4,36,List.of(),0,-1));
        assertFalse(error.getMessage().isBlank());
        assertThrows(ApiException.class,()->graph.snap(new Point(80.29,13.09)));
        assertEquals(1,graph.snap(graph.node(1).point()));
    }

    @Test void closureWithoutDetourReportsImpossibleRoute() {
        RoadGraph graph=new RoadGraph(disconnected());
        Incident closure=incident("CLOSURE",1,0,30);
        closure.physicalId="pa";
        assertThrows(ApiException.class,()->graph.route(1,2,36,List.of(closure),10,-1));
    }

    @Test void scheduledConditionsDoNotStrandOccupiedVehicleAndWaitingIsExplicit() {
        RoadGraph graph=new RoadGraph(bidirectionalDetour());
        Edge edge=graph.edge("direct:f");
        List<Incident> closure=List.of(incident("CLOSURE",1,0,30));
        assertEquals(Double.POSITIVE_INFINITY,RoadGraph.traversalSeconds(edge,100,36,closure,10,false,false));
        assertEquals(30,RoadGraph.traversalSeconds(edge,100,36,closure,10,false,true),1e-9);
        assertEquals(10,RoadGraph.traversalSeconds(edge,100,36,closure,10,true,false),1e-9);
        double wholeSlowdown=RoadGraph.traversalSeconds(edge,100,36,List.of(incident("SLOWDOWN",0.5,0,300)),0,false,false);
        double expiresMidSegment=RoadGraph.traversalSeconds(edge,100,36,List.of(incident("SLOWDOWN",0.5,0,5)),0,false,false);
        assertTrue(expiresMidSegment>10);
        assertTrue(expiresMidSegment<wholeSlowdown);
    }

    @Test void actualChennaiPairsRemainConnectedAfterValidatedPhysicalClosure() throws Exception {
        String configured=System.getProperty("cascade.test.graph",
            System.getenv().getOrDefault("SIMULATOR_GRAPH_PATH","../../data/processed/chennai_osm/road_graph.json"));
        Path path=Path.of(configured);
        Assumptions.assumeTrue(Files.isRegularFile(path),"Actual graph is optional in isolated backend builds; bind it and set -Dcascade.test.graph to test it");
        ObjectMapper mapper=new ObjectMapper();
        NetworkFile source=mapper.readValue(path.toFile(),NetworkFile.class);
        RoadGraph graph=RoadGraph.load(path,mapper);
        assertEquals("REAL_GEOGRAPHIC_DATA",source.metadata().get("dataClass"));
        @SuppressWarnings("unchecked")
        List<Map<String,Object>> pairs=(List<Map<String,Object>>)source.metadata().get("demoPairs");
        assertEquals(3,pairs.size());
        for (Map<String,Object> pair : pairs) {
            long start=((Number)pair.get("startNodeId")).longValue();
            long destination=((Number)pair.get("destinationNodeId")).longValue();
            String physical=(String)pair.get("closurePhysicalId");
            Route initial=graph.route(start,destination,120,List.of(),0,-1);
            assertConnectedGeometry(graph,initial);
            assertEquals(((Number)pair.get("baseDistanceM")).doubleValue(),initial.distanceM(),0.05);
            assertTrue(initial.edgeIds().stream().anyMatch(id->graph.edge(id).physicalId().equals(physical)));
            Incident closure=incident("CLOSURE",1,0,3600);
            closure.physicalId=physical;
            Route detour=graph.route(start,destination,120,List.of(closure),0,-1);
            assertTrue(detour.edgeIds().stream().noneMatch(id->graph.edge(id).physicalId().equals(physical)));
            assertConnectedGeometry(graph,detour);
            assertTrue(graph.route(destination,start,120,List.of(),0,-1).distanceM()>0);
        }
    }

    private static void assertConnectedGeometry(RoadGraph graph,Route route) {
        assertFalse(route.edgeIds().isEmpty());
        List<List<Double>> expected=new ArrayList<>();
        Edge previous=null;
        for(String edgeId : route.edgeIds()) {
            Edge edge=graph.edge(edgeId);
            if(previous!=null) {
                assertEquals(previous.to(),edge.from(),"Route cannot jump between unconnected road nodes");
                assertEquals(previous.geometry().get(previous.geometry().size()-1),edge.geometry().get(0));
            }
            if(expected.isEmpty())expected.addAll(edge.geometry());
            else expected.addAll(edge.geometry().subList(1,edge.geometry().size()));
            previous=edge;
        }
        assertEquals(expected,route.geometry(),"Route geometry must be assembled from its connected actual edges");
    }
}
