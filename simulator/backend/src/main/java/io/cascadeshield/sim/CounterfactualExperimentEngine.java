package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.BenchmarkModels.*;

/** Executed current-knowledge alternatives, isolated from the operator engine and hidden schedule. */
public final class CounterfactualExperimentEngine {
    public static final Map<String,Double> WEIGHTS;
    static {Map<String,Double>w=new LinkedHashMap<>();w.put("sla",.35);w.put("lateness",.25);w.put("downstream",.15);w.put("cost",.15);w.put("distance",.05);w.put("recovery",.05);WEIGHTS=Collections.unmodifiableMap(w);}
    private final RoadGraph roads;
    private final ObjectMapper mapper;
    private final ExperimentActions actions;
    public CounterfactualExperimentEngine(RoadGraph roads,ObjectMapper mapper){this.roads=roads;this.mapper=mapper;actions=new ExperimentActions(roads,mapper);}
    public State observedClone(State source) {
        State copy=mapper.convertValue(source,State.class);
        copy.replaying=false;copy.replayCursor=0;copy.replaySchedule.clear();
        copy.commandHistory.clear();
        copy.incidents.removeIf(incident->incident.startSec>copy.clockSec+1e-8);
        copy.nextIncidentId=copy.incidents.stream().mapToLong(i->{try{return Long.parseLong(i.id.substring(1));}catch(Exception ignored){return 0;}}).max().orElse(0)+1;
        copy.events.clear();copy.recommendations.clear();copy.nextSequence=0;
        // A scenario's original configuration must not expose unannounced future driver settings.
        copy.initialOperations=null;
        copy.status="PAUSED";
        SimulationEngine observed=new SimulationEngine(roads,mapper);observed.restore(copy);observed.drainEvents();
        return observed.raw();
    }
    public String fingerprint(State state) {
        try {State copy=observedClone(state);copy.runId=null;copy.scenarioId=null;
            // Audit/event UUIDs and prior recommendations are not future knowledge or physical state.
            copy.events.clear();copy.recommendations.clear();
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(mapper.writeValueAsString(copy).getBytes(StandardCharsets.UTF_8)));
        }catch(Exception error){throw new IllegalStateException("Could not fingerprint observed state",error);}
    }
    public List<Action> actions(State source,String truckId){return actions.candidates(observedClone(source),truckId);}
    public List<Violation> validate(State source,Action action){return actions.validate(observedClone(source),action);}
    public List<Violation> audit(State source){return actions.audit(source);}
    public void apply(SimulationEngine engine,Action action){actions.apply(engine,action);}
    private static void validateHorizon(State source,double horizon){if(!Double.isFinite(horizon)||horizon<source.clockSec||horizon-source.clockSec>172800||Math.abs(horizon*10-Math.rint(horizon*10))>1e-7)throw ApiException.invalid("Counterfactual horizon must use finite 0.1-second ticks, be no earlier than the observed clock, and be within 48 hours");}
    public Rollout trial(State source,Action action,double absoluteHorizonSec) {
        validateHorizon(source,absoluteHorizonSec);
        long start=System.nanoTime();State initial=observedClone(source);String knowledge=fingerprint(initial);List<Violation> violations=actions.validate(initial,action);
        if(violations.stream().anyMatch(Violation::hard))return new Rollout(action,false,violations,null,null,System.nanoTime()-start,knowledge);
        SimulationEngine trial=new SimulationEngine(roads,mapper);trial.restore(initial);trial.drainEvents();
        Map<String,Violation> measured=new TreeMap<>();collectAudit(measured,trial.raw());actions.apply(trial,action);collectAudit(measured,trial.raw());
        while(trial.raw().clockSec<absoluteHorizonSec-1e-8&&!"COMPLETED".equals(trial.raw().status)){advanceTo(trial,Math.min(absoluteHorizonSec,Math.round((trial.raw().clockSec+10)*10)/10d));collectAudit(measured,trial.raw());}
        State outcome=trial.snapshot();int changes=action.type()==ActionType.ADJUST_DOCK_RESERVATION?1:0;
        double incidentStart=initial.incidents.stream().mapToDouble(i->i.startSec).min().orElse(initial.clockSec);
        Metrics metrics=ExperimentMetrics.measure(initial,outcome,absoluteHorizonSec,incidentStart,measured.size(),0,changes);
        metrics=ExperimentMetrics.withProvenance(metrics,"MODEL_ROLLOUT_FORECAST");
        List<Violation> all=new ArrayList<>(violations);all.addAll(measured.values());
        return new Rollout(action,measured.isEmpty(),List.copyOf(all),metrics,outcome,System.nanoTime()-start,knowledge);
    }
    private void collectAudit(Map<String,Violation> measured,State state){for(Violation violation:audit(state))if(violation.hard()){String key=violation.code()+":"+String.join(",",new TreeSet<>(violation.resourceIds()));measured.putIfAbsent(key,violation);}}
    public State runObserved(State source,double absoluteHorizonSec) {
        validateHorizon(source,absoluteHorizonSec);
        SimulationEngine engine=new SimulationEngine(roads,mapper);engine.restore(observedClone(source));advanceTo(engine,absoluteHorizonSec);return engine.snapshot();
    }
    public static void advanceTo(SimulationEngine engine,double absoluteHorizonSec) {
        long target=Math.round(absoluteHorizonSec*10),current=Math.round(engine.raw().clockSec*10);
        while(current<target&&!"COMPLETED".equals(engine.raw().status)) {
            int ticks=(int)Math.min(100,target-current);engine.advance(ticks);engine.drainEvents();current=Math.round(engine.raw().clockSec*10);
        }
    }
    private static double[] dimensions(Metrics m){return new double[]{m.slaViolationRate(),m.totalDeliveryLatenessSec(),m.downstreamAffectedResources(),m.modeledOperationalCost(),m.positiveAdditionalDistanceM(),m.recoveryTimeSec()};}
    /** Min/max normalization over feasible alternatives at this decision only; no test-set maxima. */
    public List<ScoredAlternative> score(List<Rollout> rollouts) {
        double[] min=new double[6],max=new double[6];Arrays.fill(min,Double.POSITIVE_INFINITY);Arrays.fill(max,Double.NEGATIVE_INFINITY);
        for(Rollout r:rollouts)if(r.valid()&&r.metrics()!=null){double[]d=dimensions(r.metrics());for(int k=0;k<6;k++){min[k]=Math.min(min[k],d[k]);max[k]=Math.max(max[k],d[k]);}}
        double[] weights=WEIGHTS.values().stream().mapToDouble(Double::doubleValue).toArray();List<ScoredAlternative> out=new ArrayList<>();
        for(Rollout r:rollouts) {
            double score=1;
            if(r.valid()&&r.metrics()!=null){score=2*r.metrics().unfinishedDeliveries();double[]d=dimensions(r.metrics());for(int k=0;k<6;k++)if(max[k]-min[k]>1e-9)score+=weights[k]*(d[k]-min[k])/(max[k]-min[k]);}
            out.add(new ScoredAlternative(r.action(),r.valid(),score,r.metrics(),r.violations()));
        }
        return List.copyOf(out);
    }
    public Action choose(List<Rollout> rollouts) {
        return score(rollouts).stream().filter(ScoredAlternative::feasible)
            .min(Comparator.comparingDouble(ScoredAlternative::score).thenComparingInt(r->r.action().type().ordinal()).thenComparing(r->r.action().id()))
            .map(ScoredAlternative::action).orElseThrow(()->ApiException.invalid("No feasible alternatives exist"));
    }
}
