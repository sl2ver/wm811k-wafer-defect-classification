"""Bundle the portfolio PDF with its evidence files into one zip for the application form (limit 50 MB).

Layout inside the zip mirrors the repository, so the "근거: outputs/..." paths printed on each portfolio
page resolve inside the zip as well. Data (2 GB), model weights (.pt) and probability dumps (.npz) are left out.

Usage (global Python 3.14 has the `markdown` package; pandas comes from the project venv via subprocess):
    C:/Python314/python.exe portfolio/make_submission_zip.py
"""
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "portfolio" / "submission" / "wafer_map_portfolio_LeeJinseong.zip"
TOP = "wafer_map_portfolio_LeeJinseong/"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"

RECORDS = ["PLAN.md", "LOG.md", "RESULT.md", "GLOSSARY.md", "README.md", "docs/wafer_project_prompt.md"]
EXTRA = ["LICENSE", "requirements.txt"]
OUTPUT_EXTS = {".json", ".png", ".parquet"}  # .pt / .npz excluded (size)

README_FIRST = """# 웨이퍼 맵 불량 패턴 분류 — 제출 파일 안내

이진성 · SK하이닉스 AI 해커톤 2026 지원 포트폴리오

## 읽는 순서
1. `portfolio.pdf` — 6쪽 요약. 먼저 보세요.
2. `LOG.md` — 지시 원문과 시각별 진행 기록, 판단 지점 19건(프로젝트 진행 중 13건 + 포트폴리오 제작 단계 6건), 오류 15건(E1–E14 프로젝트, E15 포트폴리오 제작 단계) (읽기 편한 판: `html/LOG.html`)
3. `RESULT.md` — 최종 수치, 버린 것 9, 한계 9 (`html/RESULT.html`)
4. `PLAN.md`, `GLOSSARY.md`, `docs/wafer_project_prompt.md` — 계획과 변경 이력, 용어, 첫 지시문 원문
5. `scripts/` — 스크립트 12개 (`run_all.py`로 데이터 다운로드부터 평가까지 재실행), `README.md` — 환경 구성과 실행 방법
6. `outputs/` — 결과 JSON, 그림, 예측 파일. `outputs/cnn/test_predictions_final.csv`는 최종 모델의 test 25,444장 판정(엑셀로 열림)

포트폴리오 각 쪽 하단의 "근거(첨부 zip·GitHub 같은 경로): …"에 적힌 경로는 이 zip 안의 파일입니다. 같은 내용을 GitHub에 공개했습니다:
https://github.com/sl2ver/wm811k-wafer-defect-classification

용량 때문에 뺀 것: 데이터 WM-811K(2 GB, `README.md`의 명령으로 내려받음), 학습된 모델 가중치와 확률 파일. 재실행하면 다시 생깁니다(약 4~5시간).
"""

HTML_TMPL = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{title}</title>
<style>
body{{font-family:Pretendard,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;max-width:1000px;margin:40px auto;padding:0 20px;line-height:1.6;color:#0b0b0b}}
h1,h2,h3{{line-height:1.3}} h2{{margin-top:2em;border-bottom:1px solid #dad9d4;padding-bottom:.2em}}
table{{border-collapse:collapse;margin:1em 0;font-size:.92em}} th,td{{border:1px solid #dad9d4;padding:.35em .6em;vertical-align:top}} th{{background:#f3f3f1;text-align:left}}
code{{background:#f3f3f1;padding:.1em .3em;border-radius:3px;font-size:.92em}} pre{{background:#f3f3f1;padding:1em;overflow-x:auto}} pre code{{background:none;padding:0}}
blockquote{{border-left:3px solid #dad9d4;margin:1em 0;padding:.2em 1em;color:#52514e}}
</style></head><body>{body}</body></html>"""


def render_html(md_text, title):
    import markdown  # python-markdown (global Python)
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists", "toc"])
    return HTML_TMPL.format(title=title, body=body)


def final_predictions_csv():
    """Readable CSV of the final model's test predictions, produced by the venv (pandas + pyarrow)."""
    code = r"""
import sys, pandas as pd
sys.path.insert(0, 'scripts')
from explore_data import CLASSES
d = pd.read_parquet('outputs/cnn/test_predictions.parquet')
d = d[(d.run == 'main_ce') & (d.variant == 'calibrated')].copy()
p = d[[f'p_{c}' for c in CLASSES]].to_numpy()
out = pd.DataFrame({'id': d['id'].values, 'label': [CLASSES[i] for i in d['label']], 'pred': [CLASSES[i] for i in d['pred']],
                    'correct': (d['label'] == d['pred']).values, 'confidence': p.max(axis=1).round(4)})
sys.stdout.buffer.write(out.to_csv(index=False).encode('utf-8-sig'))
"""
    return subprocess.run([str(VENV_PY), "-c", code], cwd=ROOT, capture_output=True, check=True).stdout


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        def add(arc, data=None, src=None):
            nonlocal n
            if src is not None:
                z.write(src, TOP + arc)
            else:
                z.writestr(TOP + arc, data)
            n += 1

        add("portfolio.pdf", src=ROOT / "portfolio" / "portfolio.pdf")
        add("README_FIRST.md", data=README_FIRST.encode("utf-8"))
        add("html/README_FIRST.html", data=render_html(README_FIRST, "제출 파일 안내").encode("utf-8"))
        for rel in RECORDS + EXTRA:
            add(rel, src=ROOT / rel)
        for rel in RECORDS:
            text = (ROOT / rel).read_text(encoding="utf-8")
            add(f"html/{Path(rel).stem}.html", data=render_html(text, Path(rel).name).encode("utf-8"))
        for p in sorted((ROOT / "scripts").glob("*.py")):
            add(f"scripts/{p.name}", src=p)
        for p in sorted((ROOT / "outputs").rglob("*")):
            if p.is_file() and p.suffix in OUTPUT_EXTS:
                add(p.relative_to(ROOT).as_posix(), src=p)
        add("outputs/cnn/test_predictions_final.csv", data=final_predictions_csv())
    size = OUT.stat().st_size
    print(f"{OUT.name}: {n} files, {size / 1048576:.1f} MB (limit 50 MB) -> {OUT}")
    if size > 50 * 1048576:
        sys.exit("zip exceeds 50 MB")


if __name__ == "__main__":
    main()
