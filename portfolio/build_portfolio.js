// Portfolio deck: 9 pages, 16:9, Pretendard. Build chain (from portfolio/):
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
const TOTAL = 9;
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
  text(slide, runs, Object.assign({ fontSize: pt, lineSpacing: Math.round(pt * 1.45), paraSpaceAfter: 7 }, o));
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
// "Claude Code / 본인" strip on the content pages.
function roles(slide, ai, me, o) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: o.x, y: o.y, w: o.w, h: o.h, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.05 });
  labeled(slide, [["Claude Code", ai], ["본인", me]], { x: o.x + 0.12, y: o.y + 0.07, w: o.w - 0.24, labelW: 1.05, fontSize: o.fontSize || 11.5, fill: TINT, color: INK2, rowH: 0.27 });
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
  text(s, "WM-811K 공개 데이터", { x: ML, y: 3.5, w: CW, h: 0.4, fontSize: 14, color: INK2 });
  s.addImage({ path: "fig/p1_wafer_strip.svg", x: ML, y: 4.3, w: 11.9, h: 1.6 });
  text(s, "이진성", { x: ML, y: 6.45, w: 4, h: 0.4, fontSize: 16, bold: true });
}

// ---------------------------------------------------------------- 2. overview (doubles as table of contents)
{
  const s = pres.addSlide();
  frame(s, 1, "프로젝트 개요",
    `학습에 쓰지 않은 lot 25,444장에서 macro-F1${NB}0.909. 평가 방식을 먼저 고치고 다섯 가지로 검증`);
  table(s, [
    ["데이터", `WM-811K 웨이퍼 맵 811,457장 중 라벨 있는 172,950장, 불량 패턴${NB}9종`],
    ["문제", "같은 웨이퍼의 복사본이 학습과 평가에 섞이는 누수를 막고, 새 lot에서 성능 재기"],
    ["결과", `macro-F1 0.843(베이스라인) → 0.909(CNN), 모든 패턴 recall${NB}0.77 이상`],
    ["AI 활용", `구현·실험 Claude Code / 판단·검증 본인 / 별도 검증 에이전트 45개. 체크포인트 6개에서 판단${NB}13건, 오류${NB}15건 기록`],
  ], { x: ML, y: 2.4, w: 7.0, colW: [1.2, 5.8], rowH: 0.56, fontSize: 13 });
  labeled(s, [
    ["용어", `lot: 함께 처리한 웨이퍼 묶음(최대${NB}25장) · macro-F1: 패턴 9종 F1의 평균 · recall: 실제 그 패턴 중 맞힌 비율`],
  ], { x: ML, y: 5.0, w: 7.0, labelW: 0.7, fontSize: 11.5, color: INK2, rowH: 0.3 });

  text(s, "진행 순서", { x: 8.1, y: 2.4, w: 4.5, h: 0.3, fontSize: 12, color: GRAY });
  const steps = [["문제 정의와 평가 설계", "3쪽"], ["베이스라인과 소형 CNN", "4쪽"], ["검증과 오류 수정", "5쪽"],
    ["AI 활용 ① 시간과 자원", "6쪽"], ["AI 활용 ② 지시와 판단", "7쪽"], ["AI 활용 ③ 검증과 오류 적발", "8쪽"],
    ["결론·한계·재현 정보", "9쪽"]];
  steps.forEach(([name, page], i) => {
    const y = 2.75 + i * 0.56;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.1, y, w: 4.53, h: 0.47, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.06 });
    text(s, [{ text: `${i + 1}  `, options: { bold: true, color: NAVY } }, { text: name }],
      { x: 8.25, y, w: 3.6, h: 0.47, fontSize: 13.5, valign: "middle" });
    text(s, page, { x: 11.75, y, w: 0.8, h: 0.47, fontSize: 12, color: INK2, align: "right", valign: "middle" });
  });
}

// ---------------------------------------------------------------- 3. problem: data and evaluation design
{
  const s = pres.addSlide();
  frame(s, 2, "문제 정의: 데이터와 평가 방식",
    "에이전트 10개가 찾은 이상점 17개 중 복사본 누수를 핵심 문제로 선정. lot과 복사본을 한 묶음으로 나누는 규칙 수립",
    "근거: outputs/eda/summary.json, outputs/splits/split_summary.json");
  const lw = 5.4;
  text(s, "누수 3겹", { x: ML, y: 2.3, w: 3, h: 0.3, fontSize: 14, bold: true });
  table(s, [
    ["원본 분할", `test${NB}3,158장이 train의 복사본`],
    ["lot 단위 분할", `재검사 복사본이 양쪽에 남음(Center${NB}40.7%)`],
    ["반전·회전", "뒤집거나 돌린 복사본까지 8가지 변환으로 비교"],
  ], { x: ML, y: 2.62, w: lw, colW: [1.4, 4.0], rowH: 0.46, fontSize: 12.5 });
  labeled(s, [
    ["채택한 분할", `lot + 10픽셀 이내 복사본을 한 묶음으로 70:15:15`],
    ["성공 기준", `macro-F1${NB}0.80 이상, 모든 패턴 recall${NB}0.50 이상, 베이스라인 초과`],
  ], { x: ML, y: 4.25, w: lw, labelW: 1.3, fontSize: 13.5, rowH: 0.34 });
  roles(s, "탐색·분할 스크립트 구현, 이상점 탐색 에이전트 10개 병렬 실행",
    `정제 규칙·분할 방식·성공 기준 결정(판단 지점${NB}6·7)`, { x: ML, y: 5.65, w: lw, h: 0.85 });
  s.addImage({ path: "fig/p3_leakage.svg", x: 6.4, y: 2.3, w: 6.25, h: 3.2 });
  s.addImage({ path: "fig/p3_pairs.svg", x: 6.4, y: 5.25, w: 6.25, h: 1.7 });
}

// ---------------------------------------------------------------- 4. method and results
{
  const s = pres.addSlide();
  frame(s, 3, "방법과 결과",
    `같은 test 25,444장에서 소형 CNN macro-F1 0.843 → 0.909. Loc·Scratch recall이 가장 크게 상승`,
    "근거: outputs/baseline/results.json, outputs/cnn/results.json. 신뢰구간은 연결 성분 부트스트랩 1,000회");
  const lw = 5.6;
  table(s, [
    ["모델", "macro-F1 (95% CI)", "최저 recall"],
    ["베이스라인 (특징 23개 + RF)", "0.843 (0.820–0.858)", "0.497 (Loc)"],
    ["소형 CNN", "0.901 (0.863–0.918)", "0.763 (Loc)"],
    ["소형 CNN + val 보정 (최종)", "0.909 (0.885–0.922)", "0.775 (Loc)"],
  ], { x: ML, y: 2.35, w: lw, colW: [2.3, 2.05, 1.25], rowH: 0.4, header: true, boldRows: [3], fontSize: 12 });
  labeled(s, [
    ["방법", `64×64 축소(블록 최대값으로 Scratch 보존), 반전·회전 증강, 합성곱 4블록 58만${NB}파라미터. 보정값은 val에서만 정함`],
    ["효과 없던 시도", `class-weighted CE: 0.825, none 오탐 증가 → 미채택`],
  ], { x: ML, y: 4.25, w: lw, labelW: 1.4, fontSize: 13.5, rowH: 0.34 });
  roles(s, "특징 23개·RF·CNN 구현, 학습 5회",
    `개선 방향과 입력 크기 결정(판단 지점${NB}8), weighted CE 폐기(판단 지점${NB}10)`, { x: ML, y: 5.9, w: lw, h: 0.85 });
  s.addImage({ path: "fig/p4_recall.svg", x: 6.6, y: 2.3, w: 6.05, h: 4.45 });
}

// ---------------------------------------------------------------- 5. verification and the error that was fixed
{
  const s = pres.addSlide();
  frame(s, 4, "검증과 오류 수정",
    "예상보다 높은 점수 → 검증 에이전트 4개와 개입 실험 → 분할 절차 오류 1건 발견·수정",
    "근거: outputs/splits/split_seed_variance.json, outputs/cnn/outline_intervention.json, LOG.md 오류 E11");
  const lw = 6.0;
  table(s, [
    ["검증", "방법", "결과"],
    ["우연 수준", "라벨을 섞어 학습", `macro-F1${NB}0.102`],
    ["누수 제거 효과", "무작위 분할 vs lot 분할", `0.895${NB}vs${NB}0.909`],
    ["지름길 학습", "제품 외곽선을 바꿔 끼움", "예측 99.5% 유지"],
    ["오분류 검토", "96장, 라벨 가린 독립 판정", "라벨 의심 27%"],
    ["재현", "새 폴더에서 처음부터 재실행", "10개 항목 일치"],
  ], { x: ML, y: 2.35, w: lw, colW: [1.45, 2.65, 1.9], rowH: 0.46, header: true, fontSize: 12.5 });
  roles(s, "검증 에이전트 4개 병렬, 개입 실험 구현",
    `오류 판정, 전부 재학습 결정(판단 지점${NB}9)`, { x: ML, y: 5.5, w: lw, h: 0.85 });
  s.addImage({ path: "fig/p5_e11.svg", x: 7.1, y: 2.3, w: 5.4, h: 2.9 });
  text(s, "분할 절차 오류 (LOG E11)", { x: 7.1, y: 5.3, w: 5.5, h: 0.3, fontSize: 13, bold: true });
  labeled(s, [
    ["원인", `StratifiedGroupKFold가 큰 그룹을 seed와 무관하게 같은 fold에 고정 → 쉬운 Loc${NB}132장이 항상 test`],
    ["발견", `베이스라인이 이유 없이 오름 → seed${NB}10개로 재분할 → lot 묶음 하나를 빼 보는 실험`],
    ["수정", "fold 배정 무작위 치환, 전 모델 재학습(0.893 → 0.909), 분할 후 겹침 검사 추가"],
  ], { x: 7.1, y: 5.62, w: 5.5, labelW: 0.55, fontSize: 11, rowH: 0.28 });
}

// ---------------------------------------------------------------- 6. how the AI was used (1): time and resources
{
  const s = pres.addSlide();
  frame(s, 5, "AI 활용 ①  시간과 자원",
    `7시간${NB}40분에 계획부터 재현 확인까지. 학습이 도는 동안 검증·조사 에이전트 35개를 병렬 운용`,
    "근거: LOG.md 시각 기록(14:48–22:28), git log, scripts/*.py");
  s.addImage({ path: "fig/p6_timeline.svg", x: ML, y: 2.3, w: 11.9, h: 2.7 });
  table(s, [
    ["총 작업 시간", `7시간${NB}40분 (14:48–22:28), 1인`],
    ["GPU 학습", `5회, 3시간${NB}36분 (Quadro P2000)`],
    ["코드", `스크립트 12개 1,766줄, 커밋 16회`],
    ["에이전트", `워크플로 8회 35개, 병렬 실행 약 3시간`],
    ["기록", `LOG 1,155줄, PLAN·RESULT·GLOSSARY 412줄`],
  ], { x: ML, y: 5.2, w: 5.9, colW: [1.45, 4.45], rowH: 0.33, fontSize: 12 });
  labeled(s, [
    ["병렬", "CNN 학습이 도는 동안 검증 에이전트 4개가 지표 재계산·짝비교·지름길·이중맹검 수행(18:33–18:53)"],
    ["탐색", `에이전트 10개가 29분에 이상점 17개 → 스크립트로 재검산 1분${NB}39초`],
    ["재현", `새 폴더 재실행 1시간${NB}8분은 스크립트가 자동 비교(10개 항목)`],
  ], { x: 7.0, y: 5.2, w: 5.63, labelW: 0.7, fontSize: 12, rowH: 0.3 });
}

// ---------------------------------------------------------------- 7. how the AI was used (2): instructions and decisions
{
  const s = pres.addSlide();
  frame(s, 6, "AI 활용 ②  지시와 판단",
    "첫 지시문에 멈출 지점과 기록 규칙을 명시. 체크포인트 6개에서 판단 13건",
    "근거: docs/wafer_project_prompt.md(첫 지시문), LOG.md 17:04 보고와 판단 지점 8");
  const lw = 5.8;
  text(s, "첫 지시문의 규칙 (원문)", { x: ML, y: 2.3, w: lw, h: 0.3, fontSize: 13, bold: true });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: ML, y: 2.65, w: lw, h: 1.9, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.05 });
  paras(s, [
    "“판단이 필요한 지점에서는 멈추고 나에게 묻는다. 선택지 2~3개와 각각의 장단점을 제시하고, 추천이 있으면 이유와 함께 밝힌다.”",
    "“숫자는 실행 결과에서만 가져온다. 추정치를 결과처럼 쓰지 않는다.”",
    "“오류 기록: 네 코드나 판단이 틀렸던 경우, 누가(나/너) 어떻게 발견했고 무엇을 바꿨는지.”",
  ], { x: ML + 0.15, y: 2.78, w: lw - 0.3, h: 1.7, fontSize: 12.5, color: INK, lineSpacing: 18, paraSpaceAfter: 7 });
  text(s, "작업 흐름", { x: ML, y: 4.75, w: lw, h: 0.3, fontSize: 13, bold: true });
  const flow = [["본인", "문제 정의 · 성공 기준 · 지시문"], ["Claude Code", "구현 · 실험 · 선택지 제시"],
    ["검증 에이전트", "재계산 · 반박 · 개입 실험"], ["본인", "체크포인트에서 판단 · 기록"]];
  flow.forEach(([who, what], i) => {
    const y = 5.1 + i * 0.48;
    const dark = i % 3 === 0;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: ML, y, w: lw, h: 0.38, fill: { color: dark ? INK : TINT }, line: { color: dark ? INK : TINT }, rectRadius: 0.05 });
    text(s, [{ text: who + "   ", options: { bold: true, color: dark ? WHITE : NAVY } }, { text: what, options: { color: dark ? WHITE : INK } }],
      { x: ML + 0.15, y, w: lw - 0.3, h: 0.38, fontSize: 12.5, valign: "middle" });
    if (i < flow.length - 1) text(s, "↓", { x: ML + lw / 2 - 0.15, y: y + 0.35, w: 0.3, h: 0.15, fontSize: 10, color: GRAY, align: "center" });
  });

  // one real checkpoint: what the AI proposed, what I decided (LOG 17:04 report, 판단 지점 8)
  const rx = 6.8, rw = 5.83;
  text(s, "체크포인트 3: AI의 제안과 내 결정", { x: rx, y: 2.3, w: rw, h: 0.3, fontSize: 13, bold: true });
  table(s, [
    ["AI가 보고한 개선 방향 후보", "내 결정 (판단 지점 8)"],
    ["① 소형 CNN: 맵을 격자로 맞추고 회전·반전 증강. 손으로 만든 특징은 모양·위치 정보를 뭉갬. ② 특징 강화 + 부스팅: 가볍지만 개선 폭 제한. ③ 사후 임계값 보정: 빠르지만 드문 패턴은 val 과적합 위험",
      "①+③ 조합. weighted CE는 같은 test에서 비교해 결정하고 보정값은 val에서만. 비교 기준은 test 최고 베이스라인. 결과: weighted CE 0.825로 폐기, 보정 채택 0.909"],
  ], { x: rx, y: 2.62, w: rw, colW: [2.95, 2.88], rowH: 0.3, header: true, fontSize: 13 });
}

// ---------------------------------------------------------------- 8. how the AI was used (3): verification and catching AI errors
{
  const s = pres.addSlide();
  frame(s, 7, "AI 활용 ③  검증과 오류 적발",
    "구현 AI와 분리한 검증 에이전트가 AI 오류 15건 중 7건 적발. 8건은 자체 점검 규칙으로 발견",
    "근거: LOG.md 오류 기록 E1~E15, 워크플로 결과 항목 10건");
  const lw = 6.0;
  text(s, "AI가 낸 오류를 잡은 사례", { x: ML, y: 2.3, w: lw, h: 0.3, fontSize: 13, bold: true });
  table(s, [
    ["오류", "어떻게 드러났나", "조치"],
    ["E10 잘못된 원인 가설", "AI가 짠 진단 스크립트가 자기 가설을 반증", "가설 철회"],
    ["E11 분할 절차 오류", "반박 검증 에이전트가 sklearn 소스와 개입 실험으로 확인", "절차 수정, 전부 재학습"],
    ["E13 확률 열 버그", "지표 검증 에이전트가 보정 결과를 재현하다 발견", "저장 로직 수정"],
  ], { x: ML, y: 2.62, w: lw, colW: [1.7, 2.8, 1.5], rowH: 0.46, header: true, fontSize: 12 });
  labeled(s, [
    ["산출물 반려", "2회(대시보드 문구, 포트폴리오 1차). 참고 사례를 조사하게 한 뒤 다시 씀"],
    ["규칙", "검증 에이전트에는 원본 코드 대신 데이터와 결과 파일만 주고 다시 계산하게 함"],
  ], { x: ML, y: 5.0, w: lw, labelW: 1.2, fontSize: 12.5, color: INK2, rowH: 0.3 });

  const rx = 7.0, rw = 5.63;
  text(s, "검증·조사 워크플로 10회 (에이전트 45개)", { x: rx, y: 2.3, w: rw, h: 0.3, fontSize: 13, bold: true });
  table(s, [
    ["단계", "에이전트", "결과"],
    ["데이터 확보·문헌 조사", "10", "조사 5 + 반박 5 → E1~E4"],
    ["데이터 이상점 탐색", "10", "탐색 4 + 검증 → 정정 7건"],
    ["베이스라인·분할 재계산", "4", "재계산, 재구현, 코드 감사"],
    ["Loc recall 원인 조사", "3", "원인 추적·반박 → E11"],
    ["CNN 검증 2회", "8", "지표·짝비교·지름길·이중맹검 → E13"],
    ["문체·포트폴리오 조사", "10", "대시보드 4, 포트폴리오 6"],
  ], { x: rx, y: 2.62, w: rw, colW: [2.0, 0.9, 2.73], rowH: 0.44, header: true, fontSize: 12 });
}

// ---------------------------------------------------------------- 9. conclusion, limits, reproduction
{
  const s = pres.addSlide();
  frame(s, 8, "결론·한계·재현 정보",
    "같은 제품의 새 lot에 대한 1차 분류 보조 수준. 수율 개선 효과는 주장하지 않음");
  const cols = [
    ["결론", [
      `누수를 막은 평가에서 CNN${NB}0.909, 베이스라인${NB}0.843`,
      "분할 절차 하나로 Loc recall 12%p 차이. 모델보다 평가 방식부터 확인",
      "검증 5종 통과, 새 폴더 재현 일치",
    ]],
    ["한계·다음 단계", [
      `한 번 나눈 분할. seed${NB}10개 평균은 약${NB}0.01 낮음 → 그룹 5-fold`,
      `Near-full test${NB}18장, 신뢰구간 0.70–1.00`,
      "짧은 Scratch 약점, 라벨 노이즈 14쌍 → 라벨 기준 재정의",
    ]],
  ];
  cols.forEach(([title, items], i) => {
    const x = ML + i * 6.1;
    text(s, title, { x, y: 2.35, w: 5.6, h: 0.35, fontSize: 15, bold: true });
    bullets(s, items, { x, y: 2.75, w: 5.6, h: 2.4, fontSize: 13.5 });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: ML, y: 5.4, w: CW, h: 1.45, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.06 });
  text(s, "재현 정보", { x: ML + 0.2, y: 5.5, w: 3, h: 0.3, fontSize: 13, bold: true });
  labeled(s, [
    ["환경", "Python 3.12.6, torch 2.7.1+cu118, scikit-learn 1.9.1, Quadro P2000, 시드 0"],
    ["실행", "python scripts/run_all.py (약 4~5시간) → outputs/*.json"],
    ["저장소", "github.com/sl2ver/wm811k-wafer-defect-classification — PLAN.md / LOG.md(판단 13건·오류 15건) / RESULT.md"],
  ], { x: ML + 0.2, y: 5.85, w: CW - 0.4, labelW: 0.8, fontSize: 12, fill: TINT, rowH: 0.28 });
}

pres.writeFile({ fileName: "portfolio.pptx" }).then((f) => console.log("written", f));
