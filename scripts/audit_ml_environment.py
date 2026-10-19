"""Record actual local package/device capability, without creating research observations."""
import argparse
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import psutil
import torch
import xgboost as xgb
from ml.training import write_json, versions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError("Environment evidence already exists; choose a fresh path")
    report = {"schemaVersion": "cascadeshield.ml-environment/1.0", "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
              "pythonExecutable": sys.executable, "pythonVersion": sys.version, "prefix": sys.prefix,
              "platform": platform.platform(), "packages": versions(), "torchModulePath": torch.__file__,
              "xgboostModulePath": xgb.__file__, "cudaBuild": torch.version.cuda,
              "cudaAvailable": torch.cuda.is_available(), "provenance": "ENGINEERING_CAPABILITY_CHECK_NOT_RESEARCH_DATA"}
    memory = psutil.virtual_memory(); disk = shutil.disk_usage(Path.cwd())
    report["host"] = {"logicalCpuCount": psutil.cpu_count(), "physicalCpuCount": psutil.cpu_count(logical=False),
                      "ramTotalBytes": memory.total, "ramAvailableBytes": memory.available,
                      "diskTotalBytes": disk.total, "diskFreeBytes": disk.free,
                      "workspace": str(Path.cwd())}
    try:
        query = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.free,memory.used", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=20, check=True)
        report["nvidiaSmi"] = {"query": query.args[1:], "output": query.stdout.strip()}
        banner = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=20, check=True)
        report["nvidiaSmi"]["banner"] = banner.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        report["nvidiaSmi"] = {"unavailableReason": str(exc)}
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        report["gpu"] = {"name": props.name, "totalMemoryBytes": props.total_memory,
                         "computeCapability": [props.major, props.minor],
                         "freeMemoryBytes": torch.cuda.mem_get_info()[0]}
        a = torch.arange(64*64, dtype=torch.float32, device="cuda").reshape(64, 64)/4096.
        torch.cuda.synchronize(); start = time.perf_counter(); b = a @ a; torch.cuda.synchronize()
        report["cudaMatmulProbe"] = {"finite": bool(torch.isfinite(b).all()), "outputDevice": str(b.device),
                                    "elapsedMs": (time.perf_counter()-start)*1000., "testFixtureOnly": True}
        data = np.arange(80, dtype=np.float32).reshape(40, 2); labels = np.arange(40, dtype=np.float32)
        model = xgb.XGBRegressor(tree_method="hist", device="cuda", n_estimators=2, max_depth=2)
        model.fit(data, labels)
        config = json.loads(model.get_booster().save_config())
        report["xgbGpuProbe"] = {"device": config["learner"]["generic_param"]["device"],
                                 "updater": config["learner"]["gradient_booster"]["gbtree_train_param"]["updater"],
                                 "testFixtureOnly": True}
    write_json(args.output, report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__": main()
