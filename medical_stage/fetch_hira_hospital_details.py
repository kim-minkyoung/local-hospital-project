#!/usr/bin/env python3
"""Fetch HIRA hospital detail resources for tertiary/general hospitals.

API: 건강보험심사평가원_의료기관별상세정보서비스
Source: https://www.data.go.kr/data/15001699/openapi.do
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


BASE_URL = "https://apis.data.go.kr/B551182/MadmDtlInfoService2.8"

DETAIL_ENDPOINTS = {
    "departments": "getDgsbjtInfo2.8",
    "specialists": "getSpcSbjtSdrInfo2.8",
    "equipment": "getMedOftInfo2.8",
    "special_care": "getSpclDiagInfo2.8",
}

TARGET_CLASS_CODES = {"1", "11"}
TARGET_CLASS_NAMES = {"상급종합", "종합병원"}

BASIC_FIELD_MAP = {
    "hospital_id": "ykiho",
    "hospital_name": "yadmNm",
    "hospital_type": "clCdNm",
    "address": "addr",
    "sido": "sidoCdNm",
    "sigungu": "sgguCdNm",
    "longitude": "XPos",
    "latitude": "YPos",
}


def build_url(service_key: str, endpoint: str, params: dict[str, str | int]) -> str:
    query = urllib.parse.urlencode(params)
    key = urllib.parse.quote(service_key, safe="%")
    return f"{BASE_URL}/{endpoint}?ServiceKey={key}&{query}"


def fetch_xml(url: str, timeout: int) -> ET.Element:
    request = urllib.request.Request(url, headers={"User-Agent": "python-hira-detail-loader/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        preview = body.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"XML 파싱 실패: {preview}") from exc


def parse_items(root: ET.Element) -> tuple[list[dict[str, str]], int, str, str]:
    result_code = root.findtext(".//resultCode", "")
    result_msg = root.findtext(".//resultMsg", "")
    total_count = int(root.findtext(".//totalCount", "0") or "0")
    items = []

    for item in root.findall(".//item"):
        row = {child.tag: (child.text or "").strip() for child in list(item)}
        items.append(row)

    return items, total_count, result_code, result_msg


def load_basis_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile)
        rows = list(reader)

    filtered = []
    for row in rows:
        class_code = str(row.get("clCd", "")).strip()
        normalized_class_code = class_code.lstrip("0") or class_code
        class_name = row.get("clCdNm", "").strip()
        if normalized_class_code in TARGET_CLASS_CODES or class_name in TARGET_CLASS_NAMES:
            filtered.append(row)
    return filtered


def load_existing_raw(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    existing: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as infile:
        for line in infile:
            if not line.strip():
                continue
            record = json.loads(line)
            hospital_id = record.get("hospital_id")
            if hospital_id:
                existing[hospital_id] = record
    return existing


def fetch_endpoint_items(
    service_key: str,
    endpoint: str,
    hospital_id: str,
    *,
    num_rows: int,
    timeout: int,
    sleep: float,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    page_no = 1
    all_rows: list[dict[str, str]] = []
    total_count = 0
    result_code = ""
    result_msg = ""

    while True:
        params = {
            "ykiho": hospital_id,
            "numOfRows": num_rows,
            "pageNo": page_no,
        }
        url = build_url(service_key, endpoint, params)
        root = fetch_xml(url, timeout)
        rows, total_count, result_code, result_msg = parse_items(root)

        if result_code and result_code != "00":
            raise RuntimeError(f"API 오류: endpoint={endpoint}, resultCode={result_code}, resultMsg={result_msg}")

        all_rows.extend(rows)
        if not rows or not total_count or len(all_rows) >= total_count:
            break

        page_no += 1
        time.sleep(sleep)

    meta = {
        "total_count": total_count,
        "result_code": result_code,
        "result_msg": result_msg,
        "fetched_count": len(all_rows),
    }
    return all_rows, meta


def fetch_hospital_detail(
    basis_row: dict[str, str],
    service_key: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    hospital_id = basis_row["ykiho"]
    detail: dict[str, Any] = {
        "hospital_id": hospital_id,
        "basis": {target: basis_row.get(source, "") for target, source in BASIC_FIELD_MAP.items()},
        "resources": {},
        "meta": {},
        "success": True,
        "errors": {},
    }

    for resource_name, endpoint in DETAIL_ENDPOINTS.items():
        try:
            rows, meta = fetch_endpoint_items(
                service_key,
                endpoint,
                hospital_id,
                num_rows=args.num_rows,
                timeout=args.timeout,
                sleep=args.sleep,
            )
            detail["resources"][resource_name] = rows
            detail["meta"][resource_name] = meta
        except Exception as exc:  # noqa: BLE001 - keep collection running per hospital.
            detail["resources"][resource_name] = []
            detail["meta"][resource_name] = {"fetched_count": 0}
            detail["success"] = False
            detail["errors"][resource_name] = str(exc)

        time.sleep(args.sleep)

    return detail


def first_existing_value(rows: list[dict[str, str]], preferred_fields: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    seen = set()
    for row in rows:
        value = ""
        for field in preferred_fields:
            candidate = row.get(field, "").strip()
            if candidate:
                value = candidate
                break
        if value and value not in seen:
            values.append(value)
            seen.add(value)
    return values


def specialist_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        name = ""
        for field in ("dgsbjtCdNm", "dgsbjtNm", "spcSbjtCdNm", "spcSbjtNm"):
            if row.get(field, "").strip():
                name = row[field].strip()
                break
        if not name:
            name = row.get("spcSbjtCd", row.get("dgsbjtCd", "")).strip()
        if not name:
            continue

        count = 0
        for field in ("sdrCnt", "dtlSdrCnt", "spcSbjtSdrCnt", "totSdrCnt"):
            raw = row.get(field, "").strip()
            if raw:
                try:
                    count = int(float(raw))
                    break
                except ValueError:
                    count = 0
        counts[name] = counts.get(name, 0) + count
    return counts


def summarize_detail(record: dict[str, Any]) -> dict[str, str]:
    basis = record["basis"]
    resources = record["resources"]
    departments = first_existing_value(
        resources.get("departments", []),
        ("dgsbjtCdNm", "dgsbjtNm", "spcSbjtCdNm", "spcSbjtNm"),
    )
    equipment = first_existing_value(
        resources.get("equipment", []),
        ("oftCdNm", "oftNm", "medOftCdNm", "eqpCdNm", "eqpNm"),
    )
    special_care = first_existing_value(
        resources.get("special_care", []),
        ("spclDiagCdNm", "spclDiagNm", "diagCdNm", "diagNm"),
    )

    counts = specialist_counts(resources.get("specialists", []))
    endpoint_counts = {
        name: len(resources.get(name, []))
        for name in DETAIL_ENDPOINTS
    }

    return {
        **basis,
        "departments": json.dumps(departments, ensure_ascii=False),
        "specialist_counts": json.dumps(counts, ensure_ascii=False, sort_keys=True),
        "equipment": json.dumps(equipment, ensure_ascii=False),
        "special_care": json.dumps(special_care, ensure_ascii=False),
        "detail_success": str(bool(record.get("success"))),
        "detail_errors": json.dumps(record.get("errors", {}), ensure_ascii=False, sort_keys=True),
        "detail_row_counts": json.dumps(endpoint_counts, ensure_ascii=False, sort_keys=True),
    }


def write_summary_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [summarize_detail(record) for record in records]
    fieldnames = [
        "hospital_id",
        "hospital_name",
        "hospital_type",
        "address",
        "sido",
        "sigungu",
        "latitude",
        "longitude",
        "departments",
        "specialist_counts",
        "equipment",
        "special_care",
        "detail_success",
        "detail_errors",
        "detail_row_counts",
    ]

    with output_path.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_raw_record(record: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as outfile:
        outfile.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        outfile.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="상급종합병원/종합병원의 HIRA 상세 의료자원 데이터를 수집합니다."
    )
    parser.add_argument(
        "--service-key",
        default=os.environ.get("DATA_GO_KR_SERVICE_KEY") or os.environ.get("SERVICE_KEY"),
        help="공공데이터포털 인증키. 생략하면 DATA_GO_KR_SERVICE_KEY 또는 SERVICE_KEY 환경변수를 사용합니다.",
    )
    parser.add_argument("--basis", default="output/hira_hosp_basis_all.csv", help="병원 기본정보 CSV 경로")
    parser.add_argument("--output", default="output/hira_hosp_details.csv", help="요약 CSV 저장 경로")
    parser.add_argument("--raw-output", default="output/hira_hosp_details_raw.jsonl", help="원본 상세 JSONL 저장 경로")
    parser.add_argument("--num-rows", type=int, default=200, help="상세 API 페이지당 행 수")
    parser.add_argument("--limit", type=int, default=0, help="테스트용 최대 병원 수. 0이면 전체")
    parser.add_argument("--timeout", type=int, default=30, help="요청 타임아웃 초")
    parser.add_argument("--sleep", type=float, default=0.15, help="API 요청 사이 대기 초")
    parser.add_argument("--resume", action="store_true", help="기존 raw-output에 있는 병원은 다시 호출하지 않습니다.")

    args = parser.parse_args()
    if not args.service_key:
        parser.error("공공데이터포털 인증키가 필요합니다. --service-key 또는 DATA_GO_KR_SERVICE_KEY를 설정하세요.")
    return args


def main() -> None:
    args = parse_args()
    basis_rows = load_basis_rows(Path(args.basis))
    if args.limit:
        basis_rows = basis_rows[: args.limit]

    raw_output_path = Path(args.raw_output)
    output_path = Path(args.output)
    records_by_id = load_existing_raw(raw_output_path) if args.resume else {}
    if not args.resume:
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_output_path.write_text("", encoding="utf-8")

    print(f"target hospitals={len(basis_rows)} existing={len(records_by_id)}", file=sys.stderr)

    for index, basis_row in enumerate(basis_rows, start=1):
        hospital_id = basis_row.get("ykiho", "")
        hospital_name = basis_row.get("yadmNm", "")
        if not hospital_id:
            print(f"[{index}/{len(basis_rows)}] skipped missing ykiho: {hospital_name}", file=sys.stderr)
            continue
        if hospital_id in records_by_id:
            print(f"[{index}/{len(basis_rows)}] reuse {hospital_name}", file=sys.stderr)
            continue

        record = fetch_hospital_detail(basis_row, args.service_key, args)
        records_by_id[hospital_id] = record
        write_raw_record(record, raw_output_path)
        status = "ok" if record["success"] else "partial"
        print(f"[{index}/{len(basis_rows)}] {status} {hospital_name}", file=sys.stderr)

    ordered_records = [
        records_by_id[row["ykiho"]]
        for row in basis_rows
        if row.get("ykiho") in records_by_id
    ]
    write_summary_csv(ordered_records, output_path)
    print(f"saved {len(ordered_records)} rows to {output_path}")
    print(f"saved raw records to {raw_output_path}")


if __name__ == "__main__":
    main()
