package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.util.*;

@Repository
public class BenchmarkRepository {
    private final JdbcTemplate jdbc;private final ObjectMapper mapper;
    public BenchmarkRepository(JdbcTemplate jdbc,ObjectMapper mapper){this.jdbc=jdbc;this.mapper=mapper;}
    private String json(Object value){try{return mapper.writeValueAsString(value);}catch(Exception e){throw new IllegalStateException(e);}}
    public void interrupted(){jdbc.update("UPDATE cascadeshield_sim.benchmark_jobs SET status='FAILED',error='Backend stopped before completion. Rerun the persisted request; no missing outcomes have been fabricated.',finished_at=now() WHERE status IN ('QUEUED','RUNNING')");}
    public void create(UUID id,String network,String digest,Object request,int total){jdbc.update("INSERT INTO cascadeshield_sim.benchmark_jobs(id,network_id,graph_sha256,status,request,total_runs,provenance) VALUES(?,?,?,'QUEUED',?::jsonb,?,'SIMULATED_RESEARCH_EXPERIMENT')",id,network,digest,json(request),total);}
    public void progress(UUID id,int done){jdbc.update("UPDATE cascadeshield_sim.benchmark_jobs SET status='RUNNING',completed_runs=? WHERE id=?",done,id);}
    public void complete(UUID id,Object result,int done){jdbc.update("UPDATE cascadeshield_sim.benchmark_jobs SET status='COMPLETED',completed_runs=?,result=?::jsonb,finished_at=now() WHERE id=?",done,json(result),id);}
    public void failed(UUID id,String error,Object partial){jdbc.update("UPDATE cascadeshield_sim.benchmark_jobs SET status='FAILED',error=?,result=?::jsonb,finished_at=now() WHERE id=?",error,json(partial),id);}
    private Map<String,Object> row(java.sql.ResultSet r,boolean includeResult)throws java.sql.SQLException{try{Map<String,Object> map=new LinkedHashMap<>();map.put("id",r.getString("id"));map.put("status",r.getString("status"));map.put("completedRuns",r.getInt("completed_runs"));map.put("totalRuns",r.getInt("total_runs"));map.put("request",mapper.readValue(r.getString("request"),Map.class));map.put("createdAt",r.getString("created_at"));map.put("finishedAt",r.getString("finished_at"));map.put("error",r.getString("error"));map.put("networkId",r.getString("network_id"));map.put("graphSha256",r.getString("graph_sha256"));map.put("provenance",r.getString("provenance"));if(includeResult)map.put("result",r.getString("result")==null?null:mapper.readValue(r.getString("result"),Map.class));return map;}catch(java.io.IOException e){throw new IllegalStateException(e);}}
    public Map<String,Object> get(UUID id){var rows=jdbc.query("SELECT * FROM cascadeshield_sim.benchmark_jobs WHERE id=?",(r,n)->row(r,true),id);if(rows.isEmpty())throw new ApiException(404,"Benchmark job not found");return rows.getFirst();}
    public List<Map<String,Object>> list(){return jdbc.query("SELECT * FROM cascadeshield_sim.benchmark_jobs ORDER BY created_at DESC LIMIT 50",(r,n)->row(r,false));}
}
