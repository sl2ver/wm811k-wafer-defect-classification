"""Stage 5: one-page Streamlit dashboard of the final results.

Usage (from project root, after the pipeline has produced its outputs):
    .venv\\Scripts\\streamlit run scripts\\dashboard.py

Reads outputs/baseline/results.json, outputs/cnn/results.json,
outputs/cnn/test_predictions.parquet and data/processed/labeled_clean.pkl.
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
BASE_COLOR, CNN_COLOR = "#eb6834", "#2a78d6"
WAFER_RGB = np.array([[252, 252, 251], [214, 213, 208], [24, 79, 149]], dtype=np.uint8)  # off / good / bad die
N_SHOW = 12

st.set_page_config(page_title="WM-811K 결함 패턴 분류", layout="wide")


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


base, cnn = load_results()
final = cnn["final"]
ft = final["test"]
bar = cnn["baseline_bar"]
bt = base["splits"]["split_main"][bar["model"]]["test"]
success = cnn["success"]

st.title("WM-811K 웨이퍼 맵 결함 패턴 분류")
st.caption(
    f"주 분할 test {sum(ft['per_class'][c]['support'] for c in CLASSES):,}장 기준. "
    "lot과 쌍둥이 맵(반전·회전 포함)을 한 덩어리로 묶어 나눈 분할이라, 평가 웨이퍼는 학습 때 본 적 없는 lot에서 나온다. "
    "괄호 안은 연결 성분 부트스트랩 95 % 신뢰구간."
)

# ---- headline numbers
c1, c2, c3, c4 = st.columns(4)
c1.metric("macro-F1 (9클래스)", f"{ft['macro_f1']:.3f}", f"{ft['macro_f1'] - bt['macro_f1']:+.3f} vs 베이스라인")
c1.caption(f"[{ft['macro_f1_ci95'][0]:.3f}, {ft['macro_f1_ci95'][1]:.3f}] · 베이스라인 {bt['macro_f1']:.3f}")
c2.metric("결함 8종 macro-F1", f"{ft['defect8_macro_f1']:.3f}",
          f"{ft['defect8_macro_f1'] - bt['defect8_macro_f1']:+.3f} vs 베이스라인")
low_c = min(CLASSES, key=lambda c: ft["per_class"][c]["recall"])
low_b = min(CLASSES, key=lambda c: bt["per_class"][c]["recall"])
c3.metric("가장 낮은 클래스 recall", f"{ft['per_class'][low_c]['recall']:.3f}", f"{low_c}", delta_color="off", delta_arrow="off")
c3.caption(f"베이스라인: {low_b} {bt['per_class'][low_b]['recall']:.3f}")
c4.metric("balanced accuracy", f"{ft['balanced_acc']:.3f}", f"{ft['balanced_acc'] - bt['balanced_acc']:+.3f} vs 베이스라인")

checks = [("macro-F1 ≥ 0.80", success["macro_f1_ge_0.80"]),
          ("모든 클래스 recall ≥ 0.50", success["all_recall_ge_0.50"]),
          (f"베이스라인({bar['model']}, {bar['test_macro_f1']:.3f})보다 높음", success["beats_best_baseline"])]
st.markdown("**성공 기준** · " + " · ".join(f"{'✅ 충족' if ok else '❌ 미충족'} {text}" for text, ok in checks))
st.caption(f"최종 모델: 소형 CNN ({final['run']}, {final['variant']}) — val 성능만으로 선택. "
           f"베이스라인: 손으로 만든 특징 23개 + {bar['model']}.")

# ---- per-class bars
st.subheader("클래스별 성능")
metric = st.radio("지표", ["recall", "F1"], horizontal=True, label_visibility="collapsed")
key = "recall" if metric == "recall" else "f1"
rows = []
for model, res, color in (("베이스라인", bt, BASE_COLOR), ("최종 CNN", ft, CNN_COLOR)):
    for c in CLASSES:
        pc = res["per_class"][c]
        rows.append({"클래스": f"{c} ({pc['support']:,})", "모델": model, "값": pc[key],
                     "하한": pc["recall_ci95"][0] if key == "recall" else None,
                     "상한": pc["recall_ci95"][1] if key == "recall" else None})
bars = pd.DataFrame(rows)
order = [f"{c} ({ft['per_class'][c]['support']:,})" for c in CLASSES]
color = alt.Color("모델:N", scale=alt.Scale(domain=["베이스라인", "최종 CNN"], range=[BASE_COLOR, CNN_COLOR]),
                  legend=alt.Legend(orient="top", title=None))
base_chart = alt.Chart(bars).encode(y=alt.Y("클래스:N", sort=order, title=None), yOffset="모델:N", color=color)
chart = base_chart.mark_bar(cornerRadiusEnd=3, size=10).encode(
    x=alt.X("값:Q", scale=alt.Scale(domain=[0, 1]), title=metric),
    tooltip=["모델", "클래스", alt.Tooltip("값:Q", format=".3f"), alt.Tooltip("하한:Q", format=".3f"),
             alt.Tooltip("상한:Q", format=".3f")])
if key == "recall":
    chart += base_chart.mark_rule(color="#52514e").encode(x="하한:Q", x2="상한:Q")
    chart += alt.Chart(pd.DataFrame({"x": [0.5]})).mark_rule(color="#52514e", strokeWidth=1).encode(x="x:Q")
st.altair_chart(chart.properties(height=420), width="stretch")
if key == "recall":
    st.caption("막대 옆 가는 선: 부트스트랩 95 % 신뢰구간 · 회색 세로선: 성공 기준 0.50")

# ---- confusion matrix
st.subheader("혼동 행렬 (최종 CNN)")
normalize = st.toggle("행 기준 비율(%)로 보기", value=True)
cm = np.array(ft["confusion"])
cells = pd.DataFrame([{"정답": CLASSES[i], "예측": CLASSES[j], "장수": int(cm[i, j]),
                       "비율": cm[i, j] / max(cm[i].sum(), 1)} for i in range(len(CLASSES)) for j in range(len(CLASSES))])
value = "비율" if normalize else "장수"
heat = alt.Chart(cells).encode(x=alt.X("예측:N", sort=CLASSES, title="예측"), y=alt.Y("정답:N", sort=CLASSES, title=None))
heat = heat.mark_rect().encode(
    color=alt.Color(f"{value}:Q", scale=alt.Scale(range=["#fcfcfb", "#104281"], interpolate="rgb", type="linear" if normalize else "symlog"),
                    legend=None),
    tooltip=["정답", "예측", "장수", alt.Tooltip("비율:Q", format=".1%")]
) + heat.mark_text(fontSize=11).encode(
    text=alt.Text(f"{value}:Q", format=".0%" if normalize else ","),
    color=alt.condition(alt.datum[value] > (0.55 if normalize else cm.max() / 3), alt.value("white"), alt.value("#0b0b0b")))
st.altair_chart(heat.properties(height=430), width="stretch")
st.caption("행 = 정답 클래스, 열 = 예측 클래스. 칸에 마우스를 올리면 장수가 보인다.")

# ---- wafer examples
st.subheader("웨이퍼 맵 예시")
pred = load_predictions(final["run"], final["variant"])
left, right = st.columns([1, 3])
cls = left.selectbox("클래스", CLASSES, index=CLASSES.index("Scratch"))
view = left.radio("보기", ["정답 (맞힘)", "놓침 (이 클래스인데 다른 것으로 예측)", "오탐 (다른 클래스인데 이 클래스로 예측)"])
seed = left.number_input("표본 seed", min_value=0, value=0, step=1)
if view.startswith("정답"):
    pool = pred[(pred["true"] == cls) & (pred["predicted"] == cls)]
elif view.startswith("놓침"):
    pool = pred[(pred["true"] == cls) & (pred["predicted"] != cls)]
else:
    pool = pred[(pred["true"] != cls) & (pred["predicted"] == cls)]
left.caption(f"해당 웨이퍼 {len(pool):,}장 중 {min(N_SHOW, len(pool))}장")
if len(pool):
    picked = pool.sample(min(N_SHOW, len(pool)), random_state=int(seed)).sort_index()
    maps = load_maps(tuple(picked.index))
    cols = right.columns(4)
    for k, (wid, r) in enumerate(picked.iterrows()):
        with cols[k % 4]:
            st.image(wafer_image(maps[wid]))
            st.caption(f"#{wid} · 정답 {r['true']} · 예측 {r['predicted']} ({r['confidence']:.2f})")
    right.caption("색: 흰색 = 웨이퍼 밖, 회색 = 정상 다이, 파란색 = 불량 다이")
