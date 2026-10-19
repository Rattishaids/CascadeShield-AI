package io.cascadeshield.sim;

import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.AiModels.*;

/** Approval is tied to the exact paused backend state and consumed once. */
public final class OperatorApprovalGuard {
    public record Approval(UUID id,UUID runId,double clockSec,String status,String stateFingerprint,
                           CandidateAction candidate,Evaluation evaluation,String approvedBy,
                           String requestedAt,String approvedAt,String executedAt,String provenance) {}
    public record OperatorRequest(String approvedBy) {}
    public static void stable(State state){if(!List.of("DRAFT","PAUSED").contains(state.status))throw ApiException.conflict("Pause the simulation before requesting or executing an operator-reviewed action");if(state.replaying)throw ApiException.conflict("Reset the recorded replay before requesting operator actions");}
    public static void current(Approval approval,State state,String fingerprint){stable(state);if(!approval.runId().equals(state.runId)||!approval.stateFingerprint().equals(fingerprint))throw ApiException.conflict("Approval references a stale simulation state; generate and review a new candidate");}
    public static void executable(Approval approval,State state,String fingerprint){if(!"APPROVED".equals(approval.status()))throw ApiException.conflict("Action requires an unconsumed explicit operator approval");current(approval,state,fingerprint);if(!approval.evaluation().validation().valid())throw ApiException.conflict("Approved candidate failed backend constraints");}
    public static String operator(OperatorRequest request){if(request==null||request.approvedBy()==null||request.approvedBy().isBlank()||request.approvedBy().length()>100)throw ApiException.invalid("An explicit local operator identifier is required");return request.approvedBy().strip();}
}
