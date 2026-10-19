package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import static io.cascadeshield.sim.MlModels.*;

/** Separate read-only inference endpoint; state writes remain in the guarded simulator service. */
@RestController
@RequestMapping("/api/ml")
@CrossOrigin(origins={"http://127.0.0.1:5173","http://localhost:5173"})
public class MlController {
    public record Selection(String modelId) {}
    private final SimulationService simulation;
    private final MlFeatureExtractor features;
    private final MlInferenceClient client;
    private final MlOperatorAdvisor advisor;
    private final String graphSha;
    private final Map<UUID,ArrayDeque<Map<String,Object>>> history=new LinkedHashMap<>();
    public MlController(SimulationService simulation,ObjectMapper mapper,@Value("${simulator.graph-path}")String graphPath,
        @Value("${simulator.ml-url:http://host.docker.internal:8090}")String mlUrl,@Value("${simulator.ml-timeout-ms:1500}")int timeoutMs)throws Exception{
        this.simulation=simulation;Path path=Path.of(graphPath);RoadGraph roads=RoadGraph.load(path,mapper);features=new MlFeatureExtractor(roads,mapper);
        graphSha=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));client=new MlInferenceClient(mapper,mlUrl,timeoutMs);
        advisor=new MlOperatorAdvisor(roads,mapper,client::infer,graphSha);
    }
    @GetMapping("/status")public Map<String,Object> status(){return Map.of("schemaVersion",RESPONSE_VERSION,"featureSchema",features.featureSchema(),"networkGraphSha256",graphSha,"registry",client.status(),"authority","READ_ONLY_PREDICTION; Java transitions and operator approval remain authoritative");}
    @PostMapping("/recommendations/{truckId}")public MlOperatorAdvisor.Advice advice(@PathVariable String truckId,@RequestBody(required=false)Selection selection){return advisor.recommend(simulation.state(),truckId,selection==null||selection.modelId()==null?"xgb-v1":selection.modelId());}
    @PostMapping("/predict")public synchronized Map<String,Object> predict(@RequestBody(required=false)Selection selection){
        long started=System.nanoTime();String model=selection==null||selection.modelId()==null?"xgb-v1":selection.modelId();if(!MODEL_IDS.contains(model)&&!"rule-v1".equals(model))throw ApiException.invalid("Unsupported ML model ID");
        Models.State state=simulation.state();Map<String,Object> frame=features.frame(state);double clock=state.clockSec;
        ArrayDeque<Map<String,Object>> frames=history.computeIfAbsent(state.runId,id->new ArrayDeque<>());
        if(!frames.isEmpty()&&((Number)frames.getLast().get("clockSec")).doubleValue()>clock)frames.clear();
        List<Map<String,Object>> earlier=frames.stream().filter(f->((Number)f.get("clockSec")).doubleValue()<clock-1e-8).toList();
        Response result;String failure=null;
        try{result="rule-v1".equals(model)?fallback(frame,model,"Operator selected the deterministic baseline",0):client.infer(frame,earlier,model,graphSha);}catch(InferenceException e){failure=e.getMessage();result=fallback(frame,model,failure,(System.nanoTime()-started)/1e6);}
        if(frames.isEmpty()||clock-((Number)frames.getLast().get("clockSec")).doubleValue()>=10){frames.addLast(frame);while(frames.size()>3)frames.removeFirst();}
        while(history.size()>4)history.remove(history.keySet().iterator().next());
        Map<String,Object> output=new LinkedHashMap<>();output.put("prediction",result);output.put("requestedModelId",model);output.put("fallbackUsed",failure!=null);output.put("failureReason",failure);output.put("endToEndLatencyMs",(System.nanoTime()-started)/1e6);output.put("historicalFramesUsed",earlier.size());output.put("inputProvenance",frame.get("provenance"));output.put("stateMutated",false);return output;
    }
    @SuppressWarnings("unchecked")
    private Response fallback(Map<String,Object> frame,String requested,String reason,double elapsed){
        List<Prediction> values=new ArrayList<>();for(Map<String,Object> t:(List<Map<String,Object>>)frame.get("trucks")){
            Map<String,Object> baseline=(Map<String,Object>)t.get("baseline");Double remaining=Boolean.TRUE.equals(t.get("etaEligible"))&&baseline.get("remainingArrivalSec") instanceof Number n?n.doubleValue():null;
            values.add(new Prediction((String)t.get("truckId"),remaining,null,null,null,null));
        }
        return new Response(RESPONSE_VERSION,MlFeatureExtractor.VERSION,(String)frame.get("featureSchemaHash"),(String)frame.get("networkId"),graphSha,"rule-v1","deterministic-existing-runtime","RULE_BASED",(String)frame.get("stateFingerprint"),((Number)frame.get("clockSec")).doubleValue(),List.copyOf(values),Map.of("status","UNCALIBRATED_RULE_FALLBACK","domain","SIMULATED_OPERATIONS"),elapsed,List.of("rule-v1".equals(requested)?reason:"Requested "+requested+" unavailable: "+reason,"Absent calibrated probabilities/intervals remain null; no observations are invented."),"SIMULATED_RULE_PREDICTION");
    }
}
