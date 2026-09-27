"""Stage 5: one-page Streamlit dashboard of the final results.

Usage (from project root, after the pipeline has produced its outputs):
    .venv\\Scripts\\streamlit run scripts\\dashboard.py

Reads outputs/baseline/results.json, outputs/cnn/results.json,
outputs/cnn/test_predictions.parquet and data/processed/labeled_clean.pkl.
Copy follows dashboard conventions collected from yield-analysis tools, ML
evaluation reports and Korean UX-writing guides (see LOG.md, 21:18 entry).
"""
import json
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from explore_data import CLASSES

ROOT = Path(__file__).resolve().parents[1]
BASE_RESULTS = ROOT / "outputs" / "baseline" / "results.json"
CNN_RESULTS = ROOT / "outputs" / "cnn" / "results.json"
CNN_PREDS = ROOT / "outputs" / "cnn" / "test_predictions.parquet"
PROCESSED = ROOT / "data" / "processed" / "labeled_clean.pkl"
BASE_COLOR, CNN_COLOR, INK2 = "#eb6834", "#2a78d6", "#52514e"
GOOD_DIE, BAD_DIE = "#d6d5d0", "#184f95"
WAFER_RGB = np.array([[252, 252, 251], [214, 213, 208], [24, 79, 149]], dtype=np.uint8)  # off / good / bad die
N_SHOW = 12
VIEWS = ["맞힘", "놓침", "오탐"]

st.set_page_config(page_title="WM-811K 불량 패턴 분류", layout="wide")


@st.cache_data
def load_results():
    base = json.loads(BASE_RESULTS.read_text(encoding="utf-8"))
    cnn = json.loads(CNN_RESULTS.read_text(encoding="utf-8"))
    return base, cnn


@st.cache_data
def load_predictions(run: str, variant: str) -> pd.DataFrame:
    p = pd.read_parquet(CNN_PREDS)
    p = p[(p["run"] == run) & (p["variant"] == variant)].copy()
    p["true"] = [CLASSES[i] for i in p["label"]]
    p["predicted"] = [CLASSES[i] for i in p["pred"]]
    p["confidence"] = p[[f"p_{c}" for c in CLASSES]].to_numpy()[np.arange(len(p)), p["pred"].to_numpy()]
    return p.set_index("id")


@st.cache_data
def load_maps(ids: tuple) -> dict:
    df = pd.read_pickle(PROCESSED)
    return df.loc[list(ids), "waferMap"].to_dict()


def wafer_image(m: np.ndarray, target: int = 160) -> np.ndarray:
    """Nearest-neighbour upscale so the longer side is `target` px (keeps the map's aspect ratio)."""
    h, w = m.shape
    oh, ow = round(target * h / max(h, w)), round(target * w / max(h, w))
    return WAFER_RGB[m[np.arange(oh) * h // oh][:, np.arange(ow) * w // ow]]


def ci(values) -> str:
    return f"95% CI {values[0]:.3f}–{values[1]:.3f}"


base, cnn = load_results()
final = cnn["final"]
ft = final["test"]
bar = cnn["baseline_bar"]
bt = base["splits"]["split_main"][bar["model"]]["test"]
success = cnn["success"]
n_test = sum(ft["per_class"][c]["support"] for c in CLASSES)
low_c = min(CLASSES, key=lambda c: ft["per_class"][c]["recall"])
low_b = min(CLASSES, key=lambda c: bt["per_class"][c]["recall"])
r_c, r_b = ft["per_class"][low_c]["recall"], bt["per_class"][low_b]["recall"]

st.title("WM-811K 웨이퍼 맵 불량 패턴 분류")
st.caption(f"테스트 세트 {n_test:,}장 기준 (학습에 쓰지 않은 lot). 증감은 베이스라인 대비.")

# ---- headline numbers
c1, c2, c3, c4 = st.columns(4)
c1.metric("macro-F1 (전체 9종)", f"{ft['macro_f1']:.3f}", f"{ft['macro_f1'] - bt['macro_f1']:+.3f}",
          help=f"패턴 9종 F1의 단순 평균. 베이스라인 {bt['macro_f1']:.3f}")
c1.caption(ci(ft["macro_f1_ci95"]))
c2.metric("macro-F1 (불량 8종)", f"{ft['defect8_macro_f1']:.3f}",
          f"{ft['defect8_macro_f1'] - bt['defect8_macro_f1']:+.3f}",
          help=f"none을 뺀 불량 패턴 8종의 F1 평균. 베이스라인 {bt['defect8_macro_f1']:.3f}")
c2.caption(ci(ft["defect8_macro_f1_ci95"]))
c3.metric(f"최저 recall ({low_c})", f"{r_c:.3f}", f"{r_c - r_b:+.3f}",
          help=f"9종 중 가장 낮은 recall. 베이스라인 최저 {low_b} {r_b:.3f}")
c3.caption(ci(ft["per_class"][low_c]["recall_ci95"]))
c4.metric("balanced accuracy", f"{ft['balanced_acc']:.3f}", f"{ft['balanced_acc'] - bt['balanced_acc']:+.3f}",
          help=f"패턴별 recall의 단순 평균. 베이스라인 {bt['balanced_acc']:.3f}")
c4.caption(ci(ft["balanced_acc_ci95"]))

crit = pd.DataFrame(
    [("macro-F1", "≥ 0.80", f"{ft['macro_f1']:.3f}", success["macro_f1_ge_0.80"]),
     ("최저 recall", "≥ 0.50", f"{r_c:.3f} ({low_c})", success["all_recall_ge_0.50"]),
     ("macro-F1, 베이스라인 대비", f"> {bar['test_macro_f1']:.3f}", f"{ft['macro_f1']:.3f}", success["beats_best_baseline"])],
    columns=["기준", "목표", "결과", "판정"])
crit["판정"] = crit["판정"].map({True: "통과", False: "미달"})
top_l, top_r = st.columns([3, 2])
top_l.markdown(f"**성공 기준** {(crit['판정'] == '통과').sum()}/{len(crit)} 통과")
top_l.dataframe(crit, hide_index=True)
top_r.caption("모델: 소형 CNN, 클래스별 임계값 보정  \n선택: 검증 세트 macro-F1 기준  \n베이스라인: 랜덤 포레스트 + 수작업 특징 23개")
with top_r.expander("평가 조건"):
    st.markdown(f"- 분할: lot과 중복 맵(회전·반전 포함)을 한 묶음으로 학습·검증·테스트 세트 분리\n"
                f"- 테스트 세트: {n_test:,}장, 학습·검증에 쓰지 않은 lot\n"
                f"- 95% CI: 묶음(연결 성분) 단위 부트스트랩 1,000회\n"
                f"- 모델 선택: 검증 세트만 사용, 테스트 세트 미사용\n"
                f"- 실행 이름: CNN {final['run']} ({final['variant']}), 베이스라인 {bar['model']}")

# ---- per-class bars
st.subheader("패턴별 성능")
metric = st.radio("지표", ["recall", "F1"], horizontal=True, help="가는 선: 95% CI (recall만)")
key = "recall" if metric == "recall" else "f1"
rows = []
for model, res in (("베이스라인", bt), ("CNN", ft)):
    for c in CLASSES:
        pc = res["per_class"][c]
        rows.append({"패턴": f"{c} ({pc['support']:,})", "모델": model, "값": pc[key],
                     "하한": pc["recall_ci95"][0] if key == "recall" else None,
                     "상한": pc["recall_ci95"][1] if key == "recall" else None})
bars = pd.DataFrame(rows)
order = [f"{c} ({ft['per_class'][c]['support']:,})" for c in CLASSES]
color = alt.Color("모델:N", scale=alt.Scale(domain=["베이스라인", "CNN"], range=[BASE_COLOR, CNN_COLOR]),
                  legend=alt.Legend(orient="top", title=None))
base_chart = alt.Chart(bars).encode(y=alt.Y("패턴:N", sort=order, title=None), yOffset="모델:N", color=color)
chart = base_chart.mark_bar(cornerRadiusEnd=3, size=10).encode(
    x=alt.X("값:Q", scale=alt.Scale(domain=[0, 1]), title=metric),
    tooltip=["모델", "패턴", alt.Tooltip("값:Q", title=metric, format=".3f"),
             alt.Tooltip("하한:Q", title="95% CI 하한", format=".3f"),
             alt.Tooltip("상한:Q", title="95% CI 상한", format=".3f")])
if key == "recall":
    chart += base_chart.mark_rule().encode(x="하한:Q", x2="상한:Q")
    floor = pd.DataFrame({"x": [0.5], "t": ["기준 0.50"]})
    chart += alt.Chart(floor).mark_rule(color=INK2, strokeWidth=1).encode(x="x:Q")
    chart += alt.Chart(floor).mark_text(align="left", dx=4, dy=-6, color=INK2, fontSize=11).encode(
        x="x:Q", y=alt.value(0), text="t:N")
st.altair_chart(chart.properties(height=420), width="stretch")

# ---- confusion matrix
st.subheader("혼동 행렬 (CNN)")
mode = st.radio("표시", ["행 비율(%)", "웨이퍼 수"], horizontal=True,
                help="행 비율: 정답 패턴마다 합이 100%. 대각선 값이 recall")
normalize = mode == "행 비율(%)"
cm = np.array(ft["confusion"])
cells = pd.DataFrame([{"정답": CLASSES[i], "예측": CLASSES[j], "장수": int(cm[i, j]),
                       "비율": cm[i, j] / max(cm[i].sum(), 1)} for i in range(len(CLASSES)) for j in range(len(CLASSES))])
value = "비율" if normalize else "장수"
heat = alt.Chart(cells).encode(x=alt.X("예측:N", sort=CLASSES, title="예측"),
                               y=alt.Y("정답:N", sort=CLASSES, title="정답",
                                       axis=alt.Axis(titleAngle=0, titleAlign="right", titleBaseline="bottom",
                                                     titleX=-6, titleY=-6)))
heat = heat.mark_rect().encode(
    color=alt.Color(f"{value}:Q", scale=alt.Scale(range=["#fcfcfb", "#104281"], interpolate="rgb",
                                                  type="linear" if normalize else "symlog"), legend=None),
    tooltip=["정답", "예측", alt.Tooltip("장수:Q", title="웨이퍼 수", format=","),
             alt.Tooltip("비율:Q", title="행 비율", format=".1%")]
) + heat.mark_text(fontSize=11).encode(
    text=alt.Text(f"{value}:Q", format=".0%" if normalize else ","),
    color=alt.condition(alt.datum[value] > (0.55 if normalize else cm.max() / 3), alt.value("white"), alt.value("#0b0b0b")))
st.altair_chart(heat.properties(height=430), width="stretch")

# ---- wafer examples
st.subheader("웨이퍼 맵 예시")
pred = load_predictions(final["run"], final["variant"])
left, right = st.columns([1, 3])
cls = left.selectbox("패턴", CLASSES, index=CLASSES.index("Scratch"))
view = left.radio("분류 결과", VIEWS,
                  help=f"놓침(FN): 정답 {cls}, 예측은 다른 패턴  \n오탐(FP): 예측 {cls}, 정답은 다른 패턴")
if left.button("다른 웨이퍼 보기"):
    st.session_state["seed"] = st.session_state.get("seed", 0) + 1
seed = st.session_state.get("seed", 0)
if view == "맞힘":
    pool = pred[(pred["true"] == cls) & (pred["predicted"] == cls)]
elif view == "놓침":
    pool = pred[(pred["true"] == cls) & (pred["predicted"] != cls)]
else:
    pool = pred[(pred["true"] != cls) & (pred["predicted"] == cls)]
left.caption(f"{len(pool):,}장 중 {min(N_SHOW, len(pool))}장 표시" if len(pool)
             else {"맞힘": "맞힌 웨이퍼 없음", "놓침": "놓친 웨이퍼 없음", "오탐": "오탐 없음"}[view])
right.caption(f'<span style="color:{BAD_DIE}">■</span> 불량 다이&emsp;<span style="color:{GOOD_DIE}">■</span> 양품 다이',
              unsafe_allow_html=True)
if len(pool):
    picked = pool.sample(min(N_SHOW, len(pool)), random_state=seed).sort_index()
    maps = load_maps(tuple(picked.index))
    cols = right.columns(4)
    for k, (wid, r) in enumerate(picked.iterrows()):
        tag = {"맞힘": f"{r['confidence']:.0%}", "놓침": f"예측 {r['predicted']}", "오탐": f"정답 {r['true']}"}[view]
        with cols[k % 4]:
            st.image(wafer_image(maps[wid]))
            st.caption(f"#{wid} · {tag}",
                       help=f"정답 {r['true']}, 예측 {r['predicted']}, 신뢰도 {r['confidence']:.0%}")
