"""Acquire an immutable real OSM extract and build the first Chennai road graph.

No original acquisition manifests are edited. Speed defaults are simulation
assumptions. This script uses only the Python standard library; roads remain ODbL.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import hashlib
import heapq
import json
import math
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/chennai_network.json"
PROVENANCE = ROOT / "data/metadata/chennai_network_provenance.json"
VALIDATION = ROOT / "data/metadata/chennai_network_validation.json"
REPORT = ROOT / "reports/CHENNAI_NETWORK.md"
DENIED = {"no", "private", "agricultural", "forestry", "delivery", "destination", "customers", "permit", "military", "restricted", "local"}
VERIFIED_ACCESS_VALUES = {"", "yes", "permissive", "designated", "official"}
ACCESS_KEYS = ("access", "vehicle", "motor_vehicle", "hgv")
RESTRICTION_TYPES = {"no_left_turn", "no_right_turn", "no_straight_on", "no_u_turn",
                     "only_left_turn", "only_right_turn", "only_straight_on", "only_u_turn", "no_entry", "no_exit"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(path)


def query_for(config: dict) -> str:
    bbox = ",".join(str(x) for x in config["bbox_south_west_north_east"])
    return (f'[out:json][timeout:{config["overpass_timeout_seconds"]}];\n'
            f'way["highway"]({bbox})->.roads;\n'
            'relation(bw.roads)["type"~"^restriction"]->.restrictions;\n'
            '(.roads;.restrictions;);(._;>;);out meta;\n')


def acquire(config: dict, offline: bool = False) -> tuple[dict, dict]:
    path = ROOT / config["raw_path"]
    query = query_for(config)
    if path.exists():
        if not PROVENANCE.exists():
            raise ValueError("Existing raw file has no provenance; refusing silent reuse")
        provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        if (provenance["sourceSha256"] != digest(path) or provenance["query"] != query
                or provenance["endpoint"] != config["overpass_endpoint"]):
            raise ValueError("Immutable raw source checksum or configured query changed")
        return json.loads(path.read_text(encoding="utf-8")), provenance
    if offline:
        raise FileNotFoundError("No cached Chennai extract; run without --offline to acquire it")
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(config["overpass_endpoint"], data=data,
        headers={"User-Agent": "CascadeShieldAI/0.1 research geographic demo (bounded one-time extract)",
                 "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(request, timeout=config["overpass_timeout_seconds"] + 60) as response:
        raw_bytes = response.read(40 * 1024 * 1024 + 1)
        headers = {k: v for k, v in response.headers.items() if k.lower() in {"content-type", "date", "last-modified"}}
        final_url = response.url
    if len(raw_bytes) > 40 * 1024 * 1024:
        raise ValueError("Bounded extract unexpectedly exceeds 40 MiB; source not saved")
    raw = json.loads(raw_bytes)
    if raw.get("remark") or not raw.get("elements"):
        raise ValueError(f"Overpass returned incomplete or empty data: {raw.get('remark')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never normalize or overwrite the response: exact acquired bytes are evidence.
    with path.open("xb") as handle:
        handle.write(raw_bytes)
    provenance = {"source": "OpenStreetMap via public Overpass API", "endpoint": config["overpass_endpoint"],
        "finalUrl": final_url, "method": "POST", "query": query,
        "acquiredAtUtc": datetime.now(timezone.utc).isoformat(), "headers": headers,
        "sourcePath": config["raw_path"], "sourceBytes": len(raw_bytes), "sourceSha256": digest(path),
        "osmBaseTimestamp": raw.get("osm3s", {}).get("timestamp_osm_base"),
        "bbox": config["bbox_south_west_north_east"], "license": config["license"],
        "licenseUrl": config["license_url"], "attribution": config["attribution"],
        "attributionUrl": config["attribution_url"], "dataClass": "REAL_GEOGRAPHIC_DATA"}
    write_json(PROVENANCE, provenance)
    return raw, provenance


def distance(a: dict, b: dict) -> float:
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat, dlon = lat2 - lat1, math.radians(b["lon"] - a["lon"])
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(hav)))


def speed_for(tags: dict, highway: str, direction: str, config: dict) -> tuple[float, str]:
    keys = [f"maxspeed:hgv:{direction}", "maxspeed:hgv", f"maxspeed:{direction}", "maxspeed"]
    for key in keys:
        value = tags.get(key, "")
        # Multiple mapped limits use the smallest value, with source retained in tags.
        parsed = []
        for item in value.split(";"):
            match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(km/h|kph|mph)?\s*", item)
            if not match:
                parsed = []
                break
            kph = float(match.group(1)) * (1.609344 if match.group(2) == "mph" else 1)
            if not 0 < kph <= 160:
                parsed = []
                break
            parsed.append(kph)
        if parsed:
            return min(parsed), "OSM_TAG:" + key
    return float(config["speed_fallback_kph"][highway]), "SIMULATION_ASSUMPTION"


def permitted(tags: dict) -> tuple[bool, str]:
    for key in ACCESS_KEYS:
        value = tags.get(key, "").lower()
        if value in DENIED or value not in VERIFIED_ACCESS_VALUES:
            return False, f"access:{key}={value}"
    if tags.get("service") in {"parking_aisle", "driveway", "emergency_access"}:
        return False, "unsuitable_service"
    for key in tags:
        if (key.endswith(":conditional") and (key.split(":")[0] in {*ACCESS_KEYS, "oneway"})):
            return False, "uninterpreted_conditional_access"
        if key.split(":")[0] in {"maxweight", "maxheight", "maxwidth", "maxlength", "maxaxleload"}:
            return False, "unmodelled_vehicle_dimension_or_weight_limit"
    if tags.get("construction") or tags.get("proposed") or tags.get("impassable") == "yes":
        return False, "construction_or_impassable"
    return True, ""


def restrictions_for(relations: list[dict]) -> tuple[list[dict], set[int], list[dict]]:
    supported, excluded_ways, exclusions = [], set(), []
    for relation in relations:
        tags, members = relation.get("tags", {}), relation.get("members", [])
        mode_tags = {k: v for k, v in tags.items() if k == "restriction" or k.startswith("restriction:")}
        exceptions = set(re.split(r"[;,]", tags.get("except", "")))
        if exceptions & {"hgv", "motor_vehicle", "vehicle"}:
            continue
        # Bicycle-only and other vehicle-specific restrictions do not govern freight.
        kind = tags.get("restriction:hgv") or tags.get("restriction:motor_vehicle") or tags.get("restriction")
        conditional = any(k.endswith(":conditional") for k in mode_tags)
        if not kind and not conditional:
            continue
        froms = [m["ref"] for m in members if m["role"] == "from" and m["type"] == "way"]
        tos = [m["ref"] for m in members if m["role"] == "to" and m["type"] == "way"]
        vias = [m for m in members if m["role"] == "via"]
        legacy = any(k in tags for k in ("day_on", "day_off", "hour_on", "hour_off"))
        reason = ""
        if conditional or legacy:
            reason = "conditional_turn_restriction_not_modelled"
        elif kind not in RESTRICTION_TYPES:
            reason = "unknown_turn_restriction"
        elif len(vias) != 1 or vias[0]["type"] != "node" or not froms or not tos:
            reason = "via_way_or_invalid_turn_restriction"
        elif (len(froms) != 1 and kind != "no_entry") or (len(tos) != 1 and kind != "no_exit"):
            reason = "unsupported_multi_member_turn_restriction"
        if reason:
            ways = [m["ref"] for m in members if m["type"] == "way"]
            excluded_ways.update(ways)
            exclusions.append({"relationId": relation["id"], "reason": reason, "excludedWayIds": ways})
            continue
        for from_way in froms:
            for to_way in tos:
                supported.append({"fromWay": from_way, "viaNode": vias[0]["ref"], "toWay": to_way, "type": kind})
    return supported, excluded_ways, exclusions


def strong_components(nodes: dict[int, dict], edges: list[dict]) -> list[set[int]]:
    adjacency, reverse = defaultdict(list), defaultdict(list)
    for edge in edges:
        adjacency[edge["from"]].append(edge["to"])
        reverse[edge["to"]].append(edge["from"])
    visited, finish = set(), []
    for start in sorted(nodes):
        if start in visited:
            continue
        visited.add(start)
        stack = [(start, iter(adjacency[start]))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                finish.append(node)
                stack.pop()
            elif child not in visited:
                visited.add(child)
                stack.append((child, iter(adjacency[child])))
    components, visited = [], set()
    for start in reversed(finish):
        if start in visited:
            continue
        component, queue = set(), [start]
        visited.add(start)
        while queue:
            node = queue.pop()
            component.add(node)
            for child in reverse[node]:
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
        components.append(component)
    return sorted(components, key=lambda component: (-len(component), min(component)))


def build_graph(raw: dict, config: dict, provenance: dict) -> tuple[dict, dict]:
    elements = raw["elements"]
    raw_nodes = {n["id"]: n for n in elements if n["type"] == "node"}
    ways = [w for w in elements if w["type"] == "way"]
    relations = [r for r in elements if r["type"] == "relation"]
    restrictions, excluded_ways, restriction_exclusions = restrictions_for(relations)
    south, west, north, east = config["bbox_south_west_north_east"]
    counts, edges, nodes = Counter(), [], {}
    allowed_types = config["speed_fallback_kph"]
    blocked_nodes = set()
    for node_id, node in raw_nodes.items():
        tags = node.get("tags", {})
        permitted_node, _ = permitted(tags)
        if not permitted_node or tags.get("barrier", "") not in {"", "no", "entrance", "toll_booth"}:
            blocked_nodes.add(node_id)
    for way in sorted(ways, key=lambda item: item["id"]):
        tags, way_id = way.get("tags", {}), way["id"]
        highway = tags.get("highway", "")
        if highway not in allowed_types:
            counts["unsuitable_highway_ways"] += 1
            continue
        if way_id in excluded_ways:
            counts["unsupported_restriction_ways"] += 1
            continue
        allowed, reason = permitted(tags)
        if not allowed:
            counts[reason] += 1
            continue
        oneway = tags.get("oneway:hgv", tags.get("oneway:motor_vehicle", tags.get("oneway", ""))).lower()
        if oneway not in {"", "no", "0", "false", "yes", "1", "true", "-1", "reverse"}:
            counts["unsupported_oneway_value"] += 1
            continue
        if not oneway and (tags.get("junction") in {"roundabout", "circular"} or highway == "motorway"):
            oneway = "yes"
        directions = [("f", "forward")] if oneway in {"yes", "1", "true"} else [("r", "backward")] if oneway in {"-1", "reverse"} else [("f", "forward"), ("r", "backward")]
        ids = way["nodes"]
        for index, (node_a, node_b) in enumerate(zip(ids, ids[1:])):
            if node_a not in raw_nodes or node_b not in raw_nodes:
                raise ValueError(f"Incomplete source: missing nodes in way {way_id}")
            a, b = raw_nodes[node_a], raw_nodes[node_b]
            if not all(south <= n["lat"] <= north and west <= n["lon"] <= east for n in (a, b)):
                counts["segments_clipped_at_bbox"] += 1
                continue
            if node_a in blocked_nodes or node_b in blocked_nodes:
                counts["barrier_or_access_node_segments"] += 1
                continue
            length = distance(a, b)
            if node_a == node_b or length <= 0.01:
                counts["zero_length_segments"] += 1
                continue
            for suffix, direction in directions:
                if any(tags.get(f"{key}:{direction}", "").lower() in DENIED for key in ACCESS_KEYS):
                    counts["directional_access_excluded_edges"] += 1
                    continue
                start, end = (a, b) if suffix == "f" else (b, a)
                speed, source = speed_for(tags, highway, direction, config)
                edges.append({"id": f"{way_id}:{index}:{suffix}", "physicalId": f"{way_id}:{index}",
                    "from": start["id"], "to": end["id"], "wayId": way_id,
                    "lengthM": round(length, 6), "speedKph": round(speed, 6), "speedSource": source,
                    "highway": highway, "name": tags.get("name", tags.get("name:en", "")),
                    "geometry": [[start["lon"], start["lat"]], [end["lon"], end["lat"]]], "tags": tags})
                for n in (start, end):
                    nodes[n["id"]] = {"id": n["id"], "longitude": n["lon"], "latitude": n["lat"]}
    components = strong_components(nodes, edges)
    if not components or len(components[0]) < 100:
        raise ValueError("No sufficiently connected real Chennai road component found")
    keep = components[0]
    counts["outside_largest_strong_component_nodes"] = len(nodes) - len(keep)
    counts["outside_largest_strong_component_edges"] = sum(e["from"] not in keep or e["to"] not in keep for e in edges)
    nodes = {nid: node for nid, node in nodes.items() if nid in keep}
    edges = [e for e in edges if e["from"] in keep and e["to"] in keep]
    kept_ways = {e["wayId"] for e in edges}
    # Keep applicable restrictions even when their to-way is outside the graph:
    # an only-turn may deliberately leave no feasible transition at a boundary.
    restrictions = [r for r in restrictions if r["fromWay"] in kept_ways and r["viaNode"] in nodes]
    metadata = {**provenance, "simulationScope": config["scope"],
        "speedAssumptions": config["speed_fallback_kph"],
        "speedAssumptionProvenance": config["speed_fallback_provenance"],
        "topology": "Real OSM shared node IDs only; no invented intersections or coordinate-based merging",
        "restrictionPolicy": "Node-via restrictions retained; unsupported conditional/via-way restrictions exclude all participating ways",
        "profile": "Conservative simulated freight; private/restricted roads, unknown barriers and unmodelled weight/dimension limits excluded",
        "boundaryPolicy": "Only consecutive-node segments whose two real endpoints lie inside the requested bbox",
        "componentPolicy": "Largest strongly connected directed road component; turn restrictions also checked by route engine"}
    graph = {"networkId": config["network_id"], "name": config["name"], "bbox": config["bbox_south_west_north_east"],
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]), "edges": edges,
        "restrictions": restrictions, "metadata": metadata}
    validation = {"rawElements": dict(Counter(e["type"] for e in elements)),
        "sourceSha256": provenance["sourceSha256"], "nodeCount": len(nodes), "directedEdgeCount": len(edges),
        "physicalSegmentCount": len({e["physicalId"] for e in edges}), "wayCount": len(kept_ways),
        "restrictionCount": len(restrictions), "restrictionExclusions": restriction_exclusions,
        "exclusionCounts": dict(counts), "initialStrongComponentSizes": [len(c) for c in components[:20]],
        "speedSourceCounts": dict(Counter(e["speedSource"] for e in edges)),
        "graphChecks": {"uniqueNodeIds": len(nodes) == len({n["id"] for n in graph["nodes"]}),
            "uniqueDirectedEdgeIds": len(edges) == len({e["id"] for e in edges}),
            "allEndpointsPresent": all(e["from"] in nodes and e["to"] in nodes for e in edges),
            "positiveLengthsAndSpeeds": all(e["lengthM"] > 0 and e["speedKph"] > 0 for e in edges),
            "allGeometryMatchesEndpoints": all(e["geometry"] == [[nodes[e["from"]]["longitude"], nodes[e["from"]]["latitude"]],
                [nodes[e["to"]]["longitude"], nodes[e["to"]]["latitude"]]] for e in edges),
            "directedStronglyConnectedBeforeTurnConstraints": len(strong_components(nodes, edges)) == 1}}
    if not all(validation["graphChecks"].values()):
        raise ValueError("Graph validation failed")
    return graph, validation


def route(graph: dict, start: int, destination: int, closed_physical: str | None = None) -> list[dict]:
    adjacency, restrictions = defaultdict(list), defaultdict(list)
    for edge in graph["edges"]:
        if edge["physicalId"] != closed_physical:
            adjacency[edge["from"]].append(edge)
    for restriction in graph["restrictions"]:
        restrictions[(restriction["fromWay"], restriction["viaNode"])].append(restriction)
    queue = [(0.0, start, -1)]
    costs, previous = {(start, -1): 0.0}, {}
    final = None
    while queue:
        cost, node, previous_way = heapq.heappop(queue)
        state = node, previous_way
        if cost != costs.get(state):
            continue
        if node == destination:
            final = state
            break
        turns = restrictions.get((previous_way, node), [])
        for edge in adjacency[node]:
            if any((r["type"].startswith("no_") and edge["wayId"] == r["toWay"])
                   or (r["type"].startswith("only_") and edge["wayId"] != r["toWay"]) for r in turns):
                continue
            nxt = edge["to"], edge["wayId"]
            candidate = cost + edge["lengthM"] / (edge["speedKph"] / 3.6)
            if candidate < costs.get(nxt, math.inf):
                costs[nxt], previous[nxt] = candidate, (state, edge)
                heapq.heappush(queue, (candidate, *nxt))
    if final is None:
        return []
    result = []
    while final in previous:
        final, edge = previous[final]
        result.append(edge)
    return list(reversed(result))


def demo_pairs(graph: dict) -> list[dict]:
    # Coordinates are operator demonstration selection targets, not claimed warehouses.
    targets = [(13.052, 80.25, 13.079, 80.275), (13.083, 80.252, 13.049, 80.276),
               (13.06, 80.282, 13.087, 80.26)]
    result = []
    for index, (lat1, lon1, lat2, lon2) in enumerate(targets, 1):
        starts = sorted(graph["nodes"], key=lambda n: (n["latitude"] - lat1) ** 2 + (n["longitude"] - lon1) ** 2)[:10]
        ends = sorted(graph["nodes"], key=lambda n: (n["latitude"] - lat2) ** 2 + (n["longitude"] - lon2) ** 2)[:10]
        selected = None
        for start in starts:
            for end in ends:
                path = route(graph, start["id"], end["id"])
                if len(path) < 10:
                    continue
                # Locate a closure that admits a genuine connected alternative route.
                candidates = path[len(path)//3:2*len(path)//3]
                for segment in sorted(candidates, key=lambda e: (-e["lengthM"], e["id"]))[:8]:
                    detour = route(graph, start["id"], end["id"], segment["physicalId"])
                    if not detour:
                        continue
                    selected = {"id": f"demo-{index}", "startNodeId": start["id"], "destinationNodeId": end["id"],
                        "start": [start["longitude"], start["latitude"]],
                        "destination": [end["longitude"], end["latitude"]],
                        "baseDistanceM": round(sum(e["lengthM"] for e in path), 3),
                        "baseTravelSeconds": round(sum(e["lengthM"] / (e["speedKph"] / 3.6) for e in path), 3),
                        "baseEdgeCount": len(path), "closurePhysicalId": segment["physicalId"],
                        "closureEdgeId": segment["id"], "closureWayName": segment["name"],
                        "closureMidpoint": [(segment["geometry"][0][0] + segment["geometry"][1][0]) / 2,
                                            (segment["geometry"][0][1] + segment["geometry"][1][1]) / 2],
                        "detourDistanceM": round(sum(e["lengthM"] for e in detour), 3),
                        "detourTravelSeconds": round(sum(e["lengthM"] / (e["speedKph"] / 3.6) for e in detour), 3),
                        "detourEdgeCount": len(detour), "returnRouteFeasible": bool(route(graph, end["id"], start["id"])),
                        "dataClass": "SIMULATED_SELECTION_OF_REAL_GEOGRAPHIC_NODES"}
                    break
                if selected:
                    break
            if selected:
                break
        if selected is None:
            raise ValueError(f"Could not validate real OD pair with road-closure detour {index}")
        result.append(selected)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Only rebuild from checksummed immutable cached raw data")
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw, provenance = acquire(config, args.offline)
    graph, validation = build_graph(raw, config, provenance)
    pairs = demo_pairs(graph)
    graph["metadata"]["demoPairs"] = pairs
    validation["demoPairs"] = pairs
    features = []
    seen = set()
    for edge in graph["edges"]:
        if edge["physicalId"] in seen:
            continue
        seen.add(edge["physicalId"])
        features.append({"type": "Feature", "id": edge["physicalId"],
            "properties": {k: edge[k] for k in ("id", "physicalId", "wayId", "lengthM", "speedKph", "speedSource", "highway", "name")},
            "geometry": {"type": "LineString", "coordinates": edge["geometry"]}})
    geojson = {"type": "FeatureCollection", "features": features,
               "attribution": config["attribution"], "license": config["license"], "dataClass": "REAL_GEOGRAPHIC_DATA"}
    write_json(ROOT / config["graph_path"], graph)
    write_json(ROOT / config["geojson_path"], geojson)
    validation["artifacts"] = [{"path": config[key], "sha256": digest(ROOT / config[key]),
                                "bytes": (ROOT / config[key]).stat().st_size} for key in ("graph_path", "geojson_path")]
    validation["sourceChecksumStillMatches"] = digest(ROOT / config["raw_path"]) == provenance["sourceSha256"]
    write_json(VALIDATION, validation)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render_report(graph, validation), encoding="utf-8")
    print(json.dumps({"networkId": graph["networkId"], "nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
                      "restrictionCount": len(graph["restrictions"]), "paths": validation["artifacts"], "demoPairs": pairs}, indent=2))


def render_report(graph: dict, validation: dict) -> str:
    metadata = graph["metadata"]
    lines = ["# Chennai road network for simulator milestone 1", "",
        "This is real OpenStreetMap road geography for central Chennai, India. Every vehicle, assignment and disruption in the demonstration is SIMULATED. This extract is separate from the existing GB, Brazil, Porto, NYC and Cambridge research cohorts.", "",
        f"- Source: public [{metadata['source']}]({metadata['endpoint']}); OSM base timestamp `{metadata['osmBaseTimestamp']}`.",
        f"- Bounding box (south, west, north, east): `{graph['bbox']}`.",
        f"- Attribution: [{metadata['attribution']}]({metadata['attributionUrl']}); derived road database is [{metadata['license']}]({metadata['licenseUrl']}).",
        f"- Immutable exact response: `{metadata['sourcePath']}` ({metadata['sourceBytes']:,} bytes); SHA-256 `{metadata['sourceSha256']}`.",
        f"- Prepared graph: {validation['nodeCount']:,} real nodes, {validation['directedEdgeCount']:,} directed edges, {validation['physicalSegmentCount']:,} physical segments, {validation['wayCount']:,} ways, {validation['restrictionCount']} supported turn restrictions.", "",
        "## Reproduce", "", "```powershell", "python scripts/prepare_chennai_network.py", "python scripts/prepare_chennai_network.py --offline", "```", "",
        "Existing raw files are checksummed and never overwritten. Changing the bbox, endpoint or source bytes requires a separately named acquisition/configuration. No original acquisition manifests are modified.", "",
        "## Schema and routing policy", "",
        "`road_graph.json` contains `networkId`, `name`, `bbox`, `nodes`, `edges`, `restrictions`, and `metadata`. Nodes contain `id`, `longitude`, `latitude`. Edges contain `id`, `physicalId`, `from`, `to`, `wayId`, `lengthM`, `speedKph`, `speedSource`, `highway`, `name`, `geometry`, and original OSM `tags`. Restriction rows contain `fromWay`, `viaNode`, `toWay`, `type`. `roads.geojson` holds one displayed feature per physical segment; closures use `physicalId` to close both directions.", "",
        "Only consecutive OSM nodes are joined. Crossing coordinates are never merged, so bridges/tunnels preserve the source's grade-separated topology. Directed edges respect mapped one-way direction, reverse one-way and implied roundabout/motorway one-way unless explicitly overridden. The largest strongly connected component is retained; route search must additionally enforce turn restrictions.", "",
        "Conservative freight profile excludes private, no-access, destination-only and permit-dependent ways; parking aisles, driveways and emergency access; unmodelled height/weight/dimension limits; unknown physical barriers; conditional access; unsupported one-way values. Unsupported conditional or via-way turn restrictions exclude all participating ways. This sacrifices coverage rather than assuming permission. Missing OSM restrictions and regional heavy-vehicle regulations are not verified: use only as a simulated research demonstration, not an operational/legal truck router.", "",
        "Node-via `no_*` and `only_*` restrictions must be enforced by `(incoming way, via node, outgoing way)` state. Mode-specific HGV restrictions override general restrictions; HGV exceptions are respected. Same-way U-turn restrictions are conservatively enforced against all same-way transitions at that node; coverage may decrease. Edges clipped at the boundary require both actual endpoints inside the bbox; there are no invented boundary nodes.", "",
        "## Speeds and scope", "",
        "Numeric OSM `maxspeed:hgv`, directional maxspeed and maxspeed tags are retained with `OSM_TAG:<key>` provenance. Unsupported or absent limits receive explicitly labelled `SIMULATION_ASSUMPTION` baseline speeds. These are neither measured speeds nor asserted legal speed limits. Vehicle maximum speeds and injected conditions are further simulation constraints. A tag-derived speed limit is still mapping information, not a guarantee of current law.", "",
        f"Fallback baseline speeds (km/h): `{json.dumps(metadata['speedAssumptions'], sort_keys=True)}`.", "",
        f"Actual edge speed source counts: `{json.dumps(validation['speedSourceCounts'], sort_keys=True)}`.", "",
        "## Validation and demonstration selections", "",
        f"Graph invariants: `{json.dumps(validation['graphChecks'], sort_keys=True)}`.",
        f"Exact source checksum unchanged after ETL: `{validation['sourceChecksumStillMatches']}`.",
        "Three origin/destination pairs below use real source nodes, satisfy turn-aware routing, have a return route, and admit a route after closing the specified physical segment. These are demonstration selections, not observed shipments or actual warehouses.", "",
        "| Pair | Start node | Destination node | Initial metres / seconds | Closure segment | Detour metres / seconds |",
        "|---|---:|---:|---:|---|---:|"]
    for pair in validation["demoPairs"]:
        lines.append(f"| {pair['id']} | {pair['startNodeId']} | {pair['destinationNodeId']} | {pair['baseDistanceM']} / {pair['baseTravelSeconds']} | `{pair['closurePhysicalId']}` | {pair['detourDistanceM']} / {pair['detourTravelSeconds']} |")
    lines.extend(["", f"Exclusion counts: `{json.dumps(validation['exclusionCounts'], sort_keys=True)}`.",
        f"Unsupported restriction exclusions: `{json.dumps(validation['restrictionExclusions'], sort_keys=True)}`.", "",
        "The snapshot is reusable offline. No weather records, observed traffic, truck telemetry, freight dependency labels, ML predictions or research results are created by this preparation. Geographic coverage and tags may be incomplete; snapshot date is unrelated to historical overseas cohorts.", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    main()
