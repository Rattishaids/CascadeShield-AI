package io.cascadeshield.sim;

import java.util.List;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.AiModels.*;
import static io.cascadeshield.sim.OpsModels.*;

/** Boundaries for future external inference; implementations cannot execute operator actions. */
public final class AiArchitecture {
    private AiArchitecture() {}
    public interface PredictionProvider { PredictionBatch predict(State state); }
    public interface GraphRiskProvider { CascadeView graphRisk(State state); }
    public interface CandidateActionGenerator { CandidateBatch candidates(State state,String truckId); }
    public interface CounterfactualEvaluator { Evaluation evaluate(State state,CandidateAction action); }
    public interface ConstraintValidator { ValidationResult validate(State state,CandidateAction action); }
    public interface ActionOptimizer { CandidateAction optimize(List<Evaluation> evaluations,double clockSec); }
    public interface DecisionExplainer { Explanation explain(Evaluation evaluation); }
}
