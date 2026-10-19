package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import static io.cascadeshield.sim.Models.*;

@Service
public class SimulationService {
    private final SimulationRepository repository;private final ObjectMapper mapper;
    private final RoadGraph graph;private SimulationEngine engine;private final Object roads;private final AiFallbackPipeline ai;
    private final TransactionTemplate transactions;
    private int schedulerTicks=0;private String persistenceError=null;
    public SimulationService(SimulationRepository repository,ObjectMapper mapper,PlatformTransactionManager transactionManager,
        @Value("${simulator.graph-path}")String graphPath,@Value("${simulator.geojson-path}")String geojsonPath) throws Exception {
        this.repository=repository;this.mapper=mapper;this.transactions=new TransactionTemplate(transactionManager);
        Path path=Path.of(graphPath);graph=RoadGraph.load(path,mapper);
        String digest=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
        repository.initializeNetwork(graph,digest);roads=mapper.readValue(Path.of(geojsonPath).toFile(),Object.class);
        engine=new SimulationEngine(graph,mapper);ai=new AiFallbackPipeline(graph,mapper);repository.loadState().ifPresent(engine::restore);checkpoint();
    }
    public synchronized Map<String,Object> network(){List<Double> box=graph.network.bbox();return Map.of("networkId",graph.network.networkId(),"name",graph.network.name(),"bbox",box,"center",List.of((box.get(1)+box.get(3))/2,(box.get(0)+box.get(2))/2),"metadata",graph.network.metadata());}
    public Object roads(){return roads;}
    public synchronized State state(){return engine.snapshot();}
    public synchronized Map<String,Object> health(){boolean db=repository.healthy();return Map.of("status",db&&persistenceError==null?"UP":"DEGRADED","database",db,"networkId",graph.network.networkId(),"roadNodes",graph.network.nodes().size(),"directedEdges",graph.network.edges().size(),"operationsProvenance","SIMULATED","riskSource","RULE_BASED","apiVersion",AiModels.API_VERSION,"persistenceError",persistenceError==null?"":persistenceError);}
    private void writable(){if(persistenceError!=null)throw new ApiException(503,"Backend paused after persistence failure: "+persistenceError);}
    private void checkpoint(){repository.checkpoint(engine.raw(),engine.drainEvents());}
    @Scheduled(fixedDelay=100)
    public synchronized void tick() {
        if(!"RUNNING".equals(engine.raw().status)||persistenceError!=null)return;
        try{engine.schedulerTick();if(++schedulerTicks%10==0||!"RUNNING".equals(engine.raw().status))checkpoint();}
        catch(RuntimeException error){engine.raw().status="PAUSED";persistenceError=error.getMessage();}
    }
    public synchronized Route preview(RouteRequest request){return engine.preview(request);}
    public synchronized State add(TruckSpec request){writable();engine.addTruck(request);checkpoint();return engine.snapshot();}
    public synchronized State update(String id,TruckSpec request){writable();engine.updateTruck(id,request);checkpoint();return engine.snapshot();}
    public synchronized State delete(String id){writable();engine.deleteTruck(id);checkpoint();return engine.snapshot();}
    public synchronized State control(ControlRequest request){writable();engine.control(request);checkpoint();return engine.snapshot();}
    public synchronized State incident(IncidentRequest request){writable();engine.addIncident(request);checkpoint();return engine.snapshot();}
    public synchronized State resolve(String id){writable();engine.removeIncident(id);checkpoint();return engine.snapshot();}
    public synchronized State decision(DecisionRequest request){writable();engine.decide(request);checkpoint();return engine.snapshot();}
    public synchronized State resource(String kind,Map<String,Object> request,boolean create,String id){writable();if(id!=null&&!id.equals(request.get("id")))throw ApiException.invalid("Resource ID cannot change while editing");engine.resource(kind,request,create);checkpoint();return engine.snapshot();}
    public synchronized State removeResource(String kind,String id){writable();engine.removeResource(kind,id);checkpoint();return engine.snapshot();}
    public synchronized State assign(OpsModels.AssignmentSpec request){writable();engine.assign(request);checkpoint();return engine.snapshot();}
    public synchronized State unassign(String truckId){writable();engine.unassign(truckId);checkpoint();return engine.snapshot();}
    public synchronized State availability(String id,OpsModels.AvailabilityRequest request){writable();if(request.available()==null)throw ApiException.invalid("Driver availability must be explicitly true or false");engine.availability(id,request.available());checkpoint();return engine.snapshot();}
    public synchronized AiModels.PredictionBatch predict(){return ai.predict(engine.snapshot());}
    public synchronized AiModels.CandidateBatch candidates(String truckId){return ai.candidates(engine.snapshot(),truckId);}
    public synchronized AiModels.Evaluation evaluate(AiModels.CandidateAction candidate){return ai.evaluate(engine.snapshot(),candidate);}
    public synchronized AiModels.ValidationResult validate(AiModels.CandidateAction candidate){return ai.validate(engine.snapshot(),candidate);}
    public synchronized AiModels.RecommendationResult recommend(String truckId){return ai.recommend(engine.snapshot(),truckId);}
    public synchronized AiModels.Explanation explain(AiModels.CandidateAction candidate){return ai.explain(ai.evaluate(engine.snapshot(),candidate));}
    public synchronized GraphSnapshotExporter.GraphSnapshot snapshot(){return ai.snapshot(engine.snapshot());}
    public synchronized Map<String,Object> persistSnapshot(){writable();return repository.saveSnapshot(snapshot());}
    public synchronized Object inspectIncident(String id){State s=engine.snapshot();Incident incident=s.incidents.stream().filter(i->i.id.equals(id)).findFirst().orElseThrow(()->new ApiException(404,"Incident not found"));return Map.of("incident",incident,"directTruckIds",s.trucks.stream().filter(t->t.affectedIncidentIds.contains(id)).map(t->t.id).toList(),"affectedResources",s.operations.cascade.nodeRisks().stream().filter(r->r.causeIds().contains(id)||r.causeIds().contains("INCIDENT:"+id)).toList(),"provenance","SIMULATED");}
    public synchronized Object affected(String incidentId){State s=engine.snapshot();if(incidentId!=null&&s.incidents.stream().noneMatch(i->i.id.equals(incidentId)))throw new ApiException(404,"Incident not found");Set<String> above=new HashSet<>(s.operations.cascade.affectedNodeIds());var risks=s.operations.cascade.nodeRisks().stream().filter(r->above.contains(r.nodeId())&&(incidentId==null||r.causeIds().contains("INCIDENT:"+incidentId))).toList();Set<String> ids=new HashSet<>(risks.stream().map(OpsModels.NodeRisk::nodeId).toList());return Map.of("schemaVersion",AiModels.API_VERSION,"clockSec",s.clockSec,"nodes",s.operations.graph.nodes().stream().filter(n->ids.contains(n.id())).toList(),"risks",risks,"edges",s.operations.graph.edges().stream().filter(e->ids.contains(e.source())&&ids.contains(e.target())).toList(),"provenance","SIMULATED_PREDICTION");}
    public synchronized List<Map<String,Object>> approvals(){return repository.approvals(engine.raw().runId);}
    public synchronized OperatorApprovalGuard.Approval requestApproval(AiModels.CandidateAction candidate){writable();State state=engine.snapshot();OperatorApprovalGuard.stable(state);AiModels.Evaluation evaluation=ai.evaluate(state,candidate);if(!evaluation.validation().valid())throw ApiException.conflict("Candidate failed backend constraints");return repository.requestApproval(state,candidate,evaluation);}
    public synchronized OperatorApprovalGuard.Approval approve(UUID id,OperatorApprovalGuard.OperatorRequest request){writable();State state=engine.snapshot();OperatorApprovalGuard.Approval approval=repository.approval(id);OperatorApprovalGuard.current(approval,state,ai.fingerprint(state));return repository.approve(id,OperatorApprovalGuard.operator(request));}
    public synchronized State execute(UUID id){
        writable();State before=engine.snapshot();OperatorApprovalGuard.Approval approval=repository.approval(id);
        OperatorApprovalGuard.executable(approval,before,ai.fingerprint(before));
        if(!ai.validate(before,approval.candidate()).valid())throw ApiException.conflict("Backend constraints changed before execution");
        SimulationEngine prepared=new SimulationEngine(graph,mapper);prepared.restore(before);
        prepared.decide(new DecisionRequest(approval.candidate().truckId(),approval.candidate().action(),approval.candidate().recommendationId()));
        List<Event> events=new ArrayList<>(engine.pendingEvents());events.addAll(prepared.pendingEvents());
        transactions.executeWithoutResult(transaction->{repository.executed(id);repository.checkpoint(prepared.raw(),events);});
        // Publish only after the transaction template has successfully committed.
        prepared.drainEvents();engine=prepared;return engine.snapshot();
    }
    @Transactional
    public synchronized Map<String,Object> saveScenario(ScenarioRequest request){writable();if(engine.raw().trucks.isEmpty())throw ApiException.invalid("Create trucks before saving a scenario");String name=request.name()==null?"Chennai scenario":request.name().strip();if(name.isEmpty()||name.length()>100)throw ApiException.invalid("Scenario name must contain 1-100 characters");engine.raw().scenarioName=name;Map<String,Object> saved=repository.saveScenario(name,engine.raw().networkId,engine.scenarioConfiguration());engine.raw().scenarioId=UUID.fromString((String)saved.get("id"));checkpoint();return saved;}
    public List<Map<String,Object>> scenarios(){return repository.scenarios();}
    public Map<String,Object> scenario(UUID id){return repository.scenario(id);}
    @SuppressWarnings("unchecked")
    public synchronized State replay(UUID id){writable();Map<String,Object> scenario=repository.scenario(id);engine.replay((String)scenario.get("name"),(Map<String,Object>)scenario.get("configuration"));engine.raw().scenarioId=id;checkpoint();return engine.snapshot();}
    @PreDestroy
    public synchronized void shutdown(){if(persistenceError==null)checkpoint();}
}
