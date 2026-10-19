package io.cascadeshield.sim;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;
import static io.cascadeshield.sim.OperationalDependencyGraphTest.*;

class GraphRiskBaselineTest {
    private final GraphRiskBaseline baseline=new GraphRiskBaseline();

    @Test void oneCauseAcrossMultipleParentsUsesMaximumProductRatherThanDoubleCounting() {
        State s=incidentState("I1",1);
        GraphView g=graph(List.of("TRUCK:T1","DOCK:D1","DELIVERY:L1","WAREHOUSE:W1"),List.of(
                e("a","TRUCK:T1","DOCK:D1",0,100,.8),e("b","TRUCK:T1","DELIVERY:L1",0,100,.6),
                e("c","DOCK:D1","WAREHOUSE:W1",0,100,.5),e("d","DELIVERY:L1","WAREHOUSE:W1",0,100,.8)));
        CascadeView result=baseline.predict(s,g);
        assertEquals(.48,score(result,"WAREHOUSE:W1"),1e-12);
        assertEquals(List.of("INCIDENT:I1"),risk(result,"WAREHOUSE:W1").causeIds());
        assertFalse(risk(result,"WAREHOUSE:W1").direct());
    }

    @Test void genuinelyDifferentCausesAggregateAtMultipleIncomingDependencies() {
        State s=incidentState("I1",1);
        Truck b=new Truck();b.id="T2";b.risk=new Risk(1,"HIGH","RULE_BASED");b.affectedIncidentIds.add("I2");s.trucks.add(b);
        Incident i=new Incident();i.id="I2";i.severity=1;i.startSec=0;i.endSec=100;i.status="ACTIVE";s.incidents.add(i);
        GraphView g=graph(List.of("TRUCK:T1","TRUCK:T2","WAREHOUSE:W1"),List.of(
                e("a","TRUCK:T1","WAREHOUSE:W1",0,100,.4),e("b","TRUCK:T2","WAREHOUSE:W1",0,100,.5)));
        CascadeView r=baseline.predict(s,g);
        assertEquals(.7,score(r,"WAREHOUSE:W1"),1e-12);
        assertEquals(List.of("INCIDENT:I1","INCIDENT:I2"),risk(r,"WAREHOUSE:W1").causeIds());
    }

    @Test void cyclesCannotAmplifyOrIterateWithoutBound() {
        State s=incidentState("I1",1);
        GraphView g=graph(List.of("TRUCK:T1","DOCK:D1","DRIVER:DR1"),List.of(
                e("a","TRUCK:T1","DOCK:D1",0,100,.8),e("b","DOCK:D1","DRIVER:DR1",0,100,.7),
                e("c","DRIVER:DR1","TRUCK:T1",0,100,1),e("d","DOCK:D1","TRUCK:T1",0,100,1)));
        CascadeView r=baseline.predict(s,g);
        assertEquals(1,score(r,"TRUCK:T1"),1e-12);
        assertEquals(.8,score(r,"DOCK:D1"),1e-12);
        assertEquals(.56,score(r,"DRIVER:DR1"),1e-12);
        assertTrue(r.iterations() <= g.nodes().size()-1);
        assertTrue(r.nodeRisks().stream().allMatch(n -> Double.isFinite(n.score()) && n.score() >= 0 && n.score() <= 1));
    }

    @Test void expiredDependenciesAndResolvedCausesDoNotPropagate() {
        State s=incidentState("I1",1);s.clockSec=10;
        GraphView g=graph(List.of("TRUCK:T1","DOCK:D1","DELIVERY:L1"),List.of(
                e("expired","TRUCK:T1","DOCK:D1",0,10,1),e("future","TRUCK:T1","DELIVERY:L1",20,100,.5)));
        CascadeView r=baseline.predict(s,g);
        assertEquals(0,score(r,"DOCK:D1"));
        assertEquals(.5,score(r,"DELIVERY:L1"));
        s.incidents.get(0).status="RESOLVED";
        assertTrue(baseline.predict(s,g).nodeRisks().stream().allMatch(n -> n.score() == 0));
    }

    @Test void severityChangesSeedsAndAffectedSubgraphThreshold() {
        State s=incidentState("I1",.2);s.trucks.get(0).risk=new Risk(0,"LOW","RULE_BASED");
        GraphView g=graph(List.of("TRUCK:T1","DOCK:D1"),List.of(e("a","TRUCK:T1","DOCK:D1",0,100,.8)));
        CascadeView mild=baseline.predict(s,g);
        assertEquals(.31,mild.threshold(),1e-12);
        assertEquals(.07,score(mild,"TRUCK:T1"),1e-12);
        assertTrue(mild.affectedNodeIds().isEmpty());
        s.incidents.get(0).severity=1;
        CascadeView severe=baseline.predict(s,g);
        assertEquals(.15,severe.threshold(),1e-12);
        assertEquals(.35,score(severe,"TRUCK:T1"),1e-12);
        assertTrue(severe.affectedNodeIds().contains("DOCK:D1"));
    }

    @Test void noRoadResourceConstraintSeedsSimulatedPredictionAndNeverClaimsObservation() {
        State s=fixture();
        s.operations.predictedImpacts.add(new Impact("P1","DRIVER_UNAVAILABLE",List.of("DRIVER:DR1"),List.of("T1"),0,100,100,true,"explicit unavailable driver","SIMULATED_PREDICTION"));
        GraphView graph=new OperationalDependencyGraph().build(s);
        CascadeView result=baseline.predict(s,graph);
        assertTrue(score(result,"DRIVER:DR1") > 0);
        assertTrue(score(result,"TRUCK:T1") > 0);
        assertEquals(List.of("OPERATIONS:P1"),risk(result,"TRUCK:T1").causeIds());
        assertEquals("SIMULATED_PREDICTION",result.provenance());
        assertEquals("RULE_BASED_GRAPH_BASELINE",result.provider());
    }

    @Test void roadInducedDockConstraintRetainsSameIncidentCauseAcrossResourceCycles() {
        State s=fixture();
        Incident i=new Incident();i.id="I1";i.severity=1;i.endSec=1000;i.status="ACTIVE";s.incidents.add(i);
        s.trucks.get(0).risk=new Risk(1,"HIGH","RULE_BASED");s.trucks.get(0).affectedIncidentIds.add("I1");
        s.operations.predictedImpacts.add(new Impact("P1","DOCK_OVERLAP",List.of("DOCK:D1","TRUCK:T1"),List.of("T2"),100,300,120,true,"explicit forecast","SIMULATED_PREDICTION"));
        CascadeView result=baseline.predict(s,new OperationalDependencyGraph().build(s));
        assertEquals(List.of("INCIDENT:I1"),risk(result,"TRUCK:T2").causeIds());
        assertTrue(score(result,"TRUCK:T2") <= score(result,"DOCK:D1"));
        assertFalse(risk(result,"TRUCK:T2").direct());
    }

    @Test void encounteredExpiredRoadIncidentRetainsOnlyCurrentBlockerConsequenceAttribution() {
        State s=fixture();s.clockSec=30;
        Incident incident=new Incident();incident.id="I1";incident.severity=1;incident.startSec=0;incident.endSec=10;incident.status="RESOLVED";s.incidents.add(incident);
        Truck blocker=s.trucks.get(0);blocker.encounteredIncidentIds.add("I1");blocker.arrivalSec=30;blocker.baselineArrivalSec=10;blocker.etaSec=30;
        s.operations.predictedImpacts.add(new Impact("P1","DOCK_OVERLAP",List.of("DOCK:D1","TRUCK:T1"),List.of("T2"),30,100,70,true,"current blocker was physically delayed","SIMULATED_PREDICTION"));
        CascadeView result=baseline.predict(s,new OperationalDependencyGraph().build(s));
        assertEquals(List.of("INCIDENT:I1"),risk(result,"TRUCK:T2").causeIds());
        assertTrue(score(result,"TRUCK:T2") > 0);
        assertEquals(0,score(result,"TRUCK:T1"),1e-12);
        assertFalse(risk(result,"TRUCK:T1").direct());
        assertEquals(.15,result.threshold(),1e-12);
        s.operations.predictedImpacts.clear();
        CascadeView cleared=baseline.predict(s,new OperationalDependencyGraph().build(s));
        assertTrue(cleared.nodeRisks().stream().allMatch(r -> r.score() == 0));
    }

    @Test void unknownDriverAvailabilitySeedsItsOwnConstraintWithoutInventingDuration() {
        State s=fixture();s.operations.drivers.get(0).available=false;
        s.operations.predictedImpacts.add(new Impact("P1","DRIVER_UNAVAILABLE",List.of("DRIVER:DR1"),List.of("T1"),0,1000,0,true,"ETA unknown","SIMULATED_PREDICTION"));
        CascadeView result=baseline.predict(s,new OperationalDependencyGraph().build(s));
        assertEquals(.8,score(result,"DRIVER:DR1"),1e-12);
        assertEquals(List.of("OPERATIONS:P1"),risk(result,"TRUCK:T1").causeIds());
        assertTrue(result.affectedNodeIds().contains("TRUCK:T1"));
    }

    @Test void deterministicOrderingAndEmptyGraphsAreStable() {
        State s=incidentState("I1",1);
        List<GraphNode> nodes=new ArrayList<>(List.of(n("TRUCK:T1"),n("DOCK:D1"),n("WAREHOUSE:W1")));
        List<GraphEdge> edges=new ArrayList<>(List.of(e("a","TRUCK:T1","DOCK:D1",0,100,.8),e("b","DOCK:D1","WAREHOUSE:W1",0,100,.7)));
        CascadeView first=baseline.predict(s,new GraphView("test",0,"test",nodes,edges,"SIMULATED"));
        Collections.reverse(nodes);Collections.reverse(edges);
        assertEquals(first,baseline.predict(s,new GraphView("test",0,"test",nodes,edges,"SIMULATED")));
        CascadeView empty=baseline.predict(new State(),graph(List.of(),List.of()));
        assertEquals(0,empty.iterations());assertTrue(empty.nodeRisks().isEmpty());
    }

    static State incidentState(String id,double severity) {
        State s=new State();s.networkId="test-network";
        Truck t=new Truck();t.id="T1";t.risk=new Risk(1,"HIGH","RULE_BASED");t.affectedIncidentIds.add(id);s.trucks.add(t);
        Incident i=new Incident();i.id=id;i.severity=severity;i.startSec=0;i.endSec=100;i.status="ACTIVE";s.incidents.add(i);
        return s;
    }
    static GraphView graph(List<String> nodes,List<GraphEdge> edges) {return new GraphView("test",0,"test",nodes.stream().map(OperationalDependencyGraphTest::n).toList(),edges,"SIMULATED");}
    static NodeRisk risk(CascadeView view,String id) {return view.nodeRisks().stream().filter(r -> r.nodeId().equals(id)).findFirst().orElseThrow();}
    static double score(CascadeView view,String id) {return risk(view,id).score();}
}
