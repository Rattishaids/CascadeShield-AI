# Missing data requirements

The acquired real data supports contextual and source-specific research. It does not yet support a defensible evaluation of CascadeShield's ability to prevent logistics cascades. Acquisition and validation are completed for the bounded available scope; unavailable data and reuse gates remain explicit. No ML training or experimental results are included.

| Required evidence | What is missing | Why it is needed |
|---|---|---|
| Real freight operations in one study region and period | Consented vehicle GPS, shipment/order IDs, pickup/delivery timestamps, routes, carrier/fleet IDs, promised deadlines and actual outcomes | Relate disruptions to affected shipments within the same real operation |
| Operational dependency network | Shipment-to-vehicle-to-route-to-depot links, transfer schedules, supplier/customer dependencies and effective dates | Observe propagation rather than treating unrelated spatial proximity as a cascade |
| Disruption ground truth | Incident start/end, road/lane closures, affected links, severity, queue/delay observations, capacity reductions and recovery times | DfT injury collisions are a subset of incidents and do not provide closure durations or measured logistics impacts |
| Ground-truth cascade labels | Verified primary incident, downstream disruptions, temporal order and operator confirmation | Prevent invented causal links or synthetic evaluation targets |
| Intervention evidence | Dispatch/reroute actions, decision times, available alternatives, operator constraints and counterfactual/evaluation design | Measure prevention or effectiveness rather than assume a benefit |
| Freight-usable road network | Full study-area topology, turn restrictions, one-way/access/HGV/weight/height limits, time-dependent closures and verified travel times | The acquired OSM geometry pilot is not a validated freight routing graph; no default speed/capacity is invented |
| Facility effective dates and observed capacity | Active/inactive dates, actual loading-bay counts, dock throughput, operating hours, queues, ownership and verified IDs | Cambridge is a static 2023 publication without per-site observation dates; bays are author-modelled estimates |
| Spatially relevant weather and availability times | Historical weather/forecast cells covering all selected routes/sites, forecast issuance and lead times | The initial weather extract is one Birmingham ERA5 grid cell; reanalysis can leak future information into operational backtests |
| Timestamp conventions | Explicit source timezones, DST policies, clock quality and event/availability-time distinction | DfT supplies local date/time; Olist rows do not declare a timezone. Neither is silently converted to UTC |
| Data-use permissions | Explicit Porto data license; NYC dataset reuse permission; authorized Traccar fleet-data license/consent | Public download availability and a software license do not establish fleet or dataset reuse permission |
| Traccar access | Authorized server URL, credentials/token, approved device IDs and time window | Traccar is software/API infrastructure, not a public historical fleet dataset. No demo data is substituted |
| Independent evaluation protocol | One coherent region, operator and overlapping period; leakage controls; data availability and split definitions; held-out real incidents | Brazil, Portugal, NYC and GB cannot be combined as if they describe the same logistics operation |

Olist can support a separate Brazil delivery-delay study using its observed dates, subject to its CC BY-NC-SA 4.0 terms. It lacks GPS trajectories, a verified road-incident linkage and cascade/intervention ground truth. No linkage to GB accidents, Porto taxi trips, NYC drivers or Birmingham weather is made.

Porto and NYC are retained only as quarantined originals for inspection and full-file validation. Resolve permission before research reuse or creation of new research derivatives. A sample ID list or medallion mapping is not a trajectory dataset or a shipment outcome table.

The full DfT historical archive, all OSM worldwide data and weather at every possible point are outside this bounded acquisition run. The selected annual tables are complete; the OSM/weather geographic subsets are explicitly scoped in config/acquisition.json. Expansion should follow a chosen research protocol and available storage.
