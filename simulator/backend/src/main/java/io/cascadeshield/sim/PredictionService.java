package io.cascadeshield.sim;

import java.util.List;
import static io.cascadeshield.sim.Models.*;

/** Replaceable direct-impact estimator; does not conflate the road and dependency graphs. */
public interface PredictionService {
    record Estimate(double arrivalSec,double remainingDistanceM,List<String> incidentIds) {}
    Estimate estimate(State state,Truck truck);
    Risk risk(Truck truck,double arrivalSec,double baselineRemainingSec,double clockSec);
}
