package io.cascadeshield.sim;

import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.http.converter.HttpMessageNotReadableException;
import java.util.*;
import java.util.concurrent.*;
import static io.cascadeshield.sim.Models.*;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins={"http://localhost:5173","http://127.0.0.1:5173"})
public class SimulatorController {
    private final SimulationService simulation;
    private final ScheduledExecutorService streams=Executors.newSingleThreadScheduledExecutor(r->{Thread t=new Thread(r,"simulator-sse");t.setDaemon(true);return t;});
    public SimulatorController(SimulationService simulation){this.simulation=simulation;}
    @GetMapping("/health")public Object health(){return simulation.health();}
    @GetMapping("/network")public Object network(){return simulation.network();}
    @GetMapping("/network/roads")public Object roads(){return simulation.roads();}
    @GetMapping("/state")public Object state(){return simulation.state();}
    @PostMapping("/routes/preview")public Object preview(@RequestBody RouteRequest request){return simulation.preview(request);}
    @PostMapping("/trucks")public Object add(@RequestBody TruckSpec request){return simulation.add(request);}
    @PutMapping("/trucks/{id}")public Object update(@PathVariable String id,@RequestBody TruckSpec request){return simulation.update(id,request);}
    @DeleteMapping("/trucks/{id}")public Object delete(@PathVariable String id){return simulation.delete(id);}
    @PostMapping("/control")public Object control(@RequestBody ControlRequest request){return simulation.control(request);}
    @PostMapping("/incidents")public Object incident(@RequestBody IncidentRequest request){return simulation.incident(request);}
    @DeleteMapping("/incidents/{id}")public Object resolve(@PathVariable String id){return simulation.resolve(id);}
    @GetMapping("/recommendations")public Object recommendations(){return simulation.state().recommendations;}
    @PostMapping("/decisions")public Object decision(@RequestBody DecisionRequest request){return simulation.decision(request);}
    @GetMapping("/operations")public Object operations(){return simulation.state().operations;}
    @GetMapping("/operations/graph")public Object operationalGraph(){return simulation.state().operations.graph;}
    @GetMapping("/operations/cascade")public Object cascade(){return simulation.state().operations.cascade;}
    @GetMapping("/operations/affected")public Object affected(@RequestParam(required=false) String incidentId){return simulation.affected(incidentId);}
    @PostMapping("/operations/{kind:warehouses|docks|drivers|deliveries}")public Object resource(@PathVariable String kind,@RequestBody Map<String,Object> request){return simulation.resource(kind,request,true,null);}
    @PutMapping("/operations/{kind:warehouses|docks|drivers|deliveries}/{id}")public Object resourceEdit(@PathVariable String kind,@PathVariable String id,@RequestBody Map<String,Object> request){return simulation.resource(kind,request,false,id);}
    @DeleteMapping("/operations/{kind:warehouses|docks|drivers|deliveries}/{id}")public Object resourceDelete(@PathVariable String kind,@PathVariable String id){return simulation.removeResource(kind,id);}
    @PostMapping("/operations/assignments")public Object assign(@RequestBody OpsModels.AssignmentSpec request){return simulation.assign(request);}
    @DeleteMapping("/operations/assignments/{truckId}")public Object unassign(@PathVariable String truckId){return simulation.unassign(truckId);}
    @PatchMapping("/operations/drivers/{id}/availability")public Object availability(@PathVariable String id,@RequestBody OpsModels.AvailabilityRequest request){return simulation.availability(id,request);}
    @GetMapping("/incidents/{id}")public Object inspectIncident(@PathVariable String id){return simulation.inspectIncident(id);}
    @PostMapping("/ai/predict")public Object predict(){return simulation.predict();}
    @PostMapping("/ai/candidates/{truckId}")public Object candidates(@PathVariable String truckId){return simulation.candidates(truckId);}
    @PostMapping("/ai/counterfactual")public Object counterfactual(@RequestBody AiModels.CandidateAction candidate){return simulation.evaluate(candidate);}
    @PostMapping("/ai/validate")public Object validate(@RequestBody AiModels.CandidateAction candidate){return simulation.validate(candidate);}
    @GetMapping("/ai/recommendations/{truckId}")public Object recommend(@PathVariable String truckId){return simulation.recommend(truckId);}
    @PostMapping("/ai/explain")public Object explain(@RequestBody AiModels.CandidateAction candidate){return simulation.explain(candidate);}
    @GetMapping("/ai/graph-snapshot")public Object graphSnapshot(){return simulation.snapshot();}
    @PostMapping("/ai/graph-snapshots")public Object persistGraphSnapshot(){return simulation.persistSnapshot();}
    @GetMapping("/ai/approvals")public Object approvals(){return simulation.approvals();}
    @PostMapping("/ai/approvals")public Object requestApproval(@RequestBody AiModels.CandidateAction candidate){return simulation.requestApproval(candidate);}
    @PostMapping("/ai/approvals/{id}/approve")public Object approve(@PathVariable UUID id,@RequestBody OperatorApprovalGuard.OperatorRequest request){return simulation.approve(id,request);}
    @PostMapping("/ai/approvals/{id}/execute")public Object execute(@PathVariable UUID id){return simulation.execute(id);}
    @GetMapping("/scenarios")public Object scenarios(){return simulation.scenarios();}
    @PostMapping("/scenarios")public Object save(@RequestBody ScenarioRequest request){return simulation.saveScenario(request);}
    @GetMapping({"/scenarios/{id}","/scenarios/{id}/export"})public Object scenario(@PathVariable UUID id){return simulation.scenario(id);}
    @PostMapping("/scenarios/{id}/replay")public Object replay(@PathVariable UUID id){return simulation.replay(id);}
    @GetMapping(value="/stream",produces=MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(){SseEmitter emitter=new SseEmitter(600000L);ScheduledFuture<?> future=streams.scheduleAtFixedRate(()->{try{emitter.send(SseEmitter.event().name("state").data(simulation.state()));}catch(Exception e){emitter.complete();}},0,250,TimeUnit.MILLISECONDS);emitter.onCompletion(()->future.cancel(false));emitter.onTimeout(()->future.cancel(false));emitter.onError(e->future.cancel(false));return emitter;}
}

@RestControllerAdvice
class SimulatorErrors {
    @ExceptionHandler(ApiException.class)public ResponseEntity<Map<String,String>> domain(ApiException error){return ResponseEntity.status(error.status).body(Map.of("error",error.getMessage()));}
    @ExceptionHandler({HttpMessageNotReadableException.class,IllegalArgumentException.class})public ResponseEntity<Map<String,String>> input(Exception error){return ResponseEntity.badRequest().body(Map.of("error","Invalid request: "+error.getMessage()));}
    @ExceptionHandler(Exception.class)public ResponseEntity<Map<String,String>> unexpected(Exception error){org.slf4j.LoggerFactory.getLogger(SimulatorErrors.class).error("Simulator request failed",error);return ResponseEntity.internalServerError().body(Map.of("error","Backend operation failed; inspect server logs. Simulation state remains in the backend."));}
}
