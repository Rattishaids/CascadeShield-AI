"""Small CPU heterogeneous message passing with optional causal snapshot-history GRU.

Only existing operational relations are consumed. There are no invented physical roads,
reverse operational links, rollout-outcome inputs, or cross-scenario recurrent states.
"""
from __future__ import annotations

import numpy as np
import torch
from torch import nn
from torch_geometric.nn import MessagePassing

from .data import validate_frame
from .features import FEATURES, feature_vector

NODE_TYPES = ("TRUCK", "DRIVER", "DOCK", "DELIVERY", "WAREHOUSE")
RELATIONS = (
    "ASSIGNED_DRIVER", "RESERVED_DOCK", "CARRIES_DELIVERY", "DOCK_AT_WAREHOUSE",
    "DELIVERY_TO_WAREHOUSE", "SHARED_DOCK_CONFLICT", "SHARED_DRIVER_CONFLICT",
    "DRIVER_UNAVAILABLE", "SHIFT_EXCEEDED", "DOCK_OVERLAP", "DOCK_WINDOW",
    "DELIVERY_DEADLINE", "DRIVER_OVERLAP",
)


def raw_graph(frame, node_schema):
    pack = validate_frame(frame)
    stores = {}
    for kind in NODE_TYPES:
        store = pack["node_stores"].get(kind)
        names = node_schema[kind]
        if store is None:
            stores[kind] = {"ids": [], "x": np.empty((0, len(names)), dtype=np.float32)}
            continue
        if kind == "TRUCK":
            context = {t["truckId"]: t for t in frame["trucks"]}
            x = [feature_vector(context[tid]["features"]) for tid in store["resource_ids"]]
        else:
            if store["feature_names"] != names:
                raise ValueError(f"Unsupported {kind} graph feature vocabulary")
            x = [[v if mask else float("nan") for v, mask in zip(values, masks)]
                 for values, masks in zip(store["x"], store["x_mask"])]
        stores[kind] = {"ids": store["node_ids"], "x": np.asarray(x, dtype=np.float32).reshape(len(x), len(names))}
    edges = []
    clock = frame["clockSec"]
    for store in pack["edge_stores"]:
        source, relation, target = store["edge_type"]
        if source not in NODE_TYPES or target not in NODE_TYPES or relation not in RELATIONS:
            raise ValueError(f"Unsupported operational graph relation: {store['edge_type']}")
        weights = []
        for weight, start, end in store["edge_attr"]:
            # Time encoding is computed from prediction-time forecast validity, never a final label.
            remaining = max(0., min(end-clock, 3600.)) / 3600.
            lead = max(0., min(start-clock, 3600.)) / 3600.
            weights.append([weight, lead, remaining])
        edges.append((source, relation, target, np.asarray(store["edge_index"], dtype=np.int64),
                      np.asarray(weights, dtype=np.float32)))
    return {"nodes": stores, "edges": edges, "clockSec": clock}


def fit_normalizers(graphs, node_schema):
    result = {}
    for kind in NODE_TYPES:
        arrays = [g["nodes"][kind]["x"] for g in graphs if len(g["nodes"][kind]["x"])]
        x = np.concatenate(arrays) if arrays else np.zeros((1, len(node_schema[kind])), dtype=np.float32)
        median = np.nanmedian(x, axis=0)
        median = np.nan_to_num(median, nan=0.)
        filled = np.where(np.isnan(x), median, x)
        mean, scale = filled.mean(axis=0), filled.std(axis=0)
        scale = np.where(scale > 1e-6, scale, 1.)
        result[kind] = {"median": median.tolist(), "mean": mean.tolist(), "scale": scale.tolist()}
    return result


def tensor_graph(graph, normalizers, device="cpu"):
    nodes = {}
    for kind, store in graph["nodes"].items():
        stats = normalizers[kind]
        x = store["x"]
        mask = ~np.isnan(x)
        filled = np.where(mask, x, np.asarray(stats["median"]))
        z = np.clip((filled - np.asarray(stats["mean"])) / np.asarray(stats["scale"]), -20, 20)
        nodes[kind] = torch.tensor(np.concatenate((z, mask.astype(float)), axis=1), dtype=torch.float32, device=device)
    edges = [(s, r, t, torch.as_tensor(index, dtype=torch.long, device=device), torch.as_tensor(attr, dtype=torch.float32, device=device))
             for s, r, t, index, attr in graph["edges"]]
    return {"x": nodes, "ids": {k: v["ids"] for k, v in graph["nodes"].items()}, "edges": edges,
            "clockSec": graph["clockSec"]}


class RelationMessage(MessagePassing):
    def __init__(self, hidden):
        super().__init__(aggr="mean")
        self.transform = nn.Linear(hidden, hidden, bias=False)
        self.edge_gate = nn.Linear(3, 1)

    def forward(self, source, target, edge_index, edge_attr):
        return self.propagate(edge_index, x=(self.transform(source), target), edge_attr=edge_attr,
                              size=(source.size(0), target.size(0)))

    def message(self, x_j, edge_attr):
        return x_j * torch.sigmoid(self.edge_gate(edge_attr))


class OperationalGNN(nn.Module):
    def __init__(self, node_schema, hidden=24, temporal=False):
        super().__init__()
        self.temporal = temporal
        self.encoders = nn.ModuleDict({k: nn.Linear(2*len(names), hidden) for k, names in node_schema.items()})
        self.messages = nn.ModuleList([nn.ModuleDict({r: RelationMessage(hidden) for r in RELATIONS}) for _ in range(2)])
        self.self_layers = nn.ModuleList([nn.ModuleDict({k: nn.Linear(hidden, hidden) for k in NODE_TYPES}) for _ in range(2)])
        self.gru = nn.ModuleDict({k: nn.GRUCell(hidden+1, hidden) for k in NODE_TYPES}) if temporal else None
        self.truck_heads = nn.Linear(hidden, 3)  # nonnegative remaining ETA, SLA logit, adverse-impact logit
        self.impact_heads = nn.ModuleDict({k: nn.Linear(hidden, 1) for k in NODE_TYPES if k != "TRUCK"})

    def encode(self, graph):
        h = {k: torch.relu(self.encoders[k](x)) for k, x in graph["x"].items()}
        for step in range(2):
            sums = {k: self.self_layers[step][k](v) for k, v in h.items()}
            counts = {k: 1 for k in h}
            for source, relation, target, index, attr in graph["edges"]:
                if index.numel():
                    sums[target] = sums[target] + self.messages[step][relation](h[source], h[target], index, attr)
                    counts[target] += 1
            h = {k: torch.relu(v/counts[k]) for k, v in sums.items()}
        return h

    def forward(self, history):
        if not history:
            raise ValueError("At least one as-of graph is required")
        current = history[-1]
        if not self.temporal:
            state = self.encode(current)
        else:
            memory = {k: {} for k in NODE_TYPES}
            state = None
            previous_clock = history[0]["clockSec"]
            for graph in history[-3:]:
                embedding = self.encode(graph)
                state = {}
                elapsed = max(0., graph["clockSec"]-previous_clock)/600.
                for kind, values in embedding.items():
                    prior = torch.stack([memory[kind].get(node, values.new_zeros(values.shape[1])) for node in graph["ids"][kind]]) if len(values) else torch.zeros_like(values)
                    dt = values.new_full((len(values), 1), min(elapsed, 10.))
                    state[kind] = self.gru[kind](torch.cat((values, dt), dim=1), prior)
                    memory[kind] = dict(zip(graph["ids"][kind], state[kind]))
                previous_clock = graph["clockSec"]
        raw = self.truck_heads(state["TRUCK"])
        # Scale is fixed simulation seconds; no label normalization fitted on assessment.
        truck = torch.stack((torch.nn.functional.softplus(raw[:, 0])*600., raw[:, 1], raw[:, 2]), dim=1)
        impact = {"TRUCK": truck[:, 2]}
        impact.update({k: self.impact_heads[k](state[k]).flatten() for k in NODE_TYPES if k != "TRUCK"})
        return truck, impact
