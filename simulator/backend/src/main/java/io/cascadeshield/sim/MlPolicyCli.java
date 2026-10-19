package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.*;
import java.nio.file.*;
import java.lang.management.*;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.BenchmarkModels.*;

/** Resumable, standalone paired execution; no database, web application or operator state is loaded. */
public final class MlPolicyCli {
    public static void main(String[] args)throws Exception{
        if(args.length<5)throw new IllegalArgumentException("Usage: MlPolicyCli graph protocol output-directory diagnostics|final service-url [frozen-model-manifest]");
        ObjectMapper mapper=new ObjectMapper().findAndRegisterModules();Path graph=Path.of(args[0]),protocolPath=Path.of(args[1]),out=Path.of(args[2]);Files.createDirectories(out);
        String graphSha=MlExperimentProtocol.sha(Files.readAllBytes(graph)),protocolSha=MlExperimentProtocol.sha(Files.readAllBytes(protocolPath));RoadGraph roads=new RoadGraph(mapper.readValue(Files.readAllBytes(graph),NetworkFile.class));
        MlExperimentProtocol protocol=new MlExperimentProtocol(protocolPath,roads,mapper);BenchmarkPolicyRunner original=new BenchmarkPolicyRunner(roads,mapper);MlInferenceClient client=new MlInferenceClient(mapper,args[4],2000);
        List<Map<String,Object>> all=new ArrayList<>();String mode=args[3];
        if("diagnostics".equals(mode)){
            JsonNode declaration=mapper.readTree(Files.readAllBytes(protocolPath)).path("developmentDiagnostics");Set<Long> seeds=new HashSet<>();for(JsonNode seed:declaration.path("seeds"))seeds.add(seed.asLong());Set<String> families=new HashSet<>();for(JsonNode family:declaration.path("families"))families.add(family.asText());
            for(ScenarioSpec source:protocol.scenarios("validation"))if(seeds.contains(source.seed())&&families.contains(source.profile()))for(JsonNode variant:declaration.path("variants")){
                Map<String,Object> p=new LinkedHashMap<>(source.parameters());p.put("maxDecisions",variant.path("maxDecisions").asInt());p.put("rolloutHorizonSec",variant.path("rolloutHorizonSec").asDouble());
                ScenarioSpec scenario=new ScenarioSpec(source.id(),source.name(),source.seed(),source.profile(),source.configuration(),source.exogenousSchedule(),source.horizonSec(),source.inputFingerprint(),p,source.provenance());String id=variant.path("id").asText();
                PolicySpec policy=new PolicySpec(id,"M4 development diagnostic only",MlPolicyRunner.COMMON,true,true,true);all.add(execute(out,scenario,id,protocolSha,graphSha,"NOT_APPLICABLE",()->original.run(scenario,policy),mapper));}
        }else if("final".equals(mode)){
            if(args.length<7)throw new IllegalArgumentException("Frozen model selection manifest and source corpus directory required");Path frozenPath=Path.of(args[5]);JsonNode frozen=mapper.readTree(Files.readAllBytes(frozenPath));MlCorpusCli.validateFreeze(frozen,Path.of(args[6]),protocolSha,graphSha,new MlFeatureExtractor(roads,mapper).featureSchemaHash());
            String selectionSha=MlExperimentProtocol.sha(Files.readAllBytes(frozenPath));Set<String> models=new HashSet<>();for(JsonNode id:frozen.path("validatedModelIds"))models.add(id.asText());if(!models.contains("xgb-v1"))throw new IllegalArgumentException("Validated XGBoost is required before final B5 assessment");
            MlCorpusCli.immutableJson(out.resolve("final_assessment_freeze.json"),Map.of("selectionManifestSha256",selectionSha,"protocolSha256",protocolSha,"graphSha256",graphSha,"selectionManifest",frozen),mapper);
            MlPolicyRunner learned=new MlPolicyRunner(roads,mapper,client::infer,graphSha);List<String> omitted=new ArrayList<>();for(MlPolicyRunner.Variant variant:MlPolicyRunner.variants())if(variant.modelId()!=null&&!models.contains(variant.modelId()))omitted.add(variant.id());
            for(ScenarioSpec scenario:protocol.scenarios("final")){
                for(PolicySpec policy:BenchmarkPolicyRunner.catalog(true))all.add(execute(out,scenario,policy.id(),protocolSha,graphSha,selectionSha,()->original.run(scenario,policy),mapper));
                for(MlPolicyRunner.Variant variant:MlPolicyRunner.variants())if(variant.modelId()==null||models.contains(variant.modelId()))all.add(execute(out,scenario,variant.id(),protocolSha,graphSha,selectionSha,()->learned.run(scenario,variant),mapper));}
            MlCorpusCli.immutableJson(out.resolve("omitted_policy_variants.json"),Map.of("omittedPolicyIds",omitted,"reason","Only actually trained and validated IDs in the pre-assessment selection manifest are eligible"),mapper);
        }else throw new IllegalArgumentException("Unknown policy experiment mode");
        MlCorpusCli.immutableJson(out.resolve(mode+"_results.json"),Map.of("schemaVersion","cascadeshield.milestone4-policy-runs/1.0","mode",mode,"protocolSha256",protocolSha,"graphSha256",graphSha,"runs",all,"provenance",PROVENANCE),mapper);
        System.out.println("Completed "+all.size()+" "+mode+" policy outcomes");
    }
    private interface Run{PolicyRun get();}
    private static Map<String,Object> execute(Path output,ScenarioSpec scenario,String id,String protocolSha,String graphSha,String selectionSha,Run operation,ObjectMapper mapper)throws Exception{
        Path path=output.resolve(scenario.id()+"__"+id+".json");if(Files.exists(path)){@SuppressWarnings("unchecked") Map<String,Object> prior=mapper.readValue(Files.readAllBytes(path),Map.class);if(!protocolSha.equals(prior.get("protocolSha256"))||!selectionSha.equals(prior.get("selectionManifestSha256"))||!scenario.inputFingerprint().equals(prior.get("inputFingerprint")))throw new IllegalStateException("Existing outcome belongs to different experiment inputs");System.out.println("REUSED "+scenario.id()+" "+id);return prior;}
        for(MemoryPoolMXBean pool:ManagementFactory.getMemoryPoolMXBeans())try{pool.resetPeakUsage();}catch(UnsupportedOperationException ignored){}
        long started=System.nanoTime();PolicyRun run=operation.get();long peak=ManagementFactory.getMemoryPoolMXBeans().stream().filter(p->p.getType()==MemoryType.HEAP).map(MemoryPoolMXBean::getPeakUsage).filter(Objects::nonNull).mapToLong(MemoryUsage::getUsed).sum();
        Map<String,Object> row=new LinkedHashMap<>();row.put("protocolSha256",protocolSha);row.put("graphSha256",graphSha);row.put("selectionManifestSha256",selectionSha);row.put("scenarioId",scenario.id());row.put("family",scenario.profile());row.put("seed",scenario.seed());row.put("inputFingerprint",scenario.inputFingerprint());row.put("parameters",scenario.parameters());row.put("policyId",id);row.put("run",run);row.put("executionWallMs",(System.nanoTime()-started)/1e6);row.put("javaHeapPoolPeakBytes",peak);row.put("memoryScope","Sum of per-heap-pool peaks during this run; excludes Python service, GPU, native and container memory; not simultaneous RSS");
        MlCorpusCli.immutableJson(path,row,mapper);System.out.println("DONE "+scenario.id()+" "+id+" SLA="+run.metrics().slaViolationRate()+" late="+run.metrics().totalDeliveryLatenessSec()+" decisions="+run.decisions().size());return row;
    }
}
