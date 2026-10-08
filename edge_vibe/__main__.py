"""Run: python -m edge_vibe --help. No hardware or network I/O is implemented."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys

from . import __version__
from .baseline import DEFAULT_CONFIG, train_baseline, validate_baseline, validate_config
from .data import load_jsonl, strict_json, validate_window, write_json, write_jsonl
from .demo import monitoring_windows, reference_windows
from .dsp import extract_features
from .monitor import replay, summarize
from .outbox import Outbox, validate_message
from .report import export_csv, render_report


def config_from(path):
    return validate_config(strict_json(path.read_text(encoding="utf-8-sig"))) if path else deepcopy(DEFAULT_CONFIG)


def model_from(path):
    return validate_baseline(strict_json(path.read_text(encoding="utf-8-sig")))


def protect_paths(inputs, outputs):
    input_paths = {p.resolve() for p in inputs if p is not None}
    output_paths = [p.resolve() for p in outputs if p is not None]
    if len(set(output_paths)) != len(output_paths) or input_paths.intersection(output_paths):
        raise ValueError("Outputs must be distinct and cannot overwrite inputs")


def compact_message(record):
    validate_message(record)
    message = deepcopy(record)
    if message["kind"] == "assessment":
        for axis in message["features"]["axes"].values():
            axis.pop("spectrum", None)
    return message


def write_analysis(windows, model, output, queue=None):
    assessments, events = replay(windows, model)
    write_jsonl(windows, output / "windows.jsonl")
    write_json(model, output / "baseline.json")
    write_jsonl(assessments, output / "assessments.jsonl")
    write_jsonl(events, output / "events.jsonl")
    export_csv(assessments, output / "measurements.csv")
    summary = summarize(assessments, events)
    write_json(summary, output / "summary.json")
    render_report(windows, assessments, events, model, output / "report.html", queue=queue)
    return assessments, events, summary


ANALYSIS_FILES = ("windows.jsonl", "baseline.json", "assessments.jsonl", "events.jsonl", "measurements.csv", "summary.json", "report.html")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Standalone vibration/temperature monitoring prototype")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Generate simulated motor/actuator monitoring and offline reports")
    demo.add_argument("--output", type=Path, default=Path("demo-output"))
    train = commands.add_parser("train", help="Fit a frozen baseline from explicitly approved reference windows")
    train.add_argument("input", type=Path)
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--config", type=Path)
    features = commands.add_parser("features", help="Extract acceleration and FFT features without a baseline")
    features.add_argument("input", type=Path)
    features.add_argument("--output", type=Path, required=True)
    features.add_argument("--config", type=Path)
    analyze = commands.add_parser("analyze", help="Replay chronological windows against an approved baseline")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--baseline", type=Path, required=True)
    analyze.add_argument("--output", type=Path, required=True, help="Directory for analysis artifacts")
    report = commands.add_parser("report", help="Regenerate a report from waveform records and a baseline")
    report.add_argument("input", type=Path)
    report.add_argument("--baseline", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    outbox = commands.add_parser("outbox", help="Local SQLite queue; no network upload")
    queue = outbox.add_subparsers(dest="queue_command", required=True)
    enqueue = queue.add_parser("enqueue")
    enqueue.add_argument("input", type=Path)
    enqueue.add_argument("--db", type=Path, required=True)
    export = queue.add_parser("export")
    export.add_argument("--db", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--limit", type=int, default=100)
    ack = queue.add_parser("ack", help="Mark the supplied batch acknowledged only after confirmed delivery")
    ack.add_argument("batch", type=Path)
    ack.add_argument("--db", type=Path, required=True)
    status = queue.add_parser("status")
    status.add_argument("--db", type=Path, required=True)
    prune = queue.add_parser("prune", help="Delete acknowledged messages to bound local storage; pending messages are kept")
    prune.add_argument("--db", type=Path, required=True)
    prune.add_argument("--keep", type=int, default=0, help="Keep this many most recent acknowledged messages")
    return parser.parse_args(argv)


def demo(args):
    references, windows = reference_windows(), monitoring_windows()
    model = train_baseline(references)
    write_jsonl(references, args.output / "references.jsonl")
    write_json(DEFAULT_CONFIG, args.output / "config.json")
    assessments, events = replay(windows, model)
    with Outbox(args.output / "outbox.sqlite") as outbox:
        messages = [compact_message(r) for r in assessments + events]
        added = outbox.enqueue(messages)
        duplicate_added = outbox.enqueue(messages)
        batch = outbox.export_batch(10)
        write_json(batch, args.output / "acknowledged-demo-batch.json")
        acknowledged = outbox.acknowledge(batch)  # Demonstration only; no server is contacted.
        pending = outbox.export_batch()
        write_json(pending, args.output / "pending-batch.json")
        queue_summary = {"added": added, "duplicate_added": duplicate_added, "demo_acknowledged": acknowledged, **outbox.status()}
    write_json(queue_summary, args.output / "queue-summary.json")
    _, _, summary = write_analysis(windows, model, args.output, queue_summary)
    return {"provenance": "simulated", **summary, "baseline_groups": len(model["groups"]),
            "ready_groups": sum(g["ready"] for g in model["groups"].values()),
            "queue": queue_summary, "output": str(args.output.resolve())}


def main(argv=None):
    args = parse_args(argv)
    try:
        code = 0
        if args.command == "demo":
            result = demo(args)
        elif args.command == "train":
            protect_paths([args.input, args.config], [args.output])
            model = train_baseline(load_jsonl(args.input, validate_window), config_from(args.config))
            write_json(model, args.output)
            result = {"baseline": str(args.output), "groups": len(model["groups"]),
                      "ready_groups": sum(g["ready"] for g in model["groups"].values()),
                      "excluded": len(model["excluded_reference_ids"])}
        elif args.command == "features":
            protect_paths([args.input, args.config], [args.output])
            config = config_from(args.config)
            windows = load_jsonl(args.input, validate_window)
            records = [{"window_id": w["window_id"], "device_id": w["device_id"], "asset_id": w["asset_id"],
                        "provenance": w["provenance"], "features": extract_features(w, config)} for w in windows]
            write_jsonl(records, args.output)
            result = {"windows": len(records), "features": str(args.output)}
        elif args.command in ("analyze", "report"):
            targets = [args.output / name for name in ANALYSIS_FILES] if args.command == "analyze" else [args.output]
            protect_paths([args.input, args.baseline], targets)
            windows = load_jsonl(args.input, validate_window)
            model = model_from(args.baseline)
            if args.command == "analyze":
                _, _, result = write_analysis(windows, model, args.output)
                code = 1 if result["final_alarm_active"] else 0
            else:
                assessments, events = replay(windows, model)
                result = {"report": str(render_report(windows, assessments, events, model, args.output).resolve())}
        else:
            inputs = [getattr(args, "input", None), getattr(args, "batch", None)]
            protect_paths(inputs, [args.db, getattr(args, "output", None)])
            if args.queue_command in ("status", "export", "ack", "prune") and not args.db.is_file():
                raise ValueError("Outbox database does not exist")
            with Outbox(args.db) as outbox:
                if args.queue_command == "enqueue":
                    records = [compact_message(r) for r in load_jsonl(args.input)]
                    result = {"inserted": outbox.enqueue(records), **outbox.status()}
                elif args.queue_command == "export":
                    batch = outbox.export_batch(args.limit)
                    write_json(batch, args.output)
                    result = {"exported": len(batch["messages"]), **outbox.status()}
                elif args.queue_command == "ack":
                    batch = strict_json(args.batch.read_text(encoding="utf-8-sig"))
                    result = {"acknowledged_now": outbox.acknowledge(batch), **outbox.status()}
                elif args.queue_command == "prune":
                    result = {"deleted": outbox.prune(args.keep), **outbox.status()}
                else:
                    result = outbox.status()
        print(json.dumps(result, indent=2, allow_nan=False))
        return code
    except (ValueError, TypeError, KeyError, OSError, OverflowError, sqlite3.Error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
