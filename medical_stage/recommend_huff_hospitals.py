#!/usr/bin/env python3
"""Huff-model candidate narrowing with Haversine straight-line distance."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


GEOCODE_URL = "https://apis.openapi.sk.com/tmap/geo/fullAddrGeo"
ROUTE_URL = "https://apis.openapi.sk.com/tmap/routes"
SUPPORTED_DISEASES = {"암", "뇌졸중", "급성심근경색"}
DISEASE_SPECIALIST_FIELDS = {
    "암": ("방사선종양학과", "외과", "병리과", "핵의학과"),
    "뇌졸중": ("신경과", "신경외과", "응급의학과"),
    "급성심근경색": ("내과", "응급의학과", "심장혈관흉부외과"),
}

HUFF_COLUMNS = [
    "huff_rank",
    "selected_for_next_step",
    "selection_method",
    "ykiho",
    "hospital_name",
    "hospital_type",
    "disease",
    "specialist_score",
    "hospital_weight",
    "capability_score",
    "straight_distance_km",
    "huff_utility",
    "huff_probability",
    "cumulative_probability",
    "kneedle_score",
    "tmap_success",
    "tmap_error",
    "route_distance_km",
    "route_duration_min",
    "taxi_fare",
    "toll_fare",
    "final_utility",
    "final_probability",
    "is_pareto",
    "matched_reason",
]

FINAL_COLUMNS = [
    "recommendation_type",
    "hospital_name",
    "hospital_type",
    "capability_score",
    "straight_distance_km",
    "route_distance_km",
    "route_duration_min",
    "taxi_fare",
    "toll_fare",
    "final_utility",
    "final_probability",
    "is_pareto",
    "selection_fallback",
    "matched_reason",
]


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_candidates(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as csvfile:
        return list(csv.DictReader(csvfile))


def request_json(
    url: str,
    *,
    app_key: str,
    method: str = "GET",
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    payload = None
    headers = {
        "Accept": "application/json",
        "appKey": app_key,
    }
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def find_lon_lat(value: Any) -> tuple[float, float] | None:
    if isinstance(value, dict):
        key_pairs = (
            ("lon", "lat"),
            ("newLon", "newLat"),
            ("frontLon", "frontLat"),
            ("centerLon", "centerLat"),
        )
        for lon_key, lat_key in key_pairs:
            if lon_key in value and lat_key in value:
                try:
                    lon = float(value[lon_key])
                    lat = float(value[lat_key])
                except (TypeError, ValueError):
                    continue
                if 120 <= lon <= 135 and 30 <= lat <= 45:
                    return lon, lat
        for child in value.values():
            found = find_lon_lat(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_lon_lat(child)
            if found:
                return found
    return None


def geocode_address(address: str, app_key: str, timeout: int) -> tuple[float, float]:
    data = request_json(
        GEOCODE_URL,
        app_key=app_key,
        params={
            "version": "1",
            "format": "json",
            "coordType": "WGS84GEO",
            "addressFlag": "F00",
            "fullAddr": address,
        },
        timeout=timeout,
    )
    found = find_lon_lat(data)
    if not found:
        raise RuntimeError(f"주소 좌표 변환 실패: {address}")
    return found


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def first_numeric(value: Any, keys: tuple[str, ...]) -> int | None:
    if isinstance(value, dict):
        for key in keys:
            if key in value:
                try:
                    return int(float(value[key]))
                except (TypeError, ValueError):
                    pass
        for child in value.values():
            found = first_numeric(child, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = first_numeric(child, keys)
            if found is not None:
                return found
    return None


def extract_route_path(data: dict[str, Any]) -> list[list[float]]:
    """Extract a Leaflet-ready ``[lat, lon]`` path from a TMAP route response."""
    path: list[list[float]] = []

    def append_line(coordinates: Any) -> None:
        if not isinstance(coordinates, list):
            return
        for coordinate in coordinates:
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                continue
            try:
                lon = float(coordinate[0])
                lat = float(coordinate[1])
            except (TypeError, ValueError):
                continue
            point = [lat, lon]
            if not path or path[-1] != point:
                path.append(point)

    for feature in data.get("features", []):
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry", {})
        if not isinstance(geometry, dict):
            continue
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")
        if geometry_type == "LineString":
            append_line(coordinates)
        elif geometry_type == "MultiLineString" and isinstance(coordinates, list):
            for line in coordinates:
                append_line(line)

    return path


def tmap_car_route(
    row: dict[str, str],
    *,
    origin_lat: float,
    origin_lon: float,
    app_key: str,
    timeout: int,
) -> dict[str, str | int | float | None]:
    body = {
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "searchOption": "0",
        "carType": "1",
        "startX": str(origin_lon),
        "startY": str(origin_lat),
        "endX": row["longitude"],
        "endY": row["latitude"],
        "startName": urllib.parse.quote("출발지"),
        "endName": urllib.parse.quote(row.get("hospital_name", "병원")),
    }
    data = request_json(
        ROUTE_URL,
        app_key=app_key,
        method="POST",
        params={"version": "1"},
        body=body,
        timeout=timeout,
    )
    distance_m = first_numeric(data, ("totalDistance", "distance"))
    duration_sec = first_numeric(data, ("totalTime", "time"))
    taxi_fare = first_numeric(data, ("taxiFare",))
    toll_fare = first_numeric(data, ("tollFare",))

    if distance_m is None or duration_sec is None:
        raise RuntimeError(f"TMAP 경로 응답 파싱 실패: {row.get('hospital_name')}")

    return {
        **row,
        "route_distance_km": distance_m / 1000,
        "route_duration_min": duration_sec / 60,
        "taxi_fare": taxi_fare or 0,
        "toll_fare": toll_fare or 0,
        "route_path": extract_route_path(data),
    }


def read_profiles(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as csvfile:
        rows = list(csv.DictReader(csvfile))
    profiles = {}
    for row in rows:
        ykiho = normalize_ykiho(row.get("ykiho", ""))
        if ykiho:
            profiles[ykiho] = {**row, "ykiho": ykiho}
    return profiles


def normalize_ykiho(value: str) -> str:
    return (value or "").strip()


def parse_json_object(value: str) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def numeric_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def specialist_score(specialists: dict[str, Any], disease: str) -> float:
    return sum(numeric_value(specialists.get(name, 0)) for name in DISEASE_SPECIALIST_FIELDS[disease])


def hospital_weight(hospital_type: str) -> float:
    if hospital_type.strip() in {"상급종합", "상급종합병원"}:
        return 2.0
    if hospital_type.strip() == "종합병원":
        return 1.0
    return 1.0


def disease_candidate_rows(rows: list[dict[str, str]], disease: str) -> list[dict[str, str]]:
    seen = set()
    filtered = []
    for row in rows:
        ykiho = normalize_ykiho(row.get("ykiho", ""))
        if row.get("disease") != disease or not ykiho or ykiho in seen:
            continue
        filtered.append({**row, "ykiho": ykiho})
        seen.add(ykiho)
    return filtered


def build_huff_candidates(args: argparse.Namespace) -> list[dict[str, Any]]:
    profiles_by_ykiho = read_profiles(Path(args.profiles))
    candidates = disease_candidate_rows(read_candidates(Path(args.candidates)), args.disease)

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        ykiho = normalize_ykiho(candidate.get("ykiho", ""))
        profile = profiles_by_ykiho.get(ykiho, {})
        specialists = parse_json_object(profile.get("specialists", ""))
        try:
            hospital_lat = float(candidate["latitude"])
            hospital_lon = float(candidate["longitude"])
        except (KeyError, TypeError, ValueError):
            continue

        s_score = specialist_score(specialists, args.disease)
        g_weight = hospital_weight(candidate.get("hospital_type", ""))
        capability_score = s_score * g_weight
        distance_km = haversine_km(args.origin_lat, args.origin_lon, hospital_lat, hospital_lon)
        huff_utility = (capability_score**args.alpha) / ((distance_km + args.epsilon) ** args.beta)

        rows.append(
            {
                "ykiho": ykiho,
                "hospital_name": candidate.get("hospital_name", ""),
                "hospital_type": candidate.get("hospital_type", ""),
                "disease": candidate.get("disease", ""),
                "latitude": candidate.get("latitude", ""),
                "longitude": candidate.get("longitude", ""),
                "specialist_score": s_score,
                "hospital_weight": g_weight,
                "capability_score": capability_score,
                "straight_distance_km": distance_km,
                "huff_utility": huff_utility,
                "matched_reason": candidate.get("matched_reason", ""),
            }
        )

    utility_sum = sum(row["huff_utility"] for row in rows)
    for row in rows:
        row["huff_probability"] = row["huff_utility"] / utility_sum if utility_sum else 0.0

    ranked = sorted(
        rows,
        key=lambda row: (
            -float(row["huff_probability"]),
            -float(row["capability_score"]),
            float(row["straight_distance_km"]),
        ),
    )
    for index, row in enumerate(ranked, start=1):
        row["huff_rank"] = index
        row["selected_for_next_step"] = False
        row["selection_method"] = ""

    cumulative_probability = 0.0
    total_count = len(ranked)
    for index, row in enumerate(ranked, start=1):
        cumulative_probability += float(row["huff_probability"])
        row["cumulative_probability"] = cumulative_probability
        if total_count <= 1:
            row["kneedle_score"] = 0.0
        else:
            x_normalized = (index - 1) / (total_count - 1)
            y_normalized = cumulative_probability
            row["kneedle_score"] = y_normalized - x_normalized

    return ranked


def kneedle_selection_limit(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    best_row = max(
        rows,
        key=lambda row: (
            float(row["kneedle_score"]),
            float(row["cumulative_probability"]),
            -int(row["huff_rank"]),
        ),
    )
    return int(best_row["huff_rank"])


def selection_limit(args: argparse.Namespace, rows: list[dict[str, Any]]) -> int:
    min_candidates = max(1, args.min_next_step_candidates)
    if args.selection_method == "kneedle":
        return max(min_candidates, kneedle_selection_limit(rows))
    if args.selection_method == "top-pct":
        if args.huff_top_pct is None:
            raise RuntimeError("--selection-method top-pct를 쓰려면 --huff-top-pct가 필요합니다.")
        if not 0 < args.huff_top_pct <= 100:
            raise RuntimeError("--huff-top-pct는 0보다 크고 100 이하이어야 합니다.")
        return max(min_candidates, math.ceil(len(rows) * args.huff_top_pct / 100))
    if args.selection_method == "top-n":
        return max(min_candidates, args.huff_top_n)
    raise RuntimeError(f"알 수 없는 selection_method: {args.selection_method}")


def mark_selected_candidates(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    limit = min(selection_limit(args, rows), len(rows))
    for row in rows[:limit]:
        row["selected_for_next_step"] = True
        row["selection_method"] = args.selection_method
    return rows[:limit]


def add_tmap_routes(
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
    app_key: str,
) -> list[dict[str, Any]]:
    successful = []
    for row in rows:
        row["tmap_success"] = ""
        row["tmap_error"] = ""
        row["route_distance_km"] = ""
        row["route_duration_min"] = ""
        row["taxi_fare"] = ""
        row["toll_fare"] = ""
        row["route_path"] = []
        row["final_utility"] = ""
        row["final_probability"] = ""
        row["is_pareto"] = ""
        if not row.get("selected_for_next_step"):
            continue

        try:
            route_row = tmap_car_route(
                {
                    **row,
                    "latitude": str(row["latitude"]),
                    "longitude": str(row["longitude"]),
                },
                origin_lat=args.origin_lat,
                origin_lon=args.origin_lon,
                app_key=app_key,
                timeout=args.timeout,
            )
            row["route_distance_km"] = route_row["route_distance_km"]
            row["route_duration_min"] = route_row["route_duration_min"]
            row["taxi_fare"] = route_row["taxi_fare"]
            row["toll_fare"] = route_row["toll_fare"]
            row["route_path"] = route_row["route_path"]
            row["tmap_success"] = True
            successful.append(row)
        except Exception as exc:  # noqa: BLE001 - keep all other selected hospitals.
            row["tmap_success"] = False
            row["tmap_error"] = str(exc)

    return successful


def calculate_final_probabilities(rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    for row in rows:
        duration_min = float(row["route_duration_min"])
        capability_score = float(row["capability_score"])
        row["final_utility"] = (capability_score**args.alpha) / ((duration_min + args.epsilon) ** args.beta)

    utility_sum = sum(float(row["final_utility"]) for row in rows)
    for row in rows:
        row["final_probability"] = float(row["final_utility"]) / utility_sum if utility_sum else 0.0


def mark_pareto_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pareto_rows = []
    for row in rows:
        duration = float(row["route_duration_min"])
        capability = float(row["capability_score"])
        dominated = False
        for other in rows:
            if other is row:
                continue
            other_duration = float(other["route_duration_min"])
            other_capability = float(other["capability_score"])
            no_worse = other_duration <= duration and other_capability >= capability
            strictly_better = other_duration < duration or other_capability > capability
            if no_worse and strictly_better:
                dominated = True
                break
        row["is_pareto"] = not dominated
        if not dominated:
            pareto_rows.append(row)
    return pareto_rows


def pick_unique(
    rows: list[dict[str, Any]],
    *,
    recommendation_type: str,
    sort_key: Any,
    selected_ykiho: set[str],
    fallback: bool,
) -> dict[str, Any] | None:
    for row in sorted(rows, key=sort_key):
        if row["ykiho"] not in selected_ykiho:
            selected_ykiho.add(row["ykiho"])
            return {
                **row,
                "recommendation_type": recommendation_type,
                "selection_fallback": fallback,
            }
    return None


def pareto_balance_sort_key(pareto_rows: list[dict[str, Any]]) -> Any:
    durations = [float(row["route_duration_min"]) for row in pareto_rows]
    capabilities = [float(row["capability_score"]) for row in pareto_rows]
    min_duration = min(durations)
    max_duration = max(durations)
    min_capability = min(capabilities)
    max_capability = max(capabilities)
    duration_range = max_duration - min_duration
    capability_range = max_capability - min_capability

    def sort_key(row: dict[str, Any]) -> tuple[float, float, float]:
        duration = float(row["route_duration_min"])
        capability = float(row["capability_score"])
        accessibility_score = 1.0 if duration_range == 0 else 1 - ((duration - min_duration) / duration_range)
        capability_score_normalized = (
            1.0 if capability_range == 0 else (capability - min_capability) / capability_range
        )
        distance_from_ideal = math.hypot(1 - accessibility_score, 1 - capability_score_normalized)
        return (
            distance_from_ideal,
            -float(row["final_probability"]),
            float(row["route_duration_min"]),
        )

    return sort_key


def final_recommendations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pareto_rows = [row for row in rows if row.get("is_pareto") is True]
    selected_ykiho: set[str] = set()
    picks = []
    picked_types = set()

    criteria = [
        (
            "접근성추천",
            rows,
            lambda row: (float(row["route_duration_min"]), -float(row["capability_score"])),
        ),
        (
            "원거리 전문역량 대안",
            rows,
            lambda row: (-float(row["capability_score"]), float(row["route_duration_min"])),
        ),
    ]
    if pareto_rows:
        criteria.append(
            (
                "종합추천",
                pareto_rows,
                pareto_balance_sort_key(pareto_rows),
            )
        )

    for recommendation_type, candidate_rows, sort_key in criteria:
        pick = pick_unique(
            candidate_rows,
            recommendation_type=recommendation_type,
            sort_key=sort_key,
            selected_ykiho=selected_ykiho,
            fallback=False,
        )
        if pick is not None:
            picks.append(pick)
            picked_types.add(recommendation_type)

    if len(picks) < 3:
        missing_types = [
            recommendation_type for recommendation_type, _, _ in criteria if recommendation_type not in picked_types
        ]
        fallback_rows = sorted(rows, key=lambda item: -float(item["final_probability"]))
        for recommendation_type in missing_types:
            for row in fallback_rows:
                if row["ykiho"] in selected_ykiho:
                    continue
                selected_ykiho.add(row["ykiho"])
                picks.append(
                    {
                        **row,
                        "recommendation_type": recommendation_type,
                        "selection_fallback": True,
                    }
                )
                break

    return picks


def huff_row(row: dict[str, Any]) -> dict[str, Any]:
    return {column: row.get(column, "") for column in HUFF_COLUMNS}


def final_row(row: dict[str, Any]) -> dict[str, Any]:
    return {column: row.get(column, "") for column in FINAL_COLUMNS}


def write_csv(rows: list[dict[str, Any]], path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def get_tmap_app_key() -> str:
    return (
        os.environ.get("TMAP_APP_KEY")
        or os.environ.get("TMAP_API_KEY")
        or os.environ.get("tmap_app_key")
        or os.environ.get("tmap_api_key")
        or ""
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="허프모델 기반 병원 추천을 실행합니다.")
    parser.add_argument("--address", help="사용자 출발 주소. 생략하면 실행 중 입력받습니다.")
    parser.add_argument("--disease", choices=sorted(SUPPORTED_DISEASES), help="질병명. 생략하면 실행 중 입력받습니다.")
    parser.add_argument("--candidates", default="output/hira_disease_candidates_semi.csv", help="질병별 1차 후보 CSV")
    parser.add_argument("--profiles", default="output/hira_hospital_profiles.csv", help="병원 통합 프로필 CSV")
    parser.add_argument("--huff-output", default="output/hira_huff_candidates.csv", help="허프 후보 전체 CSV")
    parser.add_argument("--final-output", default="output/hira_final_recommendations.csv", help="최종 추천 병원 CSV")
    parser.add_argument("--alpha", type=float, default=1.0, help="허프모델 역량 민감도")
    parser.add_argument("--beta", type=float, default=2.0, help="허프모델 거리 민감도")
    parser.add_argument("--epsilon", type=float, default=0.1, help="0거리 방지용 거리 보정값(km)")
    parser.add_argument(
        "--selection-method",
        choices=("kneedle", "top-n", "top-pct"),
        default="kneedle",
        help="다음 단계 후보 선정 방식",
    )
    parser.add_argument("--huff-top-n", type=int, default=10, help="selection-method=top-n일 때 넘길 허프 상위 병원 수")
    parser.add_argument("--huff-top-pct", type=float, help="selection-method=top-pct일 때 넘길 허프 상위 퍼센트")
    parser.add_argument("--min-next-step-candidates", type=int, default=3, help="다음 단계로 넘길 최소 후보 병원 수")
    parser.add_argument("--origin-lat", type=float, help="사용자 위도. 지정하면 address 지오코딩을 생략합니다.")
    parser.add_argument("--origin-lon", type=float, help="사용자 경도. 지정하면 address 지오코딩을 생략합니다.")
    parser.add_argument("--timeout", type=int, default=20, help="API 요청 타임아웃 초")
    return parser.parse_args()


def prompt_for_missing_inputs(args: argparse.Namespace) -> None:
    if args.origin_lat is None or args.origin_lon is None:
        if not args.address:
            args.address = input("출발 주소를 입력하세요: ").strip()
        while not args.address:
            args.address = input("출발 주소는 비워둘 수 없습니다. 다시 입력하세요: ").strip()

    prompt_for_missing_disease(args)


def prompt_for_missing_disease(args: argparse.Namespace) -> None:
    disease_options = sorted(SUPPORTED_DISEASES)
    if not args.disease:
        print("질병을 선택하세요.")
        for index, disease in enumerate(disease_options, start=1):
            print(f"{index}. {disease}")
        value = input("질병명 또는 번호를 입력하세요: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(disease_options):
            args.disease = disease_options[int(value) - 1]
        else:
            args.disease = value

    while args.disease not in SUPPORTED_DISEASES:
        value = input("암, 뇌졸중, 급성심근경색 중 하나를 입력하세요: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(disease_options):
            args.disease = disease_options[int(value) - 1]
        else:
            args.disease = value


def main() -> None:
    load_dotenv()
    args = parse_args()
    app_key = get_tmap_app_key()

    if args.origin_lat is None or args.origin_lon is None:
        prompt_for_missing_inputs(args)
        if not app_key:
            raise RuntimeError(
                "주소를 좌표로 바꾸려면 TMAP_APP_KEY 또는 TMAP_API_KEY가 필요합니다. "
                "API 없이 실행하려면 --origin-lat/--origin-lon을 직접 넣어주세요."
            )
        origin_lon, origin_lat = geocode_address(args.address, app_key, args.timeout)
        args.origin_lon = origin_lon
        args.origin_lat = origin_lat
    else:
        prompt_for_missing_disease(args)

    if not app_key:
        raise RuntimeError("TMAP 자동차 경로 조회를 위해 TMAP_APP_KEY 또는 TMAP_API_KEY 환경변수가 필요합니다.")

    huff_candidates = build_huff_candidates(args)
    selected = mark_selected_candidates(huff_candidates, args)
    tmap_success_rows = add_tmap_routes(huff_candidates, args, app_key)
    calculate_final_probabilities(tmap_success_rows, args)
    pareto_rows = mark_pareto_candidates(tmap_success_rows)
    final_rows = final_recommendations(tmap_success_rows)

    write_csv([huff_row(row) for row in huff_candidates], Path(args.huff_output), HUFF_COLUMNS)
    write_csv([final_row(row) for row in final_rows], Path(args.final_output), FINAL_COLUMNS)

    print(f"huff_candidates={len(huff_candidates)}")
    print(f"selected_for_next_step={len(selected)}")
    print(f"tmap_success={len(tmap_success_rows)}")
    print(f"pareto_candidates={len(pareto_rows)}")
    print(f"final_recommendations={len(final_rows)}")
    print(f"saved_huff={args.huff_output}")
    print(f"saved_final={args.final_output}")


if __name__ == "__main__":
    main()
