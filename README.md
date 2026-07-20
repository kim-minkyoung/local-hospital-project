# Hospital Recommendation Pipeline

사용자의 위치와 질병명을 입력받아 병원 3곳과 대표 교통비를 산출하는 병원 추천 파이프라인입니다.

이 프로젝트는 심평원 병원 데이터로 질병별 후보군을 만들고, Huff 모델과 Kneedle로 TMAP 호출 대상을 줄인 뒤, 실제 자동차 이동시간과 병원 역량을 함께 고려해 최종 병원을 추천합니다.

## Input

최종 추천 실행에는 아래 입력이 필요합니다.

```text
disease
- 암
- 뇌졸중
- 급성심근경색

location
- 도로명주소
- 또는 위도/경도
```

주소를 입력하면 TMAP 주소 검색 API로 위도/경도를 변환합니다. 위도/경도를 직접 넣으면 주소 변환 단계는 생략됩니다.

## Output

최종 출력은 병원 3곳과 대표 교통비입니다.

```text
1. 접근성추천
   - 전체 TMAP 성공 후보 중 자동차 소요시간이 가장 짧은 병원

2. 원거리 전문역량 대안
   - 전체 TMAP 성공 후보 중 전문역량점수가 가장 높은 병원

3. 종합추천
   - 파레토 후보 중 소요시간과 전문역량의 균형점에 해당하는 병원
```

각 병원별 출력값:

```text
recommendation_type
hospital_name
hospital_type
transport_cost
route_duration_min
route_distance_km
taxi_fare
toll_fare
capability_score
final_probability
```

대표 교통비:

```text
final_transport_cost = 종합추천 병원의 transport_cost
final_transport_cost_basis = "종합추천 교통비"
representative_transport_cost = 종합추천 병원의 transport_cost
representative_transport_cost_basis = "종합추천 교통비"
```

`transport_cost`는 TMAP `taxi_fare` 기준입니다. 통행료는 더하지 않고 `toll_fare`에 참고값으로만 저장합니다.

## Architecture Overview

```text
[사용자 입력]
  disease, address
  또는 disease, latitude, longitude
        |
        v
[좌표 확보]
  address 입력 시 TMAP 주소 검색 API 호출
  latitude/longitude 입력 시 그대로 사용
        |
        v
[질병별 1차 후보 로드]
  output/hira_disease_candidates_semi.csv
        |
        v
[병원 프로필 결합]
  output/hira_hospital_profiles.csv
  ykiho 기준으로 specialists 정보 결합
        |
        v
[전문역량점수 계산]
  specialist_score = 질병 관련 전문의 수 합
  hospital_weight = 상급종합병원 2.0, 종합병원 1.0
  capability_score = specialist_score * hospital_weight
        |
        v
[직선거리 기반 Huff 계산]
  straight_distance_km = Haversine 거리
  huff_utility = capability_score^alpha / (straight_distance_km + epsilon)^beta
  huff_probability = huff_utility / sum(huff_utility)
        |
        v
[Kneedle 후보 축소]
  huff_probability 누적곡선의 elbow 지점 탐지
  selected_for_next_step=True 후보만 TMAP 호출
        |
        v
[TMAP 자동차 경로 조회]
  route_distance_km
  route_duration_min
  taxi_fare
  toll_fare
        |
        v
[실제 소요시간 기반 최종 Huff 계산]
  final_utility = capability_score^alpha / (route_duration_min + epsilon)^beta
  final_probability = final_utility / sum(final_utility)
        |
        v
[Pareto 필터]
  소요시간은 짧을수록 좋음
  전문역량점수는 높을수록 좋음
  두 기준에서 모두 밀리는 병원 제거
        |
        v
[최종 3곳 선정]
  접근성추천 = route_duration_min 최소
  원거리 전문역량 대안 = capability_score 최대
  종합추천 = 파레토 후보 중 시간-역량 균형점
        |
        v
[최종 결과]
  병원 3곳
  병원별 시간/거리/교통비
  최종 교통비 = 종합추천 교통비
```

## Data Build Pipeline

데이터셋을 처음부터 다시 만들 때의 흐름입니다.

```text
[심평원 병원정보서비스]
  전국 병원 기본정보 수집
  hospital_id/ykiho, 병원명, 종별, 주소, 위도, 경도
        |
        v
[기관 필터]
  상급종합병원
  종합병원
        |
        v
[의료기관별 상세정보서비스]
  진료과목
  전문과목별 전문의 수
  의료장비
  특수진료/진료가능분야
        |
        v
[병원 통합 프로필 생성]
  ykiho 기준 결합
  병원당 한 행
  JSON 문자열 컬럼 저장
        |
        v
output/hira_hospital_profiles.csv
        |
        v
[질병별 1차 후보 생성]
  specialists와 special_treatments 기준 필터
        |
        v
output/hira_disease_candidates_semi.csv
```

## Disease Candidate Rules

### 암

다음 중 하나 이상 충족:

```text
방사선종양학과 전문의 1명 이상
외과, 병리과, 핵의학과 전문의가 각각 1명 이상
특수진료에 조혈모세포이식 포함
```

### 뇌졸중

다음을 모두 충족:

```text
신경과 전문의 1명 이상
신경외과 전문의 1명 이상
응급의학과 전문의 1명 이상
```

### 급성심근경색

다음을 모두 충족:

```text
내과 전문의 1명 이상
응급의학과 전문의 1명 이상
특수진료에 응급의료기관 포함
```

그리고 다음 중 하나 이상 충족:

```text
심장혈관흉부외과 전문의 1명 이상
특수진료에 경피적 좌심방이 폐색술 포함
특수진료에 경피적 대동맥판삽입 포함
특수진료에 심실 보조장치 포함
특수진료에 심장질환자 재택의료 포함
```

## Scoring

질병별 관련 전문의 수:

```text
암: 방사선종양학과 + 외과 + 병리과 + 핵의학과
뇌졸중: 신경과 + 신경외과 + 응급의학과
급성심근경색: 내과 + 응급의학과 + 심장혈관흉부외과
```

병원종별 가중치:

```text
상급종합병원: 2.0
종합병원: 1.0
```

역량점수:

```text
capability_score = specialist_score * hospital_weight
```

Huff 기본값:

```text
alpha = 1.0
beta = 2.0
epsilon = 0.1
```

## Files

필수 실행 파일:

```text
main.py
medical_stage/recommend_huff_hospitals.py
```

데이터 구축용 파일:

```text
medical_stage/fetch_hira_hospitals.py
medical_stage/fetch_hira_hospital_details.py
medical_stage/build_hira_hospital_profiles.py
medical_stage/build_hira_disease_candidates.py
```

핵심 데이터:

```text
output/hira_hospital_profiles.csv
output/hira_disease_candidates_semi.csv
```

재구축용 원천 데이터:

```text
output/hira_hosp_basis_all.csv
output/hira_hosp_details_raw.jsonl
```

실행 산출물:

```text
output/hira_huff_candidates.csv
output/hira_final_recommendations.csv
```

## Environment

`.env.example`을 참고해 `.env`를 만듭니다.

```bash
TMAP_API_KEY=your_tmap_api_key
DATA_GO_KR_SERVICE_KEY=your_data_go_kr_service_key
```

최종 추천만 실행할 때는 `TMAP_API_KEY`가 필요합니다. 심평원 데이터를 새로 수집할 때는 `DATA_GO_KR_SERVICE_KEY`가 필요합니다.

## Usage

프로젝트 폴더로 이동합니다.

```bash
cd hospital_recommendation
```

주소 입력 방식:

```bash
python3 main.py --address "전남 함평군 함평읍 중앙길 200" --disease "뇌졸중"
```

좌표 입력 방식:

```bash
python3 main.py --origin-lat 35.065 --origin-lon 126.516 --disease "뇌졸중"
```

파이썬 함수 방식:

```python
from main import get_result

result = get_result("뇌졸중", 35.065, 126.516)

recommendations = result["recommendations"]
representative_cost = result["representative_transport_cost"]
final_cost = result["final_transport_cost"]
```

## Example Function Output

```python
{
    "disease": "뇌졸중",
    "origin": {
        "latitude": 35.065,
        "longitude": 126.516,
    },
    "recommendations": [
        {
            "recommendation_type": "접근성추천",
            "hospital_name": "의료법인대송의료재단 무안병원",
            "hospital_type": "종합병원",
            "transport_cost": 19700,
            "route_duration_min": 14.9,
            "route_distance_km": 12.2,
            "taxi_fare": 19700,
            "toll_fare": 0,
            "capability_score": 13.0,
            "final_probability": 0.08,
        }
    ],
    "final_transport_cost": 75400,
    "final_transport_cost_basis": "종합추천 교통비",
    "representative_transport_cost": 75400,
    "representative_transport_cost_basis": "종합추천 교통비",
    "counts": {
        "disease_candidates": 249,
        "selected_for_tmap": 32,
        "tmap_success": 32,
        "pareto_candidates": 11,
        "final_recommendations": 3,
    },
    "output_files": {
        "huff_candidates": "output/hira_huff_candidates.csv",
        "final_recommendations": "output/hira_final_recommendations.csv",
    },
}
```
