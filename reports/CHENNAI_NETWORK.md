# Chennai road network for simulator milestone 1

This is real OpenStreetMap road geography for central Chennai, India. Every vehicle, assignment and disruption in the demonstration is SIMULATED. This extract is separate from the existing GB, Brazil, Porto, NYC and Cambridge research cohorts.

- Source: public [OpenStreetMap via public Overpass API](https://overpass-api.de/api/interpreter); OSM base timestamp `2026-10-09T05:33:21Z`.
- Bounding box (south, west, north, east): `[13.04, 80.24, 13.095, 80.29]`.
- Attribution: [© OpenStreetMap contributors](https://www.openstreetmap.org/copyright); derived road database is [ODbL-1.0](https://opendatacommons.org/licenses/odbl/1-0/).
- Immutable exact response: `data/raw/chennai_osm/central_chennai.json` (7,984,665 bytes); SHA-256 `38ab5bdea18ca7859daea5a3801f1a5d138d320e29a841aa8d67f00c1c87e80d`.
- Prepared graph: 12,386 real nodes, 23,907 directed edges, 14,147 physical segments, 3,419 ways, 10 supported turn restrictions.

## Reproduce

```powershell
python scripts/prepare_chennai_network.py
python scripts/prepare_chennai_network.py --offline
```

Existing raw files are checksummed and never overwritten. Changing the bbox, endpoint or source bytes requires a separately named acquisition/configuration. No original acquisition manifests are modified.

## Schema and routing policy

`road_graph.json` contains `networkId`, `name`, `bbox`, `nodes`, `edges`, `restrictions`, and `metadata`. Nodes contain `id`, `longitude`, `latitude`. Edges contain `id`, `physicalId`, `from`, `to`, `wayId`, `lengthM`, `speedKph`, `speedSource`, `highway`, `name`, `geometry`, and original OSM `tags`. Restriction rows contain `fromWay`, `viaNode`, `toWay`, `type`. `roads.geojson` holds one displayed feature per physical segment; closures use `physicalId` to close both directions.

Only consecutive OSM nodes are joined. Crossing coordinates are never merged, so bridges/tunnels preserve the source's grade-separated topology. Directed edges respect mapped one-way direction, reverse one-way and implied roundabout/motorway one-way unless explicitly overridden. The largest strongly connected component is retained; route search must additionally enforce turn restrictions.

Conservative freight profile excludes private, no-access, destination-only and permit-dependent ways; parking aisles, driveways and emergency access; unmodelled height/weight/dimension limits; unknown physical barriers; conditional access; unsupported one-way values. Unsupported conditional or via-way turn restrictions exclude all participating ways. This sacrifices coverage rather than assuming permission. Missing OSM restrictions and regional heavy-vehicle regulations are not verified: use only as a simulated research demonstration, not an operational/legal truck router.

Node-via `no_*` and `only_*` restrictions must be enforced by `(incoming way, via node, outgoing way)` state. Mode-specific HGV restrictions override general restrictions; HGV exceptions are respected. Same-way U-turn restrictions are conservatively enforced against all same-way transitions at that node; coverage may decrease. Edges clipped at the boundary require both actual endpoints inside the bbox; there are no invented boundary nodes.

## Speeds and scope

Numeric OSM `maxspeed:hgv`, directional maxspeed and maxspeed tags are retained with `OSM_TAG:<key>` provenance. Unsupported or absent limits receive explicitly labelled `SIMULATION_ASSUMPTION` baseline speeds. These are neither measured speeds nor asserted legal speed limits. Vehicle maximum speeds and injected conditions are further simulation constraints. A tag-derived speed limit is still mapping information, not a guarantee of current law.

Fallback baseline speeds (km/h): `{"living_street": 10, "motorway": 60, "motorway_link": 30, "primary": 40, "primary_link": 25, "residential": 20, "secondary": 35, "secondary_link": 25, "service": 15, "tertiary": 30, "tertiary_link": 20, "trunk": 50, "trunk_link": 30, "unclassified": 25}`.

Actual edge speed source counts: `{"OSM_TAG:maxspeed": 331, "SIMULATION_ASSUMPTION": 23576}`.

## Validation and demonstration selections

Graph invariants: `{"allEndpointsPresent": true, "allGeometryMatchesEndpoints": true, "directedStronglyConnectedBeforeTurnConstraints": true, "positiveLengthsAndSpeeds": true, "uniqueDirectedEdgeIds": true, "uniqueNodeIds": true}`.
Exact source checksum unchanged after ETL: `True`.
Three origin/destination pairs below use real source nodes, satisfy turn-aware routing, have a return route, and admit a route after closing the specified physical segment. These are demonstration selections, not observed shipments or actual warehouses.

| Pair | Start node | Destination node | Initial metres / seconds | Closure segment | Detour metres / seconds |
|---|---:|---:|---:|---|---:|
| demo-1 | 247685517 | 2241833897 | 6291.4 / 662.547 | `567205827:4` | 6379.227 / 691.888 |
| demo-2 | 2269952774 | 262666325 | 6561.023 / 754.181 | `240472111:0` | 6899.271 / 759.922 |
| demo-3 | 13313036398 | 333218903 | 5057.786 / 537.554 | `28152147:1` | 4971.817 / 551.927 |

Exclusion counts: `{"access:access=customers": 1, "access:access=military": 43, "access:access=no": 13, "access:access=permit": 1, "access:access=private": 1512, "access:motor_vehicle=no": 15, "access:motor_vehicle=private": 2, "barrier_or_access_node_segments": 192, "outside_largest_strong_component_edges": 2257, "outside_largest_strong_component_nodes": 1568, "segments_clipped_at_bbox": 877, "unmodelled_vehicle_dimension_or_weight_limit": 1, "unsuitable_highway_ways": 635, "unsuitable_service": 13, "unsupported_restriction_ways": 74}`.
Unsupported restriction exclusions: `[{"excludedWayIds": [1033769803, 1033769805, 1033769807], "reason": "via_way_or_invalid_turn_restriction", "relationId": 15537811}, {"excludedWayIds": [1033769807, 1033769802, 1033769803], "reason": "via_way_or_invalid_turn_restriction", "relationId": 16706459}, {"excludedWayIds": [155750051, 1289116085, 1289116083], "reason": "via_way_or_invalid_turn_restriction", "relationId": 17960753}, {"excludedWayIds": [1373602748, 1311245037, 1373602749], "reason": "via_way_or_invalid_turn_restriction", "relationId": 17976044}, {"excludedWayIds": [1349155568, 1349155567, 1349716692], "reason": "via_way_or_invalid_turn_restriction", "relationId": 18526036}, {"excludedWayIds": [1296314154, 1050933537, 1149836408], "reason": "via_way_or_invalid_turn_restriction", "relationId": 18780846}, {"excludedWayIds": [1059454601, 566538373, 155785667], "reason": "via_way_or_invalid_turn_restriction", "relationId": 18922307}, {"excludedWayIds": [155785667, 1059454600, 1059454601], "reason": "via_way_or_invalid_turn_restriction", "relationId": 18922309}, {"excludedWayIds": [1374029225, 155785667, 1059454600, 1373640995], "reason": "via_way_or_invalid_turn_restriction", "relationId": 18928849}, {"excludedWayIds": [1391540465, 700994986, 1391540466], "reason": "via_way_or_invalid_turn_restriction", "relationId": 18964507}, {"excludedWayIds": [1391540467, 700994986, 1391540466], "reason": "via_way_or_invalid_turn_restriction", "relationId": 19203029}, {"excludedWayIds": [1421511722, 1039298151, 1421511723], "reason": "via_way_or_invalid_turn_restriction", "relationId": 19448335}, {"excludedWayIds": [1237642835, 1237642841, 1237642840, 1373638877], "reason": "via_way_or_invalid_turn_restriction", "relationId": 19523205}, {"excludedWayIds": [1052956026, 1149875361, 1039224806], "reason": "via_way_or_invalid_turn_restriction", "relationId": 19893562}, {"excludedWayIds": [1374029224, 1059454601, 566538373, 1373640993], "reason": "via_way_or_invalid_turn_restriction", "relationId": 19917746}, {"excludedWayIds": [1464339459, 1364431987, 1464339461], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20049832}, {"excludedWayIds": [1082631141, 155750051, 1289116085, 1042122764], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20086571}, {"excludedWayIds": [1476409560, 1311245037, 1476409561], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20199571}, {"excludedWayIds": [1374029227, 566538373, 155785667, 1373640994], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20199601}, {"excludedWayIds": [1424749200, 1237642838, 1342404643, 1373638878], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20199614}, {"excludedWayIds": [1237642838, 1342404643, 1237642841], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20199615}, {"excludedWayIds": [1237642841, 1237642840, 1237642838], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20199616}, {"excludedWayIds": [1218729896, 1218729897, 1218729898], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20199635}, {"excludedWayIds": [1482858543, 1031619242, 1482858541], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20259737}, {"excludedWayIds": [1501754976, 1349138739, 1501754980], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20514886}, {"excludedWayIds": [1374029227, 566538373, 1373640993], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20664207}, {"excludedWayIds": [1525067669, 1296314154, 1525067670], "reason": "via_way_or_invalid_turn_restriction", "relationId": 20796930}, {"excludedWayIds": [1149818935, 1149818933, 1532576389], "reason": "via_way_or_invalid_turn_restriction", "relationId": 21033347}, {"excludedWayIds": [1546878591, 1033769807, 1033769802, 1546878590], "reason": "via_way_or_invalid_turn_restriction", "relationId": 21180648}, {"excludedWayIds": [1501754976, 1349138739], "reason": "via_way_or_invalid_turn_restriction", "relationId": 21210726}, {"excludedWayIds": [1555042368, 1149875532, 1149875530], "reason": "via_way_or_invalid_turn_restriction", "relationId": 21324691}, {"excludedWayIds": [1502782201, 696377459, 1557276460, 1557276455], "reason": "via_way_or_invalid_turn_restriction", "relationId": 21367400}]`.

The snapshot is reusable offline. No weather records, observed traffic, truck telemetry, freight dependency labels, ML predictions or research results are created by this preparation. Geographic coverage and tags may be incomplete; snapshot date is unrelated to historical overseas cohorts.
