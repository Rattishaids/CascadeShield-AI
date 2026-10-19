package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import java.net.InetSocketAddress;
import java.util.*;
import java.util.concurrent.Executors;
import static io.cascadeshield.sim.MlModels.*;
import static org.junit.jupiter.api.Assertions.*;

class MlInferenceClientTest {
    private final ObjectMapper mapper=new ObjectMapper();
    private static final String HASH="a".repeat(64),GRAPH="b".repeat(64);
    private Map<String,Object> frame(){return new LinkedHashMap<>(Map.of("schemaVersion","cascadeshield.ml-frame/1.0","featureSchemaVersion",MlFeatureExtractor.VERSION,"featureSchemaHash",HASH,"networkId","TEST_FIXTURE_ONLY","clockSec",10d,"stateFingerprint","fixture-current","trucks",List.of(Map.of("truckId","TEST-T","etaEligible",true,"deliveryEligible",true)),"graphSnapshot",Map.of("realizedLabels",List.of())));}
    private Request request(){return new Request(REQUEST_VERSION,MlFeatureExtractor.VERSION,HASH,"TEST_FIXTURE_ONLY",GRAPH,"xgb-v1","fixture-current",frame(),List.of());}
    private Response response(){return new Response(RESPONSE_VERSION,MlFeatureExtractor.VERSION,HASH,"TEST_FIXTURE_ONLY",GRAPH,"xgb-v1",MODEL_VERSION,"TRAINED_SIMULATION_MODEL","fixture-current",10d,List.of(new Prediction("TEST-T",30d,20d,40d,.4,.2)),Map.of("status","TEST_FIXTURE_ONLY"),1d,List.of(),"SIMULATED_PREDICTION");}
    @Test void validVersionedFinitePredictionAccepted(){assertDoesNotThrow(()->MlInferenceClient.validateResponse(request(),response()));}
    @Test void incompatibleVersionAndFingerprintRejected(){for(String field:List.of("modelVersion","stateFingerprint","networkId","featureSchemaHash","graphSha256","schemaVersion")){Map<String,Object> bad=mapper.convertValue(response(),Map.class);bad.put(field,"wrong");Response changed=mapper.convertValue(bad,Response.class);assertThrows(InferenceException.class,()->MlInferenceClient.validateResponse(request(),changed),field);}}
    @Test void probabilityAndEtaRangesAreChecked(){for(Prediction bad:List.of(new Prediction("TEST-T",30d,40d,20d,.4,.2),new Prediction("TEST-T",-1d,0d,20d,.4,.2),new Prediction("TEST-T",30d,20d,40d,1.1,.2),new Prediction("TEST-T",30d,20d,40d,.4,Double.NaN))){Response base=response();Response changed=new Response(base.schemaVersion(),base.featureSchemaVersion(),base.featureSchemaHash(),base.networkId(),base.graphSha256(),base.modelId(),base.modelVersion(),base.source(),base.stateFingerprint(),base.clockSec(),List.of(bad),base.calibration(),base.latencyMs(),base.warnings(),base.provenance());assertThrows(InferenceException.class,()->MlInferenceClient.validateResponse(request(),changed));}}
    @Test void missingAndDuplicatedTruckOutputsRejected(){for(List<Prediction> bad:List.of(List.<Prediction>of(),List.of(response().predictions().getFirst(),response().predictions().getFirst()))){Response base=response();Response changed=new Response(base.schemaVersion(),base.featureSchemaVersion(),base.featureSchemaHash(),base.networkId(),base.graphSha256(),base.modelId(),base.modelVersion(),base.source(),base.stateFingerprint(),base.clockSec(),bad,base.calibration(),base.latencyMs(),base.warnings(),base.provenance());assertThrows(InferenceException.class,()->MlInferenceClient.validateResponse(request(),changed));}}
    @Test void missingRequiredCalibratedOutputsRejected(){Map<String,Object> bad=mapper.convertValue(response(),Map.class);bad.put("predictions",List.of(Map.of("truckId","TEST-T","futureImpactProbability",.2)));assertThrows(InferenceException.class,()->MlInferenceClient.validateResponse(request(),mapper.convertValue(bad,Response.class)));}
    @Test void futureOrLabelBearingHistoryRejectedBeforeTransport(){MlInferenceClient client=new MlInferenceClient(mapper,"http://127.0.0.1:1",100);Map<String,Object> future=frame();future.put("clockSec",20d);assertThrows(InferenceException.class,()->client.infer(frame(),List.of(future),"xgb-v1",GRAPH));Map<String,Object> label=frame();label.put("labels",Map.of("remainingArrivalSec",30d));assertThrows(InferenceException.class,()->client.infer(label,List.of(),"xgb-v1",GRAPH));Map<String,Object> schedule=frame();schedule.put("exogenousSchedule",List.of());assertThrows(InferenceException.class,()->client.infer(schedule,List.of(),"xgb-v1",GRAPH));}
    @Test void typedHttpRoundTripPreservesInput()throws Exception{
        HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);server.createContext("/predict",exchange->{byte[] data=mapper.writeValueAsBytes(response());exchange.sendResponseHeaders(200,data.length);exchange.getResponseBody().write(data);exchange.close();});server.start();
        try{Map<String,Object> source=frame();String before=mapper.writeValueAsString(source);Response result=new MlInferenceClient(mapper,"http://127.0.0.1:"+server.getAddress().getPort(),1000).infer(source,List.of(),"xgb-v1",GRAPH);assertEquals(30,result.predictions().getFirst().remainingArrivalSec());assertEquals(before,mapper.writeValueAsString(source));}finally{server.stop(0);}
    }
    @Test void unavailableServiceAndUnsupportedModelDoNotBecomePredictions(){MlInferenceClient client=new MlInferenceClient(mapper,"http://127.0.0.1:1",100);assertThrows(InferenceException.class,()->client.infer(frame(),List.of(),"xgb-v1",GRAPH));assertThrows(InferenceException.class,()->client.infer(frame(),List.of(),"untrained-model",GRAPH));assertEquals(false,client.status().get("available"));}
    @Test void deadlineBoundsAreEnforced()throws Exception{
        HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);var worker=Executors.newSingleThreadExecutor();server.setExecutor(worker);server.createContext("/predict",exchange->{try{Thread.sleep(300);exchange.sendResponseHeaders(503,-1);}catch(Exception ignored){}finally{exchange.close();}});server.start();
        try{assertThrows(InferenceException.class,()->new MlInferenceClient(mapper,"http://127.0.0.1:"+server.getAddress().getPort(),50).infer(frame(),List.of(),"xgb-v1",GRAPH));}finally{server.stop(0);worker.shutdownNow();}
    }
}
