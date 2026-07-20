# Hospital Recommendation Pipeline

도로명주소 또는 위도/경도와 질병명을 입력하면, 심평원 병원 데이터와 TMAP 자동차 경로 API를 이용해 병원 3곳을 추천하는 파이프라인입니다.

## 입력

- `disease`: `암`, `뇌졸중`, `급성심근경색` 중 하나
- `address`: 사용자 도로명주소
- 또는 `latitude`, `longitude`: 사용자 좌표

## 출력

최종 추천 병원 3곳:

- `접근성추천`: TMAP 자동차 소요시간이 가장 짧은 병원
- `원거리 전문역량 대안`: 전문역량점수(`capability_score`)가 가장 높은 병원
- `종합추천`: 파레토 후보 중 시간과 전문역량의 균형점

각 병원별 산출값:

- 병원명
- 추천 유형
- 자동차 소요시간
- 도로거리
- 교통비
- 전문역량점수
- 최종 허프 확률

교통비(`transport_cost`)는 통행료를 더하지 않은 TMAP `taxi_fare` 기준입니다. 통행료는 `toll_fare` 컬럼에 참고값으로 따로 저장합니다.

## 최종 파이프라인

```text
1. 심평원 병원 기본정보 + 상세 의료자원 결합
2. 상급종합병원/종합병원만 사용
3. 질병별 1차 후보 필터링
4. 사용자 좌표와 병원 좌표 간 Haversine 직선거리 계산
5. 질병별 관련 전문의 수와 병원종별 가중치로 전문역량점수 계산
6. 직선거리 기반 Huff 효용/상대확률 계산
7. Kneedle로 TMAP 호출 후보 축소
8. TMAP 자동차 경로 API로 도로거리/소요시간/택시비/통행료 조회
9. 실제 소요시간 기반 최종 Huff 확률 계산
10. 시간-역량 파레토 필터 적용
11. 접근성추천, 원거리 전문역량 대안, 종합추천 3곳 선정
12. 대표 교통비는 종합추천 병원의 교통비로 산출
```

## 준비

프로젝트 폴더로 이동합니다.

```bash
cd hospital_recommendation
```

`.env.example`을 참고해 `.env`를 만듭니다.

```bash
TMAP_API_KEY=your_tmap_api_key
DATA_GO_KR_SERVICE_KEY=your_data_go_kr_service_key
```

## 실행

주소를 입력하는 방식:

```bash
python3 main.py --address "전남 함평군 함평읍 중앙길 200" --disease "뇌졸중"
```

좌표를 직접 입력하는 방식:

```bash
python3 main.py --origin-lat 35.065 --origin-lon 126.516 --disease "뇌졸중"
```

파이썬 함수로 사용하는 방식:

```python
from main import get_result

result = get_result("뇌졸중", 35.065, 126.516)
print(result["recommendations"])
print(result["representative_transport_cost"])
print(result["representative_transport_cost_basis"])
```

## 주요 파일

- `main.py`: 최종 실행 진입점과 `get_result()` 함수
- `medical_stage/recommend_huff_hospitals.py`: 주소 변환, Huff, Kneedle, TMAP, Pareto, 최종 추천 로직
- `medical_stage/build_hira_hospital_profiles.py`: 병원 기본정보와 상세정보 결합
- `medical_stage/build_hira_disease_candidates.py`: 질병별 1차 후보 생성
- `medical_stage/fetch_hira_hospitals.py`: 심평원 병원 기본정보 수집
- `medical_stage/fetch_hira_hospital_details.py`: 심평원 의료기관별 상세정보 수집

## 핵심 데이터

- `output/hira_hosp_basis_all.csv`: 심평원 병원 기본정보
- `output/hira_hosp_details_raw.jsonl`: 의료기관별 상세정보 원본
- `output/hira_hospital_profiles.csv`: 병원별 통합 프로필
- `output/hira_disease_candidates_semi.csv`: 질병별 1차 후보

## 산출물

- `output/hira_huff_candidates.csv`: Huff/Kneedle 및 TMAP 후보 상세
- `output/hira_final_recommendations.csv`: 최종 추천 병원 3곳
