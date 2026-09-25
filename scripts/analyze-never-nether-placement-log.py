#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "worldgen-spec" / "never-nether-structures.json"

LINE_RE = re.compile(
    r"\[NeverNetherPlacement\]\s+"
    r"pool=(?P<pool>\S+)\s+"
    r"profile=(?P<profile>\S+)\s+"
    r"mode=(?P<mode>\S+)\s+"
    r"chunk=(?P<chunk_x>-?\d+),(?P<chunk_z>-?\d+)\s+"
    r"result=(?P<result>REJECT|-?\d+)\s+"
    r"reason=(?P<reason>\S+)"
)


def alias_id(structure_id: str) -> str:
    namespace, path = structure_id.split(":", 1)
    safe = f"{namespace}__{path}".replace("/", "__")
    return f"neverfolia:never_nether/start/{safe}"


def structure_aliases() -> dict[str, str]:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for group in spec["placement_groups"].values():
        for entry in group["structures"]:
            result[alias_id(entry["id"])] = entry["id"]
    return result


def parse_log(path: Path) -> list[dict]:
    aliases = structure_aliases()
    events: list[dict] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_no, line in enumerate(fh, 1):
            match = LINE_RE.search(line)
            if not match:
                continue
            raw = match.groupdict()
            result_raw = raw["result"]
            events.append(
                {
                    "line": line_no,
                    "pool": raw["pool"],
                    "structure": aliases.get(raw["pool"], raw["pool"]),
                    "profile": raw["profile"],
                    "mode": raw["mode"],
                    "chunk_x": int(raw["chunk_x"]),
                    "chunk_z": int(raw["chunk_z"]),
                    "accepted": result_raw != "REJECT",
                    "y": None if result_raw == "REJECT" else int(result_raw),
                    "reason": raw["reason"],
                }
            )
    return events


def summarize(events: list[dict]) -> dict:
    accepted = [event for event in events if event["accepted"]]
    rejected = [event for event in events if not event["accepted"]]

    by_structure: dict[str, dict] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        grouped[event["structure"]].append(event)

    for structure in sorted(grouped):
        group = grouped[structure]
        ok = [event for event in group if event["accepted"]]
        bad = [event for event in group if not event["accepted"]]
        ys = [event["y"] for event in ok if event["y"] is not None]
        by_structure[structure] = {
            "decisions": len(group),
            "accepted": len(ok),
            "rejected": len(bad),
            "accept_rate": round(len(ok) / len(group), 4) if group else 0.0,
            "accepted_y_min": min(ys) if ys else None,
            "accepted_y_median": statistics.median(ys) if ys else None,
            "accepted_y_max": max(ys) if ys else None,
            "rejection_reasons": dict(sorted(Counter(event["reason"] for event in bad).items())),
        }

    candidate_keys = [
        (event["structure"], event["chunk_x"], event["chunk_z"])
        for event in events
    ]
    duplicates = sum(count - 1 for count in Counter(candidate_keys).values() if count > 1)

    return {
        "decisions": len(events),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "accept_rate": round(len(accepted) / len(events), 4) if events else 0.0,
        "duplicate_candidate_decisions": duplicates,
        "rejection_reasons": dict(sorted(Counter(event["reason"] for event in rejected).items())),
        "by_structure": by_structure,
    }


def print_text(summary: dict) -> None:
    print("NeverNether placement diagnostics")
    print(f"  decisions: {summary['decisions']}")
    print(f"  accepted:  {summary['accepted']}")
    print(f"  rejected:  {summary['rejected']}")
    print(f"  accept rate: {summary['accept_rate']:.2%}")
    print(f"  duplicate candidate decisions: {summary['duplicate_candidate_decisions']}")

    if summary["rejection_reasons"]:
        print("\nRejection reasons:")
        for reason, count in summary["rejection_reasons"].items():
            print(f"  {reason}: {count}")

    if summary["by_structure"]:
        print("\nPer structure:")
        for structure, item in summary["by_structure"].items():
            y_range = "-"
            if item["accepted_y_min"] is not None:
                y_range = (
                    f"{item['accepted_y_min']}..{item['accepted_y_max']} "
                    f"(median {item['accepted_y_median']})"
                )
            print(
                f"  {structure}: decisions={item['decisions']} "
                f"accepted={item['accepted']} rejected={item['rejected']} "
                f"rate={item['accept_rate']:.2%} Y={y_range}"
            )
            for reason, count in item["rejection_reasons"].items():
                print(f"    reject/{reason}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize NeverNether native placement diagnostics from server.log"
    )
    parser.add_argument("log", type=Path, help="Paper/Folia server.log containing placement diagnostics")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--output", type=Path, help="Also write the summary to this file")
    args = parser.parse_args()

    if not args.log.is_file():
        parser.error(f"log file not found: {args.log}")

    events = parse_log(args.log)
    summary = summarize(events)
    if args.json:
        rendered = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
        print(rendered, end="")
    else:
        print_text(summary)
        rendered = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")

    if not events:
        raise SystemExit(
            "No NeverNether placement decisions found. Start the server with "
            "-Dneverfolia.nevernether.debugPlacement=true and generate candidate regions."
        )


if __name__ == "__main__":
    main()
