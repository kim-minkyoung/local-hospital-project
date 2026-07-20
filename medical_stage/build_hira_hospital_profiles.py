#!/usr/bin/env python3
"""Build one-row-per-hospital recommendation profiles from HIRA basis/details."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


TARGET_CLASS_CODES = {"1", "11"}
TARGET_CLASS_NAMES = {"상급종합", "종합병원"}

OUTPUT_COLUMNS = [
    "ykiho",
    "hospital_name",
    "hospital_type",
    "address",
    "latitude",
    "longitude",
    "departments",
    "specialists",
    "equipment",
    "special_treatments",
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as csvfile:
        return list(csv.DictReader(csvfile))


def is_target_hospital(row: dict[str, str]) -> bool:
    class_code = (row.get("clCd") or "").strip()
    normalized_class_code = class_code.lstrip("0") or class_code
    class_name = (row.get("clCdNm") or "").strip()
    return normalized_class_code in TARGET_CLASS_CODES or class_name in TARGET_CLASS_NAMES


def load_detail_records(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as infile:
        for line in infile:
            if not line.strip():
                continue
            record = json.loads(line)
            hospital_id = record.get("hospital_id")
            if hospital_id:
                records[hospital_id] = record
    return records


def unique_values(rows: list[dict[str, str]], fields: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    seen = set()
    for row in rows:
        value = ""
        for field in fields:
            candidate = (row.get(field) or "").strip()
            if candidate:
                value = candidate
                break
        if value and value not in seen:
            values.append(value)
            seen.add(value)
    return values


def parse_int(value: str) -> int:
    if not value:
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def specialist_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        name = ""
        for field in ("dgsbjtCdNm", "dgsbjtNm", "spcSbjtCdNm", "spcSbjtNm"):
            candidate = (row.get(field) or "").strip()
            if candidate:
                name = candidate
                break
        if not name:
            continue

        count = 0
        for field in ("dtlSdrCnt", "sdrCnt", "spcSbjtSdrCnt", "totSdrCnt", "dgsbjtPrSdrCnt"):
            count = parse_int((row.get(field) or "").strip())
            if count:
                break
        counts[name] = counts.get(name, 0) + count
    return dict(sorted(counts.items()))


def profile_from_rows(
    basis_row: dict[str, str],
    detail_record: dict[str, Any] | None,
) -> dict[str, str]:
    resources = (detail_record or {}).get("resources", {})
    departments = unique_values(
        resources.get("departments", []),
        ("dgsbjtCdNm", "dgsbjtNm", "spcSbjtCdNm", "spcSbjtNm"),
    )
    equipment = unique_values(
        resources.get("equipment", []),
        ("oftCdNm", "oftNm", "medOftCdNm", "eqpCdNm", "eqpNm"),
    )
    special_treatments = unique_values(
        resources.get("special_care", []),
        ("srchCdNm", "spclDiagCdNm", "spclDiagNm", "diagCdNm", "diagNm"),
    )
    specialists = specialist_counts(resources.get("specialists", []))

    return {
        "ykiho": basis_row.get("ykiho", ""),
        "hospital_name": basis_row.get("yadmNm", ""),
        "hospital_type": basis_row.get("clCdNm", ""),
        "address": basis_row.get("addr", ""),
        "latitude": basis_row.get("YPos", ""),
        "longitude": basis_row.get("XPos", ""),
        "departments": json.dumps(departments, ensure_ascii=False),
        "specialists": json.dumps(specialists, ensure_ascii=False, sort_keys=True),
        "equipment": json.dumps(equipment, ensure_ascii=False),
        "special_treatments": json.dumps(special_treatments, ensure_ascii=False),
    }


def has_no_detail(profile: dict[str, str]) -> bool:
    return (
        json.loads(profile["departments"]) == []
        and json.loads(profile["specialists"]) == {}
        and json.loads(profile["equipment"]) == []
        and json.loads(profile["special_treatments"]) == []
    )


def write_profiles(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HIRA 병원 추천용 통합 프로필 CSV를 생성합니다.")
    parser.add_argument("--basis", default="output/hira_hosp_basis_all.csv", help="병원 기본정보 CSV")
    parser.add_argument("--details-raw", default="output/hira_hosp_details_raw.jsonl", help="상세정보 원본 JSONL")
    parser.add_argument("--output", default="output/hira_hospital_profiles.csv", help="통합 프로필 CSV")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    basis_rows = [row for row in read_csv_rows(Path(args.basis)) if is_target_hospital(row)]
    detail_records = load_detail_records(Path(args.details_raw))
    profiles = [
        profile_from_rows(row, detail_records.get(row.get("ykiho", "")))
        for row in basis_rows
    ]
    write_profiles(profiles, Path(args.output))

    print(f"joined_hospitals={len(profiles)}")
    print(f"hospitals_without_details={sum(1 for row in profiles if has_no_detail(row))}")
    print(f"columns={','.join(OUTPUT_COLUMNS)}")


if __name__ == "__main__":
    main()
