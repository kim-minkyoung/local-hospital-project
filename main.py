#!/usr/bin/env python3
"""Run the hospital recommendation pipeline from address and disease input.

Input:
  - road-name address
  - disease: 암 / 뇌졸중 / 급성심근경색

Output:
  - 3 recommended hospitals with travel time, road distance, and transport cost
  - output/hira_huff_candidates.csv
  - output/hira_final_recommendations.csv
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Any

from medical_stage.recommend_huff_hospitals import (
    FINAL_COLUMNS,
    HUFF_COLUMNS,
    SUPPORTED_DISEASES,
    add_tmap_routes,
    build_huff_candidates,
    calculate_final_probabilities,
    final_recommendations,
    final_row,
    geocode_address,
    get_tmap_app_key,
    huff_row,
    load_dotenv,
    mark_pareto_candidates,
    mark_selected_candidates,
    write_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="도로명주소와 질병으로 병원 3곳을 추천합니다.")
    parser.add_argument("--address", help="사용자 도로명주소. 생략하면 실행 중 입력받습니다.")
    parser.add_argument("--disease", choices=sorted(SUPPORTED_DISEASES), help="질병명. 생략하면 실행 중 입력받습니다.")
    parser.add_argument("--origin-lat", type=float, help="사용자 위도. 지정하면 주소 지오코딩을 생략합니다.")
    parser.add_argument("--origin-lon", type=float, help="사용자 경도. 지정하면 주소 지오코딩을 생략합니다.")
    parser.add_argument("--candidates", default="output/hira_disease_candidates_semi.csv", help="질병별 1차 후보 CSV")
    parser.add_argument("--profiles", default="output/hira_hospital_profiles.csv", help="병원 통합 프로필 CSV")
    parser.add_argument("--huff-output", default="output/hira_huff_candidates.csv", help="허프 후보 전체 CSV")
    parser.add_argument("--final-output", default="output/hira_final_recommendations.csv", help="최종 추천 CSV")
    parser.add_argument("--alpha", type=float, default=1.0, help="허프모델 역량 민감도")
    parser.add_argument("--beta", type=float, default=2.0, help="허프모델 거리/시간 민감도")
    parser.add_argument("--epsilon", type=float, default=0.1, help="0거리/시간 방지 보정값")
    parser.add_argument(
        "--selection-method",
        choices=("kneedle", "top-n", "top-pct"),
        default="kneedle",
        help="TMAP 전 후보 선정 방식",
    )
    parser.add_argument("--huff-top-n", type=int, default=10, help="selection-method=top-n일 때 후보 수")
    parser.add_argument("--huff-top-pct", type=float, help="selection-method=top-pct일 때 후보 비율")
    parser.add_argument("--min-next-step-candidates", type=int, default=3, help="TMAP 전 최소 후보 병원 수")
    parser.add_argument("--timeout", type=int, default=20, help="API 요청 타임아웃 초")
    return parser.parse_args()


def prompt_for_missing_inputs(args: argparse.Namespace) -> None:
    if args.origin_lat is None or args.origin_lon is None:
        if not args.address:
            args.address = input("도로명주소를 입력하세요: ").strip()
        while not args.address:
            args.address = input("도로명주소는 비워둘 수 없습니다. 다시 입력하세요: ").strip()

    disease_options = sorted(SUPPORTED_DISEASES)
    if not args.disease:
        print("질병을 선택하세요.")
        for index, disease in enumerate(disease_options, start=1):
            print(f"{index}. {disease}")
        value = input("질병명 또는 번호를 입력하세요: ").strip()
        args.disease = disease_options[int(value) - 1] if value.isdigit() and 1 <= int(value) <= len(disease_options) else value

    while args.disease not in SUPPORTED_DISEASES:
        value = input("암, 뇌졸중, 급성심근경색 중 하나를 입력하세요: ").strip()
        args.disease = disease_options[int(value) - 1] if value.isdigit() and 1 <= int(value) <= len(disease_options) else value


def write_final_with_transport_cost(rows: list[dict[str, Any]], path: Path) -> None:
    final_transport_cost = representative_transport_cost(rows)
    fieldnames = [
        *FINAL_COLUMNS,
        "transport_cost",
        "final_transport_cost",
        "final_transport_cost_basis",
    ]
    output_rows = []
    for row in rows:
        serialized = final_row(row)
        taxi_fare = float(serialized.get("taxi_fare") or 0)
        serialized["transport_cost"] = int(taxi_fare)
        serialized["final_transport_cost"] = final_transport_cost
        serialized["final_transport_cost_basis"] = "종합추천 교통비"
        output_rows.append(serialized)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)


def add_transport_cost(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "transport_cost": int(float(row.get("taxi_fare") or 0)),
    }


def representative_transport_cost(rows: list[dict[str, Any]]) -> int:
    for row in rows:
        if row.get("recommendation_type") == "종합추천":
            return int(float(row.get("transport_cost") or 0))
    return 0


def result_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "recommendation_type": row.get("recommendation_type", ""),
        "hospital_name": row.get("hospital_name", ""),
        "hospital_type": row.get("hospital_type", ""),
        "latitude": float(row.get("latitude") or 0),
        "longitude": float(row.get("longitude") or 0),
        "route_path": row.get("route_path") or [],
        "transport_cost": int(float(row.get("transport_cost") or 0)),
        "route_duration_min": round(float(row.get("route_duration_min") or 0), 1),
        "route_distance_km": round(float(row.get("route_distance_km") or 0), 1),
        "taxi_fare": int(float(row.get("taxi_fare") or 0)),
        "toll_fare": int(float(row.get("toll_fare") or 0)),
        "capability_score": float(row.get("capability_score") or 0),
        "final_probability": float(row.get("final_probability") or 0),
    }


def get_result(
    disease: str,
    latitude: float,
    longitude: float,
    *,
    alpha: float = 1.0,
    beta: float = 2.0,
    epsilon: float = 0.1,
    selection_method: str = "kneedle",
    huff_top_n: int = 10,
    huff_top_pct: float | None = None,
    min_next_step_candidates: int = 3,
    timeout: int = 20,
    candidates: str = "output/hira_disease_candidates_semi.csv",
    profiles: str = "output/hira_hospital_profiles.csv",
    huff_output: str = "output/hira_huff_candidates.csv",
    final_output: str = "output/hira_final_recommendations.csv",
    save_csv: bool = True,
) -> dict[str, Any]:
    """Return 3 hospital recommendations for a disease and origin coordinates."""
    load_dotenv()
    if disease not in SUPPORTED_DISEASES:
        raise ValueError("disease는 암, 뇌졸중, 급성심근경색 중 하나여야 합니다.")

    app_key = get_tmap_app_key()
    if not app_key:
        raise RuntimeError(".env에 TMAP_API_KEY 또는 TMAP_APP_KEY가 필요합니다.")

    args = argparse.Namespace(
        address=None,
        disease=disease,
        origin_lat=float(latitude),
        origin_lon=float(longitude),
        candidates=candidates,
        profiles=profiles,
        huff_output=huff_output,
        final_output=final_output,
        alpha=alpha,
        beta=beta,
        epsilon=epsilon,
        selection_method=selection_method,
        huff_top_n=huff_top_n,
        huff_top_pct=huff_top_pct,
        min_next_step_candidates=min_next_step_candidates,
        timeout=timeout,
    )

    huff_candidates = build_huff_candidates(args)
    selected_rows = mark_selected_candidates(huff_candidates, args)
    tmap_success_rows = add_tmap_routes(huff_candidates, args, app_key)
    calculate_final_probabilities(tmap_success_rows, args)
    pareto_rows = mark_pareto_candidates(tmap_success_rows)
    final_rows = [add_transport_cost(row) for row in final_recommendations(tmap_success_rows)]

    if save_csv:
        write_csv([huff_row(row) for row in huff_candidates], Path(huff_output), HUFF_COLUMNS)
        write_final_with_transport_cost(final_rows, Path(final_output))

    recommendations = [result_row(row) for row in final_rows]
    return {
        "disease": disease,
        "origin": {
            "latitude": float(latitude),
            "longitude": float(longitude),
        },
        "recommendations": recommendations,
        "final_transport_cost": representative_transport_cost(final_rows),
        "final_transport_cost_basis": "종합추천 교통비",
        "representative_transport_cost": representative_transport_cost(final_rows),
        "representative_transport_cost_basis": "종합추천 교통비",
        "counts": {
            "disease_candidates": len(huff_candidates),
            "selected_for_tmap": len(selected_rows),
            "tmap_success": len(tmap_success_rows),
            "pareto_candidates": len(pareto_rows),
            "final_recommendations": len(final_rows),
        },
        "output_files": {
            "huff_candidates": huff_output if save_csv else "",
            "final_recommendations": final_output if save_csv else "",
        },
    }


def format_money(value: Any) -> str:
    try:
        return f"{int(float(value)):,}원"
    except (TypeError, ValueError):
        return "0원"


def print_recommendations(rows: list[dict[str, Any]], final_output: str) -> None:
    if not rows:
        print("최종 추천 병원이 없습니다. TMAP 호출 오류 또는 후보 부족 여부를 확인하세요.")
        print(f"결과 파일: {final_output}")
        return

    print("\n최종 추천 병원 3곳")
    for index, row in enumerate(rows, start=1):
        taxi_fare = float(row.get("taxi_fare") or 0)
        toll_fare = float(row.get("toll_fare") or 0)
        transport_cost = taxi_fare
        print(
            f"{index}. [{row['recommendation_type']}] {row['hospital_name']} ({row['hospital_type']})\n"
            f"   소요시간: {float(row['route_duration_min']):.1f}분 | "
            f"도로거리: {float(row['route_distance_km']):.1f}km | "
            f"교통비: {format_money(transport_cost)} "
            f"(택시비 기준, 통행료 참고 {format_money(toll_fare)})"
        )
    print(f"\n최종 교통비: {format_money(representative_transport_cost(rows))} (종합추천 교통비)")
    print(f"\n저장 완료: {final_output}")


def run_pipeline(args: argparse.Namespace) -> list[dict[str, Any]]:
    load_dotenv()
    prompt_for_missing_inputs(args)

    app_key = get_tmap_app_key()
    if not app_key:
        raise RuntimeError(".env에 TMAP_API_KEY 또는 TMAP_APP_KEY가 필요합니다.")

    if args.origin_lat is None or args.origin_lon is None:
        origin_lon, origin_lat = geocode_address(args.address, app_key, args.timeout)
        args.origin_lon = origin_lon
        args.origin_lat = origin_lat

    huff_candidates = build_huff_candidates(args)
    selected_rows = mark_selected_candidates(huff_candidates, args)
    tmap_success_rows = add_tmap_routes(huff_candidates, args, app_key)
    calculate_final_probabilities(tmap_success_rows, args)
    pareto_rows = mark_pareto_candidates(tmap_success_rows)
    final_rows = [add_transport_cost(row) for row in final_recommendations(tmap_success_rows)]

    write_csv([huff_row(row) for row in huff_candidates], Path(args.huff_output), HUFF_COLUMNS)
    write_final_with_transport_cost(final_rows, Path(args.final_output))

    print(
        "pipeline_summary="
        f"질병후보 {len(huff_candidates)}개, "
        f"TMAP전 후보 {len(selected_rows)}개, "
        f"TMAP성공 {len(tmap_success_rows)}개, "
        f"Pareto {len(pareto_rows)}개, "
        f"최종 {len(final_rows)}개"
    )
    return final_rows


def main() -> None:
    args = parse_args()
    rows = run_pipeline(args)
    print_recommendations(rows, args.final_output)


if __name__ == "__main__":
    main()
