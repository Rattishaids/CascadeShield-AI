package io.cascadeshield.sim;

import java.util.*;
import org.jgrapht.Graph;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;

/** Bounded deterministic exposure ranking. Scores are never calibrated probabilities. */
public final class GraphRiskBaseline {
    public CascadeView predict(State state,GraphView view) {
        Graph<String,GraphEdge> graph=OperationalDependencyGraph.materialize(view);
        SortedMap<String,SortedMap<String,Double>> seeds=new TreeMap<>();
        SortedMap<String,Double> incidentSeverity=new TreeMap<>();
        SortedMap<String,Double> encounteredSeverity=new TreeMap<>();
        for (Incident incident : state.incidents) encounteredSeverity.put(incident.id,clamp(incident.severity));
        for (Incident incident : state.incidents) if (!"RESOLVED".equals(incident.status) && incident.endSec > state.clockSec)
            incidentSeverity.put(incident.id,clamp(incident.severity));
        SortedMap<String,Truck> trucks=new TreeMap<>();
        for (Truck t : state.trucks) trucks.put(t.id,t);
        double maxSeverity=0;
        for (Truck t : trucks.values()) for (String incidentId : new TreeSet<>(t.affectedIncidentIds)) {
            if (!incidentSeverity.containsKey(incidentId) || !graph.containsVertex("TRUCK:"+t.id)) continue;
            double severity=incidentSeverity.get(incidentId);
            maxSeverity=Math.max(maxSeverity,severity);
            seed(seeds,"INCIDENT:"+incidentId,"TRUCK:"+t.id,clamp(.65*clamp(t.risk.score())+.35*severity));
        }
        for (Impact impact : state.operations.predictedImpacts) {
            boolean unknownDriver="DRIVER_UNAVAILABLE".equals(impact.code());
            if (!impact.predicted() || impact.endSec() <= state.clockSec || (!unknownDriver && impact.delaySec() <= 0)) continue;
            SortedSet<String> causes=new TreeSet<>();
            SortedMap<String,Double> causalSeed=new TreeMap<>();
            SortedSet<String> involved=new TreeSet<>(impact.truckIds());
            for (String resource : impact.resourceIds()) if (resource.startsWith("TRUCK:")) involved.add(resource.substring(6));
            for (String truckId : involved) if (!unknownDriver) {
                Truck t=trucks.get(truckId);
                if (t != null) for (String incidentId : t.affectedIncidentIds) if (incidentSeverity.containsKey(incidentId)) causes.add("INCIDENT:"+incidentId);
            }
            // Only explicit blocker references retain physically encountered, resolved incident history.
            for (String resource : impact.resourceIds()) if (!unknownDriver && resource.startsWith("TRUCK:")) {
                Truck blocker=trucks.get(resource.substring(6));
                if (blocker == null) continue;
                for (String incidentId : new TreeSet<>(blocker.encounteredIncidentIds)) {
                    Double severity=encounteredSeverity.get(incidentId);
                    if (severity == null) continue;
                    String cause="INCIDENT:"+incidentId;
                    causes.add(cause);maxSeverity=Math.max(maxSeverity,severity);
                    double measuredDelay=blocker.arrivalSec >= 0 ? Math.max(0,blocker.arrivalSec-blocker.baselineArrivalSec)
                            : Math.max(0,blocker.etaSec-blocker.baselineArrivalSec);
                    causalSeed.merge(cause,clamp(.65*Math.min(1,measuredDelay/600)+.35*severity),Math::max);
                }
            }
            double impactScore=unknownDriver ? .80 : clamp(.20+.80*Math.min(1,Math.max(0,impact.delaySec())/600));
            if (causes.isEmpty()) causes.add("OPERATIONS:"+impact.id());
            for (String cause : causes) {
                double score=impactScore;
                if (cause.startsWith("INCIDENT:")) {
                    double largestSeed=Math.max(causalSeed.getOrDefault(cause,0d),seeds.getOrDefault(cause,new TreeMap<>()).values().stream().mapToDouble(Double::doubleValue).max().orElse(0));
                    score=Math.min(score,largestSeed);
                }
                for (String resource : new TreeSet<>(impact.resourceIds())) if (!resource.startsWith("TRUCK:") && graph.containsVertex(resource)) seed(seeds,cause,resource,score);
                // Deadline constraints have an explicit resource dependency. Other impacts use their resource->truck edge.
                if ("DELIVERY_DEADLINE".equals(impact.code())) for (String truckId : impact.truckIds())
                    if (graph.containsVertex("TRUCK:"+truckId)) seed(seeds,cause,"TRUCK:"+truckId,score);
            }
        }

        List<GraphEdge> eligible=graph.edgeSet().stream().filter(e -> e.validUntilSec() > state.clockSec)
                .sorted(Comparator.comparing(GraphEdge::id)).toList();
        SortedMap<String,SortedMap<String,Double>> byCause=new TreeMap<>();
        int maxPasses=Math.max(0,graph.vertexSet().size()-1),iterations=0;
        for (var cause : seeds.entrySet()) {
            SortedMap<String,Double> scores=new TreeMap<>(cause.getValue());
            for (int pass=0;pass<maxPasses;pass++) {
                SortedMap<String,Double> next=new TreeMap<>(scores);
                for (GraphEdge edge : eligible) {
                    double candidate=scores.getOrDefault(edge.source(),0d)*graph.getEdgeWeight(edge);
                    if (candidate > next.getOrDefault(edge.target(),0d)) next.put(edge.target(),candidate);
                }
                iterations=Math.max(iterations,pass+1);
                if (next.equals(scores)) break;
                scores=next;
            }
            byCause.put(cause.getKey(),scores);
        }
        double threshold=Math.max(.15,Math.min(.35,.35-.20*maxSeverity));
        List<NodeRisk> risks=new ArrayList<>();
        for (String node : new TreeSet<>(graph.vertexSet())) {
            double remaining=1;
            List<String> causes=new ArrayList<>();
            boolean direct=false;
            for (var cause : byCause.entrySet()) {
                double score=clamp(cause.getValue().getOrDefault(node,0d));
                if (score <= 0) continue;
                remaining*=1-score;
                causes.add(cause.getKey());
                direct|=seeds.get(cause.getKey()).getOrDefault(node,0d)>0;
            }
            risks.add(new NodeRisk(node,clamp(1-remaining),direct,List.copyOf(causes)));
        }
        List<String> affected=risks.stream().filter(r -> r.score() >= threshold).map(NodeRisk::nodeId).toList();
        Set<String> affectedSet=new HashSet<>(affected);
        List<String> affectedEdges=eligible.stream().filter(e -> affectedSet.contains(e.source()) && affectedSet.contains(e.target())).map(GraphEdge::id).toList();
        return new CascadeView("RULE_BASED_GRAPH_BASELINE",threshold,iterations,List.copyOf(risks),affected,affectedEdges,"SIMULATED_PREDICTION");
    }
    private static void seed(Map<String,SortedMap<String,Double>> seeds,String cause,String node,double score) {
        if (!Double.isFinite(score) || score <= 0) return;
        seeds.computeIfAbsent(cause,k -> new TreeMap<>()).merge(node,clamp(score),Math::max);
    }
    private static double clamp(double n) {return Double.isFinite(n) ? Math.max(0,Math.min(1,n)) : 0;}
}
