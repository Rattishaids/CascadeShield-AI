package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static io.cascadeshield.sim.BenchmarkModels.*;

class MlPolicyRunnerTest {
    private static final ObjectMapper M=new ObjectMapper().findAndRegisterModules();
    private static ScenarioSpec scenario(){return new BenchmarkScenarioGenerator(MlCorpusTest.roads(),M).generate("closure-contention",1001,MlCorpusTest.parameters());}
    private static MlPolicyRunner.Variant variant(String id){return MlPolicyRunner.variants().stream().filter(v->v.id().equals(id)).findFirst().orElseThrow();}
    @Test void newPoliciesHaveSameFiveActionsAsControlledHistoricalPolicies(){assertEquals(BenchmarkPolicyRunner.catalog(true).getLast().allowedActions(),MlPolicyRunner.COMMON);assertFalse(MlPolicyRunner.COMMON.contains(ActionType.ADJUST_DOCK_RESERVATION));assertEquals(6,MlPolicyRunner.variants().size());}
    @Test void serviceOutageUsesExactRulePolicyAndRecordsFallback(){MlPolicyRunner r=new MlPolicyRunner(MlCorpusTest.roads(),M,(f,h,id,sha)->{MlInferenceClient.validateInputs(f);throw new MlModels.InferenceException("UNIT_TEST_OUTAGE");},"0".repeat(64));PolicyRun rule=r.run(scenario(),variant("B5_RULE_V1")),failed=r.run(scenario(),variant("B5_XGB_V1"));assertEquals(rule.finalSummary().get("finalFingerprint"),failed.finalSummary().get("finalFingerprint"));assertEquals(rule.metrics().slaViolationRate(),failed.metrics().slaViolationRate());assertEquals(rule.decisions().stream().map(DecisionTrace::selectedActionId).toList(),failed.decisions().stream().map(DecisionTrace::selectedActionId).toList());assertTrue(((Number)failed.finalSummary().get("failedInferenceRequests")).intValue()>0);assertTrue(((Number)failed.finalSummary().get("fallbackDecisions")).intValue()>0);assertEquals(0,failed.metrics().constraintViolations());}
    @Test void learnedRiskChangesFixedScoreAndDoesNotUseCandidateMinMax(){var observed=new BenchmarkScenarioGenerator(MlCorpusTest.roads(),M).initial(scenario());Map<String,Object> frame=new MlFeatureExtractor(MlCorpusTest.roads(),M).frame(observed);Map<String,MlModels.Prediction> low=Map.of("T1",new MlModels.Prediction("T1",20d,10d,30d,0d,0d)),high=Map.of("T1",new MlModels.Prediction("T1",20d,10d,30d,1d,0d));double a=MlPolicyRunner.predictionScore(observed,frame,low,1000),b=MlPolicyRunner.predictionScore(observed,frame,high,1000);assertEquals(.3,b-a,1e-9);}
    @Test void newCounterfactualVariantExecutesTrialsWithForecastProvenance(){MlPolicyRunner r=new MlPolicyRunner(MlCorpusTest.roads(),M,(f,h,id,sha)->{throw new MlModels.InferenceException("UNIT_TEST_OUTAGE");},"0".repeat(64));PolicyRun run=r.run(scenario(),variant("B5_XGB_CF_V1"));assertTrue(((Number)run.finalSummary().get("simulationRolloutCount")).intValue()>0);assertTrue(run.decisions().stream().flatMap(d->d.alternatives().stream()).filter(a->a.metrics()!=null).allMatch(a->a.metrics().provenance().equals("MODEL_ROLLOUT_FORECAST")));assertEquals(0,run.metrics().constraintViolations());}
}
