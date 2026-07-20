# HIRA 의료기관별상세정보서비스 수집 파일

Source: 건강보험심사평가원_의료기관별상세정보서비스

Base URL: `https://apis.data.go.kr/B551182/MadmDtlInfoService2.8`

공공데이터포털 페이지: https://www.data.go.kr/data/15001699/openapi.do

## 사용 endpoint

| 수집 항목 | endpoint | 요약 CSV 컬럼 |
| --- | --- | --- |
| 진료과목정보 | `getDgsbjtInfo2.8` | `departments` |
| 전문과목별 전문의 수 | `getSpcSbjtSdrInfo2.8` | `specialist_counts` |
| 의료장비정보 | `getMedOftInfo2.8` | `equipment` |
| 특수진료정보(진료가능분야조회) | `getSpclDiagInfo2.8` | `special_care` |

## 입력 파일

`output/hira_hosp_basis_all.csv`

병원 기본정보서비스 `getHospBasisList` 결과입니다. 상세 수집 스크립트는 여기서 다음 기관만 고정으로 사용합니다.

| `clCd` | `clCdNm` |
| --- | --- |
| `1` | 상급종합 |
| `11` | 종합병원 |

의료원, 대학병원 같은 명칭은 필터 기준으로 사용하지 않습니다.

## 출력 파일

### `output/hira_hosp_details.csv`

추천/필터링 파이프라인에서 바로 쓰기 쉬운 병원별 1행 요약 파일입니다.

| 컬럼 | 의미 |
| --- | --- |
| `hospital_id` | 암호화된 요양기호, `ykiho` |
| `hospital_name` | 병원명 |
| `hospital_type` | 의료기관 종별 |
| `address` | 주소 |
| `sido` | 시도 |
| `sigungu` | 시군구 |
| `latitude` | 위도 |
| `longitude` | 경도 |
| `departments` | 진료과 목록, JSON 배열 문자열 |
| `specialist_counts` | 전문과목별 전문의 수, JSON 객체 문자열 |
| `equipment` | 장비 목록, JSON 배열 문자열 |
| `special_care` | 특수진료/진료가능분야 목록, JSON 배열 문자열 |
| `detail_success` | 네 상세 endpoint 모두 성공했는지 여부 |
| `detail_errors` | endpoint별 오류 내용, JSON 객체 문자열 |
| `detail_row_counts` | endpoint별 원본 행 수, JSON 객체 문자열 |

### `output/hira_hosp_details_raw.jsonl`

상세 API 응답을 병원별 JSON 한 줄로 보관하는 원본 백업 파일입니다. 요약 컬럼에 빠진 응답 필드를 나중에 다시 쓰고 싶을 때 API를 재호출하지 않고 재가공할 수 있습니다.

## 실행 예시

```bash
export DATA_GO_KR_SERVICE_KEY='공공데이터포털_인증키'
python3 medical_stage/fetch_hira_hospital_details.py --resume
```

테스트로 일부 병원만 호출하려면:

```bash
python3 medical_stage/fetch_hira_hospital_details.py --limit 5
```

중간에 끊기면 같은 `raw-output` 파일을 둔 채 `--resume`으로 다시 실행합니다.
