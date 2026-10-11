"""Record a human decision to let a model artifact drive paper-trading decisions.

    python -m ml.models.approve --artifact artifacts/models/x.json --by "Name" \
        --reason "shadow results from ... reviewed" [--revoke]

The approval is part of the checksummed artifact. It never enables live trading: the worker
refuses ML strategies in TRADING_MODE=live regardless of approval.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from ml.features.pipeline import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from ml.models.artifact import ModelPredictor, read_artifact, write_artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--by", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()

    document = read_artifact(args.artifact)
    predictor = ModelPredictor(document, FEATURE_SCHEMA_VERSION, FEATURE_NAMES)  # must be valid
    if predictor.validation_failed and not args.revoke:
        raise SystemExit(f"Refusing: artifact failed validation ({predictor.validation_failed}); "
                         "it is a research/shadow artifact and can never be approved to trade.")
    document["approval"] = {
        "approved_for_trading": not args.revoke,
        "approved_by": args.by,
        "reason": args.reason,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    digest = write_artifact(document, args.artifact)
    state = "REVOKED" if args.revoke else "APPROVED (paper/testnet only)"
    print(f"{args.artifact}: {state}, sha256={digest}")


if __name__ == "__main__":
    main()
