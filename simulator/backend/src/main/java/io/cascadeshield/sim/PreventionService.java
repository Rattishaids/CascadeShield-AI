package io.cascadeshield.sim;

import static io.cascadeshield.sim.Models.*;

/** Future dependency-aware optimizers can replace this interface without moving state into the UI. */
public interface PreventionService {
    Recommendation recommend(State state,Truck truck);
}
