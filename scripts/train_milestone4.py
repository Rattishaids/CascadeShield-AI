"""Fit on development scenarios, or evaluate frozen models on a separate assessment file."""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fit", "evaluate-validation", "evaluate-final"))
    parser.add_argument("--corpus", type=Path, default=Path("data/processed/milestone4/corpus_v2"))
    parser.add_argument("--models", type=Path, default=Path("models/milestone4/v1"))
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--protocol", type=Path, default=Path("config/milestone4_protocol_v2.json"))
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--gnn-device", choices=("cpu", "cuda"), help="Optional independently measured graph-training device; defaults to --device")
    parser.add_argument("--resume", action="store_true", help="Resume an unfinished, unfrozen training directory from best GNN checkpoints; never refit a published bundle")
    parser.add_argument("--audit", type=Path, default=Path("reports/milestone4_leakage_audit.json"))
    args = parser.parse_args()
    if args.mode == "fit":
        from ml.training import fit
        fit(args.corpus, args.models, args.reports, args.protocol, args.device, args.resume, args.audit, args.gnn_device)
    else:
        from ml.evaluation import evaluate
        split = "final" if args.mode == "evaluate-final" else "validation"
        report = evaluate(args.corpus / f"{split}.jsonl", args.models, args.reports, split)
        print(f"Evaluated {report['dataset']['scenarioCount']} independent {split} scenarios; no model was refit.", flush=True)


if __name__ == "__main__":
    main()
