package io.cascadeshield.sim;

import java.util.*;
import static io.cascadeshield.sim.Models.*;

public final class RuleBasedPreventionService implements PreventionService {
    public record Weights(double elapsedTime,double addedDistance,double slaExposure) {
        public Weights {if(elapsedTime<0||addedDistance<0||slaExposure<0||elapsedTime+addedDistance+slaExposure<=0)throw new IllegalArgumentException("Invalid decision weights");}
    }
    public record ReroutePlan(List<String> ids,double offsetM) {}
    private final RoadGraph graph;private final RuleBasedPredictionService prediction;private final Weights weights;
    public RuleBasedPreventionService(RoadGraph graph,RuleBasedPredictionService prediction){this(graph,prediction,new Weights(.65,.2,.15));}
    public RuleBasedPreventionService(RoadGraph graph,RuleBasedPredictionService prediction,Weights weights){this.graph=graph;this.prediction=prediction;this.weights=weights;}
    public double waitUntil(State state,Truck truck) {
        double until=state.clockSec;
        for(Incident i:state.incidents)if(truck.affectedIncidentIds.contains(i.id)&&!"RESOLVED".equals(i.status))until=Math.max(until,i.endSec);
        return until;
    }
    public ReroutePlan reroute(State state,Truck truck) {
        if(truck.edgeIndex>=truck.route.edgeIds().size())return new ReroutePlan(List.of(),0);
        Edge current=graph.edge(truck.route.edgeIds().get(truck.edgeIndex));
        boolean occupied=truck.offsetM>1e-7;long start=occupied?current.to():current.from();
        // Actual movement history survives route replacement at a junction.
        long incoming=occupied?current.wayId():truck.incomingWay;
        if(incoming==0&&truck.edgeIndex>0)incoming=graph.edge(truck.route.edgeIds().get(truck.edgeIndex-1)).wayId();
        double departure=Math.max(state.clockSec,truck.departureSec);
        if(occupied)departure+=RoadGraph.traversalSeconds(current,current.lengthM()-truck.offsetM,truck.maxSpeedKph,state.incidents,departure,true,true);
        List<Long> stops=new ArrayList<>(truck.remainingStops);
        while(!stops.isEmpty()&&stops.getFirst()==start)stops.removeFirst();
        long destination=stops.isEmpty()?truck.destinationNode:stops.getLast();
        List<Long> via=stops.isEmpty()?List.of():stops.subList(0,stops.size()-1);
        Route route=graph.route(start,destination,via,truck.maxSpeedKph,state.incidents,departure,incoming);
        List<String> ids=new ArrayList<>();if(occupied)ids.add(current.id());ids.addAll(route.edgeIds());
        return new ReroutePlan(ids,occupied?truck.offsetM:0);
    }
    public Recommendation recommend(State state,Truck truck) {
        if(truck.affectedIncidentIds.isEmpty()||"ARRIVED".equals(truck.status))return null;
        double base=prediction.baseRemaining(truck);
        PredictionService.Estimate original=prediction.estimate(state,truck);
        List<String> originalIds=truck.route.edgeIds().subList(truck.edgeIndex,truck.route.edgeIds().size());
        PredictionService.Estimate wait=prediction.estimateRoute(state,truck,originalIds,truck.offsetM,waitUntil(state,truck));
        List<Option> options=new ArrayList<>();
        options.add(new Option("CONTINUE",true,0,original.arrivalSec(),original.remainingDistanceM(),0,
            "Keep the connected route. A closed segment is never entered; the truck holds at its upstream node until reopening."));
        options.add(new Option("WAIT",true,Math.max(0,wait.arrivalSec()-original.arrivalSec()),wait.arrivalSec(),wait.remainingDistanceM(),0,
            "Finish an occupied edge, then hold at the next safe graph node until the affected incident schedule ends; keep the original route."));
        try {
            ReroutePlan plan=reroute(state,truck);
            PredictionService.Estimate alternate=prediction.estimateRoute(state,truck,plan.ids(),plan.offsetM(),0);
            options.add(new Option("REROUTE",true,alternate.arrivalSec()-original.arrivalSec(),alternate.arrivalSec(),alternate.remainingDistanceM(),Math.max(0,alternate.remainingDistanceM()-original.remainingDistanceM()),
                "Turn-aware route avoids inaccessible edges. An occupied edge is retained to its end; position cannot jump."));
        }catch(ApiException exception){options.add(new Option("REROUTE",false,0,-1,original.remainingDistanceM(),0,"No feasible detour: "+exception.getMessage()));}
        double maxTime=options.stream().filter(Option::feasible).mapToDouble(o->Math.max(1,o.estimatedArrivalSec()-state.clockSec)).max().orElse(1);
        double maxDistance=options.stream().filter(Option::feasible).mapToDouble(o->Math.max(1,o.additionalDistanceM())).max().orElse(1);
        double maxSla=options.stream().filter(Option::feasible).mapToDouble(o->Math.max(1,o.estimatedArrivalSec()-truck.deadlineSec)).max().orElse(1);
        Option best=options.stream().filter(Option::feasible).min(Comparator.comparingDouble(o->
            weights.elapsedTime()*(o.estimatedArrivalSec()-state.clockSec)/maxTime+
            weights.addedDistance()*o.additionalDistanceM()/maxDistance+
            weights.slaExposure()*Math.max(0,o.estimatedArrivalSec()-truck.deadlineSec)/maxSla)).orElseThrow();
        double before=prediction.risk(truck,original.arrivalSec(),base,state.clockSec).score();
        double after=prediction.risk(truck,best.estimatedArrivalSec(),base,state.clockSec).score();
        String signature=truck.id+":"+truck.reroutes+":"+String.join(",",truck.affectedIncidentIds);
        String id=UUID.nameUUIDFromBytes(signature.getBytes(java.nio.charset.StandardCharsets.UTF_8)).toString();
        String reason=String.format(Locale.ROOT,"%s is feasible under the current road state. Estimated arrival %.1f s versus keep-route %.1f s and wait %.1f s; extra distance %.0f m. Score uses normalized time (%.2f), added distance (%.2f), and SLA exposure (%.2f). Direct-travel rules only; no trained model or cascade prediction.",best.action(),best.estimatedArrivalSec(),original.arrivalSec(),wait.arrivalSec(),best.additionalDistanceM(),weights.elapsedTime(),weights.addedDistance(),weights.slaExposure());
        return new Recommendation(id,truck.id,List.copyOf(truck.affectedIncidentIds),"RULE_BASED",before,after,reason,options,best.action());
    }
}
