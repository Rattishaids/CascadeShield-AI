package io.cascadeshield.sim;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OperatorApprovalGuard.*;

class OperatorApprovalGuardTest {
    private Approval approval(State state,String status,String fingerprint){return new Approval(UUID.randomUUID(),state.runId,state.clockSec,status,fingerprint,null,null,"local-operator","now",null,null,"SIMULATED_OPERATOR_WORKFLOW");}
    @Test void runningAndReplayedStatesCannotRequestApproval(){State state=new State();state.status="RUNNING";assertThrows(ApiException.class,()->stable(state));state.status="PAUSED";state.replaying=true;assertThrows(ApiException.class,()->stable(state));}
    @Test void clockResourceOrRunChangesInvalidateFrozenProposal(){State state=new State();Approval a=approval(state,"APPROVED","state-1");assertDoesNotThrow(()->current(a,state,"state-1"));assertThrows(ApiException.class,()->current(a,state,"changed-state"));state.runId=UUID.randomUUID();assertThrows(ApiException.class,()->current(a,state,"state-1"));}
    @Test void unapprovedOrAlreadyConsumedActionsCannotExecute(){State state=new State();assertThrows(ApiException.class,()->executable(approval(state,"REQUESTED","f"),state,"f"));assertThrows(ApiException.class,()->executable(approval(state,"EXECUTED","f"),state,"f"));}
    @Test void operatorIdentityMustBeExplicitAndBounded(){assertThrows(ApiException.class,()->operator(null));assertThrows(ApiException.class,()->operator(new OperatorRequest(" ")));assertThrows(ApiException.class,()->operator(new OperatorRequest("a".repeat(101))));assertEquals("human",operator(new OperatorRequest(" human ")));}
}
