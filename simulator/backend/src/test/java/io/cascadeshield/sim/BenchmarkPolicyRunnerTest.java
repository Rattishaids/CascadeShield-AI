package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.BenchmarkModels.*;
import static io.cascadeshield.sim.OpsModels.*;

/** Small explicitly synthetic unit-test geography; research runs use the immutable Chennai graph. */
class BenchmarkPolicyRunnerTest {
    private static final ObjectMapper MAPPER=new ObjectMapper().findAndRegisterModules();
    private static RoadGraph roads(){
        List<Node> nodes=List.of(new Node(1,80.25,13.05),new Node(2,80.251,13.05),new Node(3,80.25,13.051),new Node(4,80.251,13.051));
        List<Edge> edges=new ArrayList<>();add(edges,nodes,"AB",1,2,100);add(edges,nodes,"BD",2,4,100);add(edges,nodes,"AC",1,3,120);add(edges,nodes,"CD",3,4,120);
        return new RoadGraph(new NetworkFile("BENCHMARK_UNIT_TEST_ONLY","Unit fixture",List.of(13d,80d,14d,81d),nodes,edges,List.of(),Map.of("provenance","TEST_FIXTURE_ONLY","demoPairs",List.of(Map.of("startNodeId",1,"destinationNodeId",4)))));
    }
    private static void add(List<Edge> e,List<Node> n,String id,long a,long b,double length){for(int direction=0;direction<2;direction++){long from=direction==0?a:b,to=direction==0?b:a;e.add(new Edge(id+(direction==0?"f":"r"),id,from,to,Math.min(a,b)*10+Math.max(a,b),length,36,"TEST_FIXTURE_ONLY","residential",id,List.of(n.get((int)from-1).point().coordinates(),n.get((int)to-1).point().coordinates()),Map.of()));}}
    private static Map<String,Object> params(){return new LinkedHashMap<>(Map.of("truckCount",2,"serviceSec",4,"departureGapSec",5,"incidentStartSec",0,"incidentDurationSec",20,"horizonSec",300,"deadlineSlackSec",5,"maxDecisions",4));}
    private static ScenarioSpec scenario(){return new BenchmarkScenarioGenerator(roads(),MAPPER).generate("closure-contention",23,params());}

    @Test void sameSeedHasIdenticalCanonicalInputsAndPhysicalInitialStates(){
        BenchmarkScenarioGenerator g=new BenchmarkScenarioGenerator(roads(),MAPPER);ScenarioSpec a=g.generate("closure-contention",23,params()),b=g.generate("closure-contention",23,params());
        assertEquals(a,b);assertEquals(MAPPER.valueToTree(g.initial(a)),MAPPER.valueToTree(g.initial(b)));
        assertNotEquals(a.inputFingerprint(),g.generate("closure-contention",24,params()).inputFingerprint());
        assertEquals(PROVENANCE,a.provenance());assertEquals(PROVENANCE,g.initial(a).operationsProvenance);
    }
    @Test void generatorKeepsAllFutureIncidentsAndDriverRestorationsOutsidePolicyState(){
        Map<String,Object> p=params();p.put("driverUnavailableFraction",1);p.put("driverRestoreSec",80);p.put("incidentStartSec",50);
        BenchmarkScenarioGenerator g=new BenchmarkScenarioGenerator(roads(),MAPPER);ScenarioSpec spec=g.generate("closure-contention",3,p);State initial=g.initial(spec);
        assertTrue(initial.incidents.isEmpty());assertTrue(initial.commandHistory.isEmpty());assertTrue(initial.replaySchedule.isEmpty());
        assertTrue(initial.operations.drivers.stream().noneMatch(d->d.available));assertTrue(initial.trucks.stream().noneMatch(t->t.etaKnown));
        assertEquals(3,spec.exogenousSchedule().size());assertTrue(spec.exogenousSchedule().stream().anyMatch(c->c.kind().equals("DRIVER_AVAILABILITY")&&c.clockSec()==80));
    }
    @Test void generatorRejectsUnboundedCountsMalformedParametersAndAbsentPreparedPairs(){
        BenchmarkScenarioGenerator g=new BenchmarkScenarioGenerator(roads(),MAPPER);
        assertThrows(ApiException.class,()->g.generate("closure-contention",1,Map.of("truckCount",2.5)));
        assertThrows(ApiException.class,()->g.generate("closure-contention",1,Map.of("severity",Double.NaN)));
        assertThrows(ApiException.class,()->g.generate("closure-contention",1,Map.of("unrecognized",1)));
        assertThrows(ApiException.class,()->g.generate("closure-contention",1,Map.of("warehouseCount",2)));
        assertThrows(ApiException.class,()->g.generate("closure-contention",1,Map.of("simultaneousIncidents","true")));
        assertThrows(ApiException.class,()->g.generate("closure-contention",1,Map.of("horizonSec",300.03)));
        assertThrows(ApiException.class,()->g.generate("closure-contention",1,Map.of("horizonSec",300,"serviceSec",600)));
    }
    @Test void allPoliciesShareIdenticalInitialFingerprintAndScenarioSchedules(){
        BenchmarkPolicyRunner runner=new BenchmarkPolicyRunner(roads(),MAPPER);ScenarioSpec spec=scenario();List<PolicyRun> runs=new ArrayList<>();
        for(PolicySpec p:BenchmarkPolicyRunner.catalog(false))runs.add(runner.run(spec,p));
        assertEquals(1,runs.stream().map(r->r.finalSummary().get("initialFingerprint")).distinct().count());
        assertTrue(runs.stream().allMatch(r->r.inputFingerprint().equals(spec.inputFingerprint())));
        assertTrue(runs.stream().allMatch(r->r.metrics().constraintViolations()==0));assertTrue(runs.stream().allMatch(r->r.metrics().completedDeliveries()==2));
        assertTrue(runs.getFirst().decisions().isEmpty());assertTrue(runs.stream().filter(r->r.policyId().equals("B4")).findFirst().orElseThrow().decisions().stream().anyMatch(d->d.alternatives().stream().anyMatch(a->a.metrics()!=null)));
    }
    @Test void equalComparisonPoliciesReceiveExactlySameRoadActions(){
        List<PolicySpec> equal=BenchmarkPolicyRunner.catalog(true);assertEquals(1,equal.stream().map(PolicySpec::allowedActions).distinct().count());
        assertFalse(equal.getFirst().allowedActions().contains(ActionType.ADJUST_DOCK_RESERVATION));
        assertEquals("EQUAL_ACTIONS",new BenchmarkPolicyRunner(roads(),MAPPER).run(scenario(),equal.getFirst()).finalSummary().get("comparisonMode"));
    }
    @Test void originalB3DelegatesSelectionToExistingFallbackForEquivalentCandidates(){
        ScenarioSpec spec=scenario();BenchmarkScenarioGenerator g=new BenchmarkScenarioGenerator(roads(),MAPPER);SimulationEngine e=new SimulationEngine(roads(),MAPPER);e.restore(g.initial(spec));
        for(ScheduledCommand c:spec.exogenousSchedule())if(c.clockSec()==0&&c.kind().equals("INCIDENT_ADD")){
            Map<String,Object> p=c.payload();e.addIncident(new IncidentRequest((String)p.get("type"),(String)p.get("physicalId"),((Number)p.get("severity")).doubleValue(),((Number)p.get("durationSec")).doubleValue(),0d));
        }
        String selected=new AiFallbackPipeline(roads(),MAPPER).recommend(e.raw(),"T1").selected().action();
        PolicyRun run=new BenchmarkPolicyRunner(roads(),MAPPER).run(spec,BenchmarkPolicyRunner.catalog(false).get(3));DecisionTrace trace=run.decisions().getFirst();
        ActionType actual=trace.alternatives().stream().filter(a->a.action().id().equals(trace.selectedActionId())).findFirst().orElseThrow().action().type();
        assertEquals(switch(selected){case "REROUTE" -> ActionType.GLOBAL_REROUTE;case "WAIT" -> ActionType.WAIT;default -> ActionType.CONTINUE;},actual);
    }
    @Test void replayOutcomesAndSelectionsAreDeterministicApartFromMeasuredComputationTime(){
        BenchmarkPolicyRunner runner=new BenchmarkPolicyRunner(roads(),MAPPER);PolicySpec p=BenchmarkPolicyRunner.catalog(false).get(4);PolicyRun a=runner.run(scenario(),p),b=runner.run(scenario(),p);
        assertEquals(a.metrics().totalDeliveryLatenessSec(),b.metrics().totalDeliveryLatenessSec());assertEquals(a.metrics().modeledOperationalCost(),b.metrics().modeledOperationalCost());
        assertEquals(a.finalSummary().get("finalFingerprint"),b.finalSummary().get("finalFingerprint"));
        assertEquals(a.decisions().stream().map(DecisionTrace::selectedActionId).toList(),b.decisions().stream().map(DecisionTrace::selectedActionId).toList());
    }
    @Test void noTemporalVariantRemovesForecastIntervalPropagationAndAdaptiveVariantChangesThreshold(){
        State s=new BenchmarkScenarioGenerator(roads(),MAPPER).initial(scenario());s.clockSec=1;
        SimulationEngine e=new SimulationEngine(roads(),MAPPER);e.restore(s);e.addIncident(new IncidentRequest("CLOSURE","AB",1,20,1d));
        BenchmarkPolicyRunner runner=new BenchmarkPolicyRunner(roads(),MAPPER);
        CascadeView full=runner.policyRisk(e.raw(),BenchmarkPolicyRunner.catalog(false).get(4));
        CascadeView fixed=runner.policyRisk(e.raw(),BenchmarkPolicyRunner.ablations().get(1));assertEquals(.35,fixed.threshold());assertTrue(full.threshold()<fixed.threshold());
        CascadeView noTemporal=runner.policyRisk(e.raw(),BenchmarkPolicyRunner.ablations().getFirst());
        assertTrue(noTemporal.nodeRisks().stream().filter(n->n.nodeId().startsWith("DELIVERY:")).mapToDouble(NodeRisk::score).sum()<full.nodeRisks().stream().filter(n->n.nodeId().startsWith("DELIVERY:")).mapToDouble(NodeRisk::score).sum());
    }
    @Test void counterfactualAblationUsesUnexecutedHeuristicAlternativesWhileFullUsesRealizedTrials(){
        BenchmarkPolicyRunner runner=new BenchmarkPolicyRunner(roads(),MAPPER);
        PolicyRun full=runner.run(scenario(),BenchmarkPolicyRunner.catalog(false).get(4)),off=runner.run(scenario(),BenchmarkPolicyRunner.ablations().get(2));
        assertFalse(full.decisions().isEmpty());assertFalse(off.decisions().isEmpty());
        assertTrue(full.decisions().getFirst().alternatives().stream().anyMatch(a->a.metrics()!=null));
        assertTrue(off.decisions().stream().flatMap(d->d.alternatives().stream()).allMatch(a->a.metrics()==null));
    }
    @Test void futureIncidentDetailsCannotChangeAnEarlierDecision(){
        ScenarioSpec original=scenario();List<ScheduledCommand> schedule=new ArrayList<>(original.exogenousSchedule());schedule.add(new ScheduledCommand(15,99,"INCIDENT_ADD",Map.of("type","SLOWDOWN","physicalId","CD","severity",1,"durationSec",50)));
        ScenarioSpec changed=new ScenarioSpec(original.id(),original.name(),original.seed(),original.profile(),original.configuration(),schedule,original.horizonSec(),original.inputFingerprint(),original.parameters(),original.provenance());
        BenchmarkPolicyRunner runner=new BenchmarkPolicyRunner(roads(),MAPPER);PolicySpec p=BenchmarkPolicyRunner.catalog(false).get(4);PolicyRun a=runner.run(original,p),b=runner.run(changed,p);
        assertEquals(a.decisions().getFirst().knowledgeFingerprint(),b.decisions().getFirst().knowledgeFingerprint());
        assertEquals(a.decisions().getFirst().selectedActionId(),b.decisions().getFirst().selectedActionId());
        assertEquals(a.decisions().getFirst().alternatives(),b.decisions().getFirst().alternatives());
    }
    @Test void decisionBudgetCapsPolicyActionsAndStillCompletesThroughActualRuntime(){
        Map<String,Object> p=params();p.put("maxDecisions",1);ScenarioSpec spec=new BenchmarkScenarioGenerator(roads(),MAPPER).generate("closure-contention",23,p);
        PolicyRun run=new BenchmarkPolicyRunner(roads(),MAPPER).run(spec,BenchmarkPolicyRunner.catalog(false).get(4));
        assertEquals(1,run.decisions().size());assertEquals(true,run.finalSummary().get("decisionLimitReached"));assertEquals(2,run.metrics().completedDeliveries());
    }
}
