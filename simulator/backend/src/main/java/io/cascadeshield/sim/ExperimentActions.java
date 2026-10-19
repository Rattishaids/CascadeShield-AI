package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import static io.cascadeshield.sim.Models.*;
import static io.cascadeshield.sim.OpsModels.*;
import static io.cascadeshield.sim.BenchmarkModels.*;

/** Actions operate on an isolated authoritative engine. No unsupported transfer or queue rule. */
public final class ExperimentActions {
    private final RoadGraph roads;
    private final ObjectMapper mapper;
    private final RuleBasedPredictionService prediction;
    public ExperimentActions(RoadGraph roads,ObjectMapper mapper){this.roads=roads;this.mapper=mapper;prediction=new RuleBasedPredictionService(roads);}
    private static double ceil(double v){return Math.ceil(v*10-1e-8)/10d;}
    private static Action action(ActionType type,String truck,double wait,String dock,double from,double until,List<String> edges,String why){String key=type+":"+truck+":"+wait+":"+dock+":"+from+":"+until+":"+edges;return new Action(UUID.nameUUIDFromBytes(key.getBytes(java.nio.charset.StandardCharsets.UTF_8)).toString(),type,truck,wait,dock,from,until,List.copyOf(edges),why);}
    public List<Action> candidates(State s,String truckId) {
        Truck t=OperationalRuntime.truck(s,truckId);List<Action> out=new ArrayList<>();
        out.add(action(ActionType.NONE,t.id,0,null,0,0,List.of(),"Keep the current plan and execute actual constraints."));
        if(!"ARRIVED".equals(t.status)) {
            out.add(action(ActionType.CONTINUE,t.id,0,null,0,0,List.of(),"Clear an approved wait and continue the current connected road plan."));
            double until=s.incidents.stream().filter(i->RoadGraph.active(i,s.clockSec)&&t.affectedIncidentIds.contains(i.id)).mapToDouble(i->i.endSec).max().orElse(s.clockSec);
            if(until>s.clockSec+.05)out.add(action(ActionType.WAIT,t.id,ceil(until-s.clockSec),null,0,0,List.of(),"Wait at the next safe road node until the observed incident duration expires."));
            try{List<String> route=global(s,t);if(changed(t,route))out.add(action(ActionType.GLOBAL_REROUTE,t.id,0,null,0,0,route,"Recalculate the whole remaining route using observed incidents and legal turns."));}catch(ApiException ignored){}
            try{List<String> route=local(s,t);if(changed(t,route))out.add(action(ActionType.LOCAL_REROUTE,t.id,0,null,0,0,route,"Repair the first observed affected segment; retain the legal prefix and suffix."));}catch(ApiException ignored){}
        }
        Assignment a=OperationalRuntime.assignment(s,t.id);
        if(a!=null&&!List.of("UNLOADING","COMPLETED").contains(a.status)&&t.etaKnown) {
            Dock old=OperationalRuntime.dock(s,a.dockId);
            for(Dock d:s.operations.docks.stream().filter(d->d.warehouseId.equals(old.warehouseId)).sorted(Comparator.comparing(d->d.id)).toList()) {
                double ready=ceil(Math.max(s.clockSec,Math.max(d.openFromSec,t.arrivalSec>=0?t.arrivalSec:t.etaSec)));
                if(d.occupiedBy!=null&&!d.occupiedBy.equals(t.id)){Assignment occupied=OperationalRuntime.assignment(s,d.occupiedBy);ready=Math.max(ready,occupied.actualDockEndSec);}
                for(int guard=0;guard<s.operations.assignments.size()+1;guard++) {
                    double end=ceil(ready+d.serviceSec);double shift=ready;
                    for(Assignment other:s.operations.assignments)if(!other.truckId.equals(t.id)&&other.dockId.equals(d.id)&&!"COMPLETED".equals(other.status)&&Math.max(ready,other.reservationStartSec)<Math.min(end,other.reservationEndSec)-1e-7)shift=Math.max(shift,other.reservationEndSec);
                    if(shift<=ready+1e-7)break;ready=ceil(shift);
                }
                double end=ceil(ready+d.serviceSec);
                if(end<=d.openUntilSec+1e-7&&(!d.id.equals(a.dockId)||Math.abs(ready-a.reservationStartSec)>.05))out.add(action(ActionType.ADJUST_DOCK_RESERVATION,t.id,0,d.id,ready,end,List.of(),"Move the reservation to a feasible interval at the same warehouse; service follows the actual dock runtime."));
            }
        }
        return out.stream().filter(a2->validate(s,a2).stream().noneMatch(Violation::hard)).toList();
    }
    private boolean changed(Truck t,List<String> ids){return !ids.equals(t.route.edgeIds().subList(Math.min(t.edgeIndex,t.route.edgeIds().size()),t.route.edgeIds().size()));}
    private List<Long> remainingStops(Truck t,long start){List<Long> stops=new ArrayList<>(t.remainingStops);while(!stops.isEmpty()&&stops.getFirst()==start)stops.removeFirst();if(!stops.isEmpty()&&stops.getLast()==t.destinationNode)stops.removeLast();return stops;}
    public List<String> global(State s,Truck t) {
        if(t.edgeIndex>=t.route.edgeIds().size())return List.of();Edge current=roads.edge(t.route.edgeIds().get(t.edgeIndex));boolean occupied=t.offsetM>1e-7;
        long start=occupied?current.to():current.from(),incoming=occupied?current.wayId():t.incomingWay;
        double departure=Math.max(s.clockSec,t.departureSec);List<String> ids=new ArrayList<>();
        if(occupied){ids.add(current.id());departure+=RoadGraph.traversalSeconds(current,current.lengthM()-t.offsetM,t.maxSpeedKph,s.incidents,departure,true,true);}
        ids.addAll(roads.route(start,t.destinationNode,remainingStops(t,start),t.maxSpeedKph,s.incidents,departure,incoming).edgeIds());return List.copyOf(ids);
    }
    public List<String> local(State s,Truck t) {
        List<String> ids=new ArrayList<>(t.route.edgeIds().subList(Math.min(t.edgeIndex,t.route.edgeIds().size()),t.route.edgeIds().size()));
        double time=Math.max(s.clockSec,t.departureSec);long incoming=t.incomingWay;
        for(int k=0;k<ids.size();k++) {
            Edge edge=roads.edge(ids.get(k));boolean occupied=k==0&&t.offsetM>1e-7;
            double distance=edge.lengthM()-(occupied?t.offsetM:0);
            double enteredAt=time;
            boolean affected=!occupied&&s.incidents.stream().anyMatch(i->i.physicalId.equals(edge.physicalId())&&RoadGraph.active(i,enteredAt));
            if(affected) {
                List<String> repair=roads.route(edge.from(),edge.to(),t.maxSpeedKph,s.incidents,time,incoming).edgeIds();
                List<String> proposed=new ArrayList<>(ids.subList(0,k));proposed.addAll(repair);proposed.addAll(ids.subList(k+1,ids.size()));
                Action candidate=action(ActionType.LOCAL_REROUTE,t.id,0,null,0,0,proposed,"local repair");
                if(validate(s,candidate).stream().anyMatch(Violation::hard))throw ApiException.invalid("Local repair violates route/resource constraints");return proposed;
            }
            time+=RoadGraph.traversalSeconds(edge,distance,t.maxSpeedKph,s.incidents,time,occupied,true);incoming=edge.wayId();
        }
        return ids;
    }
    private static Violation v(String code,String message,String resource,boolean hard){return new Violation(code,message,List.of(resource),hard);}
    public List<Violation> validate(State s,Action a) {
        List<Violation> out=new ArrayList<>();
        if(a==null||a.type()==null)return List.of(v("ACTION_REQUIRED","A supported action is required","ACTION",true));
        Truck t;try{t=OperationalRuntime.truck(s,a.truckId());}catch(ApiException error){return List.of(v("TRUCK_REFERENCE",error.getMessage(),"TRUCK:"+a.truckId(),true));}
        if(!Double.isFinite(t.loadKg)||!Double.isFinite(t.capacityKg)||t.capacityKg<=0||t.loadKg<0||t.loadKg>t.capacityKg+1e-7)out.add(v("CAPACITY","Configured cargo exceeds capacity","TRUCK:"+t.id,true));
        Assignment assignment=OperationalRuntime.assignment(s,t.id);Driver driver=null;Dock dock=null;
        if(assignment!=null) {
            try{driver=OperationalRuntime.driver(s,assignment.driverId);dock=OperationalRuntime.dock(s,assignment.dockId);Warehouse w=OperationalRuntime.warehouse(s,dock.warehouseId);double load=0;for(String id:assignment.deliveryIds){Delivery d=OperationalRuntime.delivery(s,id);load+=d.loadKg;if(!t.id.equals(d.truckId)||!w.id.equals(d.warehouseId))out.add(v("ASSIGNMENT_CONSISTENCY","Delivery/warehouse/truck references disagree","DELIVERY:"+id,true));}if(load>t.capacityKg+1e-7||load>t.loadKg+1e-7)out.add(v("ASSIGNED_CAPACITY","Assigned cargo exceeds available cargo/capacity","TRUCK:"+t.id,true));if(w.nodeId!=t.destinationNode)out.add(v("WAREHOUSE_ENDPOINT","Warehouse differs from truck route destination","TRUCK:"+t.id,true));}catch(ApiException error){out.add(v("RESOURCE_REFERENCE",error.getMessage(),"TRUCK:"+t.id,true));}
        }
        boolean intervention=!List.of(ActionType.NONE,ActionType.CONTINUE).contains(a.type());
        if(a.type()==ActionType.WAIT&&(!Double.isFinite(a.waitSec())||a.waitSec()<.1||a.waitSec()>86400))out.add(v("WAIT_INTERVAL","Wait must be finite and between 0.1 and 86400 seconds","TRUCK:"+t.id,true));
        if(List.of(ActionType.GLOBAL_REROUTE,ActionType.LOCAL_REROUTE).contains(a.type())) {
            try {
                if("ARRIVED".equals(t.status)||a.routeEdgeIds()==null||a.routeEdgeIds().isEmpty())throw ApiException.invalid("A moving truck and nonempty route are required");
                Edge old=roads.edge(t.route.edgeIds().get(t.edgeIndex));boolean occupied=t.offsetM>1e-7;
                if(occupied&&!a.routeEdgeIds().getFirst().equals(old.id()))throw ApiException.invalid("An occupied edge must remain the first route edge");
                long current=old.from(),way=t.incomingWay;List<Long> required=new ArrayList<>(t.remainingStops);
                for(int k=0;k<a.routeEdgeIds().size();k++){Edge e=roads.edge(a.routeEdgeIds().get(k));if(e.from()!=current)throw ApiException.invalid("Route contains a disconnected edge");if(!(occupied&&k==0)&&!roads.turnAllowed(current,way,e.wayId()))throw ApiException.invalid("Route violates a turn restriction");current=e.to();way=e.wayId();while(!required.isEmpty()&&required.getFirst()==current)required.removeFirst();}
                if(current!=t.destinationNode||!required.isEmpty())throw ApiException.invalid("Route skips the destination or ordered stops");
            }catch(ApiException|IndexOutOfBoundsException error){out.add(v("CONNECTED_ROUTE",error.getMessage(),"TRUCK:"+t.id,true));}
        }
        if(a.type()==ActionType.ADJUST_DOCK_RESERVATION) {
            if(assignment==null)out.add(v("ASSIGNMENT_REQUIRED","Dock adjustment needs an existing assignment","TRUCK:"+t.id,true));
            else if(dock==null)out.add(v("DOCK_REFERENCE","Current assigned dock is unavailable","TRUCK:"+t.id,true));
            else try {
                Dock target=OperationalRuntime.dock(s,a.dockId());if(!target.warehouseId.equals(dock.warehouseId))throw ApiException.invalid("A dock change must remain at the same warehouse");
                if(List.of("UNLOADING","COMPLETED").contains(assignment.status))throw ApiException.invalid("Active/completed service cannot be moved");
                double from=a.reservationStartSec(),until=a.reservationEndSec();if(!Double.isFinite(from)||!Double.isFinite(until)||from<s.clockSec-1e-7||from<target.openFromSec-1e-7||until>target.openUntilSec+1e-7||ceil(ceil(from)+target.serviceSec)>until+1e-7)throw ApiException.invalid("Reservation must fit current time, dock hours, and tick-rounded service");
                if(target.occupiedBy!=null&&!target.occupiedBy.equals(t.id)){Assignment occupied=OperationalRuntime.assignment(s,target.occupiedBy);if(from<occupied.actualDockEndSec-1e-7)throw ApiException.invalid("Reservation overlaps occupied service");}
                for(Assignment other:s.operations.assignments)if(!other.truckId.equals(t.id)&&other.dockId.equals(target.id)&&!"COMPLETED".equals(other.status)&&Math.max(from,other.reservationStartSec)<Math.min(until,other.reservationEndSec)-1e-7)throw ApiException.invalid("Reservation overlaps another configured interval");
            }catch(ApiException error){out.add(v("DOCK_RESERVATION",error.getMessage(),"DOCK:"+a.dockId(),true));}
        }
        if(intervention&&driver!=null&&t.arrivalSec<0) {
            if(!driver.available)out.add(v("DRIVER_UNAVAILABLE","No restoration time is known; a road intervention cannot promise a feasible trip","DRIVER:"+driver.id,true));
            if(s.clockSec>=driver.shiftEndSec-1e-7)out.add(v("DRIVER_SHIFT","Driver shift has ended","DRIVER:"+driver.id,true));
        }
        if(out.stream().noneMatch(Violation::hard)&&intervention) {
            State copy=mapper.convertValue(s,State.class);applyUnchecked(copy,a);Truck changed=OperationalRuntime.truck(copy,t.id);
            double eta=prediction.estimate(copy,changed).arrivalSec();eta=new OperationalRuntime(roads,mapper).adjustEta(copy,changed,eta);
            changed.etaSec=eta;
            if(driver!=null&&t.arrivalSec<0&&(!changed.etaKnown||eta>driver.shiftEndSec+1e-7))out.add(v("DRIVER_SHIFT","Action cannot finish the road trip inside the known driver duty window","DRIVER:"+driver.id,true));
            for(Impact impact:OperationalRuntime.forecast(copy,Map.of()))if(impact.truckIds().contains(t.id)&&impact.code().equals("DELIVERY_DEADLINE"))out.add(new Violation("SLA_DEADLINE",impact.message(),impact.resourceIds(),false));
        }
        return List.copyOf(out);
    }
    private void applyUnchecked(State s,Action a) {
        Truck t=OperationalRuntime.truck(s,a.truckId());
        switch(a.type()) {
            case NONE -> {}
            case CONTINUE -> {t.waitUntilSec=s.clockSec;t.approvedWaitIncidentIds.clear();}
            case WAIT -> {t.waitUntilSec=ceil(s.clockSec+a.waitSec());t.approvedWaitIncidentIds.clear();}
            case GLOBAL_REROUTE,LOCAL_REROUTE -> {t.route=roads.describe(a.routeEdgeIds(),new Point(t.position.get(0),t.position.get(1)),t.destination,t.maxSpeedKph);t.edgeIndex=0;t.reroutes++;t.waitUntilSec=s.clockSec;t.approvedWaitIncidentIds.clear();}
            case ADJUST_DOCK_RESERVATION -> {Assignment assignment=OperationalRuntime.assignment(s,t.id);assignment.dockId=a.dockId();assignment.reservationStartSec=a.reservationStartSec();assignment.reservationEndSec=a.reservationEndSec();}
        }
    }
    public void apply(SimulationEngine engine,Action a) {
        List<Violation> errors=validate(engine.raw(),a);if(errors.stream().anyMatch(Violation::hard))throw ApiException.invalid("Infeasible experiment action: "+errors);
        applyUnchecked(engine.raw(),a);engine.refresh(true);
    }
    /** Measured invariants of a physical engine state, separate from rejected proposals. */
    public List<Violation> audit(State s) {
        List<Violation> out=new ArrayList<>();
        Set<String> truckIds=new HashSet<>(),assignedDeliveries=new HashSet<>(),assignedTrucks=new HashSet<>();
        for(Truck t:s.trucks) {
            if(!truckIds.add(t.id))out.add(v("AUDIT_DUPLICATE_TRUCK","Truck ID is duplicated","TRUCK:"+t.id,true));
            if(!Double.isFinite(t.capacityKg)||t.capacityKg<=0||!Double.isFinite(t.loadKg)||t.loadKg<0||t.loadKg>t.capacityKg+1e-7)out.add(v("AUDIT_CAPACITY","Physical truck cargo/capacity is invalid","TRUCK:"+t.id,true));
            try {
                if(t.route==null||t.route.edgeIds()==null||t.route.edgeIds().isEmpty())throw ApiException.invalid("Truck has no connected route");
                long current=roads.edge(t.route.edgeIds().getFirst()).from(),way=0;
                for(String id:t.route.edgeIds()){Edge e=roads.edge(id);if(e.from()!=current||!roads.turnAllowed(current,way,e.wayId()))throw ApiException.invalid("Stored route is disconnected or violates a turn restriction");current=e.to();way=e.wayId();}
                if(current!=t.destinationNode)throw ApiException.invalid("Route endpoint differs from truck destination");
                if(t.edgeIndex<0||t.edgeIndex>t.route.edgeIds().size()||!Double.isFinite(t.offsetM)||t.offsetM<0)throw ApiException.invalid("Route progress is outside its bounds");
                List<Double> expected;
                if(t.edgeIndex==t.route.edgeIds().size()) {if(Math.abs(t.offsetM)>1e-7)throw ApiException.invalid("Completed route has a nonzero offset");expected=roads.node(t.destinationNode).point().coordinates();}
                else {Edge e=roads.edge(t.route.edgeIds().get(t.edgeIndex));if(t.offsetM>e.lengthM()+1e-7)throw ApiException.invalid("Truck offset exceeds its road edge");if(t.offsetM<=1e-7&&!roads.turnAllowed(e.from(),t.incomingWay,e.wayId()))throw ApiException.invalid("Next edge violates actual incoming-way history");expected=roads.position(e,t.offsetM);}
                if(t.position==null||t.position.size()!=2||t.position.get(0)==null||t.position.get(1)==null||!Double.isFinite(t.position.get(0))||!Double.isFinite(t.position.get(1))||RoadGraph.distance(new Point(t.position.get(0),t.position.get(1)),new Point(expected.get(0),expected.get(1)))>.05)out.add(v("AUDIT_POSITION","Physical truck position differs from its route progress","TRUCK:"+t.id,true));
            }catch(ApiException|IndexOutOfBoundsException error){out.add(v("AUDIT_ROUTE",error.getMessage(),"TRUCK:"+t.id,true));}
        }
        for(Assignment a:s.operations.assignments) {
            if(!assignedTrucks.add(a.truckId))out.add(v("AUDIT_DUPLICATE_ASSIGNMENT","Truck has multiple operational assignments","TRUCK:"+a.truckId,true));
            try {
                Truck t=OperationalRuntime.truck(s,a.truckId);Driver driver=OperationalRuntime.driver(s,a.driverId);Dock d=OperationalRuntime.dock(s,a.dockId);Warehouse w=OperationalRuntime.warehouse(s,d.warehouseId);double load=0;
                if(w.nodeId!=t.destinationNode)out.add(v("AUDIT_WAREHOUSE_ENDPOINT","Assigned warehouse differs from actual truck endpoint","TRUCK:"+t.id,true));
                if(a.deliveryIds==null||a.deliveryIds.isEmpty())out.add(v("AUDIT_EMPTY_ASSIGNMENT","Assignment has no deliveries","TRUCK:"+t.id,true));
                else for(String id:a.deliveryIds){Delivery delivery=OperationalRuntime.delivery(s,id);load+=delivery.loadKg;if(!assignedDeliveries.add(id))out.add(v("AUDIT_DUPLICATE_DELIVERY","Delivery appears in multiple assignments","DELIVERY:"+id,true));if(!t.id.equals(delivery.truckId)||!w.id.equals(delivery.warehouseId))out.add(v("AUDIT_DELIVERY_REFERENCE","Delivery, truck and warehouse ownership disagree","DELIVERY:"+id,true));if(!Double.isFinite(delivery.loadKg)||delivery.loadKg<0)out.add(v("AUDIT_DELIVERY_LOAD","Delivery cargo is invalid","DELIVERY:"+id,true));if("DELIVERED".equals(delivery.status)&&(!"COMPLETED".equals(a.status)||delivery.deliveredAtSec>s.clockSec+1e-7||Math.abs(delivery.deliveredAtSec-a.actualDockEndSec)>1e-7))out.add(v("AUDIT_DELIVERY_COMPLETION","Delivered label disagrees with actual completed dock service","DELIVERY:"+id,true));}
                if(load>t.capacityKg+1e-7||load>t.loadKg+1e-7)out.add(v("AUDIT_ASSIGNED_CAPACITY","Actual assigned cargo exceeds truck cargo/capacity","TRUCK:"+t.id,true));
                if(driver.occupiedBy!=null&&driver.occupiedBy.equals(t.id)&&t.arrivalSec>=0)out.add(v("AUDIT_DRIVER_OWNERSHIP","Arrived truck still occupies its road driver","DRIVER:"+driver.id,true));
                if(a.actualDockStartSec>=0) {
                    if(!Double.isFinite(a.actualDockStartSec)||!Double.isFinite(a.actualDockEndSec)||a.actualDockStartSec<d.openFromSec-1e-7||a.actualDockEndSec>d.openUntilSec+1e-7||a.actualDockEndSec-a.actualDockStartSec<d.serviceSec-1e-7)out.add(v("AUDIT_DOCK_WINDOW","Actual service interval violates dock hours or service duration","DOCK:"+d.id,true));
                    if(t.arrivalSec<0||a.actualDockStartSec<t.arrivalSec-1e-7||a.actualDockStartSec>s.clockSec+1e-7)out.add(v("AUDIT_DOCK_ARRIVAL","Actual dock service starts before physical arrival or in the future","TRUCK:"+t.id,true));
                }else if(a.actualDockEndSec>=0)out.add(v("AUDIT_DOCK_INTERVAL","Dock service end exists without an actual start","TRUCK:"+t.id,true));
            }catch(ApiException error){out.add(v("AUDIT_ASSIGNMENT_REFERENCE",error.getMessage(),"TRUCK:"+a.truckId,true));}
        }
        for(Delivery d:s.operations.deliveries)if(d.truckId!=null&&!assignedDeliveries.contains(d.id))out.add(v("AUDIT_ORPHAN_DELIVERY","Delivery owner has no corresponding assignment","DELIVERY:"+d.id,true));
        for(Driver d:s.operations.drivers)if(d.occupiedBy!=null){Assignment a=OperationalRuntime.assignment(s,d.occupiedBy);if(a==null||!d.id.equals(a.driverId)||s.trucks.stream().noneMatch(t->t.id.equals(d.occupiedBy)))out.add(v("AUDIT_DRIVER_REFERENCE","Driver ownership has no matching truck assignment","DRIVER:"+d.id,true));}
        for(Dock d:s.operations.docks) {
            List<Assignment> services=s.operations.assignments.stream().filter(a->a.dockId.equals(d.id)&&a.actualDockStartSec>=0).toList();
            for(int i=0;i<services.size();i++)for(int j=i+1;j<services.size();j++){Assignment a=services.get(i),b=services.get(j);if(Math.max(a.actualDockStartSec,b.actualDockStartSec)<Math.min(a.actualDockEndSec,b.actualDockEndSec)-1e-7)out.add(new Violation("AUDIT_DOCK_OVERLAP","Two actual service intervals overlap on one dock",List.of("DOCK:"+d.id,"TRUCK:"+a.truckId,"TRUCK:"+b.truckId),true));}
            if(d.occupiedBy!=null){Assignment occupied=OperationalRuntime.assignment(s,d.occupiedBy);if(occupied==null||!d.id.equals(occupied.dockId)||!"UNLOADING".equals(occupied.status)||occupied.actualDockStartSec<0||occupied.actualDockEndSec<=s.clockSec-1e-7)out.add(v("AUDIT_DOCK_OWNERSHIP","Occupied dock has no matching active actual service","DOCK:"+d.id,true));}
        }
        return List.copyOf(out);
    }
}
