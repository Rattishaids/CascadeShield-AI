package io.cascadeshield.sim;

import java.util.*;
import static io.cascadeshield.sim.Models.*;

/** Piecewise known-schedule travel calculation; risk is an uncalibrated bounded rule score. */
public final class RuleBasedPredictionService implements PredictionService {
    private final RoadGraph graph;
    public RuleBasedPredictionService(RoadGraph graph){this.graph=graph;}
    public Estimate estimate(State state,Truck truck){return estimateRoute(state,truck,truck.route.edgeIds().subList(Math.min(truck.edgeIndex,truck.route.edgeIds().size()),truck.route.edgeIds().size()),truck.offsetM,truck.waitUntilSec);}
    public Estimate estimateRoute(State state,Truck truck,List<String> ids,double offset,double requestedWaitUntil) {
        double time=Math.max(state.clockSec,truck.departureSec),distance=0;
        Set<String> affected=new TreeSet<>();
        for(int index=0;index<ids.size();index++) {
            Edge edge=graph.edge(ids.get(index));double remaining=edge.lengthM()-(index==0?offset:0);
            if(index==0&&offset<=1e-7)time=Math.max(time,requestedWaitUntil);
            double entry=time;
            double seconds=RoadGraph.traversalSeconds(edge,remaining,truck.maxSpeedKph,state.incidents,time,index==0&&offset>1e-7,true);
            time+=seconds;distance+=remaining;
            for(Incident incident:state.incidents) if(!"RESOLVED".equals(incident.status)&&incident.physicalId.equals(edge.physicalId())&&incident.startSec<time&&incident.endSec>entry)
                affected.add(incident.id);
            if(index==0&&offset>1e-7)time=Math.max(time,requestedWaitUntil);
        }
        if(ids.isEmpty())time=truck.arrivalSec>=0?truck.arrivalSec:state.clockSec;
        return new Estimate(time,distance,List.copyOf(affected));
    }
    public double baseRemaining(Truck truck) {
        double time=0;
        for(int index=truck.edgeIndex;index<truck.route.edgeIds().size();index++) {
            Edge edge=graph.edge(truck.route.edgeIds().get(index));
            time+=(edge.lengthM()-(index==truck.edgeIndex?truck.offsetM:0))/(Math.min(edge.speedKph(),truck.maxSpeedKph)/3.6);
        }
        return time;
    }
    public Risk risk(Truck truck,double arrival,double baseline,double clock) {
        double delay=Math.max(0,arrival-Math.max(clock,truck.departureSec)-baseline);
        double sla=Math.max(0,arrival-truck.deadlineSec);
        double score=Math.min(1,.6*Math.min(1,delay/600)+.4*Math.min(1,sla/600));
        if(!Double.isFinite(score))score=1;
        return new Risk(score,score>=.66?"HIGH":score>=.3?"MEDIUM":"LOW","RULE_BASED");
    }
}
