import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from procmine.io_utils import load_session_events, load_gt_executions
from procmine.segment import build_segments, label_segments, segments_to_records
from procmine.eval import evaluate_session

DATASET_A = os.path.join(os.path.dirname(__file__), "dataset_a")


def main():
    session_dirs = sorted(
        os.path.join(DATASET_A, d) for d in os.listdir(DATASET_A)
        if os.path.isdir(os.path.join(DATASET_A, d))
    )
    all_records = []
    summary = []
    for sdir in session_dirs:
        session_id = os.path.basename(sdir)
        print(f"\n=== {session_id} ===")
        events = load_session_events(sdir)
        print(f"  events: {len(events)}")
        gt_execs = load_gt_executions(sdir)
        print(f"  gt executions: {len(gt_execs)}")

        segments = build_segments(events)
        labels = label_segments(segments)
        print(f"  predicted segments: {len(segments)}  unique labels: {len(set(labels))}")

        metrics = evaluate_session(segments, labels, gt_execs)
        print(f"  boundary P/R/F1 @3s: "
              f"{metrics['boundary']['precision']:.2f} / "
              f"{metrics['boundary']['recall']:.2f} / "
              f"{metrics['boundary']['f1']:.2f}")
        print(f"  mean best IoU: {metrics['mean_best_iou']:.2f}")
        print(f"  label purity / inverse_purity: "
              f"{metrics['labels']['purity']:.2f} / {metrics['labels']['inverse_purity']:.2f}  "
              f"(matched {metrics['labels']['n_matched']} execs into "
              f"{metrics['labels'].get('n_predicted_labels','?')} labels "
              f"vs {metrics['labels'].get('n_true_codes','?')} true codes)")

        summary.append({"session_id": session_id, **metrics})
        all_records.extend(segments_to_records(session_id, segments, labels))

    print("\n\n=== AGGREGATE ===")
    n = len(summary)
    avg_f1 = sum(s["boundary"]["f1"] for s in summary) / n
    avg_iou = sum(s["mean_best_iou"] for s in summary) / n
    avg_purity = sum(s["labels"]["purity"] for s in summary) / n
    avg_invpurity = sum(s["labels"]["inverse_purity"] for s in summary) / n
    print(f"avg boundary F1@3s:  {avg_f1:.3f}")
    print(f"avg mean-best-IoU:   {avg_iou:.3f}")
    print(f"avg label purity:    {avg_purity:.3f}")
    print(f"avg label inv-purity:{avg_invpurity:.3f}")

    out_path = os.path.join(os.path.dirname(__file__), "segments_dataset_a_sample.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(all_records)} predicted segments to {out_path}")


if __name__ == "__main__":
    main()
