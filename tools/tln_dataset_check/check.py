#!/usr/bin/env python3
"""Read-only TinyLidarNet dataset audit. MIT License; Team KSK."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import html
import json
import math
from pathlib import Path
import sqlite3
import sys
import tempfile

import numpy as np
import yaml

VERSION = "0.1.1"
FILES = ("scans.npy", "steers.npy", "accelerations.npy")
DEFAULTS = dict(input_dim=750, max_range=30.0, accel_scale=1.0, decel_scale=1.0)
CHUNK = 1024


def parameters(path: Path | None, overrides: dict) -> dict:
    values = dict(DEFAULTS)
    if path is not None:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("Common YAML must be a mapping / 共通YAMLはmappingが必要です")
        ros = doc.get("/**", {}).get("ros__parameters")
        if not isinstance(ros, dict):
            raise ValueError("Missing /**.ros__parameters / ROS共通設定の階層がありません")
        if "brake_scale" in ros:
            raise ValueError("Legacy brake_scale found; use the current decel_scale schema / 旧版のキーです。版を確認してください")
        model = ros.get("model", {})
        if not isinstance(model, dict):
            raise ValueError("model must be a mapping")
        values["input_dim"] = model.get("input_dim", values["input_dim"])
        for name in ("max_range", "accel_scale", "decel_scale"):
            values[name] = ros.get(name, values[name])
    values.update({k: v for k, v in overrides.items() if v is not None})
    dim = values["input_dim"]
    if isinstance(dim, bool) or not isinstance(dim, (int, float)) or not math.isfinite(dim) or int(dim) != dim or dim < 1:
        raise ValueError("input_dim must be a positive integer")
    values["input_dim"] = int(dim)
    for name in ("max_range", "accel_scale", "decel_scale"):
        if isinstance(values[name], bool):
            raise ValueError(f"{name} must be a positive finite number")
        values[name] = float(values[name])
        if not math.isfinite(values[name]) or values[name] <= 0:
            raise ValueError(f"{name} must be a positive finite number")
    return values


def issue(report: dict, severity: str, code: str, where: str, message: str, action: str, **details) -> None:
    report["findings"].append(dict(severity=severity, code=code, location=where,
                                   message=message, action=action, details=details))


def stats(array: np.ndarray) -> dict:
    a = np.asarray(array, dtype=np.float64)
    finite = a[np.isfinite(a)]
    if not finite.size:
        return dict(count=int(a.size), finite_count=0)
    magnitude = max(float(np.max(np.abs(finite))), 1.0)
    scaled = finite / magnitude
    counts, edges = np.histogram(scaled, bins=16, range=(-1, 1))
    edges = edges * magnitude
    return dict(count=int(a.size), finite_count=int(finite.size), minimum=float(finite.min()),
                maximum=float(finite.max()), mean=float(scaled.mean() * magnitude), std=float(scaled.std() * magnitude),
                histogram=dict(counts=counts.tolist(), edges=edges.tolist()))


def sequences(root: Path, include: list[str], exclude: list[str]) -> list[Path]:
    # Match MultiSeqConcatDataset: direct child directories, OR include, OR exclude.
    return [p for p in sorted(root.iterdir()) if p.is_dir()
            and (not include or any(x in p.name for x in include))
            and not any(x in p.name for x in exclude)]


def canonical(row: np.ndarray) -> bytes:
    a = np.asarray(row, dtype="<f4").copy()
    a[a == 0] = 0  # +0 and -0 produce equivalent model inputs.
    return a.tobytes()


def inspect_sequence(path: Path, split: str, p: dict, report: dict,
                     db: sqlite3.Connection, train_sequences: dict, accel_weight: float) -> dict:
    where = f"{split}/{path.name}"
    result = dict(name=path.name, split=split, frames=0, usable=False)
    missing = [name for name in FILES if not (path / name).is_file()]
    if missing:
        issue(report, "error", "missing_files", where, "必要な配列がありません / Missing arrays",
              "抽出処理と必要トピックを確認し、この走行を再抽出してください。", files=missing)
        return result
    try:
        arrays = [np.load(path / name, mmap_mode="r", allow_pickle=False) for name in FILES]
    except (ValueError, OSError, EOFError) as exc:
        issue(report, "error", "unreadable_array", where, "配列を読み込めません / Cannot load arrays",
              "破損・object配列を確認し、元のrosbagから数値配列を再抽出してください。", error=str(exc))
        return result
    scans, steers, accels = arrays
    result["shapes"] = {name: list(a.shape) for name, a in zip(FILES, arrays)}
    if any(a.dtype.kind not in "fiu" for a in arrays):
        issue(report, "error", "invalid_dtype", where, "実数の数値配列が必要です / Non-real dtype",
              "文字列・複素数・boolの配列ではなく、数値配列を再抽出してください。")
        return result
    if scans.ndim != 2 or steers.ndim != 1 or accels.ndim != 1:
        issue(report, "error", "invalid_shape", where, "scans=(N,P), labels=(N,) が必要です / Invalid shape",
              "配列の軸と抽出コードを確認してください。自動reshapeは行いません。")
        return result
    n = len(scans)
    if not n or len(steers) != n or len(accels) != n:
        issue(report, "error", "length_mismatch", where, "空の配列、またはフレーム件数が不一致です / Empty or mismatched lengths",
              "センサーと制御指令を同期して、同じ走行を再抽出してください。")
        return result
    result["frames"] = n
    if scans.shape[1] != p["input_dim"]:
        issue(report, "error", "point_count", where, "スキャン点数が設定と違います / Input dimension mismatch",
              "model.input_dim、センサー設定、重みの入力点数をそろえてください。", expected=p["input_dim"], actual=scans.shape[1])
        return result
    result["steering"] = stats(steers)
    result["acceleration_raw"] = stats(accels)
    if not np.isfinite(steers).all() or not np.isfinite(accels).all():
        issue(report, "error", "nonfinite_labels", where, "ラベルにNaNまたはinfがあります / Non-finite labels",
              "異常な制御指令・同期処理を確認して再抽出してください。")
        return result
    with np.errstate(over="ignore", invalid="ignore"):
        targets = np.where(accels > 0, accels / p["accel_scale"], accels / p["decel_scale"])
    result["acceleration_target"] = stats(targets)
    if not np.isfinite(targets).all():
        issue(report, "error", "nonfinite_scaled_targets", where, "倍率による換算で非有限値が生じます / Scaled targets overflow",
              "加速度の単位と倍率を確認してください。極小の倍率では換算がオーバーフローします。")
        return result
    for name, values, weight in (("steering", steers, 1.0), ("acceleration", targets, accel_weight)):
        outside = int(np.count_nonzero(np.abs(values) > 1))
        boundary = int(np.count_nonzero(np.abs(values) >= 1))
        if outside:
            severity = "error" if weight > 0 else "info"
            issue(report, severity, f"{name}_target_range", where,
                  "教師がtanhの出力範囲を超えています / Targets outside tanh range",
                  "加速度はラベルに合った倍率で再学習し、推論と同じ倍率を使ってください。舵は単位とラベルを確認してください。",
                  count=outside, fraction=outside / n, loss_weight=weight)
        elif boundary and weight > 0:
            issue(report, "warning", f"{name}_saturation", where,
                  "教師が±1に達しています / Targets at saturation boundary",
                  "範囲内でも飽和の影響を検討してください。浮動小数点で±1に丸められる場合があります。", count=boundary)
        if weight > 0 and stats(values).get("std", 0) < 1e-6:
            issue(report, "warning", f"constant_{name}", where, "ほぼ一定のラベルです / Nearly constant labels",
                  "この走行の収録条件を確認してください。一定ラベルだけで学習失敗とは断定できません。")
    if np.any(np.abs(targets) > np.finfo(np.float32).max) or np.any(np.abs(steers) > np.finfo(np.float32).max):
        issue(report, "error", "float32_target_overflow", where, "モデル用float32への変換でラベルがオーバーフローします / Float32 target overflow",
              "教師の単位と加速度倍率を確認してください。")
        return result
    delta = path / "delta_times.npy"
    if delta.is_file():
        try:
            dt = np.load(delta, mmap_mode="r", allow_pickle=False)
            if dt.ndim != 1 or dt.size != n or dt.dtype.kind not in "fiu" or not np.isfinite(dt).all() or np.any(dt < 0):
                raise ValueError("Expected N finite nonnegative sensor/control alignment errors in seconds")
            result["synchronization_error_seconds"] = stats(dt)
        except (ValueError, OSError, EOFError) as exc:
            issue(report, "warning", "invalid_delta_times", where, "補助の同期誤差が不正です / Invalid delta_times",
                  "抽出処理を確認してください。TinyLidarNet本体はこのファイルを使いません。", error=str(exc))

    scan_counts = dict(nan=0, positive_inf=0, negative=0, above_max_range=0, all_equal_frames=0)
    seq_hash = hashlib.sha256(f"{n},{p['input_dim']}\n".encode())
    overlap = dict(shared_scan_frames=0, shared_sample_frames=0, examples=[])
    for start in range(0, n, CHUNK):
        raw = np.asarray(scans[start:start + CHUNK])
        scan_counts["nan"] += int(np.isnan(raw).sum())
        scan_counts["positive_inf"] += int(np.isposinf(raw).sum())
        scan_counts["negative"] += int((raw < 0).sum())
        scan_counts["above_max_range"] += int((raw > p["max_range"]).sum())
        # Same order as upstream: clip -> divide -> cast to float32.
        normal = (np.clip(raw, 0.0, p["max_range"]) / p["max_range"]).astype(np.float32)
        scan_counts["all_equal_frames"] += int(np.all(normal == normal[:, :1], axis=1).sum())
        if not np.isfinite(normal).all():
            continue
        for offset, row in enumerate(normal):
            idx = start + offset
            scan_bytes = canonical(row)
            labels = canonical(np.array([targets[idx], steers[idx]]))
            sample = hashlib.sha256(scan_bytes + labels).digest()
            scan = hashlib.sha256(scan_bytes).digest()
            seq_hash.update(scan_bytes + labels)
            location = f"{where}:{idx}"
            if split == "train":
                db.execute("INSERT OR IGNORE INTO samples VALUES (?,?)", (sample, location))
                db.execute("INSERT OR IGNORE INTO scans VALUES (?,?)", (scan, location))
            else:
                same_sample = db.execute("SELECT example FROM samples WHERE hash=?", (sample,)).fetchone()
                same_scan = db.execute("SELECT example FROM scans WHERE hash=?", (scan,)).fetchone()
                overlap["shared_scan_frames"] += int(same_scan is not None)
                overlap["shared_sample_frames"] += int(same_sample is not None)
                if same_scan and len(overlap["examples"]) < 5:
                    overlap["examples"].append(dict(train=same_scan[0], val=location, same_labels=bool(same_sample)))
        db.commit()
    result["scan_values"] = scan_counts
    if scan_counts["nan"]:
        issue(report, "error", "nan_scans", where, "スキャンにNaNがあります / NaN scans",
              "抽出時の無反射処理を確認してください。+infとNaNは区別します。", count=scan_counts["nan"])
        return result
    if scan_counts["negative"]:
        issue(report, "warning", "negative_scans", where, "負の距離が0にクリップされます / Negative distances clipped",
              "距離の単位と無効値処理を確認してください。", count=scan_counts["negative"])
    if scan_counts["all_equal_frames"]:
        issue(report, "warning", "constant_scans", where, "全点が同じになるフレームがあります / Spatially constant scans",
              "LiDARが有効か、無反射のみのフレームか確認してください。静止や空間条件でも生じ得ます。", count=scan_counts["all_equal_frames"])
    # +inf is valid here: the upstream loader clips it to max_range, then normalises to 1.
    result["usable"] = True
    fingerprint = seq_hash.hexdigest()
    result["normalised_sequence_sha256"] = fingerprint
    if split == "train":
        train_sequences.setdefault(fingerprint, where)
    else:
        result["overlap"] = overlap
        if fingerprint in train_sequences:
            issue(report, "warning", "identical_sequence", where,
                  "訓練側と全サンプルが同一です / Sequence identical to training",
                  "同じ収録のコピーなら走行単位で分割し直してください。独立に得た定数データの可能性も収録履歴で確認してください。",
                  train=train_sequences[fingerprint], frames=n)
        if overlap["shared_scan_frames"]:
            issue(report, "warning", "shared_validation_inputs", where,
                  "訓練側と同一の入力が検証側にあります / Shared validation inputs",
                  "収録元と分割方法を確認してください。静止中の同一入力も含み、これだけでは漏洩と断定できません。", **overlap)
    return result


def audit(train: Path, val: Path | None, params: dict, *, include=(), exclude=(),
          accel_weight=1.0, batch_size=64, inference_params=None) -> dict:
    report = dict(schema_version=1, tool_version=VERSION, parameters=params, findings=[], sequences=[],
                  checks=dict(overlap="all valid frames after upstream preprocessing; float32 exact hashes",
                              independence="not verified; inspect recording provenance and near-time splits"))
    if inference_params is not None and params != inference_params:
        issue(report, "error", "parameter_mismatch", "settings", "学習と推論の共通設定が違います / Parameter mismatch",
              "重みを学習した設定を保存し、その設定を推論に使ってください。", training=params, inference=inference_params)
    with tempfile.TemporaryDirectory(prefix="tln-dataset-index-") as tmp:
        with sqlite3.connect(str(Path(tmp) / "index.sqlite")) as db:
            db.execute("CREATE TABLE samples (hash BLOB PRIMARY KEY, example TEXT)")
            db.execute("CREATE TABLE scans (hash BLOB PRIMARY KEY, example TEXT)")
            fingerprints = {}
            for split, root in (("train", train), ("val", val)):
                if root is None:
                    issue(report, "warning", "validation_not_checked", split, "検証データが未指定です / No validation split",
                          "--valで検証用の走行を指定してください。重複検査は未実施です。")
                    continue
                if not root.is_dir():
                    issue(report, "error", "missing_root", split, "データルートがありません / Missing dataset root",
                          "dataset/train・dataset/valのパスを確認してください。", path=str(root))
                    continue
                selected = sequences(root, list(include), list(exclude))
                if not selected:
                    issue(report, "error", "no_sequences", split, "対象の走行ディレクトリがありません / No sequences",
                          "ルート直下の走行ディレクトリとinclude/exclude条件を確認してください。")
                for path in selected:
                    report["sequences"].append(inspect_sequence(path, split, params, report, db, fingerprints, accel_weight))
    counts = {split: sum(x["frames"] for x in report["sequences"] if x["split"] == split and x["usable"])
              for split in ("train", "val")}
    if counts["train"] and counts["train"] < batch_size:
        issue(report, "warning", "small_training_set", "train", "学習件数がbatch_size未満です / Fewer samples than batch size",
              "drop_last=Trueの版では学習バッチが0になります。実際のtrain.pyを確認し、batch_sizeを下げるか走行を追加してください。",
              frames=counts["train"], batch_size=batch_size)
    if not counts["train"]:
        issue(report, "error", "no_usable_training_data", "train", "検査を通る訓練データがありません / No usable training data",
              "上のファイル・形状・数値のエラーを解決してください。")
    if val is not None and not counts["val"]:
        issue(report, "error", "no_usable_validation_data", "val", "検査を通る検証データがありません / No usable validation data",
              "独立した走行を検証側に用意し、上のエラーを解決してください。")
    report["summary"] = dict(frames=counts, errors=sum(x["severity"] == "error" for x in report["findings"]),
                             warnings=sum(x["severity"] == "warning" for x in report["findings"]))
    return report


def render_html(report: dict) -> str:
    e = lambda x: html.escape(str(x), quote=True)
    summary = report["summary"]
    findings = "".join(f'<article class="{e(f["severity"])}"><b>{e(f["severity"].upper())}: {e(f["code"])}</b>'
                       f'<p>{e(f["location"])} — {e(f["message"])}</p><p>{e(f["action"])}</p>'
                       f'<pre>{e(json.dumps(f["details"],ensure_ascii=False,indent=2))}</pre></article>'
                       for f in report["findings"])
    rows = []
    for seq in report["sequences"]:
        charts = []
        for key in ("steering", "acceleration_target"):
            st = seq.get(key, {})
            hist = st.get("histogram")
            if not hist:
                continue
            peak = max(hist["counts"]) or 1
            bars = "".join(f'<rect x="{i*20}" y="{70-count/peak*60:.2f}" width="18" height="{count/peak*60:.2f}"><title>{count} samples, [{hist["edges"][i]:.4g}, {hist["edges"][i+1]:.4g}]</title></rect>'
                           for i, count in enumerate(hist["counts"]))
            charts.append(f'<div>{e(key)}: {st["minimum"]:.4g} … {st["maximum"]:.4g}'
                          f'<svg viewBox="0 0 320 80" role="img" aria-label="{e(key)} histogram">{bars}</svg></div>')
        rows.append(f'<tr><td>{e(seq["split"])}/{e(seq["name"])}</td><td>{seq["frames"]}</td>'
                    f'<td>{"usable" if seq["usable"] else "invalid"}</td><td>{"".join(charts)}</td></tr>')
    return f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>TinyLidarNet Dataset Check</title><style>
body{{font:16px/1.7 system-ui,sans-serif;max-width:1100px;margin:32px auto;padding:0 20px;color:#172b3a;background:#f7fafc}}
h1{{line-height:1.3}}article{{background:white;padding:16px;margin:16px 0;border-left:5px solid #567886}}
.error{{border-color:#ad3434}}.warning{{border-color:#9b6500}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}}
table{{width:100%;border-collapse:collapse}}td,th{{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid #bac9d2}}
svg{{display:block;width:320px;max-width:100%;fill:#167580}}details{{margin:16px 0}}.table{{overflow-x:auto}}
</style><h1>TinyLidarNet 学習データ診断</h1>
<p>train: {summary["frames"]["train"]:,} / val: {summary["frames"]["val"]:,} frames · errors: {summary["errors"]} · warnings: {summary["warnings"]}</p>
<p>データを修正しない読み取り検査です。警告は確認の入口です。無警告でも、時刻の近いフレームや同じコースへの過適合、走行性能は保証できません。</p>
<details><summary>検査に使った設定 / Parameters</summary><pre>{e(json.dumps(dict(parameters=report["parameters"], sources=report.get("settings_sources", {})),ensure_ascii=False,indent=2))}</pre></details>
{findings or '<p>この検査範囲で指摘はありません / No findings within the checked scope.</p>'}
<h2>走行ごとのラベル分布 / Sequences</h2><div class="table"><table><thead><tr><th>Sequence</th><th>Frames</th><th>Structure</th><th>Labels</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
<p>入力は公式ローダーと同じ clip → 正規化 → float32 の順で照合します。加速度は正負それぞれの倍率で割ります。重み・実際の学習設定との一致は利用者が確認してください。</p></html>'''


def positive(value: str) -> float:
    n = float(value)
    if not math.isfinite(n) or n <= 0:
        raise argparse.ArgumentTypeError("must be positive and finite")
    return n


def write_reports(outputs) -> None:
    """Reserve all outputs before writing; remove our new files on failure."""
    selected = [(path, content) for path, content in outputs if path is not None]
    destinations = [path.resolve() for path, _ in selected]
    if len(set(destinations)) != len(destinations):
        raise ValueError("JSON and HTML output paths must differ / 出力先は別のファイルにしてください")
    created = []
    try:
        with ExitStack() as stack:
            streams = []
            for path, content in selected:
                stream = stack.enter_context(path.open("x", encoding="utf-8"))
                created.append(path)
                streams.append((stream, content))
            for stream, content in streams:
                stream.write(content)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="TinyLidarNet .npy data check / 学習前の読み取り診断")
    ap.add_argument("--train", type=Path, required=True, help="dataset/train (direct sequence directories)")
    ap.add_argument("--val", type=Path, help="dataset/val; required to check cross-split overlap")
    ap.add_argument("--common-params", type=Path, help="training tiny_lidar_net_common.param.yaml")
    ap.add_argument("--inference-common-params", type=Path, help="optional inference YAML to compare")
    ap.add_argument("--input-dim", type=int)
    for name in ("max-range", "accel-scale", "decel-scale"):
        ap.add_argument(f"--{name}", type=positive)
    ap.add_argument("--include", action="append", default=[], help="sequence-name substring, OR, as upstream")
    ap.add_argument("--exclude", action="append", default=[], help="sequence-name substring, OR, as upstream")
    ap.add_argument("--accel-weight", type=float, default=1.0, help="actual train.loss.accel_weight; 0 disables accel range errors")
    ap.add_argument("--batch-size", type=int, default=64, help="actual training batch size")
    ap.add_argument("--json", type=Path, help="write machine-readable report")
    ap.add_argument("--html", type=Path, help="write standalone offline HTML report")
    ap.add_argument("--strict", action="store_true", help="exit 1 for warnings as well as errors")
    ap.add_argument("--version", action="version", version=VERSION)
    args = ap.parse_args(argv)
    if not math.isfinite(args.accel_weight) or args.accel_weight < 0 or args.batch_size < 1:
        ap.error("accel-weight must be nonnegative and finite; batch-size must be positive")
    try:
        overrides = {name: getattr(args, name) for name in DEFAULTS}
        p = parameters(args.common_params, overrides)
        inference = parameters(args.inference_common_params, {}) if args.inference_common_params else None
        report = audit(args.train, args.val, p, include=args.include, exclude=args.exclude,
                       accel_weight=args.accel_weight, batch_size=args.batch_size, inference_params=inference)
        report["settings_sources"] = dict(training=str(args.common_params) if args.common_params else "CLI/defaults; verify actual training settings",
                                          inference=str(args.inference_common_params) if args.inference_common_params else None,
                                          include=args.include, exclude=args.exclude, accel_weight=args.accel_weight, batch_size=args.batch_size)
        encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        # Exclusive creation protects inputs and existing reports. Roll back new
        # outputs if either reservation or writing fails.
        write_reports(((args.json, encoded), (args.html, render_html(report))))
    except (ValueError, TypeError, AttributeError, OSError, yaml.YAMLError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = report["summary"]
    print(f'Train {summary["frames"]["train"]} / Val {summary["frames"]["val"]} frames; '
          f'{summary["errors"]} errors, {summary["warnings"]} warnings')
    for f in report["findings"]:
        print(f'{f["severity"].upper()} [{f["code"]}] {f["location"]}: {f["message"]}\n  {f["action"]}')
    return int(bool(summary["errors"] or (args.strict and summary["warnings"])))


if __name__ == "__main__":
    sys.exit(main())
