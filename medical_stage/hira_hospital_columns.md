# HIRA 병원정보서비스 주요 변수

Source: 건강보험심사평가원_병원정보서비스 `getHospBasisList`

## 행 수 확인

정상 전체 행 수는 고정값이 아니라 API 응답의 `totalCount` 값입니다. 병원 개설/폐업 반영 때문에 조회 시점과 필터에 따라 달라집니다.

`fetch_hira_hospitals.py`는 실행 중 아래처럼 현재 누적 행 수와 전체 행 수를 stderr에 출력합니다.

```text
page=1 fetched=100 accumulated=100 total=...
```

CSV 행 수는 헤더가 1줄 포함되므로, 저장된 실제 데이터 수는 `wc -l` 결과에서 1을 뺀 값입니다.

## 요청 변수

| 변수명 | 의미 |
| --- | --- |
| `ServiceKey` | 공공데이터포털 인증키 |
| `numOfRows` | 한 페이지 결과 수 |
| `pageNo` | 페이지 번호 |
| `sidoCd` | 시도코드 |
| `sgguCd` | 시군구코드 |
| `emdongNm` | 읍면동명 |
| `yadmNm` | 요양기관명 |
| `zipCd` | 우편번호 |
| `clCd` | 종별코드 |
| `dgsbjtCd` | 진료과목코드 |

## 응답 변수

| 변수명 | 의미 |
| --- | --- |
| `ykiho` | 암호화된 요양기호 |
| `yadmNm` | 요양기관명 |
| `clCd` | 종별코드 |
| `clCdNm` | 종별명 |
| `sidoCd` | 시도코드 |
| `sidoCdNm` | 시도명 |
| `sgguCd` | 시군구코드 |
| `sgguCdNm` | 시군구명 |
| `emdongNm` | 읍면동명 |
| `postNo` | 우편번호 |
| `addr` | 주소 |
| `telno` | 전화번호 |
| `hospUrl` | 병원 홈페이지 URL |
| `estbDd` | 개설일자, `YYYYMMDD` |
| `XPos` | 경도 |
| `YPos` | 위도 |
| `drTotCnt` | 의사 총수 |
| `mdeptGdrCnt` | 의과 일반의 수 |
| `mdeptIntnCnt` | 의과 인턴 수 |
| `mdeptResdntCnt` | 의과 레지던트 수 |
| `mdeptSdrCnt` | 의과 전문의 수 |
| `detyGdrCnt` | 치과 일반의 수 |
| `detyIntnCnt` | 치과 인턴 수 |
| `detyResdntCnt` | 치과 레지던트 수 |
| `detySdrCnt` | 치과 전문의 수 |
| `cmdcGdrCnt` | 한방 일반의 수 |
| `cmdcIntnCnt` | 한방 인턴 수 |
| `cmdcResdntCnt` | 한방 레지던트 수 |
| `cmdcSdrCnt` | 한방 전문의 수 |
| `pnursCnt` | 조산사 수 |

## 코드 설명 보는 곳

지역코드, 종별코드, 진료과목코드 같은 코드값은 공공데이터포털 설명에 따라 보건의료빅데이터개방시스템의 코드조회 메뉴에서 확인합니다.

- 보건의료빅데이터개방시스템: https://opendata.hira.or.kr
- 경로: 서비스 소개 > 용어설명 > 코드조회
