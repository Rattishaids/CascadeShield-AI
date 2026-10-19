package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;
import static io.cascadeshield.sim.BenchmarkModels.*;

/** New fixed-version learned policies. Historical B0-B4 code is deliberately not modified. */
public final class MlPolicyRunner {
    public static final List<ActionType> COMMON=List.of(ActionType.NONE,ActionType.CONTINUE,ActionType.WAIT,ActionType.LOCAL_REROUTE,ActionType.GLOBAL_REROUTE);
    public record Variant(String id,String modelId,boolean counterfactual){}
    public interface Predictor {MlModels.Response infer(Map<String,Object> frame,List<Map<String,Object>> history,String modelId,String graphSha);}
    public static List<Variant> variants(){return List.of(new Variant("B5_RULE_V1",null,false),new Variant("B5_XGB_V1","xgb-v1",false),new Variant("B5_XGB_NO_GRAPH_V1","xgb-no-graph-v1",false),new Variant("B5_GNN_STATIC_V1","gnn-static-v1",false),new Variant("B5_GNN_TEMPORAL_V1","gnn-temporal-v1",false),new Variant("B5_XGB_CF_V1","xgb-v1",true));}
    private final RoadGraph roads;private final ObjectMapper mapper;private final Predictor predictor;private final String graphSha;
    private final CounterfactualExperimentEngine cf;private final MlFeatureExtractor extractor;private final BenchmarkPolicyRunner historical;
    private static final PolicySpec EXPOSURE=new PolicySpec("B4_M4_EXPOSURE","Original temporal/adaptive exposure",COMMON,true,true,false);
    public MlPolicyRunner(RoadGraph roads,ObjectMapper mapper,Predictor predictor,String graphSha){this.roads=roads;this.mapper=mapper;this.predictor=predictor;this.graphSha=graphSha;cf=new CounterfactualExperimentEngine(roads,mapper);extractor=new MlFeatureExtractor(roads,mapper);historical=new BenchmarkPolicyRunner(roads,mapper);}
    public PolicyRun run(ScenarioSpec spec,Variant variant){
        if(!variants().contains(variant))throw new IllegalArgumentException("Unknown frozen B5 variant");
        SimulationEngine engine=new SimulationEngine(roads,mapper);State initial=new BenchmarkScenarioGenerator(roads,mapper).initial(spec);engine.restore(mapper.convertValue(initial,State.class));engine.drainEvents();
        List<DecisionTrace> decisions=new ArrayList<>();List<Map<String,Object>> details=new ArrayList<>(),history=new ArrayList<>();Map<String,Set<String>> seen=new HashMap<>();Map<String,Violation> audits=new TreeMap<>();Set<String> resourceKeys=new HashSet<>();
        int cursor=0,rejections=0,requests=0,failedRequests=0,fallbackDecisions=0,rollouts=0;double decisionMs=0,inferenceMs=0,nextInterval=0;Map<String,Integer> failureReasons=new TreeMap<>();
        int limit=((Number)spec.parameters().get("maxDecisions")).intValue();double interval=((Number)spec.parameters().get("decisionIntervalSec")).doubleValue(),rolloutSec=((Number)spec.parameters().get("rolloutHorizonSec")).doubleValue();
        GraphView beforeGraph=engine.raw().operations.graph;CascadeView beforeRisk=historical.policyRisk(engine.raw(),EXPOSURE);boolean captured=false;
        while(engine.raw().clockSec<spec.horizonSec()-1e-8&&!"COMPLETED".equals(engine.raw().status)){
            if(Thread.currentThread().isInterrupted())throw new IllegalStateException("M4 experiment interrupted");State s=engine.raw();boolean announced=false;
            while(cursor<spec.exogenousSchedule().size()&&spec.exogenousSchedule().get(cursor).clockSec()<=s.clockSec+1e-8){MlCorpusCli.inject(engine,spec.exogenousSchedule().get(cursor++));announced=true;}
            engine.refresh(false);s=engine.raw();audit(s,audits);Set<String> current=new HashSet<>(s.operations.activePredictedKeys);boolean newResource=current.stream().anyMatch(k->!resourceKeys.contains(k));resourceKeys.addAll(current);
            double currentClock=s.clockSec;if(!captured&&(s.incidents.stream().anyMatch(i->RoadGraph.active(i,currentClock))||!s.operations.predictedImpacts.isEmpty())){beforeGraph=s.operations.graph;beforeRisk=historical.policyRisk(s,EXPOSURE);captured=true;}
            boolean periodic=s.clockSec>=nextInterval-1e-8;if(periodic)nextInterval=Math.floor(s.clockSec/interval+1)*interval;
            if((announced||newResource||periodic)&&decisions.size()<limit){Set<String> eligible=eligible(s,historical.policyRisk(s,EXPOSURE));
                for(String id:eligible){if(decisions.size()>=limit)break;s=engine.raw();Truck truck=OperationalRuntime.truck(s,id);String trigger=signature(s,truck,historical.policyRisk(s,EXPOSURE));if(trigger.isEmpty()||!seen.computeIfAbsent(id,k->new HashSet<>()).add(trigger))continue;
                    long start=System.nanoTime();State observed=cf.observedClone(s);List<Action> actions=cf.actions(observed,id).stream().filter(a->COMMON.contains(a.type())).toList();if(actions.isEmpty())continue;
                    List<Map<String,Object>> prior=history.stream().filter(h->((Number)h.get("clockSec")).doubleValue()<observed.clockSec-1e-8).toList();prior=prior.subList(Math.max(0,prior.size()-3),prior.size());
                    List<Map<String,Object>> candidateFrames=new ArrayList<>();List<Map<String,MlModels.Prediction>> predictions=new ArrayList<>();List<Map<String,Object>> predictionDetails=new ArrayList<>();boolean fallback=variant.modelId()==null;
                    for(Action action:actions){SimulationEngine copy=new SimulationEngine(roads,mapper);copy.restore(mapper.convertValue(observed,State.class));cf.apply(copy,action);Map<String,Object> frame=extractor.frame(copy.raw());candidateFrames.add(frame);Map<String,MlModels.Prediction> p=new HashMap<>();
                        if(variant.modelId()!=null){requests++;try{MlModels.Response response=predictor.infer(frame,prior,variant.modelId(),graphSha);for(MlModels.Prediction value:response.predictions())p.put(value.truckId(),value);inferenceMs+=response.latencyMs();predictionDetails.add(Map.of("actionId",action.id(),"modelVersion",response.modelVersion(),"predictions",response.predictions(),"latencyMs",response.latencyMs(),"calibration",response.calibration()));}
                            catch(MlModels.InferenceException error){fallback=true;failedRequests++;failureReasons.merge(error.getMessage(),1,Integer::sum);}}
                        predictions.add(p);}
                    if(fallback&&variant.modelId()!=null)fallbackDecisions++;
                    double baselineDistance=observed.trucks.stream().mapToDouble(t->t.remainingDistanceM).sum();List<ScoredAlternative> alternatives=new ArrayList<>();int candidateRollouts=0;
                    for(int i=0;i<actions.size();i++){Action action=actions.get(i);double direct=predictionScore(observed,candidateFrames.get(i),fallback?Map.of():predictions.get(i),baselineDistance);Metrics forecast=null;List<Violation> violations=cf.validate(observed,action);boolean feasible=violations.stream().noneMatch(Violation::hard);double score=direct;
                        if(variant.counterfactual()){Rollout trial=cf.trial(observed,action,Math.min(spec.horizonSec(),observed.clockSec+rolloutSec));candidateRollouts++;rollouts++;forecast=trial.metrics();feasible=trial.valid();violations=trial.violations();if(feasible)score=.5*direct+.5*outcomeScore(forecast,baselineDistance,observed.operations.graph.nodes().size())+2*forecast.unfinishedDeliveries();}
                        alternatives.add(new ScoredAlternative(action,feasible,score,forecast,violations));}
                    Action selected=alternatives.stream().filter(ScoredAlternative::feasible).min(Comparator.comparingDouble(ScoredAlternative::score).thenComparingInt(a->a.action().type().ordinal()).thenComparing(a->a.action().id())).orElseThrow().action();
                    if(cf.validate(s,selected).stream().anyMatch(Violation::hard)){rejections++;continue;}String knowledge=cf.fingerprint(observed);cf.apply(engine,selected);audit(engine.raw(),audits);double elapsed=(System.nanoTime()-start)/1e6;decisionMs+=elapsed;
                    String explanation=(fallback?"Deterministic B5_RULE fixed score":"Validated "+variant.modelId()+" prediction-time fixed score")+(variant.counterfactual()?" plus equally weighted executed-outcome score":"; no executed rollout")+". Same five road actions and six decision slots as controlled B4; no private schedule inputs.";
                    decisions.add(new DecisionTrace(observed.clockSec,id,trigger,observed.incidents.stream().map(i->i.id).sorted().toList(),alternatives,selected.id(),explanation,elapsed,knowledge));
                    details.add(Map.of("clockSec",observed.clockSec,"truckId",id,"requestedModel",variant.modelId()==null?"DETERMINISTIC_RULE":variant.modelId(),"fallback",fallback&&variant.modelId()!=null,"candidateCount",actions.size(),"rolloutCount",candidateRollouts,"candidatePredictions",predictionDetails));
                }
            }
            // Keep actual past sampled states only. Candidate states never enter another decision's history.
            if(history.isEmpty()||((Number)history.getLast().get("clockSec")).doubleValue()<engine.raw().clockSec-1e-8){history.add(extractor.frame(engine.raw()));if(history.size()>3)history.removeFirst();}
            s=engine.raw();double next=Math.min(spec.horizonSec(),Math.min(s.clockSec+10,nextInterval));if(cursor<spec.exogenousSchedule().size())next=Math.min(next,spec.exogenousSchedule().get(cursor).clockSec());if(next<=s.clockSec+1e-8)next=Math.min(spec.horizonSec(),s.clockSec+.1);CounterfactualExperimentEngine.advanceTo(engine,next);engine.drainEvents();
        }
        State outcome=engine.snapshot();audit(outcome,audits);double incidentStart=spec.exogenousSchedule().stream().filter(c->c.kind().equals("INCIDENT_ADD")).mapToDouble(ScheduledCommand::clockSec).min().orElse(0);
        Metrics metrics=ExperimentMetrics.measure(initial,outcome,spec.horizonSec(),incidentStart,audits.size(),decisionMs,0);Map<String,Object> summary=new LinkedHashMap<>();
        summary.put("beforeGraph",beforeGraph);summary.put("beforeCascade",beforeRisk);summary.put("afterGraph",outcome.operations.graph);summary.put("afterCascade",outcome.operations.cascade);summary.put("beforeGraphPhase",captured?"FIRST_OBSERVED_DISRUPTION":"INITIAL_STATE");summary.put("afterGraphPhase","FINAL_STATE");
        summary.put("initialFingerprint",cf.fingerprint(initial));summary.put("finalFingerprint",cf.fingerprint(outcome));summary.put("comparisonMode","EQUAL_ACTIONS");summary.put("complete",metrics.unfinishedDeliveries()==0);summary.put("censored",metrics.recoveryCensored());
        summary.put("decisionLimit",limit);summary.put("decisionLimitReached",decisions.size()>=limit);summary.put("constraintRejections",rejections);summary.put("constraintAudit",List.copyOf(audits.values()));summary.put("constraintAuditCadenceSec",10);summary.put("inferenceRequests",requests);summary.put("failedInferenceRequests",failedRequests);summary.put("fallbackDecisions",fallbackDecisions);summary.put("inferenceServiceMs",inferenceMs);summary.put("failureReasons",failureReasons);summary.put("simulationRolloutCount",rollouts);summary.put("mlDecisionDetails",details);summary.put("modelId",variant.modelId()==null?"DETERMINISTIC_RULE":variant.modelId());summary.put("deliveredAtSec",outcome.operations.deliveries.stream().collect(java.util.stream.Collectors.toMap(d->d.id,d->d.deliveredAtSec,(a,b)->a,TreeMap::new)));summary.put("realizedImpacts",outcome.operations.realizedImpacts);
        return new PolicyRun(spec.id(),spec.seed(),variant.id(),spec.inputFingerprint(),metrics,decisions,summary,PROVENANCE);
    }
    @SuppressWarnings("unchecked") public static double predictionScore(State observed,Map<String,Object> frame,Map<String,MlModels.Prediction> predictions,double baselineDistance){double risk=0,late=0,impact=0,distance=0;int count=0;double clock=((Number)frame.get("clockSec")).doubleValue();
        for(Map<String,Object> row:(List<Map<String,Object>>)frame.get("trucks")){Map<String,Object> f=(Map<String,Object>)row.get("features"),base=(Map<String,Object>)row.get("baseline");distance+=n(f.get("remaining_distance_m"),0);if(!Boolean.TRUE.equals(row.get("deliveryEligible")))continue;count++;MlModels.Prediction p=predictions.get((String)row.get("truckId"));
            risk+=p!=null&&p.slaProbability()!=null?p.slaProbability():n(base.get("slackRisk"),1);impact+=p!=null&&p.futureImpactProbability()!=null?p.futureImpactProbability():n(base.get("graphRisk"),0);
            double completion=n(base.get("deliveryCompletionSec"),clock+1800);if(p!=null&&p.remainingArrivalSec()!=null&&Boolean.TRUE.equals(row.get("etaEligible")))completion+=p.remainingArrivalSec()-n(f.get("rule_road_remaining_sec"),0);
            late+=Math.max(0,completion-(clock+n(f.get("deadline_slack_sec"),0)));}
        return .6*risk/Math.max(1,count)+.25*Math.min(1,late/(Math.max(1,count)*1800))+.1*impact/Math.max(1,count)+.05*Math.min(1,Math.max(0,distance-baselineDistance)/Math.max(1,baselineDistance));}
    public static double outcomeScore(Metrics m,double distance,int resources){return .6*m.slaViolationRate()+.25*Math.min(1,m.totalDeliveryLatenessSec()/(Math.max(1,m.deliveryCount())*1800))+.1*Math.min(1,m.downstreamAffectedResources()/(double)Math.max(1,resources))+.05*Math.min(1,m.positiveAdditionalDistanceM()/Math.max(1,distance));}
    private static double n(Object x,double fallback){return x instanceof Number value?value.doubleValue():fallback;}
    private void audit(State s,Map<String,Violation> out){for(Violation v:cf.audit(s))if(v.hard())out.putIfAbsent(v.code()+"|"+String.join(",",new TreeSet<>(v.resourceIds())),v);}
    private static Set<String> eligible(State s,CascadeView risk){Set<String> out=new TreeSet<>();for(Truck t:s.trucks)if(!t.affectedIncidentIds.isEmpty()&&t.arrivalSec<0)out.add(t.id);for(String id:risk.affectedNodeIds())if(id.startsWith("TRUCK:")){Assignment a=OperationalRuntime.assignment(s,id.substring(6));if(a==null||!List.of("COMPLETED","UNLOADING").contains(a.status))out.add(id.substring(6));}return out;}
    private static String signature(State s,Truck t,CascadeView risk){SortedSet<String> causes=new TreeSet<>(t.affectedIncidentIds);for(NodeRisk n:risk.nodeRisks())if(n.nodeId().equals("TRUCK:"+t.id)&&n.score()>=risk.threshold())causes.addAll(n.causeIds());for(Impact i:s.operations.predictedImpacts)if(i.truckIds().contains(t.id)&&!i.code().equals("DELIVERY_ETA_UNKNOWN"))causes.add(i.id());return String.join("|",causes);}
}
