package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.AiModels.*;

/** Ranks existing operator candidates on copies. It cannot approve, execute or persist an action. */
public final class MlOperatorAdvisor {
    public record Offer(CandidateAction candidate, ValidationResult validation, double score,
                        MlModels.Response prediction) {}
    public record Advice(String schemaVersion, UUID runId, String requestedModelId, String source, String stateFingerprint,
                         double clockSec, List<Offer> alternatives, CandidateAction selected,
                         boolean fallbackUsed, List<String> warnings, double latencyMs, boolean stateMutated) {}
    private final RoadGraph roads;
    private final ObjectMapper mapper;
    private final AiFallbackPipeline baseline;
    private final MlFeatureExtractor extractor;
    private final CounterfactualExperimentEngine copies;
    private final MlPolicyRunner.Predictor predictor;
    private final String graphSha;

    public MlOperatorAdvisor(RoadGraph roads,ObjectMapper mapper,MlPolicyRunner.Predictor predictor,String graphSha) {
        this.roads=roads;this.mapper=mapper;this.predictor=predictor;this.graphSha=graphSha;
        baseline=new AiFallbackPipeline(roads,mapper);extractor=new MlFeatureExtractor(roads,mapper);copies=new CounterfactualExperimentEngine(roads,mapper);
    }

    public Advice recommend(State input,String truckId,String modelId) {
        long started=System.nanoTime();
        if(!MlModels.MODEL_IDS.contains(modelId)&&!"rule-v1".equals(modelId))throw ApiException.invalid("Unsupported ML model ID");
        if(input.incidents.stream().anyMatch(i->i.startSec>input.clockSec+1e-8))throw ApiException.invalid("ML operator comparison supports current incidents only; future-scheduled road incidents require a separate reviewed planning configuration.");
        CandidateBatch batch=baseline.candidates(input,truckId);
        List<CandidateAction> candidates=batch.candidates();
        List<Map<String,Object>> frames=new ArrayList<>();
        List<ValidationResult> validations=new ArrayList<>();
        List<MlModels.Response> predictions=new ArrayList<>();
        List<String> warnings=new ArrayList<>();
        warnings.add("Operator advice ranks the existing CONTINUE/WAIT/REROUTE candidates; the isolated research B5 benchmark has a separate five-action repertoire. No policy equivalence is claimed.");
        warnings.add("Prediction-time scoring is not an observed action-effect or field-effectiveness estimate. Pause and review before requesting explicit approval.");
        if(input.operations.deliveries.stream().noneMatch(d->d.deliveredAtSec<0))warnings.add("No unfinished assigned deliveries are available for the delivery-risk score; this is not a validated operational recommendation.");
        boolean fallback="rule-v1".equals(modelId);
        for(CandidateAction candidate:candidates) {
            ValidationResult validation=baseline.validate(input,candidate);validations.add(validation);
            SimulationEngine copy=new SimulationEngine(roads,mapper);
            State state=copies.observedClone(input);
            // Only the local copy is changed. Replay and future schedules never enter model features.
            state.replaying=false;copy.restore(state);
            copy.decide(new DecisionRequest(candidate.truckId(),candidate.action(),candidate.recommendationId()));
            Map<String,Object> frame=extractor.frame(copy.raw());frames.add(frame);
            MlModels.Response response=null;
            if(!fallback) {
                try {response=predictor.infer(frame,List.of(),modelId,graphSha);warnings.addAll(response.warnings());}
                catch(MlModels.InferenceException error) {fallback=true;warnings.add("All alternatives use the deterministic score after inference failed: "+error.getMessage());}
            }
            predictions.add(response);
        }
        if("gnn-temporal-v1".equals(modelId))warnings.add("Operator candidate ranking uses the current graph without recurrent history; temporal policy experiments separately maintain causal past frames.");
        double distance=input.trucks.stream().mapToDouble(t->t.remainingDistanceM).sum();
        List<Offer> alternatives=new ArrayList<>();
        for(int i=0;i<candidates.size();i++) {
            Map<String,MlModels.Prediction> byTruck=new HashMap<>();
            MlModels.Response response=fallback?null:predictions.get(i);
            if(response!=null)for(MlModels.Prediction value:response.predictions())byTruck.put(value.truckId(),value);
            alternatives.add(new Offer(candidates.get(i),validations.get(i),
                MlPolicyRunner.predictionScore(input,frames.get(i),byTruck,distance),response));
        }
        CandidateAction selected=alternatives.stream().filter(o->o.validation().valid())
            .min(Comparator.comparingDouble(Offer::score).thenComparing(o->o.candidate().action()))
            .map(Offer::candidate).orElse(null);
        return new Advice("cascadeshield.ml-operator-advice/1.0",input.runId,modelId,fallback?"DETERMINISTIC_RULE_SCORE":"TRAINED_SIMULATION_MODEL",
            batch.context().stateFingerprint(),input.clockSec,List.copyOf(alternatives),selected,
            fallback&&!"rule-v1".equals(modelId),List.copyOf(new LinkedHashSet<>(warnings)),(System.nanoTime()-started)/1e6,false);
    }
}
