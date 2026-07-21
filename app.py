import folium
import streamlit as st
from streamlit_folium import st_folium

from main import get_result
from medical_stage.recommend_huff_hospitals import geocode_address, get_tmap_app_key, load_dotenv
from premium import get_premium_rate

load_dotenv()  # .env의 TMAP_API_KEY 등을 앱 시작 시점에 미리 읽어온다.

st.set_page_config(page_title="지역안심 중대질병 교통비보험", page_icon="🏥", layout="wide")

# ---------------------------------------------------------------------------
# 디자인 (컬러 팔레트)
# ---------------------------------------------------------------------------
PRIMARY = "#0F5B4C"
PRIMARY_DARK = "#0A3F35"
PRIMARY_SOFT = "#DCEAE5"
ACCENT = "#E4572E"
BG = "#F4F7F6"
INK = "#16211C"
INK_SOFT = "#4C5A54"
BORDER = "#DCE3DF"

st.markdown(
    f"""
    <style>
    .stApp {{ background: {BG}; }}
    h1, h2, h3 {{ color: {INK}; }}

    .app-header {{
        display: flex; align-items: center; gap: 14px;
        padding: 6px 0 18px 0; border-bottom: 1px solid {BORDER}; margin-bottom: 20px;
    }}
    .app-header .badge {{
        font-size: 16px; font-weight: 700; letter-spacing: .04em;
        color: {PRIMARY}; background: {PRIMARY_SOFT};
        padding: 7px 14px; border-radius: 999px;
    }}

    /* st.container(border=True)가 만드는 카드를 둥글고 하얗게 */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: 18px !important;
        border-color: {BORDER} !important;
        background: #FFFFFF;
        box-shadow: 0 1px 2px rgba(16,36,29,.04), 0 8px 24px rgba(16,36,29,.06);
    }}

    .section-title {{
        font-size: 19px; font-weight: 700; color: {INK}; margin-bottom: 4px;
        display: flex; align-items: center; gap: 8px;
    }}
    .section-sub {{ font-size: 12.5px; color: {INK_SOFT}; margin-bottom: 14px; }}

    .origin-chip {{
        margin-top: 10px; display: flex; align-items: center; gap: 8px;
        background: {PRIMARY_SOFT}; color: {PRIMARY_DARK}; border-radius: 10px;
        padding: 10px 14px; font-size: 13px; font-weight: 600;
    }}
    .origin-chip .dot {{ width: 8px; height: 8px; border-radius: 50%; background: {ACCENT}; }}

    .hospital-card {{
        border-radius: 16px; padding: 16px 18px; height: 100%;
        border: 1px solid {BORDER}; background: {BG};
    }}
    .hospital-card.best {{ border: 2px solid {PRIMARY}; background: {PRIMARY_SOFT}; }}
    .hospital-tag {{
        display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: .02em;
        padding: 4px 9px; border-radius: 999px; margin-bottom: 8px;
        color: #fff; background: {INK_SOFT};
    }}
    .hospital-tag.best {{ background: {PRIMARY}; }}
    .hospital-tag.speed {{ background: #2E6E8E; }}
    .hospital-tag.expert {{ background: #7A4FA3; }}
    .hospital-name {{ font-size: 17px; font-weight: 800; color: {INK}; margin: 2px 0 2px; }}
    .hospital-type {{ font-size: 12px; color: {INK_SOFT}; margin-bottom: 10px; }}
    .hospital-stat {{ display: flex; justify-content: space-between; font-size: 13px; padding: 4px 0; }}
    .hospital-stat b {{ color: {INK}; }}

    .premium-box {{
        background: linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_DARK} 100%);
        color: #fff; border-radius: 18px; padding: 22px 24px;
    }}
    .premium-box .label {{ font-size: 12.5px; opacity: .85; margin-bottom: 6px; }}
    .premium-box .value {{ font-size: 30px; font-weight: 800; }}
    .premium-box .sub {{ font-size: 12px; opacity: .8; margin-top: 8px; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 상태 초기화
# ---------------------------------------------------------------------------
if "origin_lat" not in st.session_state:
    st.session_state.origin_lat = 35.35
if "origin_lng" not in st.session_state:
    st.session_state.origin_lng = 126.80
if "origin_label" not in st.session_state:
    st.session_state.origin_label = ""

JEOLLA_BOUNDS = {"lat_min": 33.8, "lat_max": 36.4, "lng_min": 125.8, "lng_max": 127.9}


def is_within_jeolla(lat, lng):
    return (
        JEOLLA_BOUNDS["lat_min"] <= lat <= JEOLLA_BOUNDS["lat_max"]
        and JEOLLA_BOUNDS["lng_min"] <= lng <= JEOLLA_BOUNDS["lng_max"]
    )


# 다음(카카오) 주소검색 팝업에서 선택한 주소가 쿼리 파라미터로 돌아오면 지오코딩 처리
if "kakao_addr" in st.query_params:
    selected_addr = st.query_params["kakao_addr"]
    app_key = get_tmap_app_key()
    if not app_key:
        st.session_state.origin_error = "TMAP_API_KEY가 설정되어 있지 않습니다."
    else:
        try:
            lon, lat = geocode_address(selected_addr, app_key, timeout=20)
            if is_within_jeolla(lat, lon):
                st.session_state.origin_lat = lat
                st.session_state.origin_lng = lon
                st.session_state.origin_label = selected_addr
                st.session_state.origin_error = ""
            else:
                st.session_state.origin_error = "검색된 위치가 전라도 범위 밖입니다. 전라도 내 주소를 선택해 주세요."
        except Exception as e:
            st.session_state.origin_error = f"주소를 찾지 못했습니다: {e}"
    st.query_params.clear()


# ---------------------------------------------------------------------------
# 헤더
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="app-header">
        <div class="badge">보험개발원 AI 프로젝트</div>
        <h1 style="margin:0; font-size:30px;">지역안심 중대질병 교통비보험</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

left, right = st.columns([1.3, 1])

# ---------------------------------------------------------------------------
# 왼쪽: 지도 (검색 + 클릭 선택)
# ---------------------------------------------------------------------------
with left:
    with st.container(border=True):
        st.markdown('<div class="section-title">📍 위치 검색 / 선택</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="section-sub">주소를 검색하거나, 지도를 직접 클릭해 출발지를 지정하세요. (전라도 내부만 가능)</div>',
            unsafe_allow_html=True,
        )

        search_col1, search_col2 = st.columns([4, 1])
        with search_col1:
            address_input = st.text_input(
                "주소 직접 입력", placeholder="예: 전남 함평군 함평읍 중앙길 200", label_visibility="collapsed"
            )
        with search_col2:
            search_clicked = st.button("검색", width="stretch")

        if search_clicked and address_input.strip():
            app_key = get_tmap_app_key()
            if not app_key:
                st.error("TMAP_API_KEY가 설정되어 있지 않습니다.")
            else:
                with st.spinner("주소를 찾는 중입니다..."):
                    try:
                        lon, lat = geocode_address(address_input.strip(), app_key, timeout=20)
                        if not is_within_jeolla(lat, lon):
                            st.warning("검색된 위치가 전라도 범위 밖입니다. 전라도 내 주소를 입력해 주세요.")
                        else:
                            st.session_state.origin_lat = lat
                            st.session_state.origin_lng = lon
                            st.session_state.origin_label = address_input.strip()
                    except Exception as e:
                        st.error(f"주소를 찾지 못했습니다: {e}")

        st.caption("또는 아래 버튼으로 다음(카카오) 주소검색 팝업을 이용하세요.")
        st.iframe(
            f"""
            <script src="//t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js"></script>
            <button id="addr-search-btn" style="
                width:100%; padding:10px 14px; border-radius:8px; border:1px solid {BORDER};
                background:{PRIMARY}; color:#fff; font-weight:700; font-size:14px; cursor:pointer;
            ">📮 주소검색 팝업 열기</button>
            <script>
            document.getElementById('addr-search-btn').addEventListener('click', function() {{
                new daum.Postcode({{
                    oncomplete: function(data) {{
                        var addr = data.roadAddress || data.jibunAddress;
                        try {{
                            var target = window.opener || window.parent;
                            var url = new URL(target.location.href);
                            url.searchParams.set('kakao_addr', addr);
                            target.location.href = url.toString();
                        }} catch (e) {{ console.error(e); }}
                        if (window.opener) {{ window.close(); }}
                    }}
                }}).open();
            }});
            </script>
            """,
            height=50,
        )

        if st.session_state.get("origin_error"):
            st.warning(st.session_state.origin_error)

        m = folium.Map(
            location=[st.session_state.origin_lat, st.session_state.origin_lng],
            zoom_start=10,
            tiles="CartoDB positron",
        )
        folium.Marker(
            [st.session_state.origin_lat, st.session_state.origin_lng],
            tooltip="선택한 출발지",
            icon=folium.Icon(color="darkgreen", icon="flag"),
        ).add_to(m)

        map_state = st_folium(m, height=380, use_container_width=True, key="origin_map")

        if map_state and map_state.get("last_clicked"):
            clicked_lat = map_state["last_clicked"]["lat"]
            clicked_lng = map_state["last_clicked"]["lng"]
            if (clicked_lat, clicked_lng) != (st.session_state.origin_lat, st.session_state.origin_lng):
                if is_within_jeolla(clicked_lat, clicked_lng):
                    st.session_state.origin_lat = clicked_lat
                    st.session_state.origin_lng = clicked_lng
                    st.session_state.origin_label = "지도에서 선택한 위치"
                    st.rerun()
                else:
                    st.warning("전라도 범위 밖입니다. 전라도 내부를 클릭해 주세요.")

        st.markdown(
            f"""
            <div class="origin-chip">
                <span class="dot"></span>
                현재 출발지: {st.session_state.origin_label or "지도를 클릭하거나 주소를 검색하세요"}
                &nbsp;({st.session_state.origin_lat:.5f}, {st.session_state.origin_lng:.5f})
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 오른쪽: 개인 정보 입력
# ---------------------------------------------------------------------------
with right:
    with st.container(border=True):
        st.markdown('<div class="section-title">🧾 가입 정보</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-sub">가입자 정보를 입력하세요.</div>', unsafe_allow_html=True)

        gender = st.radio("성별", ["남성", "여성"], horizontal=True)
        disease = st.selectbox("대상 질병", ["암", "뇌졸중", "급성심근경색"])
        age = st.number_input("가입 나이", min_value=0, max_value=80, value=40, step=1)

    calculate = st.button("🔍 산출하기", type="primary", width="stretch")

# ---------------------------------------------------------------------------
# 계산
# ---------------------------------------------------------------------------
if calculate:
    if not st.session_state.origin_label:
        st.error("먼저 위치를 검색하거나 지도를 클릭해 출발지를 선택해 주세요.")
        st.stop()

    with st.spinner("병원을 분석하는 중입니다..."):
        try:
            result = get_result(disease, st.session_state.origin_lat, st.session_state.origin_lng)
            # 결과와 함께, 결과를 만들 때 쓴 입력값도 같이 저장해 둔다.
            st.session_state.last_result = result
            st.session_state.last_gender = gender
            st.session_state.last_disease = disease
            st.session_state.last_age = age
        except Exception as e:
            st.error(f"병원 추천 계산 중 오류가 발생했습니다: {e}")
            st.stop()

# ---------------------------------------------------------------------------
# 결과
# ---------------------------------------------------------------------------
if st.session_state.get("last_result"):
    result = st.session_state.last_result
    gender = st.session_state.last_gender
    disease = st.session_state.last_disease
    age = st.session_state.last_age

    st.markdown("### 산출 결과")

    res_col1, res_col2 = st.columns([2, 1])

    # --- 병원 추천 카드 ---
    with res_col1:
        with st.container(border=True):
            st.markdown('<div class="section-title">🏥 추천 병원</div>', unsafe_allow_html=True)

            recommendations = result.get("recommendations", [])
            tag_map = {
                "접근성추천": ("speed", "🚕 접근성추천"),
                "원거리 전문역량 대안": ("expert", "🎯 전문역량대안"),
                "종합추천": ("best", "⭐ 종합추천"),
            }

            cols = st.columns(len(recommendations)) if recommendations else []
            for col, rec in zip(cols, recommendations):
                tag_class, tag_label = tag_map.get(rec["recommendation_type"], ("", rec["recommendation_type"]))
                is_best = tag_class == "best"
                with col:
                    st.markdown(
                        f"""
                        <div class="hospital-card {'best' if is_best else ''}">
                            <span class="hospital-tag {tag_class}">{tag_label}</span>
                            <div class="hospital-name">{rec['hospital_name']}</div>
                            <div class="hospital-type">{rec.get('hospital_type','')}</div>
                            <div class="hospital-stat"><span>소요시간</span><b>{rec['route_duration_min']:.1f}분</b></div>
                            <div class="hospital-stat"><span>거리</span><b>{rec['route_distance_km']:.1f}km</b></div>
                            <div class="hospital-stat"><span>교통비(택시)</span><b>{rec['taxi_fare']:,}원</b></div>
                            <div class="hospital-stat"><span>전문역량점수</span><b>{rec['capability_score']:.1f}</b></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown('<div class="section-title">🚕 대표 교통비</div>', unsafe_allow_html=True)
            st.metric(
                label=result.get("representative_transport_cost_basis", "대표 교통비"),
                value=f"{result.get('representative_transport_cost', 0):,}원",
            )

    # --- 보험료 카드 ---
    with res_col2:
        with st.container(border=True):
            st.markdown('<div class="section-title">💰 예상 보험료</div>', unsafe_allow_html=True)

            rate = get_premium_rate(gender, disease, age)
            transport_cost = result.get("representative_transport_cost", 0)

            if rate is None:
                st.warning("해당 조건의 보험료 데이터를 찾지 못했습니다.")
            else:
                annual_premium = rate * transport_cost
                monthly_premium = annual_premium / 12
                st.markdown(
                    f"""
                    <div class="premium-box">
                        <div class="label">연간 순보험료</div>
                        <div class="value">{annual_premium:,.0f}원</div>
                        <div class="sub">월 환산 약 {monthly_premium:,.0f}원 · 보장급부액(최종 교통비) {transport_cost:,}원 기준</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.caption(f"보험료율(위험률): {rate:.6f} × 최종 교통비 {transport_cost:,}원")

    with st.expander("상세 데이터 보기"):
        st.dataframe(recommendations, width="stretch")
        st.json(result.get("counts", {}))