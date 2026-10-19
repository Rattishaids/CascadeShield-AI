package io.cascadeshield.sim;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import static io.cascadeshield.sim.Models.*;

/** Directed real OSM topology. Road graph and future operational graph are distinct. */
public final class RoadGraph {
    public final NetworkFile network;
    private final Map<Long,Node> nodes=new HashMap<>();
    private final Map<String,Edge> edges=new HashMap<>();
    private final Map<Long,List<Edge>> outgoing=new HashMap<>();
    private final Map<Long,List<Restriction>> restrictions=new HashMap<>();
    public RoadGraph(NetworkFile network) {
        this.network=network;
        for(Node node:network.nodes()) nodes.put(node.id(),node);
        for(Edge edge:network.edges()) {
            if(!nodes.containsKey(edge.from())||!nodes.containsKey(edge.to())||edge.lengthM()<=0||edge.speedKph()<=0)
                throw new IllegalArgumentException("Invalid real graph edge "+edge.id());
            edges.put(edge.id(),edge);
            outgoing.computeIfAbsent(edge.from(),ignored->new ArrayList<>()).add(edge);
        }
        outgoing.values().forEach(list->list.sort(Comparator.comparing(Edge::id)));
        if(network.restrictions()!=null) for(Restriction r:network.restrictions())
            restrictions.computeIfAbsent(r.viaNode(),ignored->new ArrayList<>()).add(r);
    }
    public static RoadGraph load(Path path,ObjectMapper mapper) throws IOException {
        return new RoadGraph(mapper.readValue(path.toFile(),NetworkFile.class));
    }
    public Node node(long id) { Node n=nodes.get(id);if(n==null)throw ApiException.invalid("Unknown road node "+id);return n; }
    public Edge edge(String id) { Edge e=edges.get(id);if(e==null)throw ApiException.invalid("Unknown road edge "+id);return e; }
    public List<Edge> physicalEdges(String id) { return network.edges().stream().filter(e->e.physicalId().equals(id)).toList(); }
    public long snap(Point point) {
        if(point==null||!Double.isFinite(point.latitude())||!Double.isFinite(point.longitude())||Math.abs(point.latitude())>90||Math.abs(point.longitude())>180)
            throw ApiException.invalid("Select a valid latitude/longitude on the Chennai map.");
        double best=Double.POSITIVE_INFINITY;long result=-1;
        for(Node node:network.nodes()) {
            double distance=distance(point,node.point());
            if(distance<best||(distance==best&&node.id()<result)){best=distance;result=node.id();}
        }
        if(best>200) throw ApiException.invalid("Point is "+Math.round(best)+" m from the prepared drivable network; choose within 200 m of a road.");
        return result;
    }
    public static double distance(Point a,Point b) {
        double p=Math.toRadians(a.latitude()),q=Math.toRadians(b.latitude());
        double dp=q-p,dl=Math.toRadians(b.longitude()-a.longitude());
        double h=Math.pow(Math.sin(dp/2),2)+Math.cos(p)*Math.cos(q)*Math.pow(Math.sin(dl/2),2);
        return 6371008.8*2*Math.atan2(Math.sqrt(h),Math.sqrt(Math.max(0,1-h)));
    }
    public boolean turnAllowed(long nodeId,long incomingWay,long nextWay) {
        if(incomingWay==0) return true;
        for(Restriction r:restrictions.getOrDefault(nodeId,List.of())) if(r.fromWay()==incomingWay) {
            if(r.type().startsWith("only_")&&r.toWay()!=nextWay)return false;
            if(r.type().startsWith("no_")&&r.toWay()==nextWay)return false;
        }
        return true;
    }
    public static boolean active(Incident incident,double time) {
        return !"RESOLVED".equals(incident.status)&&time>=incident.startSec-1e-8&&time<incident.endSec-1e-8;
    }
    public static double speedFactor(String physicalId,List<Incident> incidents,double time,boolean occupied) {
        double factor=1;
        for(Incident i:incidents) if(i.physicalId.equals(physicalId)&&active(i,time)) {
            if("CLOSURE".equals(i.type)&&!occupied)return 0;
            if("SLOWDOWN".equals(i.type))factor*=Math.max(.15,1-.85*i.severity);
        }
        return Math.max(.05,factor);
    }
    public static double nextBoundary(String physicalId,List<Incident> incidents,double time) {
        double boundary=Double.POSITIVE_INFINITY;
        for(Incident i:incidents) if(i.physicalId.equals(physicalId)&&!"RESOLVED".equals(i.status)) {
            if(i.startSec>time+1e-8)boundary=Math.min(boundary,i.startSec);
            if(i.endSec>time+1e-8)boundary=Math.min(boundary,i.endSec);
        }
        return boundary;
    }
    /** Known incident schedule, piecewise speeds; closure cannot strand an already occupied edge. */
    public static double traversalSeconds(Edge edge,double distance,double maxSpeed,List<Incident> incidents,double start,boolean alreadyOccupied,boolean allowWait) {
        double time=start,remaining=Math.max(0,distance);
        boolean entered=alreadyOccupied;
        for(int guard=0;remaining>1e-7&&guard<1000;guard++) {
            double factor=speedFactor(edge.physicalId(),incidents,time,entered);
            double boundary=nextBoundary(edge.physicalId(),incidents,time);
            if(factor==0) {
                if(!allowWait||!Double.isFinite(boundary))return Double.POSITIVE_INFINITY;
                time=boundary;continue;
            }
            entered=true;
            double speed=Math.min(edge.speedKph(),maxSpeed)/3.6*factor;
            double duration=remaining/speed;
            if(time+duration<=boundary+1e-8){time+=duration;remaining=0;}
            else {remaining-=speed*(boundary-time);time=boundary;}
        }
        return remaining>1e-7?Double.POSITIVE_INFINITY:time-start;
    }
    private record SearchKey(long node,long incomingWay) {}
    private record Label(SearchKey key,double cost) {}
    private record Parent(SearchKey prior,String edgeId) {}
    private List<String> search(long start,long destination,double maxSpeed,List<Incident> incidents,double time,long incomingWay) {
        node(start);node(destination);
        if(start==destination)return List.of();
        SearchKey origin=new SearchKey(start,incomingWay);
        Map<SearchKey,Double> costs=new HashMap<>();Map<SearchKey,Parent> parents=new HashMap<>();
        PriorityQueue<Label> queue=new PriorityQueue<>(Comparator.comparingDouble(Label::cost).thenComparingLong(x->x.key.node).thenComparingLong(x->x.key.incomingWay));
        costs.put(origin,0d);queue.add(new Label(origin,0));SearchKey finish=null;
        while(!queue.isEmpty()) {
            Label current=queue.poll();
            if(current.cost>costs.getOrDefault(current.key,Double.POSITIVE_INFINITY)+1e-8)continue;
            if(current.key.node==destination){finish=current.key;break;}
            for(Edge edge:outgoing.getOrDefault(current.key.node,List.of())) {
                if(!turnAllowed(current.key.node,current.key.incomingWay,edge.wayId()))continue;
                double seconds=traversalSeconds(edge,edge.lengthM(),maxSpeed,incidents,time+current.cost,false,false);
                if(!Double.isFinite(seconds))continue;
                SearchKey next=new SearchKey(edge.to(),edge.wayId());double proposed=current.cost+seconds;
                if(proposed+1e-8<costs.getOrDefault(next,Double.POSITIVE_INFINITY)) {
                    costs.put(next,proposed);parents.put(next,new Parent(current.key,edge.id()));queue.add(new Label(next,proposed));
                }
            }
        }
        if(finish==null)throw ApiException.invalid("No legal connected road route exists between these snapped locations under current closures and turn restrictions.");
        LinkedList<String> route=new LinkedList<>();
        for(SearchKey current=finish;!current.equals(origin);) {Parent parent=parents.get(current);route.addFirst(parent.edgeId);current=parent.prior;}
        return route;
    }
    public Route route(long start,long destination,double maxSpeed,List<Incident> incidents,double departure,long incomingWay) {
        return route(start,destination,List.of(),maxSpeed,incidents,departure,incomingWay);
    }
    public Route route(long start,long destination,List<Long> via,double maxSpeed,List<Incident> incidents,double departure,long incomingWay) {
        if(!Double.isFinite(maxSpeed)||maxSpeed<=0||maxSpeed>120)throw ApiException.invalid("Maximum simulated speed must be between 1 and 120 km/h.");
        List<String> all=new ArrayList<>();List<Long> stops=new ArrayList<>(via==null?List.of():via);stops.add(destination);
        long current=start,way=incomingWay;double elapsed=0;
        for(long stop:stops) {
            List<String> leg=search(current,stop,maxSpeed,incidents,departure+elapsed,way);
            for(String id:leg){Edge e=edge(id);elapsed+=traversalSeconds(e,e.lengthM(),maxSpeed,incidents,departure+elapsed,false,false);all.add(id);way=e.wayId();}
            current=stop;
        }
        return describe(all,node(start).point(),node(destination).point(),maxSpeed);
    }
    public Route describe(List<String> ids,Point start,Point destination,double maxSpeed) {
        List<List<Double>> coordinates=new ArrayList<>();double distance=0,time=0;
        for(String id:ids) {
            Edge e=edge(id);distance+=e.lengthM();time+=e.lengthM()/(Math.min(e.speedKph(),maxSpeed)/3.6);
            for(List<Double> coordinate:e.geometry())if(coordinates.isEmpty()||!coordinates.getLast().equals(coordinate))coordinates.add(coordinate);
        }
        if(coordinates.isEmpty())coordinates.add(start.coordinates());
        return new Route(List.copyOf(ids),List.copyOf(coordinates),distance,time,start,destination);
    }
    public List<Double> position(Edge edge,double offset) {
        double fraction=Math.min(1,Math.max(0,offset/edge.lengthM()));
        List<List<Double>> geometry=edge.geometry();
        double total=0;List<Double> lengths=new ArrayList<>();
        for(int i=1;i<geometry.size();i++){double d=distance(new Point(geometry.get(i-1).get(0),geometry.get(i-1).get(1)),new Point(geometry.get(i).get(0),geometry.get(i).get(1)));lengths.add(d);total+=d;}
        double target=fraction*total;
        for(int i=0;i<lengths.size();i++) {
            double d=lengths.get(i);
            if(target<=d||i==lengths.size()-1){double f=d>0?Math.min(1,target/d):0;List<Double>a=geometry.get(i),b=geometry.get(i+1);return List.of(a.get(0)+(b.get(0)-a.get(0))*f,a.get(1)+(b.get(1)-a.get(1))*f);}
            target-=d;
        }
        return geometry.getLast();
    }
}
