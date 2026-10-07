#!/usr/bin/env python3
"""Generate synthetic examples, never overwrite an existing directory."""
import argparse
from pathlib import Path
import numpy as np


def sequence(path, scans, steers, accels):
    path.mkdir(parents=True)
    for name, data in (("scans", scans), ("steers", steers), ("accelerations", accels)):
        np.save(path / f"{name}.npy", data, allow_pickle=False)


def main():
    parser = argparse.ArgumentParser(description="Create good/bad synthetic TinyLidarNet data")
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(2026)
    scans = rng.uniform(0, 25, (96, 750)).astype(np.float32)
    steers = rng.uniform(-0.6, 0.6, 96).astype(np.float32)
    accels = rng.uniform(-0.8, 0.8, 96).astype(np.float32)
    sequence(args.directory / "good/train/run_a", scans, steers, accels)
    sequence(args.directory / "good/val/run_b", rng.uniform(0, 25, (80, 750)).astype(np.float32),
             rng.uniform(-0.6, 0.6, 80).astype(np.float32), rng.uniform(-0.8, 0.8, 80).astype(np.float32))
    sequence(args.directory / "bad/train/run_a", scans, steers, accels)
    sequence(args.directory / "bad/val/copied_run", scans.copy(), steers.copy(), accels.copy())
    broken = scans.copy()
    broken[0, 0] = np.nan
    sequence(args.directory / "bad/train/broken_nan", broken, steers, accels)
    sequence(args.directory / "bad/train/labels_outside", scans * 0.5, steers, np.full(96, -1.6))
    (args.directory / "common.yaml").write_text(
        '/**:\n  ros__parameters:\n    model:\n      input_dim: 750\n    max_range: 30.0\n    accel_scale: 1.0\n    decel_scale: 1.0\n', encoding="utf-8")
    print(f"Synthetic data written to {args.directory}; good should pass; bad should fail.")


if __name__ == "__main__":
    main()
