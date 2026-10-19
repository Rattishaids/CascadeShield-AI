package io.cascadeshield.sim;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.*;

public final class Models {
    private Models() {}
    public record Point(double longitude,double latitude) { public List<Double> coordinates(){return List.of(longitude,latitude);} }
    public record TruckSpec(String id,String name,Point start,Point destination,List<Point> waypoints,
                            double maxSpeedKph,double capacityKg,double loadKg,String driverName,
                            String priority,double departureSec,double deadlineSec) {}
    public record RouteRequest(Point start,Point destination,List<Point> waypoints,double maxSpeedKph) {}
    public record ControlRequest(String action,Double speed,Double stepSec) {}
    public record IncidentRequest(String type,String physicalId,double severity,double durationSec,Double startSec) {}
    public record DecisionRequest(String truckId,String action,String recommendationId) {}
    public record ScenarioRequest(String name) {}
    @JsonIgnoreProperties(ignoreUnknown=true)
    public record Node(long id,double longitude,double latitude) { public Point point(){return new Point(longitude,latitude);} }
    @JsonIgnoreProperties(ignoreUnknown=true)
    public record Edge(String id,String physicalId,long from,long to,long wayId,double lengthM,
                       double speedKph,String speedSource,String highway,String name,
                       List<List<Double>> geometry,Map<String,Object> tags) {}
    @JsonIgnoreProperties(ignoreUnknown=true)
    public record Restriction(long fromWay,long viaNode,long toWay,String type) {}
    @JsonIgnoreProperties(ignoreUnknown=true)
    public record NetworkFile(String networkId,String name,List<Double> bbox,List<Node> nodes,
                              List<Edge> edges,List<Restriction> restrictions,Map<String,Object> metadata) {}
    public record Route(List<String> edgeIds,List<List<Double>> geometry,double distanceM,
                        double baseTravelSec,Point snappedStart,Point snappedDestination) {}
    public record Risk(double score,String level,String source) {}
    public record Option(String action,boolean feasible,double addedTravelSec,double estimatedArrivalSec,
                         double totalDistanceM,double additionalDistanceM,String explanation) {}
    public record Recommendation(String id,String truckId,List<String> incidentIds,String riskSource,
                                 double beforeRisk,double afterRisk,String reason,List<Option> options,
                                 String recommendedAction) {}
    public record Event(long id,double clockSec,String type,String message,String truckId,Map<String,Object> details) {}
    public record Kpis(int totalTrucks,int arrived,int lateDeliveries,double totalDelaySec,double distanceTravelledM,
                       int reroutes,int waitingTrucks,int activeIncidents,int completedTrips) {}
    public record ScheduledCommand(double clockSec,long sequence,String kind,Map<String,Object> payload) {}
    public static class Truck {
        public String id,name,driverName,priority,status="SCHEDULED";
        public Point start,destination;
        public List<Point> waypoints=new ArrayList<>();
        public double capacityKg,loadKg,maxSpeedKph,deadlineSec,departureSec;
        public long startNode,destinationNode,incomingWay;
        public Route route;
        public List<Double> position;
        public int edgeIndex=0;
        public double offsetM=0,speedKph=0,distanceTravelledM=0,remainingDistanceM=0,etaSec=0;
        public double baselineArrivalSec=0,arrivalSec=-1,waitUntilSec=0;
        public int reroutes=0;
        public boolean etaKnown=true;
        public Risk risk=new Risk(0,"LOW","RULE_BASED");
        public List<String> affectedIncidentIds=new ArrayList<>();
        public List<String> encounteredIncidentIds=new ArrayList<>();
        public List<String> approvedWaitIncidentIds=new ArrayList<>();
        public TruckSpec initialAssignment;
        public List<Long> remainingStops=new ArrayList<>();
    }
    public static class Incident {
        public String id,type,physicalId,status;
        public double severity,startSec,endSec;
        public List<Double> position;
    }
    public static class State {
        public String status="DRAFT",networkId,scenarioName="Untitled Chennai scenario";
        public String initialClockIso="2026-10-09T09:00:00+05:30";
        public UUID runId=UUID.randomUUID();
        public UUID scenarioId;
        public long randomSeed=0;
        public OpsModels.Operations operations=new OpsModels.Operations();
        public OpsModels.Configuration initialOperations;
        public double clockSec=0,speed=1;
        public long nextSequence=0,nextIncidentId=1;
        public List<Truck> trucks=new ArrayList<>();
        public List<Incident> incidents=new ArrayList<>();
        public List<Recommendation> recommendations=new ArrayList<>();
        public List<Event> events=new ArrayList<>();
        public List<ScheduledCommand> commandHistory=new ArrayList<>(),replaySchedule=new ArrayList<>();
        public int replayCursor=0;
        public boolean replaying=false;
        public Kpis kpis=new Kpis(0,0,0,0,0,0,0,0,0);
        public String operationsProvenance="SIMULATED";
        public String riskSource="RULE_BASED — uncalibrated direct-travel estimate";
    }
}
