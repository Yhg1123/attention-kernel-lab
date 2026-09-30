"""Select the fastest measured attention implementation under explicit constraints."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("results/results.csv"))
    parser.add_argument("--max-relative-error", type=float, default=0.01)
    parser.add_argument("--max-extra-mib", type=float, default=None)
    args = parser.parse_args()
    if args.max_relative_error < 0 or (args.max_extra_mib is not None and args.max_extra_mib < 0):
        parser.error("constraints must be nonnegative")
    with args.results.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    groups: dict[tuple[int, str], list[dict]] = {}
    for row in rows:
        if row["status"] != "ok":
            continue
        if float(row["relative_l2_error"]) > args.max_relative_error:
            continue
        if args.max_extra_mib is not None:
            if not row["peak_extra_mib"] or float(row["peak_extra_mib"]) > args.max_extra_mib:
                continue
        groups.setdefault((int(row["length"]), row["dtype"]), []).append(row)
    print("length,dtype,selected_backend,median_ms,relative_l2_error,peak_extra_mib")
    for key in sorted(groups):
        best = min(groups[key], key=lambda row: float(row["median_ms"]))
        print(",".join((str(key[0]), key[1], best["backend"], best["median_ms"],
                        best["relative_l2_error"], best["peak_extra_mib"])))
    if not groups:
        print("No measured configuration satisfies the constraints.")


if __name__ == "__main__":
    main()
