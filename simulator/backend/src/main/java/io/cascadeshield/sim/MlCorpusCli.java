package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;
import static io.cascadeshield.sim.BenchmarkModels.*;

/** Offline/no-database supervised export. Does not instantiate Spring or read the operator's live state. */
public final class MlCorpusCli {
    public static final double IMPACT_HORIZON_SEC=300;
    public static final Set<String> ADVERSE_CODES=Set.of("DOCK_QUEUE","DOCK_CLOSED","DELIVERY_LATE","DRIVER_BUSY","DRIVER_UNAVAILABLE","SHIFT_EXHAUSTED");
    private final RoadGraph roads;private final ObjectMapper mapper;private final MlFeatureExtractor features;private final CounterfactualExperimentEngine copies;
    public MlCorpusCli(RoadGraph roads,ObjectMapper mapper){this.roads=roads;this.mapper=mapper;features=new MlFeatureExtractor(roads,mapper);copies=new CounterfactualExperimentEngine(roads,mapper);}
    public Map<String,Object> generate(ScenarioSpec spec,String split,List<Double> clocks,String graphSha){
        SimulationEngine engine=new SimulationEngine(roads,mapper);engine.restore(new BenchmarkScenarioGenerator(roads,mapper).initial(spec));engine.drainEvents();
        List<Map<String,Object>> frames=new ArrayList<>();int cursor=0;
        for(double target:clocks){if(target>spec.horizonSec()||"COMPLETED".equals(engine.raw().status))break;
            while(cursor<spec.exogenousSchedule().size()&&spec.exogenousSchedule().get(cursor).clockSec()<=target+1e-8){ScheduledCommand command=spec.exogenousSchedule().get(cursor++);CounterfactualExperimentEngine.advanceTo(engine,command.clockSec());if(engine.raw().clockSec<command.clockSec()-1e-8)break;inject(engine,command);}
            CounterfactualExperimentEngine.advanceTo(engine,target);engine.refresh(false);if("COMPLETED".equals(engine.raw().status))break;
            frames.add(features.frame(engine.raw()));
        }
        while(cursor<spec.exogenousSchedule().size()&&!"COMPLETED".equals(engine.raw().status)){ScheduledCommand command=spec.exogenousSchedule().get(cursor++);CounterfactualExperimentEngine.advanceTo(engine,command.clockSec());if(engine.raw().clockSec<command.clockSec()-1e-8)break;inject(engine,command);}
        CounterfactualExperimentEngine.advanceTo(engine,spec.horizonSec());State outcome=engine.snapshot();List<Violation> violations=copies.audit(outcome);if(violations.stream().anyMatch(Violation::hard))throw new IllegalStateException("Corpus physical invariant failure: "+violations);
        for(Map<String,Object> frame:frames)attachLabels(frame,outcome);
        Map<String,Object> result=new LinkedHashMap<>();result.put("schemaVersion","cascadeshield.ml-corpus/1.0");result.put("scenarioId",spec.id());result.put("seed",spec.seed());result.put("split",split);result.put("family",spec.profile());
        result.put("parameters",spec.parameters());result.put("inputFingerprint",spec.inputFingerprint());result.put("graphSha256",graphSha);result.put("horizonSec",spec.horizonSec());result.put("frames",frames);
        result.put("outcomes",Map.of("finalClockSec",outcome.clockSec,"completed","COMPLETED".equals(outcome.status),"trucks",outcome.trucks.stream().map(t->Map.of("id",t.id,"arrivalSec",t.arrivalSec,"departureSec",t.departureSec)).toList(),
            "deliveries",outcome.operations.deliveries.stream().map(d->Map.of("id",d.id,"truckId",d.truckId,"deliveredAtSec",d.deliveredAtSec,"deadlineSec",d.deadlineSec,"lateSec",d.lateSec)).toList(),"realizedImpacts",outcome.operations.realizedImpacts));
        result.put("provenance",PROVENANCE);return result;
    }
    @SuppressWarnings("unchecked") public void attachLabels(Map<String,Object> frame,State outcome){double cutoff=((Number)frame.get("clockSec")).doubleValue();boolean fullWindow="COMPLETED".equals(outcome.status)||outcome.clockSec>=cutoff+IMPACT_HORIZON_SEC-1e-8;
        Set<String> affected=new HashSet<>();for(Impact i:outcome.operations.realizedImpacts)if(ADVERSE_CODES.contains(i.code())&&!i.predicted()&&i.startSec()>cutoff+1e-8&&i.startSec()<=cutoff+IMPACT_HORIZON_SEC+1e-8){affected.addAll(i.resourceIds());for(String truck:i.truckIds())affected.add("TRUCK:"+truck);}
        for(Map<String,Object> row:(List<Map<String,Object>>)frame.get("trucks")){String id=(String)row.get("truckId");Truck t=OperationalRuntime.truck(outcome,id);boolean eta=Boolean.TRUE.equals(row.get("etaEligible")),delivery=Boolean.TRUE.equals(row.get("deliveryEligible"));
            List<String> ids=(List<String>)row.get("deliveryIds");List<Delivery> ds=outcome.operations.deliveries.stream().filter(d->ids.contains(d.id)).toList();boolean resolved=!ds.isEmpty()&&ds.stream().allMatch(d->d.deliveredAtSec>=0);
            Map<String,Object> labels=new LinkedHashMap<>();labels.put("remainingArrivalSec",eta&&t.arrivalSec>=0?Math.max(0,t.arrivalSec-cutoff):null);labels.put("deliveryLate",delivery&&resolved?(ds.stream().anyMatch(d->d.deliveredAtSec>d.deadlineSec+1e-7)?1:0):null);
            labels.put("futureImpact",fullWindow?(affected.contains("TRUCK:"+id)?1:0):null);labels.put("arrivalCensored",eta&&t.arrivalSec<0);labels.put("deliveryCensored",delivery&&!resolved);labels.put("impactWindowCensored",!fullWindow);row.put("labels",labels);}
        Map<String,Object> graph=(Map<String,Object>)frame.get("graphSnapshot");List<Map<String,Object>> labels=new ArrayList<>();for(Map<String,Object> node:(List<Map<String,Object>>)graph.get("nodes")){String id=(String)node.get("id");Map<String,Object> l=new LinkedHashMap<>();l.put("nodeId",id);l.put("futureImpact",fullWindow?(affected.contains(id)?1:0):null);l.put("eligible",fullWindow);labels.add(l);}frame.put("nodeLabels",labels);
    }
    public static void inject(SimulationEngine engine,ScheduledCommand command){Map<String,Object> p=command.payload();switch(command.kind()){
        case "INCIDENT_ADD"->engine.addIncident(new IncidentRequest((String)p.get("type"),(String)p.get("physicalId"),((Number)p.get("severity")).doubleValue(),((Number)p.get("durationSec")).doubleValue(),engine.raw().clockSec));
        case "DRIVER_AVAILABILITY"->engine.availability((String)p.get("id"),(Boolean)p.get("available"));default->throw new IllegalArgumentException("Unsupported private command");}engine.drainEvents();}
    public static void main(String[] args)throws Exception{
        if(args.length<4)throw new IllegalArgumentException("Usage: MlCorpusCli graph.json protocol.json output-directory train,validation,calibration|manifest|final [frozen-selection-manifest.json]");
        ObjectMapper mapper=new ObjectMapper().findAndRegisterModules();Path graphPath=Path.of(args[0]),protocolPath=Path.of(args[1]),output=Path.of(args[2]);
        String graphSha=MlExperimentProtocol.sha(Files.readAllBytes(graphPath)),protocolSha=MlExperimentProtocol.sha(Files.readAllBytes(protocolPath));RoadGraph roads=new RoadGraph(mapper.readValue(Files.readAllBytes(graphPath),NetworkFile.class));
        MlExperimentProtocol protocol=new MlExperimentProtocol(protocolPath,roads,mapper);MlCorpusCli cli=new MlCorpusCli(roads,mapper);Files.createDirectories(output);
        immutableJson(output.resolve("generation_manifest.json"),protocol.manifest(graphSha,protocolSha),mapper);immutableJson(output.resolve("feature_schema.json"),cli.features.featureSchema(),mapper);
        if(args[3].equals("manifest"))return;
        if(!args[3].equals("final")){if(args.length<5||!Files.isRegularFile(Path.of(args[4])))throw new IllegalArgumentException("Development labels require an independent passing input-only leakage audit");validateAudit(mapper.readTree(Files.readAllBytes(Path.of(args[4]))),output,protocolSha,graphSha,cli.features.featureSchemaHash());}
        for(String split:args[3].split(",")){
            if("final".equals(split)){if(args.length<5||!Files.isRegularFile(Path.of(args[4])))throw new IllegalArgumentException("Final labels require an existing frozen selection manifest");JsonNode frozen=mapper.readTree(Files.readAllBytes(Path.of(args[4])));validateFreeze(frozen,output,protocolSha,graphSha,cli.features.featureSchemaHash());immutableJson(output.resolve("final_unlock.json"),Map.of("selectionManifestSha256",MlExperimentProtocol.sha(Files.readAllBytes(Path.of(args[4]))),"selectionManifestPath",args[4]),mapper);}
            List<String> lines=new ArrayList<>();Path cases=output.resolve("cases").resolve(split);Files.createDirectories(cases);
            for(ScenarioSpec spec:protocol.scenarios(split)){Path path=cases.resolve(spec.id()+".json");Map<String,Object> row;if(Files.exists(path)){@SuppressWarnings("unchecked") Map<String,Object> loaded=mapper.readValue(Files.readAllBytes(path),Map.class);row=loaded;if(!spec.inputFingerprint().equals(row.get("inputFingerprint"))||!graphSha.equals(row.get("graphSha256")))throw new IllegalStateException("Existing corpus checksum mismatch");}
                else{row=cli.generate(spec,split,protocol.clocks(),graphSha);immutableJson(path,row,mapper);}lines.add(mapper.writeValueAsString(row));System.out.println(split+" "+spec.id()+" frames="+((List<?>)row.get("frames")).size());}
            byte[] bytes=(String.join("\n",lines)+"\n").getBytes(StandardCharsets.UTF_8);Path jsonl=output.resolve(split+".jsonl");if(Files.exists(jsonl)){if(!Arrays.equals(Files.readAllBytes(jsonl),bytes))throw new IllegalStateException("Refusing to overwrite changed split output");}else Files.write(jsonl,bytes,StandardOpenOption.CREATE_NEW);
        }
    }
    public static void validateAudit(JsonNode audit,Path corpus,String protocolSha,String graphSha,String schemaHash)throws Exception{
        if(!audit.path("trainingAuthorizedAfterAudit").asBoolean()||!protocolSha.equals(audit.path("protocolSha256").asText())||!graphSha.equals(audit.path("graphSha256").asText())||!schemaHash.equals(audit.path("featureSchemaHash").asText())||!MlExperimentProtocol.sha(Files.readAllBytes(corpus.resolve("generation_manifest.json"))).equals(audit.path("generationManifestSha256").asText()))throw new IllegalArgumentException("Independent audit must pass and bind current protocol, graph, feature schema and generation manifest bytes");}
    public static void validateFreeze(JsonNode frozen,Path corpus,String protocolSha,String graphSha,String schemaHash)throws Exception{
        if(!frozen.path("frozen").asBoolean()||!protocolSha.equals(frozen.path("protocolSha256").asText())||!graphSha.equals(frozen.path("graphSha256").asText())||!schemaHash.equals(frozen.path("featureSchemaHash").asText()))throw new IllegalArgumentException("Frozen selection must match actual protocol, graph and feature schema hashes");
        if(!frozen.path("validatedModelIds").isArray()||frozen.path("validatedModelIds").isEmpty()||!frozen.path("models").isObject()||frozen.path("models").isEmpty()||!frozen.path("artifactSha256").isObject()||frozen.path("artifactSha256").isEmpty())throw new IllegalArgumentException("Frozen selection must identify validated models and serialized artifact checksums");
        for(var entry:Map.of("generationManifestSha256","generation_manifest.json","sourceFeatureSchemaSha256","feature_schema.json").entrySet()){Path path=corpus.resolve(entry.getValue());if(!Files.isRegularFile(path)||!MlExperimentProtocol.sha(Files.readAllBytes(path)).equals(frozen.path(entry.getKey()).asText()))throw new IllegalArgumentException("Frozen selection must match actual "+entry.getValue()+" bytes");}
        for(String split:List.of("train","validation","calibration")){Path path=corpus.resolve(split+".jsonl");if(!Files.isRegularFile(path)||!MlExperimentProtocol.sha(Files.readAllBytes(path)).equals(frozen.path("sourceCorpusSha256").path(split).asText()))throw new IllegalArgumentException("Frozen selection must match actual "+split+" corpus bytes");}
    }
    public static void immutableJson(Path path,Object value,ObjectMapper mapper)throws Exception{byte[] bytes=mapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(value);if(Files.exists(path)){if(!mapper.readTree(Files.readAllBytes(path)).equals(mapper.readTree(bytes)))throw new IllegalStateException("Refusing to overwrite changed evidence "+path);}else Files.write(path,bytes,StandardOpenOption.CREATE_NEW);}
}
