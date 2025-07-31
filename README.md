#  classification_banana

바나나 품질 분류를 위한 이미지 분류 프로젝트입니다.  
본 프로젝트는 공장에서 수집된 바나나 이미지 데이터를 바탕으로 "정상(GOOD)"과 "불량(BAD)" 바나나를 분류하는 딥러닝 모델을 PyTorch 기반으로 구현하고 학습합니다.

---

##  프로젝트 개요

- **목적:** 공정 중 바나나의 품질 상태를 자동으로 분류하여 불량품을 조기에 식별합니다.
- **기술 스택:** PyTorch, torchvision, PIL, NumPy
- **모델 구조:** CNN 기반 커스텀 모델
- **분류 클래스:**  
  - `0`: GOOD (정상 바나나)  
  - `1`: BAD (썩음, 손상, 오염 등 품질 불량 바나나)

---

##  주요 기능

- 커스텀 CNN 기반 이미지 분류기 구현
- 정사각형 Letterbox 리사이즈 적용으로 다양한 해상도 대응
- 학습/검증 정확도 출력 및 로그 저장
- 학습된 모델 저장 및 추론 결과 출력 기능 제공
- 다양한 하이퍼파라미터 설정 가능 (Epoch, Batch size 등)

---

##  디렉토리 구조

```bash
classification_banana/
├── train/                # 학습용 이미지 및 라벨
│   ├── images/
│   └── labels/
├── valid/                # 검증용 이미지 및 라벨
│   ├── images/
│   └── labels/
├── test/                 # 테스트 이미지
│   ├── images/
├── model/                # 학습된 모델 파일 저장 위치
├── logs/                 # 학습 로그 저장 위치
├── inference.py          # 추론 스크립트
├── train.py              # 학습 스크립트
├── model.py              # CNN 모델 정의
├── dataset.py            # 커스텀 Dataset 및 전처리
├── utils.py              # 보조 함수 (Letterbox 등)
└── requirements.txt      # 의존성 목록
