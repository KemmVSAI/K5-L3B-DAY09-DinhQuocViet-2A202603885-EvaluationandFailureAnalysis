"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    for label, report in (("pr", pr), ("baseline", base)):
        for metric_id, value in (report.get("metrics") or {}).items():
            if isinstance(value, float) and not math.isfinite(value):
                problems.append(f"{label}.metrics.{metric_id} is not finite")

    pr_manifest = pr.get("manifest") or {}
    rows = pr.get("rows") or []
    expected_rows = int(pr_manifest.get("items") or 0) * len(pr_manifest.get("seeds") or [])
    if len(rows) != expected_rows:
        problems.append(f"row count {len(rows)} != items {pr_manifest.get('items')} x seeds {len(pr_manifest.get('seeds') or [])}")

    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    base_keys = [(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []]
    if len(keys) != len(set(keys)):
        problems.append("duplicate (item_id, seed) rows")
    if set(keys) != set(base_keys):
        problems.append("(item_id, seed) set differs from baseline")

    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures={len(pr['evaluator_failures'])}")

    pr_metrics_by_id = {m.get("id"): m for m in spec.get("metrics") or []}
    row_keys: set[str] = set()
    for row in rows + (base.get("rows") or []):
        row_keys.update(row)
    row_metric_ids = row_keys & set(pr_metrics_by_id)
    for row in rows:
        missing = [metric_id for metric_id in sorted(row_metric_ids) if row.get(metric_id) is None]
        if missing:
            problems.append(f"row {row.get('item_id')}@{row.get('seed')} has missing metrics: {','.join(missing)}")
            break

    pr_slices = {r.get("item_id"): tuple(sorted(r.get("slices") or [])) for r in rows}
    base_slices = {r.get("item_id"): tuple(sorted(r.get("slices") or [])) for r in base.get("rows") or []}
    if pr_slices != base_slices:
        problems.append("slice tags differ from baseline")

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        problems.extend(_looser_spec_problems(spec, base_spec))
    return problems


def _looser_spec_problems(spec: dict, base_spec: dict) -> list[str]:
    problems: list[str] = []
    base_metrics = {m.get("id"): m for m in base_spec.get("metrics") or []}
    for metric_id, base_metric in base_metrics.items():
        metric = next((m for m in spec.get("metrics") or [] if m.get("id") == metric_id), None)
        if metric is None:
            problems.append(f"metric {metric_id} disappeared")
            continue
        base_threshold = base_metric.get("threshold") or {}
        threshold = metric.get("threshold") or {}
        for key in ("max", "min", "max_increase", "no_significant_drop"):
            if key in base_threshold and key not in threshold:
                problems.append(f"metric {metric_id} removed {key}")
        if bool(base_metric.get("blocking")) and not metric.get("blocking"):
            problems.append(f"metric {metric_id} became non-blocking")
        for key in ("max", "max_increase"):
            if key in base_threshold and key in threshold and float(threshold[key]) > float(base_threshold[key]):
                problems.append(f"metric {metric_id} raised {key}")
        if "min" in base_threshold and "min" in threshold and float(threshold["min"]) < float(base_threshold["min"]):
            problems.append(f"metric {metric_id} lowered min")
        if base_threshold.get("no_significant_drop") and not threshold.get("no_significant_drop"):
            problems.append(f"metric {metric_id} dropped no_significant_drop")

    base_slices = {s.get("name"): s for s in base_spec.get("slices") or []}
    spec_slices = {s.get("name"): s for s in spec.get("slices") or []}
    for name, base_slice in base_slices.items():
        slice_spec = spec_slices.get(name)
        if slice_spec is None:
            problems.append(f"slice {name} disappeared")
            continue
        if bool(base_slice.get("blocking")) and not slice_spec.get("blocking"):
            problems.append(f"slice {name} became non-blocking")
        if base_slice.get("metric") != slice_spec.get("metric"):
            problems.append(f"slice {name} changed metric")
        if "min" in base_slice and "min" not in slice_spec:
            problems.append(f"slice {name} removed min")
        if "min" in base_slice and "min" in slice_spec and float(slice_spec["min"]) < float(base_slice["min"]):
            problems.append(f"slice {name} lowered min")
        if base_slice.get("no_significant_drop") and not slice_spec.get("no_significant_drop"):
            problems.append(f"slice {name} dropped no_significant_drop")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bootstrap_cfg = spec.get("bootstrap") or {}
    for slice_spec in spec.get("slices") or []:
        name, metric_id = slice_spec.get("name"), slice_spec.get("metric")
        pr_items = per_item(pr, metric_id, slice_name=name)
        base_items = per_item(base, metric_id, slice_name=name)
        keys = sorted(set(pr_items) & set(base_items))
        if not keys:
            value = 0.0
            line = f"  slice {name}/{metric_id:<18} empty"
        else:
            value = sum(pr_items[k] for k in keys) / len(keys)
            if slice_spec.get("no_significant_drop"):
                delta, low, high = stats.paired_bootstrap(
                    [pr_items[k] for k in keys], [base_items[k] for k in keys],
                    n_resamples=int(bootstrap_cfg.get("n_resamples", 1000)),
                    rng=int(bootstrap_cfg.get("rng", 2027)),
                )
                note = f"Δ {delta:+.3f} CI [{low:+.3f}, {high:+.3f}]"
            else:
                note = ""
            line = f"  slice {name}/{metric_id:<18} {value:.4f} {note:<30}"
        failed = False
        if "min" in slice_spec and value < float(slice_spec["min"]):
            failed = True
        if keys and slice_spec.get("no_significant_drop"):
            _, low, high = stats.paired_bootstrap(
                [pr_items[k] for k in keys], [base_items[k] for k in keys],
                n_resamples=int(bootstrap_cfg.get("n_resamples", 1000)),
                rng=int(bootstrap_cfg.get("rng", 2027)),
            )
            failed = failed or high < 0
        if failed:
            if slice_spec.get("blocking"):
                blocked.append(f"slice:{name}/{metric_id}")
            line += " BLOCK" if slice_spec.get("blocking") else " warn"
        else:
            line += " ok"
        lines.append(line)
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
