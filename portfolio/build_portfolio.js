// Builds portfolio/portfolio.pptx (5 slides, 16:9) from the figures in portfolio/fig/.
// Run from the portfolio/ directory:  node build_portfolio.js
// Copy rules: assertion headline (<= 2 lines), one visual per page, noun-phrase bullets,
// numbers straight from outputs/*.json (see make_figures.py and RESULT.md).
const pptxgen = require("pptxgenjs");

const FONT = "맑은 고딕";
const INK = "0B0B0B", INK2 = "52514E", GRID = "E4E3DF", TINT = "F3F3F1", BLUE = "2A78D6";
const W = 13.333, ML = 0.6, CW = W - 2 * ML;          // slide width, left margin, content width
const REPO = "github.com/sl2ver/wm811k-wafer-defect-classification";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";                           // 13.333 x 7.5 in
pres.lang = "ko-KR";
pres.author = "이진성";
pres.title = "WM-811K 웨이퍼 맵 결함 패턴 분류";

const base = { fontFace: FONT, color: INK, isTextBox: true, margin: 0, valign: "top", align: "left" };
const text = (slide, t, o) => slide.addText(t, { ...base, ...o });
const runs = (items) => items.map((it, i) => ({ text: it.text, options: { ...(it.options || {}), breakLine: i < items.length - 1 } }));
// label + body paragraphs: [["영향", "..."], ...]
const labeled = (pairs, size = 12, gap = 6) => {
  const out = [];
  pairs.forEach(([label, body], i) => {
    out.push({ text: label + "  ", options: { bold: true, fontSize: size, color: INK, breakLine: false } });
    out.push({ text: body, options: { fontSize: size, color: INK, breakLine: i < pairs.length - 1, paraSpaceAfter: gap } });
  });
  return out;
};

function frame(slide, n, headline, bar, source) {
  slide.background = { color: "FFFFFF" };
  text(slide, headline, { x: ML, y: 0.45, w: CW, h: 1.0, fontSize: 26, bold: true, lineSpacing: 32 });
  text(slide, bar, { x: ML, y: 1.5, w: CW, h: 0.32, fontSize: 12.5, color: INK2 });
  text(slide, source, { x: ML, y: 7.02, w: CW - 0.8, h: 0.28, fontSize: 9, color: INK2 });
  text(slide, `${n} / 5`, { x: W - ML - 0.7, y: 7.02, w: 0.7, h: 0.28, fontSize: 9.5, color: INK2, align: "right" });
}

// ---------------------------------------------------------------- 1. cover
{
  const s = pres.addSlide();
  s.background = { color: "FFFFFF" };
  text(s, "웨이퍼 맵 결함 패턴 분류:\n누수 없는 평가에서 macro-F1 0.843 → 0.909", {
    x: ML, y: 0.7, w: CW, h: 1.1, fontSize: 30, bold: true, lineSpacing: 38 });
  text(s, "2026.09.27  24시간 개인 해커톤(7시간 40분 사용)  ·  판단 13건과 전 과정 검증: 본인 / 코드 구현·실험·조사: Claude Code  ·  새 환경 재현 일치",
    { x: ML, y: 1.9, w: CW, h: 0.32, fontSize: 12.5, color: INK2 });

  text(s, runs([
    { text: "이진성", options: { fontSize: 22, bold: true } },
    { text: "서울과학기술대학교 전기정보공학과 석사과정  ·  RF/EMC 계측", options: { fontSize: 12, color: INK2, paraSpaceBefore: 4 } },
    { text: "계측 데이터를 다루던 습관(수치는 측정에서만, 결과는 재현으로 확인)을 처음 만지는 반도체 제조 데이터에 그대로 적용해 본 24시간 연습",
      options: { fontSize: 12, color: INK, paraSpaceBefore: 10, lineSpacing: 18 } },
  ]), { x: ML, y: 2.55, w: 5.9, h: 1.5 });

  const tiles = [
    ["0.909", "macro-F1 (9클래스, test 25,444장)\n95% CI 0.885–0.922  ·  베이스라인 0.843"],
    ["0.775", "가장 낮은 클래스 recall (Loc)\n베이스라인 0.497 → 모든 클래스 0.50 이상"],
    ["10 / 10", "새 폴더 재현에서 일치한 항목\nclone → 데이터 → 학습 → 평가, 1시간 8분"],
  ];
  tiles.forEach(([num, label], i) => {
    const x = 7.05 + i * 2.0;
    s.addShape(pres.ShapeType.roundRect, { x, y: 2.5, w: 1.88, h: 1.55, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.06 });
    text(s, num, { x: x + 0.14, y: 2.6, w: 1.6, h: 0.55, fontSize: 24, bold: true });
    text(s, label, { x: x + 0.14, y: 3.18, w: 1.62, h: 0.85, fontSize: 9.5, color: INK2, lineSpacing: 13 });
  });

  s.addImage({ path: "fig/p1_wafer_strip.png", x: ML, y: 4.25, w: 12.1, h: 1.75 });
  text(s, "WM-811K 결함 패턴 9종 예시  ·  회색 = 정상 다이, 파란색 = 불량 다이  ·  라벨 있는 웨이퍼 172,950장 중 무작위 표본",
    { x: ML, y: 6.03, w: CW, h: 0.25, fontSize: 9.5, color: INK2 });
  text(s, "이 문서는 분류 성능을 검증한 결과이며, 수율 개선이나 공정 원인 규명 효과는 주장하지 않는다.",
    { x: ML, y: 6.4, w: CW, h: 0.3, fontSize: 11.5, color: INK });
  text(s, `데이터: WM-811K (M.-J. Wu, J.-S. R. Jang, J.-L. Chen, IEEE Trans. Semicond. Manuf. 28(1), 2015; MIR Lab)  ·  코드·기록: ${REPO}`,
    { x: ML, y: 7.02, w: CW - 0.8, h: 0.28, fontSize: 9, color: INK2 });
  text(s, "1 / 5", { x: W - ML - 0.7, y: 7.02, w: 0.7, h: 0.28, fontSize: 9.5, color: INK2, align: "right" });
}

// ---------------------------------------------------------------- 2. leakage & evaluation design
{
  const s = pres.addSlide();
  frame(s, 2,
    "원본 Test의 3,158장은 Training의 복사본이었다 — lot과 쌍둥이 맵을 한 덩어리로 묶어 다시 나눴다",
    "WM-811K 811,457장  ·  라벨 172,950장(none 85%, Near-full 149장 = 989 : 1)  ·  정제 후 169,680장을 70 / 15 / 15로",
    "출처: scripts/explore_data.py, scripts/make_splits.py 실행 결과 (outputs/eda/summary.json, outputs/splits/split_summary.json)");
  text(s, labeled([
    ["누수 1 · 복사본", "원본 Training과 Test 사이에 픽셀까지 같은 맵 3,158장(Test의 2.7%). 그중 14쌍은 라벨도 서로 다름"],
    ["누수 2 · 재기록 사본", "lot 단위로 나눠도 이웃 lot에 1~10픽셀만 다른 맵이 남음. test Center의 41%에 학습 쪽 사본"],
    ["누수 3 · 변환·재검사 사본", "상하 반전·회전한 사본, 불량 다이만 늘어난 재검사본(11~66픽셀 차이)"],
    ["결정", "라벨 충돌 14쌍·중복 3,238장·조각 맵 4장 제외. 반전·회전 8종 중 어느 것으로든 차이가 max(10, 불량 다이 10%) 이하면 쌍둥이로 보고, 쌍둥이로 이어진 lot을 한 덩어리로 묶어 분할 → train–test 겹침 0"],
    ["성공 기준 (사전 확정)", "macro-F1 0.80 이상  ·  모든 클래스 recall 0.50 이상  ·  베이스라인 초과. 신뢰구간은 덩어리 단위 부트스트랩 1,000회"],
  ]), { x: ML, y: 2.05, w: 5.0, h: 4.7, lineSpacing: 18 });
  s.addImage({ path: "fig/p2_leakage.png", x: 5.9, y: 2.0, w: 7.2, h: 4.5 });
}

// ---------------------------------------------------------------- 3. approach & results
{
  const s = pres.addSlide();
  frame(s, 3,
    "특징 23개 + 랜덤 포레스트 0.843 → 맵을 직접 보는 소형 CNN 0.909, Loc·Scratch에서 가장 크게 올랐다",
    "같은 정제 데이터 · 같은 분할 · 같은 test 25,444장  ·  모델 선택은 val만으로  ·  대괄호는 95% 신뢰구간",
    "출처: scripts/baseline.py, train_cnn.py, evaluate_cnn.py 실행 결과 (outputs/baseline/results.json, outputs/cnn/results.json)  ·  신뢰구간: 연결 성분 부트스트랩 1,000회");
  const hdr = (t) => ({ text: t, options: { bold: true, fill: { color: TINT }, color: INK2, fontSize: 10.5 } });
  const cell = (t, o = {}) => ({ text: t, options: { fontSize: 10.5, color: INK, ...o } });
  s.addTable([
    [hdr("모델"), hdr("macro-F1 (9종)"), hdr("결함 8종"), hdr("최저 recall")],
    [cell("베이스라인: 특징 23개 + RF"), cell("0.843 [0.820–0.858]"), cell("0.826"), cell("0.497 (Loc)")],
    [cell("CNN · CE"), cell("0.901 [0.863–0.918]"), cell("0.889"), cell("0.763 (Loc)")],
    [cell("CNN · CE + 보정 (최종)", { bold: true }), cell("0.909 [0.885–0.922]", { bold: true }), cell("0.899", { bold: true }), cell("0.775 (Loc)", { bold: true })],
  ], { x: ML, y: 2.0, w: 5.1, colW: [1.85, 1.55, 0.7, 1.0], rowH: 0.3, fontFace: FONT, fontSize: 10, margin: 3,
       border: { type: "solid", pt: 0.5, color: GRID }, valign: "middle" });
  text(s, labeled([
    ["입력", "64×64 비등방 리사이즈, 축소 시 블록 최대값으로 1다이 폭 Scratch 보존  ·  반전·회전 8종 증강"],
    ["모델", "합성곱 블록 4개, 파라미터 58만, CE 20 epoch(GPU 40분)  ·  클래스별 bias는 val에서만 맞춤"],
    ["효과 없던 시도", "class-weighted CE: 0.825 (none 오탐 증가). 분할을 바꿔 두 번 확인해도 같은 결론"],
    ["짝비교", "같은 test에서 CNN만 맞힘 513장 vs RF만 맞힘 177장 (정확 McNemar p ≈ 9e-39)"],
    ["용도 · 한계", "검토 순서를 정하는 1차 분류 보조. 자동 폐기 판정에는 부적합. 평가 범위는 같은 제품의 새 lot(새 제품은 121장으로만 확인)"],
  ], 11.5, 5), { x: ML, y: 3.55, w: 5.1, h: 3.3, lineSpacing: 17 });
  s.addImage({ path: "fig/p3_recall.png", x: 5.95, y: 2.0, w: 7.0, h: 4.4 });
}

// ---------------------------------------------------------------- 4. verification & the bug I fixed
{
  const s = pres.addSlide();
  frame(s, 4,
    "좋은 결과를 의심했다 — 분할 절차가 Loc recall을 12%p 부풀린 것을 찾아 고쳤다",
    "순서: 영향 → 원인 → 왜 놓쳤나 → 발견과 수정 → 재발 방지  ·  아래 검증 5가지는 모두 스크립트 실행 결과",
    "출처: outputs/splits/split_seed_variance.json, outputs/cnn/outline_intervention.json, scripts/compare_reproduction.py, LOG.md 17:39~21:05 항목");
  text(s, labeled([
    ["영향", "수정 전 test Loc recall CNN 0.82 · RF 0.62 → 수정 후 0.77 · 0.50. test Near-full의 81%도 덩어리 하나에서 나오고 있었음"],
    ["원인", "scikit-learn 1.9.1의 StratifiedGroupKFold는 크고 치우친 그룹을 seed와 무관하게 같은 fold에 넣는다. 쉬운 Loc 가족 132장(28개 lot, 한 제품)이 항상 test에 들어감"],
    ["왜 놓쳤나", "첫 검증은 '분할 사이 겹침 0'만 확인했고, test 구성이 seed에 따라 바뀌는지는 보지 않음"],
    ["발견 → 수정", "분할 변경 후 베이스라인이 '좋아진' 것을 의심 → seed 10개 재분할에서 규칙 간 Loc 격차 15%p → 가족 하나만 옮기는 개입 실험으로 확인 → fold→분할 대응을 seed로 무작위 치환하고 전 모델 재학습 (결론 유지, 대표 수치 0.893 → 0.909)"],
    ["재발 방지", "분할 직후 train–test 쌍둥이·lot 겹침 0과 클래스별 최대 덩어리 비중을 검사"],
  ]), { x: ML, y: 2.0, w: 7.0, h: 3.6, lineSpacing: 18 });
  s.addImage({ path: "fig/p4_e11.png", x: 7.9, y: 2.0, w: 5.2, h: 3.7 });

  const checks = [
    ["셔플 라벨 (negative control)", "macro-F1 0.102 = 다수 클래스 수준"],
    ["무작위 분할 vs 주 분할", "CNN 0.895 vs 0.909. 누수를 막은 뒤에는 차이 없음"],
    ["외곽선 개입 실험", "25×27 제품 외곽선을 바꿔 끼워도 예측 99.5% 이상 유지 → 지름길 아님"],
    ["오분류 96장 이중맹검 판정", "두 평가자 일치 70%. 애매 46% / 모델 27% / 라벨 의심 27%. 약점은 6~10다이 짧은 Scratch"],
    ["새 폴더 재현", "clone → README 순서 실행 1시간 8분 → 비교 10개 항목 전부 일치"],
  ];
  const cw = (CW - 4 * 0.15) / 5;
  checks.forEach(([label, body], i) => {
    const x = ML + i * (cw + 0.15);
    s.addShape(pres.ShapeType.roundRect, { x, y: 5.85, w: cw, h: 1.05, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.05 });
    text(s, runs([
      { text: label, options: { bold: true, fontSize: 10.5, paraSpaceAfter: 3 } },
      { text: body, options: { fontSize: 10, color: INK, lineSpacing: 14 } },
    ]), { x: x + 0.12, y: 5.93, w: cw - 0.24, h: 0.92 });
  });
}

// ---------------------------------------------------------------- 5. process & reflection
{
  const s = pres.addSlide();
  frame(s, 5,
    "24시간 중 7시간 40분: 체크포인트 6개에서 멈춰 판단 13건을 내리고, 오류 14건을 기록했다",
    "기록: PLAN.md(변경 이력 4건) · LOG.md(지시 원문·판단·오류) · RESULT.md(수치·버린 것 9·한계 9) · GLOSSARY.md  ·  저장소 공개",
    "출처: LOG.md(판단 지점 1~13, 오류 기록 E1~E14), PLAN.md, RESULT.md");
  s.addImage({ path: "fig/p5_timeline.png", x: ML, y: 1.95, w: 12.1, h: 2.0 });
  text(s, "시간은 T0(2026-09-27 14:48, 첫 지시) 기준 경과  ·  파란 점 = 체크포인트(보고 후 지시 대기), 주황 점 = 오류 발견",
    { x: ML, y: 3.97, w: CW, h: 0.25, fontSize: 9.5, color: INK2 });
  const colw = (CW - 2 * 0.3) / 3;
  const cols = [
    ["내가 정한 것 (13건 중 3건)", [
      ["라벨 없는 638,507장 제외", "분포가 다르고(불량 0개 맵 5.8만 장), 평가 맵의 쌍둥이 5,408장이 섞여 있어서"],
      ["성공 기준 macro-F1 0.80", "선행연구의 lot 분할 0.85는 재기록 사본 누수를 포함했을 가능성, 라벨 노이즈도 확인돼서"],
      ["불균형은 가중 손실 대신 val 사후 보정", "같은 test에서 비교해 채택 (weighted CE 0.825 < CE 0.901)"],
    ]],
    ["한계 · 다음 단계", [
      ["단일 분할", "seed 10개 평균보다 약 0.01 낙관 → 그룹 5-fold로 전체 평가"],
      ["드문 클래스", "Near-full test 18장, CI 0.70–1.00 → 표본 확보 전까지 수치 유보"],
      ["라벨 노이즈 · 짧은 Scratch", "같은 맵 다른 라벨 14쌍 → none↔Edge-Loc 기준 재정의, 6~10다이 선용 고해상도 입력"],
    ]],
    ["AI와 일한 방식", [
      ["역할", "문제 정의·평가 설계·판단·최종 검토: 본인 / 구현·실험·문헌 조사: Claude Code"],
      ["경계", "누수 판정 기준, 수치 채택, 버그 판정은 위임하지 않음. 체크포인트마다 선택지와 근거를 받아 결정"],
      ["검증", "조사·계산은 독립 에이전트가 반박 검증(오류 14건 중 7건 발견). 배운 것: 수치는 실행에서만, 좋은 결과일수록 먼저 의심"],
    ]],
  ];
  cols.forEach(([title, items], i) => {
    const x = ML + i * (colw + 0.3);
    text(s, title, { x, y: 4.32, w: colw, h: 0.3, fontSize: 12.5, bold: true });
    text(s, labeled(items, 11, 5), { x, y: 4.65, w: colw, h: 2.3, lineSpacing: 16 });
  });
}

pres.writeFile({ fileName: "portfolio.pptx" }).then((f) => console.log("written", f));
