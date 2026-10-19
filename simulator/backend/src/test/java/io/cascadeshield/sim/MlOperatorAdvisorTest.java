package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static org.junit.jupiter.api.Assertions.*;

/** Small deterministic fixtures verify safety; they are never training/evaluation records. */
class MlOperatorAdvisorTest {
    private static final ObjectMapper M=new ObjectMapper().findAndRegisterModules();
    private State disrupted(){SimulationEngine engine=new SimulationEngine(MlCorpusTest.roads(),M);engine.restore(MlCorpusTest.state());engine.addIncident(new IncidentRequest("CLOSURE","AB",1,30,null));return engine.snapshot();}
    @SuppressWarnings("unchecked") private MlModels.Response response(Map<String,Object> frame,String model){
        List<MlModels.Prediction> predictions=new ArrayList<>();
        for(Map<String,Object> truck:(List<Map<String,Object>>)frame.get("trucks"))predictions.add(new MlModels.Prediction((String)truck.get("truckId"),30d,10d,50d,.4,.2));
        return new MlModels.Response(MlModels.RESPONSE_VERSION,MlFeatureExtractor.VERSION,(String)frame.get("featureSchemaHash"),(String)frame.get("networkId"),"TEST_FIXTURE_ONLY",model,MlModels.MODEL_VERSION,"TRAINED_SIMULATION_MODEL",(String)frame.get("stateFingerprint"),((Number)frame.get("clockSec")).doubleValue(),predictions,Map.of("status","TEST_FIXTURE_ONLY"),1d,List.of(),"TEST_FIXTURE_ONLY");
    }
    @Test void copiedCandidatePredictionPreservesLiveStateAndGuardedCandidateIdentity(){
        State s=disrupted();var before=M.valueToTree(s);List<Map<String,Object>> captured=new ArrayList<>();
        var advisor=new MlOperatorAdvisor(MlCorpusTest.roads(),M,(f,h,id,sha)->{captured.add(f);assertTrue(h.isEmpty());assertFalse(f.containsKey("exogenousSchedule"));assertTrue(M.valueToTree(f).path("graphSnapshot").path("realizedLabels").isEmpty());return response(f,id);},"TEST_FIXTURE_ONLY");
        var result=advisor.recommend(s,"T1","xgb-v1");assertFalse(result.fallbackUsed());assertFalse(result.stateMutated());assertEquals(before,M.valueToTree(s));assertTrue(captured.size()>=2);assertNotNull(result.selected());
        var baseline=new AiFallbackPipeline(MlCorpusTest.roads(),M);assertEquals(baseline.fingerprint(s),result.stateFingerprint());assertTrue(baseline.validate(s,result.selected()).valid());
        assertTrue(result.alternatives().stream().allMatch(o->o.prediction()!=null));
    }
    @Test void oneFailedCandidateForcesAnEntireDeterministicComparison(){
        State s=disrupted();int[] calls={0};var advisor=new MlOperatorAdvisor(MlCorpusTest.roads(),M,(f,h,id,sha)->{if(++calls[0]==2)throw new MlModels.InferenceException("TEST_OUTAGE");return response(f,id);},"TEST_FIXTURE_ONLY");
        var result=advisor.recommend(s,"T1","xgb-v1");assertTrue(result.fallbackUsed());assertEquals("DETERMINISTIC_RULE_SCORE",result.source());assertTrue(result.alternatives().stream().allMatch(o->o.prediction()==null));assertTrue(result.warnings().stream().anyMatch(w->w.contains("TEST_OUTAGE")));
    }
    @Test void ruleSelectionNeverContactsTheLearnedService(){
        var advisor=new MlOperatorAdvisor(MlCorpusTest.roads(),M,(f,h,id,sha)->{fail("Rule comparison contacted ML");return null;},"TEST_FIXTURE_ONLY");
        var result=advisor.recommend(disrupted(),"T1","rule-v1");assertFalse(result.fallbackUsed());assertEquals("DETERMINISTIC_RULE_SCORE",result.source());assertNotNull(result.selected());
    }
    @Test void adviceDoesNotAuthorizeAnActionAndStateChangesInvalidateItsCandidate(){
        State s=disrupted();var advisor=new MlOperatorAdvisor(MlCorpusTest.roads(),M,(f,h,id,sha)->response(f,id),"TEST_FIXTURE_ONLY");var result=advisor.recommend(s,"T1","xgb-v1");
        s.clockSec+=.1;assertThrows(ApiException.class,()->new AiFallbackPipeline(MlCorpusTest.roads(),M).validate(s,result.selected()));
        assertThrows(ApiException.class,()->advisor.recommend(s,"T1","unsupported-model"));
    }
    @Test void futureScheduledRoadPlansCannotSilentlyGiveOperatorAdviceForesight(){
        State s=disrupted();Incident future=new Incident();future.id="TEST_FUTURE";future.startSec=100;future.endSec=200;s.incidents.add(future);
        var advisor=new MlOperatorAdvisor(MlCorpusTest.roads(),M,(f,h,id,sha)->{fail("Future plan reached the model");return null;},"TEST_FIXTURE_ONLY");
        assertThrows(ApiException.class,()->advisor.recommend(s,"T1","xgb-v1"));
    }
}
