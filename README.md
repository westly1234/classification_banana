
# YOLO 바나나 분석 웹 애플리케이션

이 프로젝트는 FastAPI를 백엔드로, React+TypeScript를 프론트엔드로 사용하는 AI 기반 바나나 분석 웹 애플리케이션입니다. 사용자는 바나나 이미지를 업로드하여 숙성도를 분석하고, 대시보드를 통해 분석 통계를 확인할 수 있습니다.

## 📁 프로젝트 구조

```
yolo_web/
├── backend/            # FastAPI 백엔드
│   └── main.py
├── frontend/           # React + TypeScript 프론트엔드
│   ├── public/
│   │   ├── index.html
│   │   └── metadata.json
│   ├── src/
│   │   ├── components/
│   │   │   ├── Analyze.tsx
│   │   │   ├── Auth.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   └── Sidebar.tsx
│   │   ├── services/
│   │   │   └── yoloService.ts
│   │   ├── App.tsx
│   │   ├── index.tsx
│   │   └── types.ts
│   ├── package.json
│   └── tsconfig.json
├── README.md
└── requirements.txt
```

## 🚀 시작하기

이 프로젝트를 로컬 환경에서 실행하려면 백엔드 서버와 프론트엔드 앱을 각각 실행해야 합니다.

### 1. 백엔드 (FastAPI) 설정 및 실행

백엔드는 이미지 분석 요청을 처리하고 YOLO 모델(현재는 시뮬레이션)을 실행하는 역할을 합니다.

**a. 필요한 라이브러리 설치:**

터미널을 열고 `requirements.txt` 파일에 명시된 파이썬 라이브러리들을 설치합니다.

```bash
pip install -r requirements.txt
```

**b. 백엔드 서버 실행:**

`backend` 폴더로 이동하여 아래 명령어로 Uvicorn 서버를 실행합니다.

```bash
cd backend
uvicorn main:app --reload
```

서버가 성공적으로 실행되면, 터미널에 `http://127.0.0.1:8000` 에서 애플리케이션이 실행 중이라는 메시지가 나타납니다.

### 2. 프론트엔드 (React) 실행

이 개발 환경에서는 프론트엔드 파일들이 자동으로 제공됩니다. 별도의 `npm install` 이나 `npm start` 과정 없이, 웹 미리보기에서 바로 상호작용할 수 있습니다.

만약 로컬 컴퓨터에서 직접 실행하려면, `frontend` 폴더를 정적 파일 서버로 제공해야 합니다.

```bash
# 예시: npm을 이용한 serve 라이브러리 사용
npm install -g serve
cd frontend
serve -s .
```

## ✨ 주요 기능

*   **사용자 인증**: 회원가입 및 로그인 기능.
*   **바나나 분석**: 이미지 업로드를 통해 바나나의 숙성도를 분석하고, 이미지 위에 탐지된 영역(Bounding Box)을 시각적으로 표시합니다.
*   **대시보드**: 분석 횟수, 상태 통계 등을 차트와 그래프로 시각화하여 보여줍니다.
*   **반응형 디자인**: 데스크톱과 모바일 환경 모두에서 사용하기 편하도록 디자인되었습니다.
