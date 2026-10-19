package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;

/** Deterministic simulated resources. Road arrival and completed dock delivery are separate. */
public final class OperationalRuntime {
    @FunctionalInterface public interface Log {void write(double time,String type,String message,String truck,Map<String,Object> details);}
    private final RoadGraph roads;
    private final ObjectMapper mapper;
    private final RuleBasedPredictionService prediction;
    public OperationalRuntime(RoadGraph roads,ObjectMapper mapper){this.roads=roads;this.mapper=mapper;this.prediction=new RuleBasedPredictionService(roads);}
    private static void id(String value){if(value==null||!value.matches("[A-Za-z0-9_-]{1,32}"))throw ApiException.invalid("Resource ID must contain 1–32 letters, digits, underscores or hyphens");}
    private static String name(String name,String id){return name==null||name.isBlank()?id:name.substring(0,Math.min(100,name.length()));}
    private static void window(double from,double until){if(!Double.isFinite(from)||!Double.isFinite(until)||from<0||until<=from||until>172800)throw ApiException.invalid("Resource windows must be finite, ordered seconds between 0 and 172800");}
    private static <T> T find(List<T> list,String id,java.util.function.Function<T,String> key,String type){if(id==null||id.isBlank())throw ApiException.invalid(type+" ID is required");return list.stream().filter(x->id.equals(key.apply(x))).findFirst().orElseThrow(()->new ApiException(404,type+" not found: "+id));}
    public static Truck truck(State s,String id){return find(s.trucks,id,t->t.id,"Truck");}
    public static Driver driver(State s,String id){return find(s.operations.drivers,id,d->d.id,"Driver");}
    public static Dock dock(State s,String id){return find(s.operations.docks,id,d->d.id,"Dock");}
    public static Warehouse warehouse(State s,String id){return find(s.operations.warehouses,id,w->w.id,"Warehouse");}
    public static Delivery delivery(State s,String id){return find(s.operations.deliveries,id,d->d.id,"Delivery");}
    public static Assignment assignment(State s,String truckId){return s.operations.assignments.stream().filter(a->a.truckId.equals(truckId)).findFirst().orElse(null);}
    private static boolean overlaps(double a,double b,double c,double d){return Math.max(a,c)<Math.min(b,d)-1e-7;}
    private static double ceilTick(double time){return Math.ceil(time*10-1e-8)/10d;}
    private static void reservation(Dock d,double from,double until){window(from,until);if(from<d.openFromSec||until>d.openUntilSec||ceilTick(ceilTick(from)+d.serviceSec)>until+1e-7)throw ApiException.invalid("Reservation must fit dock hours and its tick-rounded service duration");}

    public void upsert(State s,String kind,Object body,boolean create) {
        if(s.operations.warehouses.size()+s.operations.docks.size()+s.operations.drivers.size()+s.operations.deliveries.size()>=300&&create)throw ApiException.invalid("The bounded demonstration supports 300 operational resources");
        switch(kind) {
            case "warehouses" -> {WarehouseSpec spec=mapper.convertValue(body,WarehouseSpec.class);id(spec.id());if(spec.dockCapacity()<1||spec.dockCapacity()>20)throw ApiException.invalid("Warehouse dock capacity must be 1–20");long node=roads.snap(spec.location());Warehouse w=new Warehouse();w.id=spec.id();w.name=name(spec.name(),w.id);w.location=roads.node(node).point();w.nodeId=node;w.dockCapacity=spec.dockCapacity();
                if(!create){Warehouse old=warehouse(s,w.id);if(s.operations.assignments.stream().anyMatch(a->dock(s,a.dockId).warehouseId.equals(w.id))&&old.nodeId!=node)throw ApiException.conflict("Unassign warehouse deliveries before changing facility location");if(s.operations.docks.stream().filter(d->d.warehouseId.equals(w.id)).count()>w.dockCapacity)throw ApiException.invalid("Capacity is smaller than configured dock count");}put(s.operations.warehouses,w,x->x.id,create);}
            case "docks" -> {DockSpec spec=mapper.convertValue(body,DockSpec.class);id(spec.id());window(spec.openFromSec(),spec.openUntilSec());if(!Double.isFinite(spec.serviceSec())||spec.serviceSec()<.1||spec.serviceSec()>86400)throw ApiException.invalid("Dock service must be 0.1–86400 seconds");Warehouse w=warehouse(s,spec.warehouseId());long count=s.operations.docks.stream().filter(d->d.warehouseId.equals(w.id)&&!d.id.equals(spec.id())).count();if(count>=w.dockCapacity)throw ApiException.invalid("Warehouse dock capacity is exhausted");
                if(!create&&s.operations.assignments.stream().anyMatch(a->a.dockId.equals(spec.id()))&&!dock(s,spec.id()).warehouseId.equals(w.id))throw ApiException.conflict("Unassign dock before changing warehouse");Dock d=new Dock();d.id=spec.id();d.name=name(spec.name(),d.id);d.warehouseId=w.id;d.serviceSec=spec.serviceSec();d.openFromSec=spec.openFromSec();d.openUntilSec=spec.openUntilSec();if(!create)for(Assignment assigned:s.operations.assignments)if(assigned.dockId.equals(d.id))reservation(d,assigned.reservationStartSec,assigned.reservationEndSec);put(s.operations.docks,d,x->x.id,create);}
            case "drivers" -> {DriverSpec spec=mapper.convertValue(body,DriverSpec.class);id(spec.id());window(spec.shiftStartSec(),spec.shiftEndSec());Driver d=new Driver();d.id=spec.id();d.name=name(spec.name(),d.id);d.available=spec.available();d.shiftStartSec=spec.shiftStartSec();d.shiftEndSec=spec.shiftEndSec();for(Assignment a:s.operations.assignments)if(a.driverId.equals(d.id)){Truck t=truck(s,a.truckId);if(t.departureSec<d.shiftStartSec||t.baselineArrivalSec>d.shiftEndSec)throw ApiException.invalid("Shift does not contain an assigned baseline trip");}put(s.operations.drivers,d,x->x.id,create);}
            case "deliveries" -> {DeliverySpec spec=mapper.convertValue(body,DeliverySpec.class);id(spec.id());warehouse(s,spec.warehouseId());if(!Double.isFinite(spec.loadKg())||spec.loadKg()<0||!Double.isFinite(spec.deadlineSec())||spec.deadlineSec()<=0||spec.deadlineSec()>172800||spec.priority()==null||!List.of("NORMAL","HIGH").contains(spec.priority()))throw ApiException.invalid("Delivery load/deadline/priority is invalid");Delivery d=new Delivery();d.id=spec.id();d.name=name(spec.name(),d.id);d.warehouseId=spec.warehouseId();d.loadKg=spec.loadKg();d.deadlineSec=spec.deadlineSec();d.priority=spec.priority();if(!create){Delivery old=delivery(s,d.id);if(old.truckId!=null)throw ApiException.conflict("Unassign delivery before editing it");}put(s.operations.deliveries,d,x->x.id,create);}
            default -> throw ApiException.invalid("Unknown resource type");
        }
    }
    private static <T> void put(List<T> list,T item,java.util.function.Function<T,String> key,boolean create){String id=key.apply(item);int index=-1;for(int n=0;n<list.size();n++)if(id.equals(key.apply(list.get(n))))index=n;if(create&&index>=0)throw ApiException.conflict("Resource ID already exists");if(!create&&index<0)throw new ApiException(404,"Resource not found");if(index>=0)list.set(index,item);else list.add(item);}
    public void remove(State s,String kind,String id) {
        switch(kind){
            case "warehouses" -> {Warehouse w=warehouse(s,id);if(s.operations.docks.stream().anyMatch(d->d.warehouseId.equals(id))||s.operations.deliveries.stream().anyMatch(d->d.warehouseId.equals(id)))throw ApiException.conflict("Remove dependent docks/deliveries first");s.operations.warehouses.remove(w);}
            case "docks" -> {Dock d=dock(s,id);if(s.operations.assignments.stream().anyMatch(a->a.dockId.equals(id)))throw ApiException.conflict("Unassign dock first");s.operations.docks.remove(d);}
            case "drivers" -> {Driver d=driver(s,id);if(s.operations.assignments.stream().anyMatch(a->a.driverId.equals(id)))throw ApiException.conflict("Unassign driver first");s.operations.drivers.remove(d);}
            case "deliveries" -> {Delivery d=delivery(s,id);if(d.truckId!=null)throw ApiException.conflict("Unassign delivery first");s.operations.deliveries.remove(d);}
            default -> throw ApiException.invalid("Unknown resource type");
        }
    }
    public void assign(State s,AssignmentSpec spec) {
        Truck t=truck(s,spec.truckId());Driver driver=driver(s,spec.driverId());Dock dock=dock(s,spec.dockId());Warehouse warehouse=warehouse(s,dock.warehouseId);window(spec.reservationStartSec(),spec.reservationEndSec());
        reservation(dock,spec.reservationStartSec(),spec.reservationEndSec());
        if(t.departureSec<driver.shiftStartSec-1e-7||t.baselineArrivalSec>driver.shiftEndSec+1e-7)throw ApiException.invalid("Driver shift must contain the initial trip");
        if(t.destinationNode!=warehouse.nodeId)throw ApiException.invalid("Truck destination and warehouse must snap to the same real road node");
        if(spec.deliveryIds()==null||spec.deliveryIds().isEmpty()||spec.deliveryIds().size()>20||new HashSet<>(spec.deliveryIds()).size()!=spec.deliveryIds().size())throw ApiException.invalid("Assign 1–20 distinct deliveries");
        double load=0;for(String id:spec.deliveryIds()){Delivery d=delivery(s,id);if(!warehouse.id.equals(d.warehouseId))throw ApiException.invalid("All deliveries must use the reserved dock's warehouse");if(d.truckId!=null&&!d.truckId.equals(t.id))throw ApiException.conflict("Delivery already belongs to another truck");load+=d.loadKg;}
        if(load>t.capacityKg+1e-7||load>t.loadKg+1e-7)throw ApiException.invalid("Assigned delivery load exceeds vehicle capacity or configured cargo");
        List<Truck> chain=new ArrayList<>();for(Assignment other:s.operations.assignments)if(!other.truckId.equals(t.id)&&other.driverId.equals(driver.id)){Truck o=truck(s,other.truckId);if(overlaps(t.departureSec,t.baselineArrivalSec,o.departureSec,o.baselineArrivalSec))throw ApiException.conflict("Driver has overlapping baseline trips");chain.add(o);}
        chain.add(t);chain.sort(Comparator.comparingDouble((Truck trip)->trip.departureSec).thenComparing(trip->trip.id));for(int i=1;i<chain.size();i++)if(chain.get(i-1).destinationNode!=chain.get(i).startNode)throw ApiException.invalid("Consecutive trips sharing a driver must meet at the same real graph node; driver transfers are not modeled");
        unassign(s,t.id);Assignment a=new Assignment();a.truckId=t.id;a.driverId=driver.id;a.dockId=dock.id;a.deliveryIds=new ArrayList<>(spec.deliveryIds());a.reservationStartSec=spec.reservationStartSec();a.reservationEndSec=spec.reservationEndSec();s.operations.assignments.add(a);t.driverName=driver.name;
        for(String id:a.deliveryIds){Delivery d=delivery(s,id);d.truckId=t.id;d.status="ASSIGNED";}
    }
    public void unassign(State s,String truckId){Assignment a=assignment(s,truckId);if(a==null)return;for(String id:a.deliveryIds){Delivery d=delivery(s,id);d.truckId=null;d.status="UNASSIGNED";d.deliveredAtSec=-1;d.lateSec=0;}s.operations.assignments.remove(a);}
    public Configuration configuration(State s){Operations o=s.operations;return new Configuration(o.warehouses.stream().map(w->new WarehouseSpec(w.id,w.name,w.location,w.dockCapacity)).toList(),o.docks.stream().map(d->new DockSpec(d.id,d.name,d.warehouseId,d.serviceSec,d.openFromSec,d.openUntilSec)).toList(),o.drivers.stream().map(d->new DriverSpec(d.id,d.name,d.available,d.shiftStartSec,d.shiftEndSec)).toList(),o.deliveries.stream().map(d->new DeliverySpec(d.id,d.name,d.warehouseId,d.loadKg,d.deadlineSec,d.priority)).toList(),o.assignments.stream().map(a->new AssignmentSpec(a.truckId,a.driverId,a.dockId,List.copyOf(a.deliveryIds),a.reservationStartSec,a.reservationEndSec)).toList());}
    public void configure(State s,Configuration c){if(c==null)return;for(WarehouseSpec w:c.warehouses())upsert(s,"warehouses",w,true);for(DockSpec d:c.docks())upsert(s,"docks",d,true);for(DriverSpec d:c.drivers())upsert(s,"drivers",d,true);for(DeliverySpec d:c.deliveries())upsert(s,"deliveries",d,true);for(AssignmentSpec a:c.assignments())assign(s,a);}
    /** Driver ownership is acquired before edge entry. Occupied edges finish safely. */
    public String entryConstraint(State s,Truck t,Edge edge,double time){Assignment a=assignment(s,t.id);if(a==null)return null;Driver d=driver(s,a.driverId);if(!d.available)return "DRIVER_UNAVAILABLE";if(time<d.shiftStartSec-1e-8)return "SHIFT_WAIT";
        // A prior trip retains its driver even when a closure prevented its first edge entry.
        // Requiring its actual arrival prevents a driver appearing at a downstream start node.
        if(s.operations.assignments.stream().filter(other->other.driverId.equals(d.id)&&!other.truckId.equals(t.id)).map(other->truck(s,other.truckId)).anyMatch(other->other.departureSec<t.departureSec&&other.arrivalSec<0))return "DRIVER_BUSY";
        double duration=RoadGraph.traversalSeconds(edge,edge.lengthM(),t.maxSpeedKph,s.incidents,time,false,false);if(time>=d.shiftEndSec-1e-8||time+duration>d.shiftEndSec+1e-8)return "SHIFT_EXHAUSTED";if(d.occupiedBy!=null&&!d.occupiedBy.equals(t.id))return "DRIVER_BUSY";d.occupiedBy=t.id;d.status="ON_DUTY";return null;}
    public double adjustEta(State s,Truck t,double roadEta){
        Assignment a=assignment(s,t.id);t.etaKnown=true;if(a==null||"ARRIVED".equals(t.status))return roadEta;
        Driver d=driver(s,a.driverId);if(!d.available||s.clockSec>=d.shiftEndSec){t.etaKnown=false;return roadEta;}
        double originalStart=Math.max(s.clockSec,t.departureSec),ready=Math.max(originalStart,d.shiftStartSec);
        for(Assignment other:s.operations.assignments)if(other.driverId.equals(d.id)&&!other.truckId.equals(t.id)){
            Truck prior=truck(s,other.truckId);if(prior.arrivalSec>=0)continue;
            if(prior.departureSec<t.departureSec||prior.id.equals(d.occupiedBy)){
                if(!prior.etaKnown){t.etaKnown=false;return roadEta;}
                ready=Math.max(ready,prior.etaSec);
            }
        }
        double eta=roadEta;if(ready>originalStart+1e-8){PredictionService.Estimate estimate=prediction.estimateRoute(s,t,t.route.edgeIds().subList(Math.min(t.edgeIndex,t.route.edgeIds().size()),t.route.edgeIds().size()),t.offsetM,Math.max(ready,t.waitUntilSec));eta=estimate.arrivalSec();t.affectedIncidentIds=new ArrayList<>(estimate.incidentIds());}if(eta>d.shiftEndSec)t.etaKnown=false;return eta;
    }
    private static Impact impact(String code,List<String> resources,List<String> trucks,double start,double end,double delay,boolean predicted,String message){return new Impact(code+":"+String.join(",",resources)+":"+String.join(",",trucks),code,List.copyOf(resources),List.copyOf(trucks),start,Math.max(start,end),Math.max(0,delay),predicted,message,predicted?"SIMULATED_PREDICTION":"SIMULATED_OUTCOME");}
    private record Slot(Assignment assignment,double arrival,double ready,double start,double end,String blocker) {}
    private static List<Slot> slots(State s,Map<String,Double> overrides){List<Slot> result=new ArrayList<>();for(Dock d:s.operations.docks){double cursor=Math.max(s.clockSec,d.openFromSec);String prior=null;
        List<Assignment> assignments=s.operations.assignments.stream().filter(a->a.dockId.equals(d.id)&&!"COMPLETED".equals(a.status)).sorted(Comparator.<Assignment>comparingDouble(a->{Truck t=truck(s,a.truckId);return Math.max(t.arrivalSec>=0?t.arrivalSec:overrides.getOrDefault(t.id,t.etaSec),Math.max(a.reservationStartSec,d.openFromSec));}).thenComparing(a->a.truckId)).toList();
        if(d.occupiedBy!=null){Assignment active=assignment(s,d.occupiedBy);if(active!=null){cursor=Math.max(cursor,active.actualDockEndSec);prior=active.truckId;}}
        for(Assignment a:assignments){Truck t=truck(s,a.truckId);if("UNLOADING".equals(a.status)){result.add(new Slot(a,t.arrivalSec,a.actualDockStartSec,a.actualDockStartSec,a.actualDockEndSec,null));continue;}
            double arrival=t.arrivalSec>=0?t.arrivalSec:overrides.getOrDefault(t.id,t.etaSec);if(!t.etaKnown&&t.arrivalSec<0&&!overrides.containsKey(t.id)){result.add(new Slot(a,-1,-1,-1,-1,null));continue;}
            double ready=ceilTick(Math.max(Math.max(arrival,a.reservationStartSec),Math.max(s.clockSec,d.openFromSec)));double start=ceilTick(Math.max(ready,cursor)),end=ceilTick(start+d.serviceSec);result.add(new Slot(a,arrival,ready,start,end,start>ready+1e-7?prior:null));cursor=end;prior=a.truckId;}
    }return result;}
    /** Pure forecast: never changes assignments, outcomes, driver ownership or clock. */
    public static List<Impact> forecast(State s,Map<String,Double> etaOverrides){List<Impact> result=new ArrayList<>();for(Slot slot:slots(s,etaOverrides)){Assignment a=slot.assignment;Truck t=truck(s,a.truckId);Dock d=dock(s,a.dockId);Driver driver=driver(s,a.driverId);double eta=t.arrivalSec>=0?t.arrivalSec:etaOverrides.getOrDefault(t.id,t.etaSec);
        if(t.arrivalSec<0&&!driver.available)result.add(impact("DRIVER_UNAVAILABLE",List.of("DRIVER:"+driver.id),List.of(t.id),s.clockSec,driver.shiftEndSec,0,true,driver.id+" is unavailable; "+t.id+" cannot enter another road edge. Dispatch ETA is unknown."));
        if(t.arrivalSec<0&&eta>driver.shiftEndSec+1e-7)result.add(impact("SHIFT_EXCEEDED",List.of("DRIVER:"+driver.id),List.of(t.id),driver.shiftEndSec,eta,eta-driver.shiftEndSec,true,t.id+" road arrival estimate exceeds "+driver.id+" shift by "+Math.round(eta-driver.shiftEndSec)+" s; movement holds at a safe node."));
        if(slot.start<0){result.add(impact("DELIVERY_ETA_UNKNOWN",a.deliveryIds.stream().map(id->"DELIVERY:"+id).toList(),List.of(t.id),s.clockSec,s.clockSec,0,true,t.id+" delivery completion is unknown while a driver constraint prevents the trip."));continue;}
        if(slot.blocker!=null)result.add(impact("DOCK_OVERLAP",List.of("DOCK:"+d.id,"TRUCK:"+slot.blocker),List.of(t.id),slot.ready,slot.start,slot.start-slot.ready,true,slot.blocker+" occupies "+d.id+" beyond "+t.id+" ready time; projected additional dock wait "+Math.round(slot.start-slot.ready)+" s."));
        if(slot.end>d.openUntilSec+1e-7)result.add(impact("DOCK_WINDOW",List.of("DOCK:"+d.id),List.of(t.id),d.openUntilSec,slot.end,slot.end-d.openUntilSec,true,t.id+" projected service exceeds "+d.id+" opening window."));
        for(String id:a.deliveryIds){Delivery delivery=delivery(s,id);if(!"DELIVERED".equals(delivery.status)&&slot.end>delivery.deadlineSec+1e-7)result.add(impact("DELIVERY_DEADLINE",List.of("DELIVERY:"+id),List.of(t.id),delivery.deadlineSec,slot.end,slot.end-delivery.deadlineSec,true,id+" projected dock completion misses its deadline by "+Math.round(slot.end-delivery.deadlineSec)+" s."));}
    }
        for(Driver d:s.operations.drivers){List<Assignment> list=s.operations.assignments.stream().filter(a->a.driverId.equals(d.id)).sorted(Comparator.comparingDouble(a->truck(s,a.truckId).departureSec)).toList();for(int i=0;i<list.size();i++)for(int j=i+1;j<list.size();j++){Truck a=truck(s,list.get(i).truckId),b=truck(s,list.get(j).truckId);if((a.arrivalSec>=0&&a.arrivalSec<=s.clockSec)||!a.etaKnown)continue;double end=etaOverrides.getOrDefault(a.id,a.etaSec);if(end>b.departureSec+1e-7)result.add(impact("DRIVER_OVERLAP",List.of("DRIVER:"+d.id,"TRUCK:"+a.id),List.of(b.id),Math.max(s.clockSec,b.departureSec),end,end-Math.max(s.clockSec,b.departureSec),true,a.id+" may retain "+d.id+" past "+b.id+" departure."));}}
        result.sort(Comparator.comparing(Impact::id));return List.copyOf(result);
    }
    public void refresh(State s,Log log,boolean emit){Operations o=s.operations;for(Assignment a:o.assignments)if("COMPLETED".equals(a.status)){a.predictedDockStartSec=a.actualDockStartSec;a.predictedDockEndSec=a.actualDockEndSec;}for(Slot slot:slots(s,Map.of())){slot.assignment.predictedDockStartSec=slot.start;slot.assignment.predictedDockEndSec=slot.end;}
        o.predictedImpacts=new ArrayList<>(forecast(s,Map.of()));Set<String> old=new HashSet<>(o.activePredictedKeys);for(Impact impact:o.predictedImpacts)if(emit&&!old.contains(impact.id()))log.write(s.clockSec,"OPERATIONAL_PREDICTION",impact.message(),impact.truckIds().isEmpty()?null:impact.truckIds().getFirst(),Map.of("impact",impact,"provenance","SIMULATED_PREDICTION"));o.activePredictedKeys=new ArrayList<>(o.predictedImpacts.stream().map(Impact::id).toList());
        int delivered=0,late=0;double delay=0;for(Delivery d:o.deliveries){if("DELIVERED".equals(d.status)){delivered++;if(d.lateSec>1e-7)late++;delay+=d.lateSec;}}
        o.kpis=new OpsKpis(o.deliveries.size(),delivered,late,(int)o.assignments.stream().filter(a->"QUEUED".equals(a.status)).count(),(int)o.assignments.stream().filter(a->"UNLOADING".equals(a.status)).count(),(int)o.drivers.stream().filter(d->!d.available||"SHIFT_EXHAUSTED".equals(d.status)).count(),delay);
    }
    private void realized(State s,Impact impact,Log log){if(s.operations.activeRealizedKeys.contains(impact.id()))return;s.operations.activeRealizedKeys.add(impact.id());s.operations.realizedImpacts.add(impact);log.write(s.clockSec,"OPERATIONAL_OUTCOME",impact.message(),impact.truckIds().isEmpty()?null:impact.truckIds().getFirst(),Map.of("impact",impact,"provenance","SIMULATED_OUTCOME"));}
    public void tick(State s,double from,double to,Log log){Operations o=s.operations;
        for(Driver d:o.drivers){if(d.occupiedBy!=null){Truck t=truck(s,d.occupiedBy);d.dutySec+=Math.max(0,Math.min(to,t.arrivalSec>=0?t.arrivalSec:to)-from);if(t.arrivalSec>=0){d.occupiedBy=null;d.status="IDLE";}}if(!d.available)d.status="UNAVAILABLE";else if(to>=d.shiftEndSec)d.status="SHIFT_EXHAUSTED";else if(d.occupiedBy==null)d.status=to<d.shiftStartSec?"OFF_SHIFT":"IDLE";}
        for(Assignment a:o.assignments){Truck t=truck(s,a.truckId);if(List.of("DRIVER_BUSY","DRIVER_UNAVAILABLE","SHIFT_EXHAUSTED").contains(t.status))realized(s,impact(t.status,List.of("DRIVER:"+a.driverId),List.of(t.id),to,to,0,false,t.id+" held at a real graph node: "+t.status),log);}
        for(Dock d:o.docks){if(d.occupiedBy!=null){Assignment a=assignment(s,d.occupiedBy);if(to>=a.actualDockEndSec-1e-7){a.status="COMPLETED";for(String id:a.deliveryIds){Delivery delivery=delivery(s,id);delivery.status="DELIVERED";delivery.deliveredAtSec=a.actualDockEndSec;delivery.lateSec=Math.max(0,delivery.deliveredAtSec-delivery.deadlineSec);realized(s,impact(delivery.lateSec>1e-7?"DELIVERY_LATE":"DELIVERY_COMPLETED",List.of("DELIVERY:"+id,"WAREHOUSE:"+d.warehouseId),List.of(a.truckId),delivery.deliveredAtSec,delivery.deliveredAtSec,delivery.lateSec,false,id+" completed dock service at "+delivery.deliveredAtSec+" s; realized deadline lateness "+Math.round(delivery.lateSec)+" s."),log);}log.write(a.actualDockEndSec,"DOCK_RELEASED",d.id+" released by "+a.truckId,a.truckId,Map.of("dockId",d.id,"provenance","SIMULATED_OUTCOME"));d.occupiedBy=null;}}
            List<Assignment> waiting=o.assignments.stream().filter(a->a.dockId.equals(d.id)&&truck(s,a.truckId).arrivalSec>=0&&!List.of("COMPLETED","UNLOADING").contains(a.status)).sorted(Comparator.<Assignment>comparingDouble(a->Math.max(truck(s,a.truckId).arrivalSec,a.reservationStartSec)).thenComparing(a->a.truckId)).toList();
            for(Assignment a:waiting){Truck t=truck(s,a.truckId);a.status="QUEUED";a.queueSec=Math.max(0,to-t.arrivalSec);double ready=Math.max(Math.max(t.arrivalSec,a.reservationStartSec),d.openFromSec);if(d.occupiedBy==null&&to>=ready-1e-7&&ceilTick(to+d.serviceSec)<=d.openUntilSec+1e-7){a.status="UNLOADING";a.actualDockStartSec=to;a.actualDockEndSec=ceilTick(to+d.serviceSec);d.occupiedBy=a.truckId;d.status="OCCUPIED";for(String id:a.deliveryIds)delivery(s,id).status="UNLOADING";log.write(to,"DOCK_SERVICE_STARTED",a.truckId+" entered "+d.id+"; service completes at "+a.actualDockEndSec+" s",a.truckId,Map.of("dockId",d.id,"provenance","SIMULATED_OUTCOME"));}
                else if(d.occupiedBy!=null&&!d.occupiedBy.equals(t.id)&&to>=ready-1e-7)realized(s,impact("DOCK_QUEUE",List.of("DOCK:"+d.id,"TRUCK:"+d.occupiedBy),List.of(t.id),to,to,a.queueSec,false,t.id+" is physically queued at "+d.id+" behind "+d.occupiedBy),log);
                else if(to>=d.openUntilSec-1e-7)realized(s,impact("DOCK_CLOSED",List.of("DOCK:"+d.id),List.of(t.id),to,to,a.queueSec,false,t.id+" is held at closed dock "+d.id),log);
            }
            if(d.occupiedBy==null)d.status=to<d.openFromSec||to>=d.openUntilSec?"CLOSED":"AVAILABLE";
        }
    }
    public boolean complete(State s){return s.operations.assignments.stream().allMatch(a->"COMPLETED".equals(a.status));}
}
