package io.cascadeshield.sim;

import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/benchmarks")
@CrossOrigin(origins={"http://localhost:5173","http://127.0.0.1:5173"})
public class BenchmarkController {
    private final BenchmarkService benchmarks;
    public BenchmarkController(BenchmarkService benchmarks){this.benchmarks=benchmarks;}
    @GetMapping("/catalog")public Object catalog(){return benchmarks.catalog();}
    @GetMapping("/runs")public Object runs(){return benchmarks.list();}
    @PostMapping("/runs")public Object run(@RequestBody BenchmarkService.Request request){return benchmarks.submit(request);}
    @GetMapping("/runs/{id}")public Object run(@PathVariable UUID id){return benchmarks.get(id);}
    @GetMapping("/runs/{id}/export")public ResponseEntity<String> export(@PathVariable UUID id,@RequestParam(defaultValue="json")String format){String body=benchmarks.export(id,format);return ResponseEntity.ok().header(HttpHeaders.CONTENT_DISPOSITION,"attachment; filename=benchmark-"+id+"."+format).contentType("csv".equals(format)?MediaType.parseMediaType("text/csv"):MediaType.APPLICATION_JSON).body(body);}
}
