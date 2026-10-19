package io.cascadeshield.sim;

import java.util.*;
import static io.cascadeshield.sim.OpsModels.*;

/** Versioned inference contracts. Predictions are never represented as observed labels. */
public final class AiModels {
    private AiModels() {}
    public static final String API_VERSION="cascadeshield.ai/1.0";
    public record Source(String provider,String version,String provenance,boolean calibrated,String limitation) {}
    public record Context(String schemaVersion,String networkId,UUID runId,UUID scenarioId,long randomSeed,
                          double clockSec,String stateFingerprint) {}
    public record TruckPrediction(String truckId,Double estimatedArrivalSec,double conditionalRoadArrivalSec,double remainingDistanceM,
                                  double riskScore,List<String> incidentIds,Source source) {}
    public record PredictionBatch(Context context,List<TruckPrediction> trucks,CascadeView graphRisk,
                                  List<Impact> predictedImpacts,Source source) {}
    public record CandidateAction(String id,String truckId,String action,String recommendationId,
                                  String stateFingerprint,Source source) {}
    public record CandidateBatch(Context context,String truckId,List<CandidateAction> candidates,Source source) {}
    public record ConstraintViolation(String code,List<String> resourceIds,String message,boolean blocking) {}
    public record ValidationResult(boolean valid,String stateFingerprint,List<ConstraintViolation> violations,Source source) {}
    public record Evaluation(CandidateAction candidate,String stateFingerprint,double beforeArrivalSec,
                             double afterArrivalSec,double remainingDistanceM,double travelDeltaSec,
                             double beforeRisk,double afterRisk,boolean beforeEtaKnown,boolean afterEtaKnown,
                             CascadeView beforeGraphRisk,CascadeView afterGraphRisk,List<Impact> beforeImpacts,List<Impact> afterImpacts,
                             ValidationResult validation,Source source) {}
    public record Explanation(String schemaVersion,String summary,Map<String,Object> facts,Source source) {}
    public record RecommendationResult(Context context,String truckId,List<Evaluation> evaluations,
                                       CandidateAction selected,Explanation explanation,Source source) {}
}
