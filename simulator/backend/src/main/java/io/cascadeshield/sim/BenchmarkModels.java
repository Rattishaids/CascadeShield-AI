package io.cascadeshield.sim;

import java.util.*;
import static io.cascadeshield.sim.Models.*;

/** Versioned, explicitly simulated experiment contracts; not observed freight records. */
public final class BenchmarkModels {
    private BenchmarkModels() {}
    public static final String PROVENANCE="SIMULATED_RESEARCH_EXPERIMENT";
    public enum ActionType { NONE, CONTINUE, WAIT, LOCAL_REROUTE, GLOBAL_REROUTE, ADJUST_DOCK_RESERVATION }
    public record ScenarioSpec(String id,String name,long seed,String profile,
        Map<String,Object> configuration,List<ScheduledCommand> exogenousSchedule,double horizonSec,
        String inputFingerprint,Map<String,Object> parameters,String provenance) {}
    public record Action(String id,ActionType type,String truckId,double waitSec,String dockId,
        double reservationStartSec,double reservationEndSec,List<String> routeEdgeIds,String description) {}
    public record Violation(String code,String message,List<String> resourceIds,boolean hard) {}
    public record Metrics(int deliveryCount,int completedDeliveries,int unfinishedDeliveries,
        int slaViolations,double slaViolationRate,double totalDeliveryLatenessSec,
        int downstreamAffectedResources,int totalReroutes,double travelDistanceM,
        double signedAdditionalDistanceM,double positiveAdditionalDistanceM,
        double modeledOperationalCost,double recoveryTimeSec,boolean recoveryCensored,
        double finalClockSec,int constraintViolations,double decisionComputationMs,
        String provenance) {}
    public record Rollout(Action action,boolean valid,List<Violation> violations,
        Metrics metrics,State finalState,long computationNanos,String knowledgeFingerprint) {}
    public record ScoredAlternative(Action action,boolean feasible,double score,Metrics metrics,
        List<Violation> violations) {}
    public record DecisionTrace(double clockSec,String truckId,String trigger,List<String> observedIncidentIds,
        List<ScoredAlternative> alternatives,String selectedActionId,String explanation,
        double computationMs,String knowledgeFingerprint) {}
    public record PolicySpec(String id,String name,List<ActionType> allowedActions,
        boolean temporalDependencies,boolean adaptiveThreshold,boolean counterfactualEvaluation) {}
    public record PolicyRun(String scenarioId,long seed,String policyId,String inputFingerprint,
        Metrics metrics,List<DecisionTrace> decisions,Map<String,Object> finalSummary,String provenance) {}
    public record ComparisonRequest(List<String> scenarioIds,List<String> policyIds,boolean equalActionSet) {}
    public record ComparisonResult(String schemaVersion,List<ScenarioSpec> scenarios,List<PolicyRun> runs,
        Map<String,Object> summary,String provenance) {}
}
