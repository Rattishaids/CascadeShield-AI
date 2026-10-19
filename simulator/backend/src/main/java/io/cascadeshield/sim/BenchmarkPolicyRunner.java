package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;
import static io.cascadeshield.sim.BenchmarkModels.*;

/** Independent policy execution with a private exogenous schedule and current-knowledge planning. */
public final class BenchmarkPolicyRunner {
    private static final List<ActionType> COMMON=List.of(ActionType.NONE,ActionType.CONTINUE,ActionType.WAIT,ActionType.LOCAL_REROUTE,ActionType.GLOBAL_REROUTE);
    private final RoadGraph roads;
    private final ObjectMapper mapper;
    private final CounterfactualExperimentEngine counterfactual;
    private final AiFallbackPipeline fallback;
    private final BenchmarkScenarioGenerator generator;
    private record Selection(Action action,List<ScoredAlternative> alternatives,String explanation) {}

    public BenchmarkPolicyRunner(RoadGraph roads,ObjectMapper mapper){this.roads=roads;this.mapper=mapper;counterfactual=new CounterfactualExperimentEngine(roads,mapper);fallback=new AiFallbackPipeline(roads,mapper);generator=new BenchmarkScenarioGenerator(roads,mapper);}
    public static List<PolicySpec> catalog(boolean equalActionSet){return List.of(
        new PolicySpec("B0","No intervention",equalActionSet?COMMON:List.of(ActionType.NONE),true,true,false),
        new PolicySpec("B1","Global reactive road routing",equalActionSet?COMMON:List.of(ActionType.NONE,ActionType.GLOBAL_REROUTE),false,false,false),
        new PolicySpec("B2","Local reactive road repair",equalActionSet?COMMON:List.of(ActionType.NONE,ActionType.LOCAL_REROUTE),false,false,false),
        new PolicySpec("B3","Original graph/rule heuristic",equalActionSet?COMMON:List.of(ActionType.NONE,ActionType.CONTINUE,ActionType.WAIT,ActionType.GLOBAL_REROUTE),true,true,false),
        new PolicySpec("B4","Executed counterfactual cascade prevention",equalActionSet?COMMON:List.of(ActionType.values()),true,true,true));}
    public static List<PolicySpec> ablations(){List<ActionType> all=List.of(ActionType.values());return List.of(
        new PolicySpec("B4_NO_TEMPORAL","B4 without future temporal dependency exposure",all,false,true,true),
        new PolicySpec("B4_NO_ADAPTIVE","B4 with fixed exposure threshold",all,true,false,true),
        new PolicySpec("B4_NO_COUNTERFACTUAL","B4 with copied heuristic scoring",all,true,true,false));}

    public PolicyRun run(ScenarioSpec spec,PolicySpec policy){
        validateSpec(spec,policy);State initial=generator.initial(spec);SimulationEngine engine=new SimulationEngine(roads,mapper);engine.restore(mapper.convertValue(initial,State.class));engine.drainEvents();
        String initialFingerprint=counterfactual.fingerprint(engine.raw());GraphView beforeGraph=engine.raw().operations.graph;CascadeView beforeCascade=policyRisk(engine.raw(),policy);
        List<DecisionTrace> traces=new ArrayList<>();Map<String,Set<String>> seen=new HashMap<>();int cursor=0,constraintRejections=0,dockChanges=0;
        Map<String,Violation> auditViolations=new TreeMap<>();collectAudit(engine.raw(),auditViolations);
        int decisionLimit=((Number)spec.parameters().getOrDefault("maxDecisions",12)).intValue();
        double interval=((Number)spec.parameters().getOrDefault("decisionIntervalSec",30)).doubleValue();
        double rolloutSec=((Number)spec.parameters().getOrDefault("rolloutHorizonSec",1800)).doubleValue();
        double nextInterval=0,decisionMs=0;Set<String> observedResourceKeys=new HashSet<>();boolean capturedDisruption=false;
        while(engine.raw().clockSec<spec.horizonSec()-1e-8&&!"COMPLETED".equals(engine.raw().status)){
            if(Thread.currentThread().isInterrupted())throw new IllegalStateException("Benchmark interrupted");
            State state=engine.raw();boolean announced=false;
            while(cursor<spec.exogenousSchedule().size()&&spec.exogenousSchedule().get(cursor).clockSec()<=state.clockSec+1e-8){inject(engine,spec.exogenousSchedule().get(cursor++));announced=true;}
            engine.refresh(false);state=engine.raw();
            collectAudit(state,auditViolations);
            Set<String> keys=new HashSet<>(state.operations.activePredictedKeys);boolean newResource=keys.stream().anyMatch(k->!observedResourceKeys.contains(k));observedResourceKeys.addAll(keys);
            double graphClock=state.clockSec;
            if(!capturedDisruption&&(state.incidents.stream().anyMatch(i->RoadGraph.active(i,graphClock))||!state.operations.predictedImpacts.isEmpty())){
                beforeGraph=state.operations.graph;beforeCascade=policyRisk(state,policy);capturedDisruption=true;
            }
            boolean periodic=state.clockSec>=nextInterval-1e-8;
            if(periodic)nextInterval=Math.floor(state.clockSec/interval+1)*interval;
            if((announced||newResource||periodic)&&!"B0".equals(policy.id())&&traces.size()<decisionLimit){
                CascadeView risk=policyRisk(state,policy);Set<String> eligible=eligible(state,policy,risk);
                List<String> truckIds=state.trucks.stream().map(t->t.id).filter(eligible::contains).sorted().toList();
                for(String truckId:truckIds){
                    if(traces.size()>=decisionLimit)break;
                    state=engine.raw();Truck t=OperationalRuntime.truck(state,truckId);String trigger=signature(state,t,policyRisk(state,policy));
                    if(trigger.isEmpty()||!seen.computeIfAbsent(truckId,k->new HashSet<>()).add(trigger))continue;
                    long started=System.nanoTime();State observed=counterfactual.observedClone(state);String knowledge=counterfactual.fingerprint(observed);
                    List<Action> candidates=counterfactual.actions(observed,truckId).stream().filter(a->policy.allowedActions().contains(a.type())).toList();
                    if(candidates.isEmpty())continue;
                    Selection selection=select(observed,policy,candidates,Math.min(spec.horizonSec(),state.clockSec+rolloutSec));
                    List<Violation> validation=counterfactual.validate(state,selection.action);
                    if(validation.stream().anyMatch(Violation::hard)){constraintRejections++;continue;}
                    counterfactual.apply(engine,selection.action);if(selection.action.type()==ActionType.ADJUST_DOCK_RESERVATION)dockChanges++;
                    collectAudit(engine.raw(),auditViolations);
                    double elapsed=(System.nanoTime()-started)/1e6;decisionMs+=elapsed;
                    List<String> known=observed.incidents.stream().filter(i->i.startSec<=observed.clockSec).map(i->i.id).sorted().toList();
                    traces.add(new DecisionTrace(state.clockSec,truckId,trigger,known,selection.alternatives,selection.action.id(),selection.explanation,elapsed,knowledge));
                }
            }
            double next=state.clockSec+10; // identical bounded observation cadence; physical movement still has 0.1 s ticks.
            if(cursor<spec.exogenousSchedule().size())next=Math.min(next,spec.exogenousSchedule().get(cursor).clockSec());
            next=Math.min(next,Math.min(spec.horizonSec(),nextInterval));
            if(next<=state.clockSec+1e-8)next=Math.min(spec.horizonSec(),state.clockSec+.1);
            CounterfactualExperimentEngine.advanceTo(engine,next);engine.drainEvents();
        }
        State outcome=engine.snapshot();double incidentStart=spec.exogenousSchedule().stream().filter(c->c.kind().equals("INCIDENT_ADD")).mapToDouble(ScheduledCommand::clockSec).min().orElse(0);
        collectAudit(outcome,auditViolations);
        Metrics metrics=ExperimentMetrics.measure(initial,outcome,spec.horizonSec(),incidentStart,auditViolations.size(),decisionMs,dockChanges);
        Map<String,Object> summary=new LinkedHashMap<>();summary.put("beforeGraph",beforeGraph);summary.put("beforeCascade",beforeCascade);
        summary.put("afterGraph",outcome.operations.graph);summary.put("afterCascade",policyRisk(outcome,policy));
        summary.put("beforeGraphPhase",capturedDisruption?"FIRST_OBSERVED_DISRUPTION":"INITIAL_STATE");summary.put("afterGraphPhase","FINAL_STATE");
        summary.put("initialFingerprint",initialFingerprint);summary.put("finalFingerprint",counterfactual.fingerprint(outcome));
        summary.put("comparisonMode",policy.allowedActions().equals(COMMON)?"EQUAL_ACTIONS":"FULL");summary.put("comparison",summary.get("comparisonMode"));
        summary.put("ablation",policy.id().startsWith("B4_NO_")?policy.id().substring(3):"FULL");
        summary.put("complete",metrics.unfinishedDeliveries()==0);summary.put("censored",metrics.recoveryCensored());
        summary.put("deliveredAtSec",outcome.operations.deliveries.stream().collect(java.util.stream.Collectors.toMap(d->d.id,d->d.deliveredAtSec,(a,b)->a,TreeMap::new)));
        summary.put("realizedImpacts",List.copyOf(outcome.operations.realizedImpacts));summary.put("decisionLimit",decisionLimit);summary.put("decisionLimitReached",traces.size()>=decisionLimit);
        summary.put("constraintRejections",constraintRejections);summary.put("constraintAudit",List.copyOf(auditViolations.values()));summary.put("constraintAuditCadenceSec",10);
        summary.put("knowledgeRule","Only already announced incidents and current driver availability enter candidate evaluation. Private restoration/future incidents are injected externally.");
        return new PolicyRun(spec.id(),spec.seed(),policy.id(),spec.inputFingerprint(),metrics,List.copyOf(traces),Collections.unmodifiableMap(summary),PROVENANCE);
    }

    private Selection select(State observed,PolicySpec policy,List<Action> candidates,double horizon){
        if(policy.counterfactualEvaluation()){
            List<Rollout> rollouts=new ArrayList<>();for(Action action:candidates)rollouts.add(counterfactual.trial(observed,action,horizon));
            return new Selection(counterfactual.choose(rollouts),counterfactual.score(rollouts),"Executed identical current-knowledge engine copies to "+horizon+" s; choose normalized simulated SLA/lateness/downstream/cost/distance/recovery score. Hidden future events are excluded.");
        }
        if("B1".equals(policy.id()))return heuristic(observed,candidates,"ROAD",policy);
        if("B2".equals(policy.id())){
            Optional<Action> local=candidates.stream().filter(a->a.type()==ActionType.LOCAL_REROUTE).findFirst();
            if(local.isPresent())return new Selection(local.get(),descriptions(observed,candidates),"Conventional first-segment repair: use a feasible local detour when the remaining route is currently exposed.");
            return new Selection(noAction(candidates),descriptions(observed,candidates),"No feasible local segment repair; keep the current connected plan.");
        }
        if("B3".equals(policy.id())&&!policy.allowedActions().equals(COMMON))return originalHeuristic(observed,candidates);
        return heuristic(observed,candidates,"GRAPH_RULE",policy);
    }
    private Selection originalHeuristic(State observed,List<Action> actions){
        String truck=actions.getFirst().truckId();List<AiModels.Evaluation> evaluations=new ArrayList<>();Map<String,Action> matching=new HashMap<>();
        for(AiModels.CandidateAction old:fallback.candidates(observed,truck).candidates()){
            ActionType type=switch(old.action()){case "REROUTE" -> ActionType.GLOBAL_REROUTE;case "WAIT" -> ActionType.WAIT;default -> ActionType.CONTINUE;};
            Action equivalent=actions.stream().filter(a->a.type()==type).findFirst().orElse(null);
            if(equivalent==null&&type==ActionType.GLOBAL_REROUTE){
                Truck t=OperationalRuntime.truck(observed,truck);
                try{if(new ExperimentActions(roads,mapper).global(observed,t).equals(t.route.edgeIds().subList(t.edgeIndex,t.route.edgeIds().size())))equivalent=noAction(actions);}catch(ApiException ignored){}
            } // unchanged shortest route has no M3 reroute mutation; an infeasible mutation is filtered.
            if(equivalent!=null){AiModels.Evaluation value=fallback.evaluate(observed,old);if(value.validation().valid()){evaluations.add(value);matching.put(old.id(),equivalent);}}
        }
        if(evaluations.isEmpty())return new Selection(noAction(actions),descriptions(observed,actions),"Original fallback offers no feasible response under the stricter benchmark hard constraints; preserve the current plan.");
        double maxTime=evaluations.stream().mapToDouble(e->Math.max(1,e.afterArrivalSec()-observed.clockSec)).max().orElse(1);
        double maxDistance=evaluations.stream().mapToDouble(e->Math.max(1,e.remainingDistanceM())).max().orElse(1);
        double maxConflict=evaluations.stream().mapToDouble(e->Math.max(1,e.afterImpacts().stream().mapToDouble(Impact::delaySec).sum())).max().orElse(1);
        List<ScoredAlternative> scored=evaluations.stream().map(e->new ScoredAlternative(matching.get(e.candidate().id()),true,
            .65*Math.max(0,e.afterArrivalSec()-observed.clockSec)/maxTime+.2*e.remainingDistanceM()/maxDistance+.15*e.afterImpacts().stream().mapToDouble(Impact::delaySec).sum()/maxConflict,
            null,counterfactual.validate(observed,matching.get(e.candidate().id())))).toList();
        AiModels.CandidateAction selected=fallback.optimize(evaluations,observed.clockSec);
        return new Selection(matching.get(selected.id()),scored,"Original AiFallbackPipeline candidates, copied evaluations and optimize selection; unchanged routes use NONE and stricter benchmark hard constraints filter unsupported mutations.");
    }
    private Selection heuristic(State observed,List<Action> candidates,String method,PolicySpec policy){
        record H(Action action,double arrival,double distance,double exposure,List<Violation> violations) {}
        List<H> choices=new ArrayList<>();
        for(Action action:candidates){SimulationEngine copy=new SimulationEngine(roads,mapper);copy.restore(mapper.convertValue(observed,State.class));counterfactual.apply(copy,action);
            AiModels.PredictionBatch prediction=fallback.predict(copy.raw());AiModels.TruckPrediction t=prediction.trucks().stream().filter(x->x.truckId().equals(action.truckId())).findFirst().orElseThrow();
            double exposure=prediction.predictedImpacts().stream().mapToDouble(Impact::delaySec).sum();choices.add(new H(action,Math.max(0,t.conditionalRoadArrivalSec()-observed.clockSec),t.remainingDistanceM(),exposure,counterfactual.validate(observed,action)));}
        double maxTime=choices.stream().mapToDouble(H::arrival).max().orElse(1),maxDistance=choices.stream().mapToDouble(H::distance).max().orElse(1),maxExposure=choices.stream().mapToDouble(H::exposure).max().orElse(1);
        List<ScoredAlternative> scores=new ArrayList<>();
        for(H h:choices){double score="ROAD".equals(method)?h.arrival/Math.max(1,maxTime):.65*h.arrival/Math.max(1,maxTime)+.20*h.distance/Math.max(1,maxDistance)+.15*h.exposure/Math.max(1,maxExposure);
            scores.add(new ScoredAlternative(h.action,true,score,null,h.violations));}
        Action best=scores.stream().min(Comparator.comparingDouble(ScoredAlternative::score).thenComparingInt(a->a.action().type().ordinal()).thenComparing(a->a.action().id())).orElseThrow().action();
        String explanation="ROAD".equals(method)?"Reactive road-only selection minimizes projected road arrival over available connected routing actions; no rollout or dock-outcome objective.":"Reuse the original AiFallbackPipeline copied predictions with normalized time 0.65, distance 0.20 and projected operational exposure 0.15; no executed future rollout.";
        return new Selection(best,List.copyOf(scores),explanation);
    }
    private List<ScoredAlternative> descriptions(State observed,List<Action> candidates){return candidates.stream().map(a->new ScoredAlternative(a,true,a.type()==ActionType.NONE?1:0,null,counterfactual.validate(observed,a))).toList();}
    private static Action noAction(List<Action> actions){return actions.stream().filter(a->a.type()==ActionType.NONE).findFirst().orElseThrow();}
    private Set<String> eligible(State s,PolicySpec policy,CascadeView risk){
        Set<String> result=new TreeSet<>();for(Truck t:s.trucks)if(!t.affectedIncidentIds.isEmpty()&&!"ARRIVED".equals(t.status))result.add(t.id);
        if(policy.id().startsWith("B4"))for(String id:risk.affectedNodeIds())if(id.startsWith("TRUCK:")){
            String truck=id.substring(6);Assignment a=OperationalRuntime.assignment(s,truck);if(a==null||!List.of("COMPLETED","UNLOADING").contains(a.status))result.add(truck);
        }
        return result;
    }
    /** Planning ablations alter only the copy used for risk/candidate eligibility, never physical constraints. */
    public CascadeView policyRisk(State input,PolicySpec policy){
        State s=counterfactual.observedClone(input);GraphView graph=s.operations.graph;
        if(!policy.temporalDependencies()){
            s.operations.predictedImpacts=new ArrayList<>(s.operations.predictedImpacts.stream().filter(i->i.startSec()<=s.clockSec+1e-8).toList());
            GraphView built=new OperationalDependencyGraph().build(s);
            graph=new GraphView(built.schemaVersion(),built.clockSec(),built.networkId(),built.nodes(),built.edges().stream().filter(e->e.validFromSec()<=s.clockSec+1e-8&&e.validUntilSec()>s.clockSec).toList(),built.provenance());
        }
        CascadeView risk=new GraphRiskBaseline().predict(s,graph);if(policy.adaptiveThreshold())return risk;
        double threshold=.35;List<String> affected=risk.nodeRisks().stream().filter(n->n.score()>=threshold).map(NodeRisk::nodeId).toList();Set<String> nodes=new HashSet<>(affected);
        List<String> edges=graph.edges().stream().filter(e->e.validUntilSec()>s.clockSec&&nodes.contains(e.source())&&nodes.contains(e.target())).map(GraphEdge::id).toList();
        return new CascadeView(risk.provider()+"_FIXED_THRESHOLD",threshold,risk.iterations(),risk.nodeRisks(),affected,edges,risk.provenance());
    }
    private static String signature(State s,Truck t,CascadeView risk){
        SortedSet<String> causes=new TreeSet<>(t.affectedIncidentIds);
        for(NodeRisk node:risk.nodeRisks())if(node.nodeId().equals("TRUCK:"+t.id)&&node.score()>=risk.threshold())causes.addAll(node.causeIds());
        for(Impact i:s.operations.predictedImpacts)if(i.truckIds().contains(t.id)&&!i.code().equals("DELIVERY_ETA_UNKNOWN"))causes.add(i.id());
        return String.join("|",causes);
    }
    private void inject(SimulationEngine e,ScheduledCommand command){
        switch(command.kind()){
            case "INCIDENT_ADD" -> {Map<String,Object> p=command.payload();e.addIncident(new IncidentRequest((String)p.get("type"),(String)p.get("physicalId"),((Number)p.get("severity")).doubleValue(),((Number)p.get("durationSec")).doubleValue(),e.raw().clockSec));}
            case "DRIVER_AVAILABILITY" -> e.availability((String)command.payload().get("id"),(Boolean)command.payload().get("available"));
            default -> throw ApiException.invalid("Unsupported exogenous benchmark command: "+command.kind());
        }
    }
    private void collectAudit(State state,Map<String,Violation> violations){for(Violation v:counterfactual.audit(state))if(v.hard())violations.put(v.code()+"|"+String.join(",",new TreeSet<>(v.resourceIds())),v);}
    private static void validateSpec(ScenarioSpec spec,PolicySpec policy){if(spec==null||!PROVENANCE.equals(spec.provenance())||policy==null||policy.allowedActions()==null||!policy.allowedActions().contains(ActionType.NONE))throw ApiException.invalid("A simulated scenario and bounded policy with no-intervention alternative are required");}
}
