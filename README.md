# WM-811K 웨이퍼 맵 결함 패턴 분류

공개 웨이퍼 맵 데이터셋 WM-811K(LSWMD)의 결함 패턴 9종(Center, Donut, Edge-Loc, Edge-Ring, Loc, Near-full, Random, Scratch, none)을 분류하는 파이프라인과 결과 대시보드. 24시간 개인 해커톤 연습 프로젝트다. 작업 과정은 [PLAN.md](PLAN.md), [LOG.md](LOG.md), [RESULT.md](RESULT.md), [GLOSSARY.md](GLOSSARY.md)에 기록한다.

> 진행 상황: 2단계(데이터 탐색)까지 완료. 파이프라인 실행법과 대시보드 실행법은 해당 단계에서 추가한다.

## 1. 환경 구성 (Windows, Python 3.12)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

- `requirements.txt`는 버전을 고정했다. torch는 CUDA 11.8 빌드(`2.7.1+cu118`)라서 pip가 PyTorch index(`--extra-index-url`)에서 받는다. 파일 크기가 약 2.7 GB다.
- 개발 환경: Quadro P2000(Pascal, sm_61), NVIDIA 드라이버 472.84. 이 GPU를 지원하는 최신 torch(2.14+cu126)는 드라이버 560 이상이 필요해서 cu118 빌드를 골랐다.
- GPU 점검: `.venv\Scripts\python scripts\check_gpu.py`

## 2. 데이터 받기

```powershell
.venv\Scripts\python scripts\download_data.py
```

- 출처: Kaggle [`qingyi/wm811k-wafer-map`](https://www.kaggle.com/datasets/qingyi/wm811k-wafer-map). 공식 `kagglehub`로 로그인 없이 받는다(공개 데이터셋).
- 받은 zip(약 149 MiB)을 `data/raw/LSWMD.pkl`(2,095,505,977 B)로 푼다. 이어서 크기, SHA-256, DataFrame shape(811,457 × 6)를 검사하고, 이미 받은 파일이 있으면 다운로드를 건너뛴다.
- **데이터는 이 저장소에 포함하지 않는다.**

## 3. 데이터 탐색

```powershell
.venv\Scripts\python scripts\explore_data.py
```

- 클래스 분포, 맵 크기, lot 구조, 완전 중복·근사 중복(10픽셀 이내), 분할 방식별 누수율을 계산해 `outputs/eda/summary.json`에 저장하고 그림 5개를 만든다(이 PC에서 1분 39초).

## 4. 데이터 인용

WM-811K를 쓰려면 원 배포처(MIR Lab)의 조건에 따라 아래 두 가지를 인용한다.

- M.-J. Wu, J.-S. R. Jang, and J.-L. Chen, "Wafer Map Failure Pattern Recognition and Similarity Ranking for Large-Scale Data Sets," *IEEE Trans. Semiconductor Manufacturing*, vol. 28, no. 1, pp. 1–12, Feb. 2015, doi: 10.1109/TSM.2014.2364237.
- MIR Lab, WM-811K dataset, http://mirlab.org/dataSet/public/
