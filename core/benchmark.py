"""Reproducible synthetic performance case. This script never computes allocations."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time


def dataset(count=500, room_count=60):
    rooms = [dict(id=f"r{i:03}", name=f"Sala {i}", campus_id="campus", building_id=f"b{i % 3}",
                  capacity=30 + (i % 5) * 10, accessible=i % 2 == 0,
                  resources=["projetor", "laboratorio"] if i % 3 == 0 else ["projetor"],
                  status="active", unavailable=[]) for i in range(room_count)]
    classes, meetings = [], []
    for i in range(count):
        classes.append(dict(id=f"c{i:04}", campus_id="campus", size_expected=20 + i % 41,
                            teacher_emails=[f"prof{i}@example.edu"], needs_accessibility=i % 4 == 0,
                            required_resources=["laboratorio"] if i % 10 == 0 else [],
                            preferred_resources=["projetor"], preferred_building_id=f"b{i % 3}", status="approved"))
        hour = 8 + (i // 5 % 7) * 2
        meetings.append(dict(id=f"m{i:04}", class_id=f"c{i:04}", weekday=i % 5,
                             start=f"{hour:02}:00", end=f"{hour + 2:02}:00",
                             start_date="2026-08-03", end_date="2026-12-18"))
    return dict(mode="allocate", rooms=rooms, classes=classes, meetings=meetings, allocations=[])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=os.environ.get("CORE_BINARY", str(Path(__file__).with_name("ensalamento-core.exe" if os.name == "nt" else "ensalamento-core"))))
    parser.add_argument("--runs", type=int, default=3)
    options = parser.parse_args()
    if not 1 <= options.runs <= 20:
        parser.error("runs must be between 1 and 20")
    payload = json.dumps(dataset())
    durations = []
    result = None
    for _ in range(options.runs):
        before = time.perf_counter()
        process = subprocess.run([options.binary], input=payload, text=True, encoding="utf-8", capture_output=True, timeout=30, check=True)
        durations.append(round((time.perf_counter() - before) * 1000, 2))
        result = json.loads(process.stdout)
        if not result["valid"]:
            raise RuntimeError("Synthetic benchmark unexpectedly returned an invalid schedule")
    print(json.dumps(dict(dataset="500 synthetic classes / 500 meetings / 60 rooms, seed-free deterministic generator",
                          platform=platform.platform(), runs=options.runs, wall_time_ms=durations,
                          median_wall_time_ms=statistics.median(durations),
                          allocated=result["statistics"]["allocated"], conflicts=result["statistics"]["conflicts"],
                          candidate_evaluations=result["statistics"]["candidate_evaluations"]), indent=2))


if __name__ == "__main__":
    main()
