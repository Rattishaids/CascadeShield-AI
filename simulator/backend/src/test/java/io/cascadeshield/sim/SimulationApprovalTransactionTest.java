package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.*;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.AiModels.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Test-only graph and staged transaction doubles; never a research dataset or field result. */
class SimulationApprovalTransactionTest {
    @TempDir Path directory;
    private final ObjectMapper mapper=new ObjectMapper().findAndRegisterModules();

    private RoadGraph graph(){
        List<Node> nodes=List.of(new Node(1,80.25,13.05),new Node(2,80.251,13.05),
            new Node(3,80.252,13.05),new Node(4,80.251,13.052));
        List<Edge> edges=new ArrayList<>();
        for(Object[] item:List.of(new Object[]{"AB",1L,2L,100d},new Object[]{"BC",2L,3L,100d},
                new Object[]{"BD",2L,4L,150d},new Object[]{"DC",4L,3L,250d})){
            long from=(long)item[1],to=(long)item[2];
            edges.add(new Edge((String)item[0],(String)item[0],from,to,from*10+to,(double)item[3],
                36,"TEST_FIXTURE_ONLY","residential",(String)item[0],
                List.of(nodes.get((int)from-1).point().coordinates(),nodes.get((int)to-1).point().coordinates()),Map.of()));
        }
        return new RoadGraph(new NetworkFile("TEST_FIXTURE_ONLY","TEST_FIXTURE_ONLY",
            List.of(13d,80d,14d,81d),nodes,edges,List.of(),Map.of("provenance","TEST_FIXTURE_ONLY")));
    }
    private String json(State state)throws Exception{return mapper.writeValueAsString(state);}

    private final class Harness {
        final SimulationRepository repository=mock(SimulationRepository.class);
        final PlatformTransactionManager transactions=mock(PlatformTransactionManager.class);
        final TransactionStatus status=mock(TransactionStatus.class);
        final AtomicReference<OperatorApprovalGuard.Approval> approval=new AtomicReference<>();
        final UUID id=UUID.randomUUID();
        final SimulationService service;
        final SimulationEngine originalEngine;
        final String originalJson;
        final List<Event> originalPending;
        boolean failCheckpoint=false,failCommit=false,stagedExecution=false;
        int successfulCommits=0;
        List<Event> checkpointEvents=List.of();

        Harness()throws Exception {
            RoadGraph roads=graph();SimulationEngine fixture=new SimulationEngine(roads,mapper);
            fixture.addTruck(new TruckSpec("T1","Explicit unit fixture",roads.node(1).point(),
                roads.node(3).point(),List.of(),36,1000,500,"Simulated fixture driver","NORMAL",0,100));
            fixture.control(new ControlRequest("STEP",null,5d));
            when(repository.loadState()).thenReturn(Optional.of(fixture.snapshot()));
            Path graphPath=directory.resolve("graph.json"),geojsonPath=directory.resolve("roads.geojson");
            mapper.writeValue(graphPath.toFile(),roads.network);
            mapper.writeValue(geojsonPath.toFile(),Map.of("type","FeatureCollection","features",List.of()));
            when(transactions.getTransaction(any(TransactionDefinition.class))).thenReturn(status);
            service=new SimulationService(repository,mapper,transactions,graphPath.toString(),geojsonPath.toString());
            originalEngine=(SimulationEngine)Objects.requireNonNull(ReflectionTestUtils.getField(service,"engine"));
            // A pending real engine event exercises buffering across a failed checkpoint.
            originalEngine.addIncident(new IncidentRequest("CLOSURE","BC",1,900,5d));
            State initial=service.state();CandidateAction candidate=service.candidates("T1").candidates().stream()
                .filter(action->action.action().equals("REROUTE")).findFirst().orElseThrow();
            Evaluation evaluation=service.evaluate(candidate);
            approval.set(new OperatorApprovalGuard.Approval(id,initial.runId,initial.clockSec,"APPROVED",
                candidate.stateFingerprint(),candidate,evaluation,"fixture-operator",null,null,null,"SIMULATED_OPERATOR_WORKFLOW"));
            originalJson=json(initial);originalPending=originalEngine.pendingEvents();assertFalse(originalPending.isEmpty());
            when(repository.approval(id)).thenAnswer(invocation->approval.get());
            doAnswer(invocation->{
                if(!"APPROVED".equals(approval.get().status()))throw ApiException.conflict("Already consumed");
                stagedExecution=true;return null;
            }).when(repository).executed(id);
            doAnswer(invocation->{
                assertEquals(originalJson,json(service.state()),"Authoritative state must stay unchanged during SQL checkpoint");
                checkpointEvents=List.copyOf(invocation.<List<Event>>getArgument(1));
                if(failCheckpoint)throw new DataAccessResourceFailureException("Explicit test checkpoint failure");
                return null;
            }).when(repository).checkpoint(any(State.class),anyList());
            doAnswer(invocation->{
                assertEquals(originalJson,json(service.state()),"Authoritative state must stay unchanged before transaction commit");
                if(failCommit){stagedExecution=false;throw new TransactionSystemException("Explicit test commit failure");}
                assertTrue(stagedExecution);stagedExecution=false;successfulCommits++;
                OperatorApprovalGuard.Approval old=approval.get();
                approval.set(new OperatorApprovalGuard.Approval(old.id(),old.runId(),old.clockSec(),"EXECUTED",
                    old.stateFingerprint(),old.candidate(),old.evaluation(),old.approvedBy(),old.requestedAt(),
                    old.approvedAt(),"test-commit",old.provenance()));
                return null;
            }).when(transactions).commit(status);
            doAnswer(invocation->{stagedExecution=false;return null;}).when(transactions).rollback(status);
            clearInvocations(repository,transactions);
        }
        void assertUnchanged()throws Exception {
            assertEquals(originalJson,json(service.state()),"Clock, position, route, commands and events must all survive failure");
            assertSame(originalEngine,ReflectionTestUtils.getField(service,"engine"));
            assertEquals(originalPending,originalEngine.pendingEvents(),"Failure must not drain original pending events");
            assertEquals("APPROVED",approval.get().status());assertEquals(0,successfulCommits);
        }
        State executeAndAssertCommitted()throws Exception {
            State before=service.state(),after=service.execute(id);Truck t=after.trucks.getFirst();
            assertEquals(before.clockSec,after.clockSec);assertEquals(before.trucks.getFirst().position,t.position);
            assertEquals(before.trucks.getFirst().offsetM,t.offsetM);assertEquals(List.of("AB","BD","DC"),t.route.edgeIds());
            assertEquals(before.trucks.getFirst().reroutes+1,t.reroutes);
            assertEquals(before.commandHistory.size()+1,after.commandHistory.size());
            assertEquals("EXECUTED",approval.get().status());assertEquals(1,successfulCommits);
            assertNotSame(originalEngine,ReflectionTestUtils.getField(service,"engine"));
            for(Event event:originalPending)assertEquals(1,checkpointEvents.stream().filter(e->e.id()==event.id()).count(),
                "Previously pending event must be checkpointed once after successful retry");
            assertTrue(((SimulationEngine)ReflectionTestUtils.getField(service,"engine")).pendingEvents().isEmpty());
            return after;
        }
    }

    @Test void checkpointFailurePreservesAuthoritativeStateAndApprovedProposalCanRetry()throws Exception {
        Harness h=new Harness();h.failCheckpoint=true;
        assertThrows(DataAccessResourceFailureException.class,()->h.service.execute(h.id));
        h.assertUnchanged();verify(h.transactions).rollback(h.status);
        h.failCheckpoint=false;h.executeAndAssertCommitted();
    }
    @Test void commitFailurePreservesAuthoritativeStateAndApprovedProposalCanRetry()throws Exception {
        Harness h=new Harness();h.failCommit=true;
        assertThrows(TransactionSystemException.class,()->h.service.execute(h.id));h.assertUnchanged();
        h.failCommit=false;h.executeAndAssertCommitted();
    }
    @Test void successPublishesOnlyAfterCommitAndConsumedProposalCannotExecuteTwice()throws Exception {
        Harness h=new Harness();State committed=h.executeAndAssertCommitted();
        ApiException error=assertThrows(ApiException.class,()->h.service.execute(h.id));assertEquals(409,error.status);
        assertEquals(json(committed),json(h.service.state()));assertEquals(1,h.successfulCommits);
        verify(h.repository,times(1)).executed(h.id);verify(h.transactions,times(1)).commit(h.status);
    }
}
