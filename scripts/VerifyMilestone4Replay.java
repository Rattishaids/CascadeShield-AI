import com.fasterxml.jackson.databind.*;
import io.cascadeshield.sim.*;
import java.nio.file.*;
import java.util.*;
import static io.cascadeshield.sim.BenchmarkModels.*;

/** Standalone reruns of two declared final cases; no live application/database is loaded. */
public class VerifyMilestone4Replay {
    private static final ObjectMapper M=new ObjectMapper().findAndRegisterModules();
    private static final List<String> FAMILIES=List.of("single-closure","driver-unavailability");
    private static JsonNode decisionIdentity(PolicyRun run){
        var out=M.createArrayNode();
        for(DecisionTrace d:run.decisions()){
            var row=M.createObjectNode();row.put("clockSec",d.clockSec());row.put("truckId",d.truckId());
            row.put("selectedActionId",d.selectedActionId());row.put("knowledgeFingerprint",d.knowledgeFingerprint());
            var candidates=M.createArrayNode();
            for(ScoredAlternative a:d.alternatives()){
                var c=M.createObjectNode();c.put("actionId",a.action().id());c.put("feasible",a.feasible());c.put("score",a.score());candidates.add(c);
            }
            row.set("alternatives",candidates);out.add(row);
        }
        return out;
    }
    public static void main(String[] args)throws Exception{
        Path root=Path.of(args[0]), reportPath=Path.of(args[1]);
        var freeze=M.readTree(root.resolve("reports/milestone4_policy_raw/policies_implementation_freeze.json").toFile());
        RoadGraph roads=RoadGraph.load(root.resolve("data/processed/chennai_osm/road_graph.json"),M);
        var protocol=new MlExperimentProtocol(root.resolve("config/milestone4_protocol_v2.json"),roads,M);
        var client=new MlInferenceClient(M,"http://host.docker.internal:8090",2000);
        String graphSha=M.readTree(root.resolve("models/milestone4/v1/manifest.json").toFile()).path("graphSha256").asText();
        var learned=new MlPolicyRunner(roads,M,client::infer,graphSha);
        var historical=new BenchmarkPolicyRunner(roads,M);
        var checks=new ArrayList<Map<String,Object>>();
        for(ScenarioSpec spec:protocol.scenarios("final"))if(spec.seed()==4001&&FAMILIES.contains(spec.profile())){
            for(String id:List.of("B3","B5_XGB_V1")){
                Path priorPath=root.resolve("reports/milestone4_policy_raw/"+spec.id()+"__"+id+".json");
                JsonNode prior=M.readTree(priorPath.toFile());
                PolicyRun original=M.treeToValue(prior.path("run"),PolicyRun.class);
                PolicyRun replay=id.equals("B3")?historical.run(spec,BenchmarkPolicyRunner.catalog(true).stream().filter(p->p.id().equals(id)).findFirst().orElseThrow()):learned.run(spec,MlPolicyRunner.variants().stream().filter(v->v.id().equals(id)).findFirst().orElseThrow());
                var a=(com.fasterxml.jackson.databind.node.ObjectNode)M.valueToTree(original.metrics());
                var b=(com.fasterxml.jackson.databind.node.ObjectNode)M.valueToTree(replay.metrics());
                a.remove("decisionComputationMs");b.remove("decisionComputationMs");
                boolean outcomes=a.equals(b), decisions=decisionIdentity(original).equals(decisionIdentity(replay));
                boolean fingerprints=Objects.equals(original.finalSummary().get("finalFingerprint"),replay.finalSummary().get("finalFingerprint"));
                int failed=((Number)replay.finalSummary().getOrDefault("failedInferenceRequests",0)).intValue();
                boolean passed=outcomes&&decisions&&fingerprints&&failed==0;
                var row=new LinkedHashMap<String,Object>();row.put("scenarioId",spec.id());row.put("policyId",id);
                row.put("realizedMetricsEqualExceptComputation",outcomes);row.put("candidateScoresAndActionsEqual",decisions);
                row.put("finalStateFingerprintEqual",fingerprints);row.put("failedInferenceRequests",failed);row.put("passed",passed);checks.add(row);
                if(!passed)throw new IllegalStateException("Replay differs: "+M.writeValueAsString(row));
            }
        }
        if(checks.size()!=4)throw new IllegalStateException("Did not execute all four predeclared replay checks");
        var result=Map.of("schemaVersion","cascadeshield.milestone4-replay/1.0","provenance","ENGINEERING_TEST_EVIDENCE",
            "passed",true,"checks",checks,"passedChecks",checks.size(),"stateMutated",false,
            "timingExcluded",true,"selectionManifestSha256",freeze.path("selectionManifestSha256").asText());
        Files.writeString(reportPath,M.writerWithDefaultPrettyPrinter().writeValueAsString(result)+"\n");
        System.out.println("PASS: four actual frozen policy reruns; exact outcomes, candidate scores/actions and final fingerprints");
    }
}
