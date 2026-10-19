package io.cascadeshield.sim;

import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;
import static io.cascadeshield.sim.BenchmarkModels.*;

/** Realized simulator outcomes. Censored deliveries count as SLA failures, never successes. */
public final class ExperimentMetrics {
    private ExperimentMetrics() {}
    public static final Map<String,Double> COST_RATES=Map.of("vehicleKm",1d,"driverDutySec",.02,"dockServiceSec",.01,"reroute",.5,"dockChange",.25);
    public static Metrics withProvenance(Metrics m,String provenance){return new Metrics(m.deliveryCount(),m.completedDeliveries(),m.unfinishedDeliveries(),m.slaViolations(),m.slaViolationRate(),m.totalDeliveryLatenessSec(),m.downstreamAffectedResources(),m.totalReroutes(),m.travelDistanceM(),m.signedAdditionalDistanceM(),m.positiveAdditionalDistanceM(),m.modeledOperationalCost(),m.recoveryTimeSec(),m.recoveryCensored(),m.finalClockSec(),m.constraintViolations(),m.decisionComputationMs(),provenance);}
    public static Metrics measure(State initial,State result,double horizon,double incidentStart,
        int hardViolations,double decisionMs,int dockChanges) {
        int count=result.operations.deliveries.size(),completed=0,violations=0;
        double lateness=0,distance=0,baseline=0,positiveDistance=0,driverSeconds=0,dockSeconds=0;
        for(Delivery d:result.operations.deliveries) {
            boolean done="DELIVERED".equals(d.status)&&d.deliveredAtSec>=0;
            if(done)completed++;
            if(!done||d.deliveredAtSec>d.deadlineSec+1e-7)violations++;
            lateness+=done?Math.max(0,d.deliveredAtSec-d.deadlineSec):Math.max(0,result.clockSec-d.deadlineSec);
        }
        // Unassigned trips still have measurable road outcomes; they are not invented deliveries.
        if(count==0)for(Truck t:result.trucks){count++;boolean done=t.arrivalSec>=0;if(done)completed++;if(!done||t.arrivalSec>t.deadlineSec+1e-7)violations++;lateness+=Math.max(0,(done?t.arrivalSec:result.clockSec)-t.deadlineSec);}
        int reroutes=0;
        for(Truck t:result.trucks) {
            Truck source=initial.trucks.stream().filter(x->x.id.equals(t.id)).findFirst().orElseThrow();
            double planned=source.distanceTravelledM+source.remainingDistanceM;
            distance+=t.distanceTravelledM;baseline+=planned;positiveDistance+=Math.max(0,t.distanceTravelledM-planned);reroutes+=t.reroutes;
            if(OperationalRuntime.assignment(result,t.id)==null)driverSeconds+=Math.max(0,(t.arrivalSec>=0?t.arrivalSec:result.clockSec)-t.departureSec);
        }
        for(Driver d:result.operations.drivers)driverSeconds+=d.dutySec;
        for(Assignment a:result.operations.assignments)if(a.actualDockStartSec>=0)dockSeconds+=Math.max(0,Math.min(a.actualDockEndSec,result.clockSec)-a.actualDockStartSec);
        Set<String> direct=new HashSet<>();for(Truck t:result.trucks)if(!t.encounteredIncidentIds.isEmpty())direct.add(t.id);
        Set<String> downstream=new TreeSet<>();
        for(Impact impact:result.operations.realizedImpacts) {
            if(!List.of("DOCK_QUEUE","DOCK_CLOSED","DELIVERY_LATE","DRIVER_BUSY").contains(impact.code()))continue;
            if(impact.truckIds().stream().allMatch(direct::contains))continue;
            for(String id:impact.resourceIds())if(!id.startsWith("TRUCK:")||!direct.contains(id.substring(6)))downstream.add(id);
        }
        boolean censored=completed<count;
        double recovery=Math.max(0,(censored?horizon:result.clockSec)-Math.max(0,incidentStart));
        double cost=distance/1000+.02*driverSeconds+.01*dockSeconds+.5*reroutes+.25*dockChanges;
        return new Metrics(count,completed,count-completed,violations,count==0?0:(double)violations/count,
            lateness,downstream.size(),reroutes,distance,distance-baseline,positiveDistance,cost,
            recovery,censored,result.clockSec,hardViolations,decisionMs,PROVENANCE);
    }
}
