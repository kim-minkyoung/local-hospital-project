import streamlit as st

from main import get_result
from medical_stage.recommend_huff_hospitals import geocode_address, get_tmap_app_key

st.set_page_config(page_title="지역안심 중대질병 교통비보험", layout="wide")

st.title("지역안심 중대질병 교통비보험")
st.caption("성별, 대상 질병, 가입 나이, 위치를 입력하면 추천 병원과 교통비를 계산합니다.")

DISEASE_OPTIONS = ["암", "뇌졸중", "급성심근경색"]

with st.form("input_form"):
    col1, col2 = st.columns(2)
    with col1:
        gender = st.selectbox("성별", ["남성", "여성"])
        disease = st.selectbox("대상 질병", DISEASE_OPTIONS)
    with col2:
        age = st.number_input("가입 나이", min_value=0, max_value=120, value=40, step=1)
        address = st.text_input("위치 (전라도 내 도로명주소)", placeholder="예: 전남 함평군 함평읍 중앙길 200")

    submitted = st.form_submit_button("조회하기", type="primary")

if submitted:
    if not address.strip():
        st.error("위치(도로명주소)를 입력해 주세요.")
        st.stop()

    app_key = get_tmap_app_key()
    if not app_key:
        st.error("TMAP_API_KEY가 설정되어 있지 않습니다. Streamlit Cloud의 Secrets에 TMAP_API_KEY를 등록해 주세요.")
        st.stop()

    with st.spinner("위치를 확인하는 중입니다..."):
        try:
            longitude, latitude = geocode_address(address, app_key, timeout=20)
        except Exception as e:
            st.error(f"주소를 좌표로 변환하지 못했습니다: {e}")
            st.stop()

    with st.spinner("병원을 분석하는 중입니다..."):
        try:
            result = get_result(disease, latitude, longitude)
        except Exception as e:
            st.error(f"병원 추천 계산 중 오류가 발생했습니다: {e}")
            st.stop()

    st.divider()

    # 입력 요약
    st.subheader("입력 정보")
    st.write(f"**성별**: {gender} · **가입 나이**: {age}세 · **대상 질병**: {disease}")
    st.write(f"**위치**: {address} (위도 {latitude:.5f}, 경도 {longitude:.5f})")

    # 대표 교통비
    st.subheader("대표 교통비")
    st.metric(
        label=result.get("representative_transport_cost_basis", "대표 교통비"),
        value=f"{result.get('representative_transport_cost', 0):,}원",
    )

    # 추천 병원 3곳
    st.subheader("추천 병원")
    recommendations = result.get("recommendations", [])

    if not recommendations:
        st.warning("추천 가능한 병원을 찾지 못했습니다.")
    else:
        cols = st.columns(len(recommendations))
        for col, rec in zip(cols, recommendations):
            with col:
                st.markdown(f"**{rec['recommendation_type']}**")
                st.markdown(f"#### {rec['hospital_name']}")
                st.caption(rec.get("hospital_type", ""))
                st.write(f"소요시간: {rec['route_duration_min']:.1f}분")
                st.write(f"거리: {rec['route_distance_km']:.1f}km")
                st.write(f"교통비(택시비 기준): {rec['taxi_fare']:,}원")
                if rec.get("toll_fare"):
                    st.caption(f"통행료 참고: {rec['toll_fare']:,}원")
                st.write(f"전문역량점수: {rec['capability_score']:.1f}")

    with st.expander("상세 데이터 보기"):
        st.dataframe(recommendations, use_container_width=True)
        st.json(result.get("counts", {}))