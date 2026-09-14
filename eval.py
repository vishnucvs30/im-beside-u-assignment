"""
procmine.eval
-------------
Metrics for scoring a predicted segmentation against Dataset A ground truth.

Three complementary views, because no single number captures "did you find
the right units of work AND name them consistently":

1. BOUNDARY F1 @ tolerance
   Treat every GT execution start/end as a "true boundary event" and every
   predicted segment start/end as a "predicted boundary event". A predicted
   boundary counts as a hit if it falls within `tol_s` seconds of some true
   boundary (Hungarian-free greedy matching, boundaries sorted by time).
   This measures: did you find the right MOMENTS where work changed.

2. COVERAGE (mean best-IoU)
   For each GT execution, find the predicted segment with the largest
   time-overlap (IoU) and record that IoU; average over all executions.
   This measures: even if boundaries are a few seconds off, are your
   segments the right *shape* and not badly merged/split.

3. LABEL CONSISTENCY (purity / inverse-purity / V-measure-like)
   Restricting to (predicted segment, GT execution) pairs with IoU > 0.3,
   build a contingency table of predicted label vs. true process code and
   report:
     - purity: for each predicted label, % of its mass that is the single
       most common true code (are same-labeled segments actually the same
       process?)
     - inverse purity (completeness): for each true code, % of its mass
       captured by the single most common predicted label (do repeated
       executions of the same process reliably get the same label?)
   The task cares about both: precision of the label AND recall of the
   process's repeated occurrences.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Sequence

from .io_utils import GTExecution
from .segment import Segment


def _to_boundary_events(intervals: Sequence[tuple[datetime, datetime]]):
    evs = []
    for s, e in intervals:
        evs.append(s)
        evs.append(e)
    return sorted(evs)


def boundary_f1(pred_segments: list[Segment], gt_execs: list[GTExecution], tol_s: float = 3.0):
    pred_b = _to_boundary_events([(s.start, s.end) for s in pred_segments])
    true_b = _to_boundary_events([(e.start, e.end) for e in gt_execs])

    matched_true = set()
    tp = 0
    used = [False] * len(true_b)
    for pb in pred_b:
        best_idx, best_dt = None, None
        for i, tb in enumerate(true_b):
            if used[i]:
                continue
            dt = abs((pb - tb).total_seconds())
            if dt <= tol_s and (best_dt is None or dt < best_dt):
                best_idx, best_dt = i, dt
        if best_idx is not None:
            used[best_idx] = True
            tp += 1

    precision = tp / len(pred_b) if pred_b else 0.0
    recall = tp / len(true_b) if true_b else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1,
            "n_pred_boundaries": len(pred_b), "n_true_boundaries": len(true_b)}


def _iou(a_start, a_end, b_start, b_end) -> float:
    latest_start = max(a_start, b_start)
    earliest_end = min(a_end, b_end)
    inter = max(0.0, (earliest_end - latest_start).total_seconds())
    if inter == 0:
        return 0.0
    union = (max(a_end, b_end) - min(a_start, b_start)).total_seconds()
    return inter / union if union else 0.0


def mean_best_iou(pred_segments: list[Segment], gt_execs: list[GTExecution]):
    ious = []
    for ex in gt_execs:
        best = 0.0
        for seg in pred_segments:
            iou = _iou(ex.start, ex.end, seg.start, seg.end)
            if iou > best:
                best = iou
        ious.append(best)
    return sum(ious) / len(ious) if ious else 0.0, ious


def label_consistency(
    pred_segments: list[Segment],
    labels: list[str],
    gt_execs: list[GTExecution],
    iou_thresh: float = 0.3,
):
    contingency: dict[str, Counter] = defaultdict(Counter)  # label -> Counter[code]
    code_totals: Counter = Counter()

    for ex in gt_execs:
        best_iou, best_label = 0.0, None
        for seg, lab in zip(pred_segments, labels):
            iou = _iou(ex.start, ex.end, seg.start, seg.end)
            if iou > best_iou:
                best_iou, best_label = iou, lab
        if best_label is not None and best_iou >= iou_thresh:
            contingency[best_label][ex.code] += 1
            code_totals[ex.code] += 1

    total_matched = sum(code_totals.values())
    if total_matched == 0:
        return {"purity": 0.0, "inverse_purity": 0.0, "n_matched": 0}

    # purity: weighted avg over predicted labels of max-count-code / label-total
    purity_num = sum(max(c.values()) for c in contingency.values())
    purity = purity_num / total_matched

    # inverse purity: for each true code, does ONE predicted label dominate it
    code_to_labelcounts: dict[str, Counter] = defaultdict(Counter)
    for lab, c in contingency.items():
        for code, n in c.items():
            code_to_labelcounts[code][lab] += n
    inv_num = sum(max(c.values()) for c in code_to_labelcounts.values())
    inverse_purity = inv_num / total_matched

    return {
        "purity": purity,
        "inverse_purity": inverse_purity,
        "n_matched": total_matched,
        "n_predicted_labels": len(contingency),
        "n_true_codes": len(code_to_labelcounts),
    }


def evaluate_session(pred_segments, labels, gt_execs, tol_s=3.0, iou_thresh=0.3):
    bf1 = boundary_f1(pred_segments, gt_execs, tol_s=tol_s)
    iou_mean, ious = mean_best_iou(pred_segments, gt_execs)
    lab = label_consistency(pred_segments, labels, gt_execs, iou_thresh=iou_thresh)
    return {
        "n_pred_segments": len(pred_segments),
        "n_gt_executions": len(gt_execs),
        "boundary": bf1,
        "mean_best_iou": iou_mean,
        "labels": lab,
    }
