#!/usr/bin/env python3
"""Fetch hospital basis data from HIRA hospital information API.

API: 건강보험심사평가원_병원정보서비스 getHospBasisList
Source: https://www.data.go.kr/data/15001698/openapi.do
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


API_URL = "https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList"


def build_url(service_key: str, params: dict[str, str | int]) -> str:
    query = urllib.parse.urlencode(params)
    key = urllib.parse.quote(service_key, safe="%")
    return f"{API_URL}?ServiceKey={key}&{query}"


def element_text(parent: ET.Element, tag: str, default: str = "") -> str:
    value = parent.findtext(tag)
    return value.strip() if value else default


def fetch_xml(url: str, timeout: int) -> ET.Element:
    request = urllib.request.Request(url, headers={"User-Agent": "python-hira-loader/1.0"})
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


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})

    with output_path.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_hospitals(args: argparse.Namespace) -> list[dict[str, str]]:
    all_rows: list[dict[str, str]] = []
    total_count: int | None = None

    page_no = args.page_no
    while True:
        params: dict[str, str | int] = {
            "numOfRows": args.num_rows,
            "pageNo": page_no,
        }

        optional_params = {
            "sidoCd": args.sido_cd,
            "sgguCd": args.sggu_cd,
            "emdongNm": args.emdong_nm,
            "yadmNm": args.yadm_nm,
            "zipCd": args.zip_cd,
            "clCd": args.cl_cd,
            "dgsbjtCd": args.dgsbjt_cd,
        }
        params.update({key: value for key, value in optional_params.items() if value})

        url = build_url(args.service_key, params)
        root = fetch_xml(url, args.timeout)
        rows, total_count, result_code, result_msg = parse_items(root)

        if result_code and result_code != "00":
            raise RuntimeError(f"API 오류: resultCode={result_code}, resultMsg={result_msg}")

        all_rows.extend(rows)
        print(
            f"page={page_no} fetched={len(rows)} accumulated={len(all_rows)} total={total_count}",
            file=sys.stderr,
        )

        if args.limit and len(all_rows) >= args.limit:
            return all_rows[: args.limit]
        if total_count and len(all_rows) >= total_count:
            return all_rows
        if not rows:
            return all_rows

        if args.max_pages and page_no >= args.page_no + args.max_pages - 1:
            return all_rows

        page_no += 1
        time.sleep(args.sleep)

    return all_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="건강보험심사평가원 병원정보서비스 getHospBasisList 데이터를 CSV로 저장합니다."
    )
    parser.add_argument(
        "--service-key",
        default=os.environ.get("DATA_GO_KR_SERVICE_KEY") or os.environ.get("SERVICE_KEY"),
        help="공공데이터포털 인증키. 생략하면 DATA_GO_KR_SERVICE_KEY 또는 SERVICE_KEY 환경변수를 사용합니다.",
    )
    parser.add_argument("--output", default="output/hira_hosp_basis.csv", help="저장할 CSV 경로")
    parser.add_argument("--num-rows", type=int, default=100, help="페이지당 행 수")
    parser.add_argument("--page-no", type=int, default=1, help="시작 페이지 번호")
    parser.add_argument("--max-pages", type=int, default=0, help="가져올 최대 페이지 수. 0이면 totalCount까지 전체 수집")
    parser.add_argument("--limit", type=int, default=0, help="최대 저장 행 수. 0이면 제한 없음")
    parser.add_argument("--timeout", type=int, default=30, help="요청 타임아웃 초")
    parser.add_argument("--sleep", type=float, default=0.2, help="페이지 요청 사이 대기 초")

    parser.add_argument("--sido-cd", help="시도코드. 예: 서울 110000")
    parser.add_argument("--sggu-cd", help="시군구코드")
    parser.add_argument("--emdong-nm", help="읍면동명")
    parser.add_argument("--yadm-nm", help="요양기관명 검색어")
    parser.add_argument("--zip-cd", help="우편번호")
    parser.add_argument("--cl-cd", help="종별코드. 예: 의원 31")
    parser.add_argument("--dgsbjt-cd", help="진료과목코드")

    args = parser.parse_args()
    if not args.service_key:
        parser.error("공공데이터포털 인증키가 필요합니다. --service-key 또는 DATA_GO_KR_SERVICE_KEY를 설정하세요.")
    return args


def main() -> None:
    args = parse_args()
    rows = load_hospitals(args)
    output_path = Path(args.output)
    write_csv(rows, output_path)
    print(f"saved {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
