package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import static io.cascadeshield.sim.MlModels.*;

/** Shared batch/live transport. It has no reference to an engine and cannot execute actions. */
public final class MlInferenceClient {
    private final ObjectMapper mapper;
    private final HttpClient http;
    private final URI base;
    private final int timeoutMs;
    public MlInferenceClient(ObjectMapper mapper,String baseUrl,int timeoutMs){
        this.mapper=mapper;this.base=URI.create(baseUrl.endsWith("/")?baseUrl.substring(0,baseUrl.length()-1):baseUrl);
        if(!Set.of("http","https").contains(base.getScheme())||base.getHost()==null)throw new IllegalArgumentException("ML service must have an HTTP(S) URL");
        if(timeoutMs<50||timeoutMs>10000)throw new IllegalArgumentException("ML timeout must be within 50..10000 ms");
        this.timeoutMs=timeoutMs;http=HttpClient.newBuilder().connectTimeout(Duration.ofMillis(Math.min(timeoutMs,1000))).build();
    }
    public Response infer(Map<String,Object> frame,List<Map<String,Object>> history,String modelId,String graphSha){
        if(!MODEL_IDS.contains(modelId))throw new InferenceException("Unsupported model ID");
        if(frame==null||!"cascadeshield.ml-frame/1.0".equals(frame.get("schemaVersion"))||!MlFeatureExtractor.VERSION.equals(frame.get("featureSchemaVersion")))throw new InferenceException("Incompatible prediction frame schema");
        validateInputs(frame);double clock=finiteNumber(frame.get("clockSec"),"prediction clock");
        if(graphSha==null||!graphSha.matches("[a-f0-9]{64}"))throw new InferenceException("Missing immutable graph SHA-256");
        List<Map<String,Object>> past=history==null?List.of():List.copyOf(history);
        double previous=-1;
        for(Map<String,Object> h:past){validateInputs(h);double time=finiteNumber(h.get("clockSec"),"history clock");if(time>clock+1e-8||time<previous||!Objects.equals(h.get("networkId"),frame.get("networkId"))||!Objects.equals(h.get("featureSchemaHash"),frame.get("featureSchemaHash")))throw new InferenceException("History must be ordered, past-only and use the same network/schema");previous=time;}
        if(past.size()>3)throw new InferenceException("At most three preceding graph frames are supported");
        Request request=new Request(REQUEST_VERSION,MlFeatureExtractor.VERSION,(String)frame.get("featureSchemaHash"),(String)frame.get("networkId"),graphSha,modelId,(String)frame.get("stateFingerprint"),frame,past);
        try{
            HttpRequest call=HttpRequest.newBuilder(base.resolve(base.getPath()+"/predict")).timeout(Duration.ofMillis(timeoutMs)).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(request))).build();
            HttpResponse<String> reply=http.send(call,HttpResponse.BodyHandlers.ofString());
            if(reply.statusCode()!=200)throw new InferenceException("ML service HTTP "+reply.statusCode());
            Response response=mapper.readValue(reply.body(),Response.class);validateResponse(request,response);return response;
        }catch(InferenceException e){throw e;}catch(InterruptedException e){Thread.currentThread().interrupt();throw new InferenceException("ML inference interrupted",e);}catch(Exception e){throw new InferenceException("ML inference unavailable or invalid: "+e.getClass().getSimpleName(),e);}
    }
    public Map<String,Object> status(){
        try{HttpRequest request=HttpRequest.newBuilder(base.resolve(base.getPath()+"/models")).timeout(Duration.ofMillis(timeoutMs)).GET().build();HttpResponse<String> response=http.send(request,HttpResponse.BodyHandlers.ofString());if(response.statusCode()!=200)throw new InferenceException("ML models HTTP "+response.statusCode());return mapper.readValue(response.body(),Map.class);}
        catch(Exception e){if(e instanceof InterruptedException)Thread.currentThread().interrupt();return Map.of("available",false,"source","DETERMINISTIC_FALLBACK","reason",e.getClass().getSimpleName());}
    }
    static void validateInputs(Object value){
        if(value instanceof Map<?,?> map)for(var entry:map.entrySet()){
            String key=String.valueOf(entry.getKey());Object item=entry.getValue();
            if(Set.of("labels","nodeLabels","outcomes","finalOutcomes","exogenousSchedule","replaySchedule").contains(key))throw new InferenceException("Outcome/private schedule is forbidden in inference input: "+key);
            if("realizedLabels".equals(key)&&(!(item instanceof List<?> list)||!list.isEmpty()))throw new InferenceException("Realized labels must be absent from inference input");
            validateInputs(item);
        }else if(value instanceof List<?> list)for(Object item:list)validateInputs(item);
        else if(value instanceof Number n&&!Double.isFinite(n.doubleValue()))throw new InferenceException("Nonfinite inference input");
    }
    private static double finiteNumber(Object value,String label){if(!(value instanceof Number n)||!Double.isFinite(n.doubleValue()))throw new InferenceException("Invalid "+label);return n.doubleValue();}
    private static void number(Double value,String label,boolean optional){if(value==null&&optional)return;if(value==null||!Double.isFinite(value)||value<0)throw new InferenceException("Invalid "+label);}
    private static void probability(Double value,String label,boolean optional){number(value,label,optional);if(value!=null&&value>1)throw new InferenceException("Invalid "+label);}
    @SuppressWarnings("unchecked")
    static void validateResponse(Request q,Response r){
        if(r==null||!RESPONSE_VERSION.equals(r.schemaVersion())||!q.featureSchemaVersion().equals(r.featureSchemaVersion())||!q.featureSchemaHash().equals(r.featureSchemaHash())||!q.networkId().equals(r.networkId())||!q.graphSha256().equals(r.graphSha256())||!q.modelId().equals(r.modelId())||!MODEL_VERSION.equals(r.modelVersion())||!q.stateFingerprint().equals(r.stateFingerprint())||!"TRAINED_SIMULATION_MODEL".equals(r.source())||!"SIMULATED_PREDICTION".equals(r.provenance()))throw new InferenceException("ML model/schema/network/source/fingerprint mismatch");
        number(r.clockSec(),"response clock",false);if(Math.abs(r.clockSec()-finiteNumber(q.frame().get("clockSec"),"request clock"))>1e-8)throw new InferenceException("Stale ML prediction clock");
        number(r.latencyMs(),"inference latency",false);if(r.predictions()==null||r.calibration()==null||r.warnings()==null)throw new InferenceException("Missing ML provenance/calibration/output fields");
        Map<String,Map<String,Object>> expected=new LinkedHashMap<>();for(Map<String,Object> t:(List<Map<String,Object>>)q.frame().get("trucks"))expected.put((String)t.get("truckId"),t);
        Set<String> received=new HashSet<>();for(Prediction p:r.predictions()){
            if(p==null||!expected.containsKey(p.truckId())||!received.add(p.truckId()))throw new InferenceException("Missing/duplicate/unexpected prediction truck");
            Map<String,Object> t=expected.get(p.truckId());boolean eta=Boolean.TRUE.equals(t.get("etaEligible")),delivery=Boolean.TRUE.equals(t.get("deliveryEligible"));
            number(p.remainingArrivalSec(),"remaining arrival",!eta);number(p.etaLowerSec(),"ETA lower bound",!eta);number(p.etaUpperSec(),"ETA upper bound",!eta);
            if(eta&&p.etaLowerSec()>p.etaUpperSec())throw new InferenceException("Reversed ETA interval");
            probability(p.slaProbability(),"SLA probability",!delivery);probability(p.futureImpactProbability(),"future impact probability",false);
        }
        if(!received.equals(expected.keySet()))throw new InferenceException("Incomplete ML prediction coverage");
    }
}
