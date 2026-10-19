package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Path;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;
import static io.cascadeshield.sim.BenchmarkModels.*;

/** Real prepared geography smoke check; all workload/outcomes remain explicitly simulated. */
class BenchmarkChennaiScenarioTest {
    @Test void seededRealChennaiCaseHasConnectedConsistentResourcesAndExecutedIsolatedOutcomes() throws Exception {
        String path=System.getenv("SIMULATOR_GRAPH_PATH");assumeTrue(path!=null&&!path.isBlank(),"Set SIMULATOR_GRAPH_PATH for actual Chennai validation");
        ObjectMapper mapper=new ObjectMapper().findAndRegisterModules();RoadGraph graph=RoadGraph.load(Path.of(path),mapper);
        BenchmarkScenarioGenerator generator=new BenchmarkScenarioGenerator(graph,mapper);
        Map<String,Object> p=Map.of("truckCount",2,"docksPerWarehouse",2,"serviceSec",60,"maxDecisions",2,"horizonSec",1800,"rolloutHorizonSec",1200);
        ScenarioSpec spec=generator.generate("closure-contention",7,p);var initial=generator.initial(spec);
        assertEquals(graph.network.networkId(),initial.networkId);assertTrue(initial.trucks.stream().allMatch(t->t.route.distanceM()>1000));
        assertTrue(initial.incidents.isEmpty());assertEquals(2,initial.operations.assignments.size());
        BenchmarkPolicyRunner runner=new BenchmarkPolicyRunner(graph,mapper);PolicyRun b0=runner.run(spec,BenchmarkPolicyRunner.catalog(false).getFirst()),b4=runner.run(spec,BenchmarkPolicyRunner.catalog(false).get(4));
        assertEquals(b0.finalSummary().get("initialFingerprint"),b4.finalSummary().get("initialFingerprint"));
        assertEquals(PROVENANCE,b4.metrics().provenance());assertEquals(0,b4.metrics().constraintViolations());assertEquals(2,b4.metrics().completedDeliveries());
        assertEquals("FIRST_OBSERVED_DISRUPTION",b4.finalSummary().get("beforeGraphPhase"));
        assertFalse(b4.decisions().isEmpty());assertTrue(b4.decisions().getFirst().alternatives().stream().anyMatch(a->a.metrics()!=null));
    }
}
