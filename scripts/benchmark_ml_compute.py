"""Measure CPU/GPU work on real development corpus examples; never open final outcomes."""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import psutil
import torch
import xgboost as xgb

from ml.data import load_corpus, examples
from ml.features import FEATURES, feature_vector
from ml.gnn import OperationalGNN
from ml.training import (_schema, prepare_graphs, _labels, graph_loss, freeze_random,
                         versions, write_json, sha, require_training_audit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("data/processed/milestone4/corpus_v2/train.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("reports/milestone4_compute_comparison.json"))
    parser.add_argument("--protocol", type=Path, default=Path("config/milestone4_protocol_v2.json"))
    parser.add_argument("--audit", type=Path, default=Path("reports/milestone4_leakage_audit.json"))
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Compute evidence already exists; choose a new output filename")
    audit = require_training_audit(args.corpus.parent, args.protocol, args.audit)
    scenarios = load_corpus(args.corpus, {"train"})
    tiny = copy.deepcopy(scenarios[:3])
    for scenario in tiny: scenario["frames"] = scenario["frames"][:3]
    results = []
    device_options = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])
    schema = _schema(scenarios)
    for temporal in (False, True):
        freeze_random()
        initial = OperationalGNN(schema, hidden=24, temporal=temporal).state_dict()
        for device in device_options:
            freeze_random()
            graphs, normalizers = prepare_graphs(tiny, schema, device=device)
            labels = [[_labels(s, f, g, device) for f, g in zip(s["frames"], gs)] for s, gs in zip(tiny, graphs)]
            model = OperationalGNN(schema, hidden=24, temporal=temporal).to(device); model.load_state_dict(initial)
            optimizer = torch.optim.Adam(model.parameters(), lr=.003)
            # Warm framework/kernels without changing the timed model's initial weights.
            with torch.no_grad(): model(graphs[0][:1])
            if device == "cuda": torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            for epoch in range(2):
                for case_index, gs in enumerate(graphs):
                    optimizer.zero_grad()
                    loss = sum(graph_loss(model(gs[max(0, i-2):i+1]), labels[case_index][i]) for i in range(len(gs)))/len(gs)
                    loss.backward(); optimizer.step()
            if device == "cuda": torch.cuda.synchronize()
            training_ms = (time.perf_counter()-started)*1000.
            model.eval(); started = time.perf_counter()
            with torch.no_grad():
                for _ in range(10): model(graphs[0][:3])
            if device == "cuda": torch.cuda.synchronize()
            inference_ms = (time.perf_counter()-started)*1000./10
            results.append({"algorithm": "GNN_TEMPORAL" if temporal else "GNN_STATIC", "device": device,
                            "actualParameterDevice": str(next(model.parameters()).device),
                            "actualInputTensorDevice": str(graphs[0][0]["x"]["TRUCK"].device),
                            "scenarioCount": len(tiny), "framesPerScenario": 3, "epochs": 2,
                            "trainingMs": training_ms, "inferenceMsPerGraphHistory": inference_ms,
                            "peakCudaAllocatedBytes": torch.cuda.max_memory_allocated() if device == "cuda" else None,
                            "peakCudaReservedBytes": torch.cuda.max_memory_reserved() if device == "cuda" else None,
                            "processRssBytes": psutil.Process().memory_info().rss})
            del model, optimizer, graphs
            if device == "cuda": torch.cuda.empty_cache()
    rows = [r for r in examples(scenarios) if r["labels"]["remainingArrivalSec"] is not None]
    x = np.asarray([feature_vector(r["features"]) for r in rows], dtype=np.float32)
    y = np.asarray([r["labels"]["remainingArrivalSec"] for r in rows], dtype=np.float32)
    for device in device_options:
        start = time.perf_counter()
        model = xgb.XGBRegressor(n_estimators=80, max_depth=3, learning_rate=.08, tree_method="hist", device=device,
                                 random_state=4001, n_jobs=2)
        model.fit(x, y)
        training_ms = (time.perf_counter()-start)*1000.
        configuration = json.loads(model.get_booster().save_config())
        if device == "cuda" and not configuration["learner"]["generic_param"]["device"].startswith("cuda"):
            raise RuntimeError("XGBoost silently fell back from the requested GPU")
        model.set_params(device="cpu")
        start = time.perf_counter()
        for _ in range(10): model.predict(x[:32])
        results.append({"algorithm": "XGBOOST_ETA", "device": device, "trainingMs": training_ms,
                        "examples": len(rows), "cpuInferenceMsPer32Trucks": (time.perf_counter()-start)*100.,
                        "actualLearnerDevice": configuration["learner"]["generic_param"]["device"],
                        "updaters": configuration["learner"]["gradient_booster"]["gbtree_train_param"]["updater"],
                        "processRssBytes": psutil.Process().memory_info().rss})
    write_json(args.output, {"schemaVersion": "cascadeshield.compute-comparison/1.0",
                            "provenance": "TIMED_ENGINEERING_WORK_ON_SIMULATED_TRAINING_DATA",
                            "sourceCorpusSha256": sha(args.corpus), "packages": versions(),
                            "pretrainingAudit": audit,
                            "cudaAvailable": torch.cuda.is_available(), "gpuName": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                            "gpuTotalBytes": torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else None,
                            "results": results, "limitation": "Small fixed development workload; warm kernel timings, no research-effectiveness or dedicated hardware performance claim"})
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__": main()
