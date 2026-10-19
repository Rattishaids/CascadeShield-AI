package io.cascadeshield.sim;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;
import java.time.OffsetDateTime;
import java.util.*;
import static io.cascadeshield.sim.Models.*;

@Repository
public class SimulationRepository {
    private final JdbcTemplate jdbc;private final ObjectMapper mapper;
    public SimulationRepository(JdbcTemplate jdbc,ObjectMapper mapper){this.jdbc=jdbc;this.mapper=mapper;}
    public String json(Object value){try{return mapper.writeValueAsString(value);}catch(JsonProcessingException e){throw new IllegalStateException(e);}}
    @Transactional
    public void initializeNetwork(RoadGraph graph,String digest) {
        List<String> prior=jdbc.query("SELECT graph_sha256 FROM cascadeshield_sim.network_versions WHERE id=?",(r,n)->r.getString(1),graph.network.networkId());
        if(!prior.isEmpty()) {
            if(!prior.getFirst().equals(digest))throw new IllegalStateException("Network identity was reused with changed geographic bytes; version the network.");
            return;
        }
        jdbc.update("INSERT INTO cascadeshield_sim.network_versions(id,graph_sha256,metadata) VALUES(?,?,?::jsonb)",graph.network.networkId(),digest,json(graph.network.metadata()));
        jdbc.batchUpdate("INSERT INTO cascadeshield_sim.road_nodes(network_id,osm_node_id,geom) VALUES(?,?,ST_SetSRID(ST_MakePoint(?,?),4326))",graph.network.nodes(),500,(s,n)->{
            s.setString(1,graph.network.networkId());s.setLong(2,n.id());s.setDouble(3,n.longitude());s.setDouble(4,n.latitude());});
        jdbc.batchUpdate("INSERT INTO cascadeshield_sim.road_edges(network_id,id,physical_id,from_node,to_node,osm_way_id,length_m,speed_kph,speed_source,tags,geom) VALUES(?,?,?,?,?,?,?,?,?,?::jsonb,ST_SetSRID(ST_GeomFromGeoJSON(?),4326))",graph.network.edges(),500,(s,e)->{
            s.setString(1,graph.network.networkId());s.setString(2,e.id());s.setString(3,e.physicalId());s.setLong(4,e.from());s.setLong(5,e.to());s.setLong(6,e.wayId());s.setDouble(7,e.lengthM());s.setDouble(8,e.speedKph());s.setString(9,e.speedSource());s.setString(10,json(e.tags()));s.setString(11,json(Map.of("type","LineString","coordinates",e.geometry())));});
    }
    public Optional<State> loadState(){return jdbc.query("SELECT state::text FROM cascadeshield_sim.current_state WHERE id=1",(r,n)->{
        try{return mapper.readValue(r.getString(1),State.class);}catch(Exception e){throw new IllegalStateException("Persisted simulator state is unreadable",e);}}).stream().findFirst();}
    public void saveState(State state){jdbc.update("INSERT INTO cascadeshield_sim.current_state(id,network_id,state) VALUES(1,?,?::jsonb) ON CONFLICT(id) DO UPDATE SET network_id=excluded.network_id,state=excluded.state,checkpoint_at=now()",state.networkId,json(state));}
    public void saveEvent(UUID run,Event event){jdbc.update("INSERT INTO cascadeshield_sim.simulation_events(run_id,sequence,clock_sec,event_type,truck_id,event) VALUES(?,?,?,?,?,?::jsonb) ON CONFLICT DO NOTHING",run,event.id(),event.clockSec(),event.type(),event.truckId(),json(event));}
    @Transactional
    public void checkpoint(State state,List<Event> events){saveState(state);for(Event event:events)saveEvent(state.runId,event);saveOperations(state);}
    private void saveOperations(State state){
        jdbc.update("DELETE FROM cascadeshield_sim.operational_resources WHERE run_id=?",state.runId);
        Map<String,List<?>> types=new LinkedHashMap<>();types.put("WAREHOUSE",state.operations.warehouses);types.put("DOCK",state.operations.docks);types.put("DRIVER",state.operations.drivers);types.put("DELIVERY",state.operations.deliveries);
        for(var entry:types.entrySet())for(Object resource:entry.getValue()){String id=mapper.valueToTree(resource).get("id").asText();jdbc.update("INSERT INTO cascadeshield_sim.operational_resources(run_id,resource_type,resource_id,definition,provenance) VALUES(?,?,?,?::jsonb,'SIMULATED')",state.runId,entry.getKey(),id,json(resource));}
        jdbc.update("DELETE FROM cascadeshield_sim.operational_assignments WHERE run_id=?",state.runId);
        for(var assignment:state.operations.assignments)jdbc.update("INSERT INTO cascadeshield_sim.operational_assignments(run_id,truck_id,assignment,provenance) VALUES(?,?,?::jsonb,'SIMULATED')",state.runId,assignment.truckId,json(assignment));
    }
    public Map<String,Object> saveSnapshot(GraphSnapshotExporter.GraphSnapshot snapshot){UUID id=UUID.randomUUID();jdbc.update("INSERT INTO cascadeshield_sim.graph_snapshots(id,schema_version,network_id,run_id,scenario_id,clock_sec,snapshot,operations_provenance) VALUES(?,?,?,?,?,?,?::jsonb,'SIMULATED')",id,snapshot.schemaVersion(),snapshot.networkId(),snapshot.runId(),snapshot.scenarioId(),snapshot.simulationTime().clockSec(),json(snapshot));return Map.of("id",id,"schemaVersion",snapshot.schemaVersion(),"clockSec",snapshot.simulationTime().clockSec(),"snapshot",snapshot);}
    public OperatorApprovalGuard.Approval requestApproval(State state,AiModels.CandidateAction candidate,AiModels.Evaluation evaluation){UUID id=UUID.randomUUID();jdbc.update("INSERT INTO cascadeshield_sim.operator_approvals(id,run_id,clock_sec,status,state_fingerprint,candidate,evaluation,provenance) VALUES(?,?,?,'REQUESTED',?,?::jsonb,?::jsonb,'SIMULATED_OPERATOR_WORKFLOW')",id,state.runId,state.clockSec,evaluation.stateFingerprint(),json(candidate),json(evaluation));return approval(id);}
    public OperatorApprovalGuard.Approval approval(UUID id){var values=jdbc.query("SELECT * FROM cascadeshield_sim.operator_approvals WHERE id=?",(r,n)->{try{return new OperatorApprovalGuard.Approval(UUID.fromString(r.getString("id")),UUID.fromString(r.getString("run_id")),r.getDouble("clock_sec"),r.getString("status"),r.getString("state_fingerprint"),mapper.readValue(r.getString("candidate"),AiModels.CandidateAction.class),mapper.readValue(r.getString("evaluation"),AiModels.Evaluation.class),r.getString("approved_by"),r.getString("requested_at"),r.getString("approved_at"),r.getString("executed_at"),r.getString("provenance"));}catch(Exception e){throw new IllegalStateException("Approval record unreadable",e);}},id);if(values.isEmpty())throw new ApiException(404,"Approval not found");return values.getFirst();}
    public List<Map<String,Object>> approvals(UUID runId){return jdbc.query("SELECT id,status,clock_sec,approved_by,requested_at FROM cascadeshield_sim.operator_approvals WHERE run_id=? ORDER BY requested_at DESC LIMIT 100",(r,n)->{Map<String,Object> row=new LinkedHashMap<>();row.put("id",r.getString(1));row.put("status",r.getString(2));row.put("clockSec",r.getDouble(3));row.put("approvedBy",r.getString(4));row.put("requestedAt",r.getString(5));return row;},runId);}
    public OperatorApprovalGuard.Approval approve(UUID id,String operator){int changed=jdbc.update("UPDATE cascadeshield_sim.operator_approvals SET status='APPROVED',approved_by=?,approved_at=now() WHERE id=? AND status='REQUESTED'",operator,id);if(changed!=1)throw ApiException.conflict("Approval is not awaiting operator review");return approval(id);}
    public void executed(UUID id){if(jdbc.update("UPDATE cascadeshield_sim.operator_approvals SET status='EXECUTED',executed_at=now() WHERE id=? AND status='APPROVED'",id)!=1)throw ApiException.conflict("Approval was already consumed or was not approved");}
    public Map<String,Object> saveScenario(String name,String network,Object config){UUID id=UUID.randomUUID();jdbc.update("INSERT INTO cascadeshield_sim.scenarios(id,name,network_id,configuration) VALUES(?,?,?,?::jsonb)",id,name,network,json(config));return Map.of("id",id.toString(),"name",name,"createdAt",OffsetDateTime.now().toString());}
    public List<Map<String,Object>> scenarios(){return jdbc.query("SELECT id,name,created_at FROM cascadeshield_sim.scenarios ORDER BY created_at DESC",(r,n)->Map.of("id",r.getString(1),"name",r.getString(2),"createdAt",r.getString(3)));}
    @SuppressWarnings("unchecked")
    public Map<String,Object> scenario(UUID id){List<Map<String,Object>> data=jdbc.query("SELECT name,network_id,configuration::text FROM cascadeshield_sim.scenarios WHERE id=?",(r,n)->{
        try{return Map.of("id",id.toString(),"name",r.getString(1),"networkId",r.getString(2),"configuration",mapper.readValue(r.getString(3),Map.class));}catch(Exception e){throw new IllegalStateException(e);}},id);if(data.isEmpty())throw new ApiException(404,"Scenario not found");return data.getFirst();}
    public boolean healthy(){return Integer.valueOf(1).equals(jdbc.queryForObject("SELECT 1",Integer.class));}
}
