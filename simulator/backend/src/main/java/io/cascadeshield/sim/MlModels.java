package io.cascadeshield.sim;

import java.util.*;

/** Read-only inference DTOs; probabilities describe simulated outcomes, never field truth. */
public final class MlModels {
    private MlModels() {}
    public static final String REQUEST_VERSION="cascadeshield.ml-request/1.0";
    public static final String RESPONSE_VERSION="cascadeshield.ml-response/1.0";
    public static final String MODEL_VERSION="milestone4-v1";
    public static final Set<String> MODEL_IDS=Set.of("xgb-v1","xgb-no-graph-v1","gnn-static-v1","gnn-temporal-v1");
    public record Request(String schemaVersion,String featureSchemaVersion,String featureSchemaHash,String networkId,
        String graphSha256,String modelId,String stateFingerprint,Map<String,Object> frame,List<Map<String,Object>> history) {}
    public record Prediction(String truckId,Double remainingArrivalSec,Double etaLowerSec,Double etaUpperSec,
        Double slaProbability,Double futureImpactProbability) {}
    public record Response(String schemaVersion,String featureSchemaVersion,String featureSchemaHash,String networkId,
        String graphSha256,String modelId,String modelVersion,String source,String stateFingerprint,Double clockSec,
        List<Prediction> predictions,Map<String,Object> calibration,Double latencyMs,List<String> warnings,String provenance) {}
    public static final class InferenceException extends RuntimeException {
        public InferenceException(String message){super(message);}
        public InferenceException(String message,Throwable cause){super(message,cause);}
    }
}
