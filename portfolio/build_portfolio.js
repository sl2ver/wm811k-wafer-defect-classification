// Portfolio deck: 8 pages, 16:9, Pretendard. Build chain (from portfolio/):
//   export NODE_PATH="$(npm root -g)" && node build_portfolio.js
//   python postprocess_pptx.py portfolio.pptx      # Korean word-wrap (latinLnBrk=0 + lang=ko-KR)
//   powershell -NoProfile -ExecutionPolicy Bypass -File export_pdf.ps1   # PDF + preview PNGs via PowerPoint
// Line breaks are planned here with Pretendard advance widths (font_metrics.json): a paragraph that
// needs more than one line is broken at sentence/phrase boundaries when those fit, otherwise at word
// boundaries with even line lengths, so no line ends with a stray word. " " keeps a number with its unit.
// All numbers come from outputs/*.json and LOG.md (see the footer of each page).
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.lang = "ko-KR";
pres.author = "이진성";
pres.title = "웨이퍼 맵 불량 패턴 분류";

const F = "Pretendard";
const FS = "Pretendard SemiBold";
const INK = "0B0B0B", INK2 = "52514E", GRAY = "8F8E8A", LINE = "DAD9D4", TINT = "F3F3F1", NAVY = "1F4E9A", WHITE = "FFFFFF";
const W = 13.333, ML = 0.7, CW = W - 2 * ML; // content width 11.933
const TOTAL = 8;
const NB = " ";

// ---------------------------------------------------------------- text measurement and line planning
const METRICS = JSON.parse(fs.readFileSync("font_metrics.json", "utf8"));
function advance(ch, style) {
  const m = METRICS[style];
  if (ch === NB) ch = " ";
  const w = m.w[ch];
  if (w !== undefined) return w / m.upem;
  const cp = ch.codePointAt(0);
  if (cp >= 0xac00 && cp <= 0xd7a3) return m.hangul / m.upem;
  return 0.9; // unknown (CJK punctuation etc.): assume full width
}
function measure(text, pt, style) {
  let s = 0;
  for (const ch of text) s += advance(ch, style);
  return (s * pt) / 72; // inches
}
// Pack units (words or phrases) into the fewest lines, then narrow the width until one more line
// would be needed, so the lines come out even. `sep` is the string re-inserted between units.
function pack(units, sep, maxW, pt, style) {
  const uw = units.map((u) => measure(u, pt, style)), sw = measure(sep, pt, style);
  const greedy = (limit) => {
    const lines = [];
    let cur = [], curW = 0;
    units.forEach((u, i) => {
      const add = cur.length ? sw + uw[i] : uw[i];
      if (cur.length && curW + add > limit) { lines.push(cur.join(sep)); cur = [u]; curW = uw[i]; }
      else { cur.push(u); curW += add; }
    });
    if (cur.length) lines.push(cur.join(sep));
    return lines;
  };
  const n = greedy(maxW).length;
  let lo = 0, hi = maxW;
  for (let k = 0; k < 30; k++) { const mid = (lo + hi) / 2; if (greedy(mid).length > n) lo = mid; else hi = mid; }
  return greedy(hi);
}
// Split after each delimiter (the delimiter stays with the preceding phrase).
function phrases(text, delims) {
  const out = [];
  let cur = "";
  for (let i = 0; i < text.length; i++) {
    cur += text[i];
    for (const d of delims) {
      if (cur.endsWith(d)) { out.push(cur.trimEnd()); cur = ""; break; }
    }
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}
const BOUNDARIES = [[". "], [". ", " / "], [". ", " / ", ", "], [". ", " / ", ", ", " → "]];
function wrap(text, widthIn, pt, style) {
  const target = widthIn * 0.965; // safety margin for kerning/rounding differences in PowerPoint
  if (measure(text, pt, style) <= target) return [text];
  const byWords = pack(text.split(" "), " ", target, pt, style);
  for (const delims of BOUNDARIES) {
    const ph = phrases(text, delims);
    if (ph.length < 2 || ph.some((p) => measure(p, pt, style) > target)) continue;
    const lines = pack(ph, " ", target, pt, style);
    if (lines.length <= byWords.length) return lines;
  }
  return byWords;
}
// Runs for one paragraph: soft line breaks inside, hard break after (unless last).
function paraRuns(lines, opts, last) {
  return lines.map((ln, i) => ({
    text: ln,
    options: Object.assign({}, opts, i > 0 ? { softBreakBefore: true } : {}, i === lines.length - 1 && !last ? { breakLine: true } : {}),
  }));
}

// ---------------------------------------------------------------- helpers
function text(slide, str, o) {
  slide.addText(str, Object.assign({ fontFace: F, color: INK, isTextBox: true, margin: 0, valign: "top" }, o));
}
// One wrapped paragraph (plain text box).
function para(slide, str, o) {
  const pt = o.fontSize || 14, style = o.bold ? "Bold" : o.fontFace === FS ? "SemiBold" : "Regular";
  text(slide, paraRuns(wrap(str, o.w, pt, style), {}, true), o);
}
// Several wrapped paragraphs in one box (quotes etc.).
function paras(slide, items, o) {
  const pt = o.fontSize || 12, style = o.bold ? "Bold" : "Regular";
  const runs = [];
  items.forEach((it, i) => runs.push(...paraRuns(wrap(it, o.w, pt, style), {}, i === items.length - 1)));
  text(slide, runs, o);
}
// Bullets, one paragraph each, wrapped to the box width minus the bullet indent.
function bullets(slide, items, o) {
  const pt = o.fontSize || 13, indent = 0.22;
  const runs = [];
  items.forEach((it, i) => {
    const lines = wrap(it, o.w - indent, pt, "Regular");
    lines.forEach((ln, j) => runs.push({
      text: ln,
      options: Object.assign({}, j === 0 ? { bullet: { indent: 14 } } : { softBreakBefore: true },
        j === lines.length - 1 && i < items.length - 1 ? { breakLine: true } : {}),
    }));
  });
  text(slide, runs, Object.assign({ fontSize: pt, lineSpacing: Math.round(pt * 1.45), paraSpaceAfter: 6 }, o));
}
// "Label | body" rows as a borderless table, so wrapped body lines align under the body column.
function labeled(slide, pairs, o) {
  const pt = o.fontSize || 13, labelW = o.labelW || 1.2, bodyW = o.w - labelW;
  const rows = pairs.map(([label, body]) => [
    { text: label, options: { bold: true, color: o.color || INK, valign: "top" } },
    { text: paraRuns(wrap(body, bodyW - 0.12, pt, "Regular"), {}, true), options: { color: o.color || INK, valign: "top" } },
  ]);
  slide.addTable(rows, {
    x: o.x, y: o.y, w: o.w, colW: [labelW, bodyW], fontFace: F, fontSize: pt, color: o.color || INK,
    border: { type: "none" }, fill: { color: o.fill || WHITE }, margin: [0.04, 0.06, 0.05, 0], rowH: o.rowH || 0.3,
  });
}
// Bordered table; first column (or header row) tinted; every cell wrapped to its column width.
function table(slide, rows, o) {
  const header = !!o.header, pt = o.fontSize || 12;
  const body = rows.map((r, ri) => r.map((c, ci) => {
    const bold = (header && ri === 0) || (!header && ci === 0) || (o.boldRows || []).includes(ri);
    const lines = wrap(c, o.colW[ci] - 0.22, pt, bold ? "Bold" : "Regular");
    return {
      text: paraRuns(lines, {}, true),
      options: { bold, fill: { color: (header && ri === 0) || (!header && ci === 0) ? TINT : WHITE }, color: INK, valign: "middle", align: "left" },
    };
  }));
  slide.addTable(body, {
    x: o.x, y: o.y, w: o.w, colW: o.colW, rowH: o.rowH || 0.4, fontFace: F, fontSize: pt, color: INK,
    border: { type: "solid", pt: 0.5, color: LINE }, margin: [0.05, 0.1, 0.05, 0.1], valign: "middle",
  });
}
// "AI가 한 일 / 내가 한 일" strip on the content pages.
function roles(slide, ai, me, o) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: o.x, y: o.y, w: o.w, h: o.h, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.05 });
  labeled(slide, [["Claude Code", ai], ["본인", me]], { x: o.x + 0.12, y: o.y + 0.06, w: o.w - 0.24, labelW: 1.0, fontSize: o.fontSize || 11, fill: TINT, color: INK2, rowH: 0.26 });
}
function frame(slide, n, title, key, source) {
  slide.addShape(pres.shapes.RECTANGLE, { x: ML, y: 0.55, w: 0.55, h: 0.55, fill: { color: INK }, line: { color: INK } });
  text(slide, String(n).padStart(2, "0"), { x: ML, y: 0.55, w: 0.55, h: 0.55, fontSize: 16, bold: true, color: WHITE, align: "center", valign: "middle" });
  text(slide, title, { x: ML + 0.75, y: 0.48, w: CW - 0.75, h: 0.7, fontSize: 28, bold: true, valign: "middle" });
  para(slide, key, { x: ML, y: 1.33, w: CW, h: 0.9, fontFace: FS, fontSize: 18, color: NAVY, lineSpacing: 26 });
  if (source) text(slide, source, { x: ML, y: 7.02, w: CW - 1.0, h: 0.3, fontSize: 10, color: GRAY });
  text(slide, `${n + 1} / ${TOTAL}`, { x: W - ML - 1.0, y: 7.02, w: 1.0, h: 0.3, fontSize: 10, color: GRAY, align: "right" });
}

// ---------------------------------------------------------------- 1. cover
{
  const s = pres.addSlide();
  text(s, "웨이퍼 맵 불량 패턴 분류", { x: ML, y: 1.9, w: CW, h: 0.9, fontSize: 40, bold: true });
  text(s, "lot 단위로 나눈 평가에서 macro-F1 0.909를 확인한 소형 CNN", { x: ML, y: 2.85, w: CW, h: 0.5, fontFace: FS, fontSize: 20, color: NAVY });
  text(s, "WM-811K 공개 데이터  |  개인 프로젝트  |  2026. 9.", { x: ML, y: 3.5, w: CW, h: 0.4, fontSize: 14, color: INK2 });
  s.addImage({ path: "fig/p1_wafer_strip.png", x: ML, y: 4.3, w: 11.9, h: 1.6 });
  text(s, "이진성", { x: ML, y: 6.45, w: 4, h: 0.4, fontSize: 16, bold: true });
}

// ---------------------------------------------------------------- 2. overview (doubles as table of contents)
{
  const s = pres.addSlide();
  frame(s, 1, "프로젝트 개요",
    "Claude Code에 구현과 실험을 맡기고 평가 방식과 판단·검증은 제가 맡아, 학습에 쓰지 않은 lot에서 macro-F1 0.909를 확인했습니다.");
  table(s, [
    ["기간·형태", "2026년 9월, 개인 프로젝트(1인)"],
    ["AI 활용", `구현·실험·문헌 조사: Claude Code / 문제 정의·평가 설계·판단·검증: 본인. 별도 검증 에이전트 45개(워크플로${NB}10회), 체크포인트 6개에서 판단${NB}13건, 오류${NB}15건 기록`],
    ["데이터", `WM-811K 웨이퍼 맵 811,457장 중 라벨 있는 172,950장, 불량 패턴${NB}9종`],
    ["문제", "같은 웨이퍼의 복사본이 학습과 평가에 섞이는 누수를 막고, 새 lot에서의 성능을 재기"],
    ["결과", `macro-F1 0.843(베이스라인) → 0.909(CNN), 모든 패턴 recall${NB}0.77 이상`],
    ["환경", "Python 3.12, PyTorch 2.7(CUDA 11.8), scikit-learn 1.9.1, Streamlit, Quadro P2000"],
  ], { x: ML, y: 2.4, w: 7.0, colW: [1.25, 5.75], rowH: 0.46, fontSize: 12.5 });

  text(s, "진행 순서", { x: 8.1, y: 2.4, w: 4.5, h: 0.3, fontSize: 12, color: GRAY });
  const steps = [["데이터 탐색과 누수 확인", "3쪽"], ["평가 설계: lot 단위 분할, 성공 기준", "3쪽"],
    ["베이스라인과 소형 CNN", "4쪽"], ["검증 다섯 가지와 오류 수정", "5쪽"], ["AI 활용 방식: 지시와 역할", "6쪽"],
    ["AI 활용 방식: 검증과 오류 적발", "7쪽"], ["결론·한계·재현 정보", "8쪽"]];
  steps.forEach(([name, page], i) => {
    const y = 2.75 + i * 0.56;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.1, y, w: 4.53, h: 0.47, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.06 });
    text(s, [{ text: `${i + 1}  `, options: { bold: true, color: NAVY } }, { text: name }],
      { x: 8.25, y, w: 3.6, h: 0.47, fontSize: 13, valign: "middle" });
    text(s, page, { x: 11.75, y, w: 0.8, h: 0.47, fontSize: 12, color: INK2, align: "right", valign: "middle" });
  });

  labeled(s, [
    ["lot", `같은 공정 조건으로 함께 처리한 웨이퍼 묶음(최대${NB}25장). 한 lot의 맵은 서로 닮아서 분할의 기본 단위로 씀`],
    ["macro-F1", "패턴 9종 F1의 단순 평균. 85%를 차지하는 none에 점수가 치우치지 않음"],
    ["recall", "실제 그 패턴인 웨이퍼 중 맞힌 비율"],
  ], { x: ML, y: 5.95, w: 7.0, labelW: 1.0, fontSize: 11.5, color: INK2, rowH: 0.27 });
}

// ---------------------------------------------------------------- 3. problem: data and evaluation design
{
  const s = pres.addSlide();
  frame(s, 2, "문제 정의: 데이터와 평가 방식",
    "AI 에이전트 10개의 탐색으로 이상점 17개를 받았고, 그중 '같은 웨이퍼의 복사본이 학습과 평가에 섞인다'를 핵심 문제로 정해 lot과 복사본을 한 묶음으로 나누는 규칙을 세웠습니다.",
    "근거: scripts/explore_data.py, scripts/make_splits.py → outputs/eda/summary.json, outputs/splits/split_summary.json");
  text(s, "누수 3겹", { x: ML, y: 2.3, w: 3, h: 0.3, fontSize: 14, bold: true });
  table(s, [
    ["원본 분할", `test${NB}3,158장이 train의 복사본. 같은 맵에 다른 라벨이 붙은 쌍${NB}14개`],
    ["lot 단위 분할", `재검사로 생긴 거의 같은 맵이 양쪽에 남음. Center 패턴은 test의${NB}40.7%`],
    ["반전·회전 복사본", "뒤집거나 돌린 복사본도 있어 8가지 변환을 모두 비교해서 묶음"],
  ], { x: ML, y: 2.62, w: 6.1, colW: [1.55, 4.55], rowH: 0.46 });
  labeled(s, [
    ["데이터", `라벨 있는 172,950장 사용. none${NB}85.2%, Near-full${NB}149장(0.09%)으로 불균형`],
    ["채택한 분할", `lot과 10픽셀 이내 복사본(반전·회전 포함)을 한 묶음으로 나눔. 학습:검증:테스트 = 70:15:15`],
    ["성공 기준", `test macro-F1${NB}0.80 이상, 모든 패턴 recall${NB}0.50 이상, 베이스라인 초과. 95% 신뢰구간 병기`],
  ], { x: ML, y: 4.2, w: 6.1, labelW: 1.25, fontSize: 13, rowH: 0.34 });
  roles(s, "탐색·정제·분할 스크립트 3개 구현, 이상점 탐색 에이전트 10개 병렬 실행",
    `정제 규칙, 분할 방식, 성공 기준 결정(판단 지점${NB}6·7). 라벨 없는 638,507장 제외 결정`, { x: ML, y: 6.05, w: 6.1, h: 0.82 });
  s.addImage({ path: "fig/p3_leakage.png", x: 7.05, y: 2.35, w: 5.6, h: 2.9 });
  s.addImage({ path: "fig/p3_pairs.png", x: 7.05, y: 5.35, w: 5.6, h: 1.55 });
}

// ---------------------------------------------------------------- 4. method and results
{
  const s = pres.addSlide();
  frame(s, 3, "방법과 결과",
    "베이스라인과 CNN 구현은 AI에 맡기고, 개선 방향(맵을 직접 보는 소형 CNN + val 보정)과 채택 기준은 제가 정했습니다. 같은 test 25,444장에서 macro-F1 0.843 → 0.909.",
    "근거: scripts/baseline.py, train_cnn.py, evaluate_cnn.py → outputs/baseline/results.json, outputs/cnn/results.json. 신뢰구간은 연결 성분 부트스트랩 1,000회");
  table(s, [
    ["모델", "macro-F1 (95% CI)", "최저 recall"],
    ["베이스라인: 특징 23개 + 랜덤 포레스트", "0.843 (0.820–0.858)", "0.497 (Loc)"],
    ["소형 CNN, CE", "0.901 (0.863–0.918)", "0.763 (Loc)"],
    ["소형 CNN, CE + val 보정 (최종)", "0.909 (0.885–0.922)", "0.775 (Loc)"],
  ], { x: ML, y: 2.35, w: 6.2, colW: [2.9, 2.05, 1.25], rowH: 0.36, header: true, boldRows: [3] });
  labeled(s, [
    ["입력", `64×64로 축소. 축소할 때 블록 최대값을 써서 1다이 폭 Scratch를 남김. 반전·회전 8종${NB}증강`],
    ["모델", `합성곱 블록 4개, 파라미터 58만, CE 20${NB}epoch(GPU${NB}40분). 패턴별 점수 보정값은 val에서만 정함`],
    ["효과 없던 시도", `class-weighted CE: macro-F1${NB}0.825, none 오탐 증가 → 미채택`],
    ["용도", "엔지니어가 어떤 웨이퍼를 먼저 볼지 정하는 1차 분류 보조. 자동 폐기 판정에는 부적합"],
  ], { x: ML, y: 3.92, w: 6.2, labelW: 1.3, fontSize: 12.5, rowH: 0.3 });
  roles(s, "특징 23개·랜덤 포레스트·CNN 구현, 학습 5회(CE, weighted CE, 셔플 라벨, 무작위 분할, 재학습)",
    `개선 방향과 입력 크기 결정(판단 지점${NB}8), weighted CE 폐기와 val 보정 채택(판단 지점${NB}10)`, { x: ML, y: 5.98, w: 6.2, h: 0.95, fontSize: 10.5 });
  s.addImage({ path: "fig/p4_recall.png", x: 7.05, y: 2.35, w: 5.6, h: 4.4 });
}

// ---------------------------------------------------------------- 5. verification and the error that was fixed
{
  const s = pres.addSlide();
  frame(s, 4, "검증과 오류 수정",
    "점수가 예상보다 높게 나오자 검증 에이전트 4개를 병렬로 돌리고 개입 실험을 시켰습니다. 그 과정에서 분할 절차의 오류 하나를 잡아 고쳤습니다.",
    "근거: outputs/splits/split_seed_variance.json, outputs/cnn/outline_intervention.json, scripts/compare_reproduction.py, LOG.md 오류 기록 E11");
  table(s, [
    ["검증", "방법", "결과"],
    ["우연 수준", "라벨을 섞어 같은 CNN 학습", `macro-F1${NB}0.102 (우연 수준)`],
    ["누수 제거 효과", "무작위 분할 vs lot 분할, 같은 모델", `0.895${NB}vs${NB}0.909, 차이 없음`],
    ["지름길 학습", "25×27 제품 외곽선을 다른 제품 것으로 교체", `예측 99.5% 이상 유지`],
    ["오분류 검토", "96장을 라벨 가린 채 독립 판정 2회", `애매${NB}46% / 모델 오류${NB}27% / 라벨 의심${NB}27%`],
    ["재현", "새 폴더에 clone 후 README 순서로 재실행", `1시간${NB}8분, 비교 항목 10개 일치`],
  ], { x: ML, y: 2.35, w: 6.5, colW: [1.35, 2.85, 2.3], rowH: 0.46, header: true });
  roles(s, "검증 에이전트 4개 병렬 실행, 개입 실험·재현 비교 스크립트 구현",
    `오류 판정, 절차 수정 후 전부 재학습 결정(판단 지점${NB}9), 재현 범위 결정(판단 지점${NB}11·12)`, { x: ML, y: 5.5, w: 6.5, h: 0.72 });
  s.addImage({ path: "fig/p5_e11.png", x: 7.45, y: 2.3, w: 4.77, h: 2.6 });
  text(s, "분할 절차 오류 (LOG E11)", { x: 7.45, y: 4.98, w: 5.2, h: 0.3, fontSize: 13, bold: true });
  labeled(s, [
    ["원인", `StratifiedGroupKFold(scikit-learn 1.9.1)가 크고 치우친 그룹을 seed와 무관하게 같은 fold에 배정 → 맞히기 쉬운 Loc 웨이퍼${NB}132장이 항상 test에 들어감`],
    ["발견", `베이스라인 점수가 이유 없이 오름 → seed${NB}10개로 다시 나눠 Loc recall 최대${NB}15%p 차이 확인 → lot 묶음 하나를 test에서 빼 보는 실험`],
    ["수정", `fold 배정을 seed로 무작위 치환하고 모든 모델 재학습(0.893 → 0.909). 분할 직후 겹침과 lot 묶음 비중을 검사하는 단계 추가`],
  ], { x: 7.45, y: 5.28, w: 5.2, labelW: 0.55, fontSize: 10.5, rowH: 0.28 });
}

// ---------------------------------------------------------------- 6. how the AI was used (1): instructions and roles
{
  const s = pres.addSlide();
  frame(s, 5, "AI 활용 방식 ①  지시와 역할",
    "첫 지시문에 AI가 할 일과 멈출 지점, 수치와 오류의 기록 규칙을 정해 두고, 체크포인트 6개에서 판단 13건을 내렸습니다.",
    "근거: docs/wafer_project_prompt.md(첫 지시문 원문), LOG.md 지시 원문·판단 지점 1~13");
  text(s, "첫 지시문에서 정한 규칙 (원문)", { x: ML, y: 2.3, w: 6.0, h: 0.3, fontSize: 13, bold: true });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: ML, y: 2.65, w: 6.0, h: 2.65, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.05 });
  paras(s, [
    "“판단이 필요한 지점에서는 멈추고 나에게 묻는다. 선택지 2~3개와 각각의 장단점을 제시하고, 추천이 있으면 이유와 함께 밝힌다. 조용히 하나를 골라 진행하지 않는다.”",
    "“내 지시가 틀렸다고 생각하면 반대 의견임을 명시하고 근거를 댄다. 그대로 따르지 않는다.”",
    "“숫자는 실행 결과에서만 가져온다. 추정치를 결과처럼 쓰지 않는다. 결과를 적을 때는 어떤 스크립트·어떤 설정에서 나온 값인지 함께 적는다.”",
    "“오류 기록: 네 코드나 판단이 틀렸던 경우, 누가(나/너) 어떻게 발견했고 무엇을 바꿨는지. 틀린 것을 숨기지 말고 반드시 남긴다.”",
    "“각 체크포인트(★)에서는 반드시 멈추고 나에게 보고한 뒤 지시를 기다린다.”",
  ], { x: ML + 0.15, y: 2.78, w: 5.7, h: 2.45, fontSize: 12, color: INK, lineSpacing: 17, paraSpaceAfter: 7 });
  table(s, [
    ["판단", "선택", "근거"],
    ["라벨 없는 638,507장", "제외", `불량 0개 맵이 5.8만${NB}장 등 분포가 다르고, 평가 맵의 복사본 5,408장이 섞여 있음`],
    ["분할 오류 대응", "절차 수정 후 전부 재학습", "닮은 맵 묶음 규칙은 유지하고 fold 배정만 무작위로. 이전 결과는 '편향된 분할'로 표시해 남김"],
  ], { x: ML, y: 5.45, w: 6.0, colW: [1.35, 1.55, 3.1], rowH: 0.3, header: true, fontSize: 10.5 });

  // work loop
  const fx = 7.0, fw = 5.63;
  text(s, "작업 흐름", { x: fx, y: 2.3, w: fw, h: 0.3, fontSize: 13, bold: true });
  const flow = [["본인", "문제 정의 · 성공 기준 · 지시문 작성"], ["Claude Code", "구현 · 실험 · 선택지와 근거 제시"],
    ["검증 에이전트 (별도 세션)", "재계산 · 반박 · 개입 실험"], ["본인", "체크포인트에서 판단 · 채택/폐기 · 기록"]];
  flow.forEach(([who, what], i) => {
    const y = 2.65 + i * 0.52;
    const dark = i % 3 === 0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: fx, y, w: fw, h: 0.4, fill: { color: dark ? INK : TINT }, line: { color: dark ? INK : TINT }, rectRadius: 0.05 });
    text(s, [{ text: who + "   ", options: { bold: true, color: dark ? WHITE : NAVY } }, { text: what, options: { color: dark ? WHITE : INK } }],
      { x: fx + 0.15, y, w: fw - 0.3, h: 0.4, fontSize: 12.5, valign: "middle" });
    if (i < flow.length - 1) text(s, "↓", { x: fx + fw / 2 - 0.15, y: y + 0.37, w: 0.3, h: 0.16, fontSize: 10, color: GRAY, align: "center" });
  });
  text(s, `체크포인트 6개 · 판단 13건 · 검증 워크플로 10회(에이전트 45개) · 오류 15건 · 작업 시간 7시간${NB}40분`, { x: fx, y: 4.72, w: fw, h: 0.28, fontSize: 10, color: INK2 });

  // one real checkpoint: what the AI proposed, what I decided (LOG 17:04 report, 판단 지점 8)
  table(s, [
    ["체크포인트 3에서 AI가 보고한 개선 방향 후보", "내 결정 (판단 지점 8)"],
    ["① 소형 CNN: 맵을 격자로 맞추고 회전·반전 증강. 약한 패턴은 모양·위치가 핵심인데 손으로 만든 특징은 이를 뭉갬(덩어리 특징만 빼도 0.81 → 0.68). ② 특징 강화 + 부스팅: 직선·국부 덩어리 특징 추가. 가볍지만 개선 폭 제한. ③ 사후 임계값 보정: val에서 패턴별 가중 조정. 빠르지만 드문 패턴은 val 과적합 위험",
      "①+③ 조합. 가중 없는 CE와 weighted CE를 같은 test에서 비교하고, 보정값은 val에서만 정함. 비교 기준은 test 최고 베이스라인(더 엄격한 쪽). 입력은 비등방 64×64 불량 보존 축소. 결과: weighted CE는 0.825로 폐기, 보정 채택으로 0.909"],
  ], { x: fx, y: 5.02, w: fw, colW: [2.85, 2.78], rowH: 0.3, header: true, fontSize: 10.5 });
}

// ---------------------------------------------------------------- 7. how the AI was used (2): verification and catching AI errors
{
  const s = pres.addSlide();
  frame(s, 6, "AI 활용 방식 ②  검증과 오류 적발",
    "구현한 AI와 별개의 검증 에이전트 45개를 10회 돌려 AI가 낸 오류 15건 중 7건을 잡았고, 나머지 8건은 실행 전 검토와 커밋 전 대조 규칙에서 나왔습니다.",
    "근거: LOG.md 오류 기록 E1~E15와 각 워크플로 결과 항목(15:11, 15:57, 16:55, 17:02, 17:39, 18:33, 20:57, 21:18, 23:0x, 00:03)");
  text(s, "AI가 낸 오류를 잡은 사례", { x: ML, y: 2.3, w: 6.1, h: 0.3, fontSize: 13, bold: true });
  table(s, [
    ["오류", "어떻게 드러났나", "조치"],
    ["E10 잘못된 원인 가설", "AI가 세운 가설(라벨이 다른 재검사 쌍의 역누수)을 AI가 짠 진단 스크립트가 반증", "가설 철회, 원인 조사 워크플로로 전환"],
    ["E11 분할 절차 오류", "반박 검증 에이전트가 scikit-learn 소스와 개입 실험으로 확인", "절차 수정, 모든 모델 재학습"],
    ["E13 확률 열 버그", "지표 검증 에이전트가 예측 파일로 보정 결과를 재현하다 발견", "저장 로직 수정 후 재평가, 지표 변화 없음"],
  ], { x: ML, y: 2.62, w: 6.1, colW: [1.5, 2.9, 1.7], rowH: 0.4, header: true, fontSize: 11 });
  text(s, "산출물 반려", { x: ML, y: 4.85, w: 6.1, h: 0.3, fontSize: 13, bold: true });
  table(s, [
    ["산출물", "문제", "조치"],
    ["대시보드 문구", "AI가 쓴 티: 한다체 설명문, 이모지, 내부 실행 이름", "수율 도구·ML 리포트·UX 라이팅 관례 조사 후 재작성"],
    ["포트폴리오 1차", "과밀, 반말 서술 제목, 쪽별 주장 파악 안 됨", "실제 국내 덱 6건 조사 후 8쪽으로 재구성"],
  ], { x: ML, y: 5.17, w: 6.1, colW: [1.3, 2.5, 2.3], rowH: 0.4, header: true, fontSize: 11 });

  const rx = 7.0, rw = 5.63;
  text(s, "독립 검증·조사 워크플로 10회 (에이전트 45개)", { x: rx, y: 2.3, w: rw, h: 0.3, fontSize: 13, bold: true });
  table(s, [
    ["단계", "에이전트", "한 일"],
    ["데이터 확보·문헌 조사", "10", `조사 5 + 반박 검증 5. 오류${NB}E1~E4 발견`],
    ["데이터 이상점 탐색", "10", `탐색 4 + 검증. 부분 정정 7건(E7)`],
    ["베이스라인·분할 재계산", "4", "지표 재계산, 독립 재구현, 코드 감사"],
    ["Loc recall 원인 조사", "3", "원인 추적·구성 점검·반박 → E11"],
    ["CNN 검증 2회", "8", "지표 재계산, 짝비교, 지름길, 이중맹검 → E13"],
    ["문체·포트폴리오 조사", "10", "대시보드 문구 4, 포트폴리오 3 + 3"],
  ], { x: rx, y: 2.62, w: rw, colW: [1.9, 0.85, 2.88], rowH: 0.38, header: true, fontSize: 11 });
  labeled(s, [
    ["규칙", "구현한 에이전트와 검증하는 에이전트를 분리. 검증 쪽에는 원본 코드 대신 데이터와 결과 파일만 주고 다시 계산하게 함"],
    ["나머지 8건", "실행 전 자체 검토, 그림·표를 직접 열어 확인, 커밋 전 grep 대조, 내보내기 후 pdffonts 점검에서 발견(E5·E6·E8·E9·E12·E14·E15)"],
  ], { x: rx, y: 5.5, w: rw, labelW: 1.0, fontSize: 11.5, color: INK2, rowH: 0.3 });
}

// ---------------------------------------------------------------- 8. conclusion, limits, reproduction
{
  const s = pres.addSlide();
  frame(s, 7, "결론·한계·재현 정보",
    "이 결과는 같은 제품의 새 lot에 대한 1차 분류 보조 수준입니다. 수율 개선이나 공정 원인 규명 효과는 주장하지 않습니다.");
  const cols = [
    ["결론", [
      `누수를 막은 평가에서 CNN${NB}0.909, 베이스라인${NB}0.843`,
      `분할 절차 하나로 Loc recall이 12%p 달라짐. 모델을 고르기 전에 평가 방식부터 확인해야 함`,
      "검증 5종 통과, 새 폴더 재현 일치",
    ]],
    ["한계·다음 단계", [
      `한 번 나눈 분할의 결과. seed${NB}10개로 나눠 평균하면 약${NB}0.01 낮음 → 그룹 5-fold로 전체 평가`,
      `Near-full test${NB}18장, 신뢰구간 0.70–1.00 → 표본 확보 전까지 수치 유보`,
      `같은 맵 다른 라벨${NB}14쌍, 6~10다이 짧은 Scratch 약점 → 라벨 기준 재정의, 고해상도 입력`,
    ]],
    ["배운 점", [
      "수치는 스크립트 실행 결과에서만 옮긴다. 추정치는 쓰지 않는다",
      "점수가 갑자기 오르면 원인을 찾기 전까지 채택하지 않는다",
      "새 데이터를 받으면 모델을 만들기 전에 분할 방식과 라벨 품질부터 검사한다",
    ]],
  ];
  cols.forEach(([title, items], i) => {
    const x = ML + i * 4.05;
    text(s, title, { x, y: 2.35, w: 3.75, h: 0.35, fontSize: 15, bold: true });
    bullets(s, items, { x, y: 2.75, w: 3.75, h: 2.5, fontSize: 13 });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: ML, y: 5.4, w: CW, h: 1.5, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.06 });
  text(s, "재현 정보", { x: ML + 0.2, y: 5.5, w: 3, h: 0.3, fontSize: 13, bold: true });
  labeled(s, [
    ["환경", "Windows 11, Python 3.12.6, torch 2.7.1+cu118, scikit-learn 1.9.1, Quadro P2000. 시드 0 고정"],
    ["실행", "python scripts/run_all.py  (데이터 다운로드 → 분할 → 베이스라인 → CNN → 평가, 약 4~5시간). 결과 outputs/*.json"],
    ["저장소", "github.com/sl2ver/wm811k-wafer-defect-classification (MIT). PLAN.md 계획·변경 이력 / LOG.md 지시 원문·판단 13건·오류 15건 / RESULT.md 수치·버린 것 9·한계 9"],
  ], { x: ML + 0.2, y: 5.85, w: CW - 0.4, labelW: 0.8, fontSize: 11.5, fill: TINT, rowH: 0.28 });
}

pres.writeFile({ fileName: "portfolio.pptx" }).then((f) => console.log("written", f));
