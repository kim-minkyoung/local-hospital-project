#!/usr/bin/env python3
"""Build semi-broad disease candidate hospitals before distance/TMAP calls."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


OUTPUT_COLUMNS = [
    "ykiho",
    "hospital_name",
    "hospital_type",
    "latitude",
    "longitude",
    "disease",
    "matched_reason",
]

CARDIAC_SPECIAL_TREATMENTS = (
    "경피적 좌심방이 폐색술",
    "경피적 대동맥판삽입",
    "심실 보조장치",
    "심장질환자 재택의료",
)


def read_profiles(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as csvfile:
        return list(csv.DictReader(csvfile))


def parse_json(value: str, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def specialist_count(specialists: dict[str, Any], name: str) -> int:
    value = specialists.get(name, 0)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def has_treatment(special_treatments: list[str], keyword: str) -> bool:
    return any(keyword in treatment for treatment in special_treatments)


def matched_diseases(row: dict[str, str]) -> list[tuple[str, str]]:
    specialists = parse_json(row.get("specialists", ""), {})
    special_treatments = parse_json(row.get("special_treatments", ""), [])

    if not specialists and not special_treatments:
        return []

    matches: list[tuple[str, str]] = []

    cancer_reasons = []
    if specialist_count(specialists, "방사선종양학과") >= 1:
        cancer_reasons.append("방사선종양학과 전문의 1명 이상")
    if all(
        specialist_count(specialists, department) >= 1
        for department in ("외과", "병리과", "핵의학과")
    ):
        cancer_reasons.append("외과·병리과·핵의학과 전문의 각각 1명 이상")
    if has_treatment(special_treatments, "조혈모세포이식"):
        cancer_reasons.append("특수진료 조혈모세포이식 포함")
    if cancer_reasons:
        matches.append(("암", "; ".join(cancer_reasons)))

    if all(
        specialist_count(specialists, department) >= 1
        for department in ("신경과", "신경외과", "응급의학과")
    ):
        matches.append(("뇌졸중", "신경과·신경외과·응급의학과 전문의 각각 1명 이상"))

    ami_reasons = []
    has_ami_required = (
        specialist_count(specialists, "내과") >= 1
        and specialist_count(specialists, "응급의학과") >= 1
        and has_treatment(special_treatments, "응급의료기관")
    )
    cardiac_treatment_matches = [
        keyword
        for keyword in CARDIAC_SPECIAL_TREATMENTS
        if has_treatment(special_treatments, keyword)
    ]
    has_ami_extra = (
        specialist_count(specialists, "심장혈관흉부외과") >= 1
        or bool(cardiac_treatment_matches)
    )
    if has_ami_required and has_ami_extra:
        ami_reasons.append("내과·응급의학과 전문의 각각 1명 이상")
        ami_reasons.append("특수진료 응급의료기관 포함")
        if specialist_count(specialists, "심장혈관흉부외과") >= 1:
            ami_reasons.append("심장혈관흉부외과 전문의 1명 이상")
        if cardiac_treatment_matches:
            ami_reasons.append("특수진료 " + "·".join(cardiac_treatment_matches) + " 포함")
        matches.append(("급성심근경색", "; ".join(ami_reasons)))

    return matches


def build_candidates(profiles: list[dict[str, str]]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for row in profiles:
        for disease, reason in matched_diseases(row):
            candidates.append(
                {
                    "ykiho": row.get("ykiho", ""),
                    "hospital_name": row.get("hospital_name", ""),
                    "hospital_type": row.get("hospital_type", ""),
                    "latitude": row.get("latitude", ""),
                    "longitude": row.get("longitude", ""),
                    "disease": disease,
                    "matched_reason": reason,
                }
            )
    return candidates


def write_candidates(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="질병별 1차 후보 병원 CSV를 생성합니다.")
    parser.add_argument("--profiles", default="output/hira_hospital_profiles.csv", help="병원 통합 프로필 CSV")
    parser.add_argument("--output", default="output/hira_disease_candidates_semi.csv", help="질병 후보 CSV")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profiles = read_profiles(Path(args.profiles))
    candidates = build_candidates(profiles)
    write_candidates(candidates, Path(args.output))

    counts: dict[str, int] = {}
    for row in candidates:
        counts[row["disease"]] = counts.get(row["disease"], 0) + 1

    for disease in ("암", "뇌졸중", "급성심근경색"):
        print(f"{disease}: {counts.get(disease, 0)}")


if __name__ == "__main__":
    main()
