"""Regression tests for data defects and read-only/report behaviour."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import numpy as np

import check


class DatasetCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.train = self.root / "train"
        self.val = self.root / "val"
        self.train.mkdir()
        self.val.mkdir()
        self.rng = np.random.default_rng(31)
        self.p = dict(check.DEFAULTS, input_dim=8)
        self.write(self.train / "a")
        self.write(self.val / "b")

    def write(self, path, scans=None, steers=None, accels=None):
        path.mkdir(exist_ok=True)
        data = (self.rng.uniform(0, 25, (70, 8)) if scans is None else scans,
                self.rng.uniform(-0.8, 0.8, 70) if steers is None else steers,
                self.rng.uniform(-0.8, 0.8, 70) if accels is None else accels)
        for name, values in zip(check.FILES, data):
            np.save(path / name, values)

    def run_audit(self, **kwargs):
        return check.audit(self.train, self.val, self.p, **kwargs)

    def codes(self, report):
        return {f["code"] for f in report["findings"]}

    def test_valid_data_passes(self):
        r = self.run_audit()
        self.assertEqual(r["summary"], {"frames": {"train": 70, "val": 70}, "errors": 0, "warnings": 0})

    def test_missing_required_labels(self):
        (self.train / "a/accelerations.npy").unlink()
        self.assertIn("missing_files", self.codes(self.run_audit()))

    def test_shape_does_not_silently_flatten_labels(self):
        self.write(self.train / "a", steers=np.zeros((70, 1)))
        self.assertIn("invalid_shape", self.codes(self.run_audit()))

    def test_length_and_point_count(self):
        self.write(self.train / "a", accels=np.zeros(69))
        self.assertIn("length_mismatch", self.codes(self.run_audit()))
        self.write(self.train / "a", scans=np.zeros((70, 7)))
        self.assertIn("point_count", self.codes(self.run_audit()))

    def test_nan_labels_and_scans(self):
        self.write(self.train / "a", accels=np.full(70, np.nan))
        self.assertIn("nonfinite_labels", self.codes(self.run_audit()))
        self.write(self.train / "a", scans=np.full((70, 8), np.nan))
        self.assertIn("nan_scans", self.codes(self.run_audit()))

    def test_positive_infinity_is_valid_upstream_input(self):
        scans = self.rng.uniform(0, 20, (70, 8))
        scans[:, 0] = np.inf
        self.write(self.train / "a", scans=scans)
        self.assertEqual(self.run_audit()["summary"]["errors"], 0)

    def test_correct_negative_acceleration_scale(self):
        self.write(self.train / "a", accels=np.linspace(-1.6, 1.37, 70))
        self.assertIn("acceleration_target_range", self.codes(self.run_audit()))
        self.p.update(accel_scale=2.0, decel_scale=2.0)
        self.assertNotIn("acceleration_target_range", self.codes(self.run_audit()))

    def test_acceleration_loss_disabled(self):
        self.write(self.train / "a", accels=np.full(70, -1.6))
        r = self.run_audit(accel_weight=0)
        self.assertEqual(r["summary"]["errors"], 0)
        self.assertEqual(next(f for f in r["findings"] if f["code"] == "acceleration_target_range")["severity"], "info")

    def test_overlap_detects_renamed_and_changed_dtype_sequence(self):
        data = [np.load(self.train / "a" / name) for name in check.FILES]
        # Compare after float32 preprocessing, as the actual model sees the data.
        self.write(self.val / "b", *data)
        r = self.run_audit()
        self.assertIn("identical_sequence", self.codes(r))
        self.assertEqual(r["sequences"][1]["overlap"]["shared_sample_frames"], 70)

    def test_preprocessing_equivalence_and_different_labels(self):
        scans = self.rng.uniform(0, 20, (70, 8))
        scans[:, 0] = np.inf
        self.write(self.train / "a", scans=scans)
        val_scans = scans.copy()
        val_scans[:, 0] = 30
        self.write(self.val / "b", scans=val_scans)
        r = self.run_audit()
        overlap = r["sequences"][1]["overlap"]
        self.assertEqual(overlap["shared_scan_frames"], 70)
        self.assertEqual(overlap["shared_sample_frames"], 0)

    def test_filters_match_upstream_directories(self):
        (self.train / "ignored").mkdir()
        (self.val / "ignored").mkdir()
        self.assertNotIn("missing_files", self.codes(self.run_audit(exclude=["ignored"])))

    def test_no_validation_and_invalid_roots_report_incomplete_scope(self):
        r = check.audit(self.train, None, self.p)
        self.assertIn("validation_not_checked", self.codes(r))
        r = check.audit(self.root / "missing", self.val, self.p)
        self.assertIn("missing_root", self.codes(r))

    def test_small_batch_and_parameter_mismatch(self):
        r = self.run_audit(batch_size=128, inference_params=dict(self.p, max_range=25))
        self.assertTrue({"small_training_set", "parameter_mismatch"} <= self.codes(r))

    def test_object_array_is_rejected_without_unpickling(self):
        np.save(self.train / "a/scans.npy", np.array([object()], dtype=object))
        self.assertIn("unreadable_array", self.codes(self.run_audit()))

    def test_invalid_yaml_values(self):
        path = self.root / "common.yaml"
        for content in ('[]', '/**: {}', '/**:\n  ros__parameters:\n    max_range: .nan',
                        '/**:\n  ros__parameters:\n    brake_scale: 2.0'):
            path.write_text(content)
            with self.assertRaises(ValueError):
                check.parameters(path, {})
        for dim in (0, -2, 1.5, True):
            with self.assertRaises(ValueError):
                check.parameters(None, {"input_dim": dim})

    def test_cli_reports_and_does_not_modify_source_or_overwrite(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*.npy")}
        out = self.root / "report.json"
        args = ["--train", str(self.train), "--val", str(self.val), "--input-dim", "8", "--json", str(out)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check.main(args), 0)
            original = out.read_bytes()
            self.assertEqual(check.main(args), 2)
            self.assertEqual(out.read_bytes(), original)
        self.assertTrue(all(p.read_bytes() == contents for p, contents in before.items()))

    def test_strict_warning_exit_and_html_escaping(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check.main(["--train", str(self.train), "--input-dim", "8", "--strict"]), 1)
        r = self.run_audit()
        check.issue(r, "warning", "x", "<script>x</script>", "<img src=x>", "action")
        result = check.render_html(r)
        self.assertNotIn("<script>x</script>", result)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", result)

    def test_auxiliary_delta_times(self):
        np.save(self.train / "a/delta_times.npy", np.zeros(70))
        self.assertEqual(self.run_audit()["summary"]["warnings"], 0)
        np.save(self.train / "a/delta_times.npy", np.array([0] + [0.05] * 69))
        self.assertNotIn("invalid_delta_times", self.codes(self.run_audit()))
        np.save(self.train / "a/delta_times.npy", np.full(70, -1.0))
        self.assertIn("invalid_delta_times", self.codes(self.run_audit()))

    def test_extreme_finite_labels_do_not_break_report(self):
        self.write(self.train / "a", accels=np.linspace(-1e300, 1e300, 70))
        r = self.run_audit()
        import json
        json.dumps(r, allow_nan=False)
        self.assertIn("acceleration_target_range", self.codes(r))
        self.p["decel_scale"] = 1e-300
        self.assertIn("nonfinite_scaled_targets", self.codes(self.run_audit()))


if __name__ == "__main__":
    unittest.main()
