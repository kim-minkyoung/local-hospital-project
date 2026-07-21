"""보험료 엑셀(위험률_산출_기초자료_v2.xlsx)의 '연납보험료' 시트만 읽어
성별·질병·가입나이로 연납 순보험료율을 조회하는 모듈.
"""
from functools import lru_cache
from pathlib import Path

import openpyxl

EXCEL_PATH = Path(__file__).parent / "data" / "premium_table.xlsx"
SHEET_NAME = "연납보험료"

# (시작열, 끝열) - 1-indexed. 시트 안에 6개 블록이 가로로 나열되어 있음.
_BLOCKS = [(1, 4), (6, 9), (11, 14), (16, 19), (21, 24), (26, 29)]

GENDER_MAP = {"남성": "남", "여성": "여"}


@lru_cache(maxsize=1)
def _load_table():
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb[SHEET_NAME]
    table = {}
    for row in ws.iter_rows(min_row=7, values_only=True):
        for start, end in _BLOCKS:
            chunk = row[start - 1:end]
            if len(chunk) < 4:
                continue
            gender, age, disease, rate = chunk
            if gender is None or age is None or disease is None:
                continue
            table[(gender, disease, int(age))] = float(rate or 0)
    return table


def get_premium_rate(gender_kr: str, disease: str, age: int):
    """gender_kr: '남성' 또는 '여성'.
    반환값: 기준 보험금 1원당 연납 순보험료율. 조회 실패 시 None.
    """
    gender = GENDER_MAP.get(gender_kr, gender_kr)
    table = _load_table()
    return table.get((gender, disease, int(age)))