# Feedscan AI Daily Pipeline

매일 자동으로 Feedscan AI의 인기 콘텐츠를 분석하여 영상을 제작하고, YouTube/Threads/X에 배포하는 파이프라인입니다.

## 작동 흐름
1. Feedscan AI에서 오늘자 탑10 데이터 수집
2. GPT-4o가 가장 반응 좋을 1개 선정 + 나레이션/글감 생성
3. Google Cloud TTS (Neural2-C)로 음성 생성
4. Python(Pillow)으로 배경 위에 텍스트 합성
5. ASS 자막 자동 생성
6. FFmpeg로 MP4 렌더링
7. YouTube Shorts 자동 업로드
8. Threads/X에 글감 3개 시간차(60초) 게시

## 실행 시간
- 매일 한국 시간 오전 8시 자동 실행
- GitHub Actions에서 "Run workflow" 버튼으로 수동 실행 가능

## GitHub Secrets 설정

| Secret | 값 |
|--------|-----|
| `OPENAI_API_KEY` | OpenAI API 키 |
| `OPENAI_API_BASE` | OpenAI API 베이스 URL (선택) |
| `GCP_TTS_KEY` | Google Cloud TTS API 키 |
| `THREADS_TOKEN` | Threads Access Token |
| `X_CONSUMER_KEY` | X API Key |
| `X_CONSUMER_SECRET` | X API Secret |
| `X_ACCESS_TOKEN` | X Access Token |
| `X_ACCESS_SECRET` | X Access Token Secret |
| `YT_CLIENT_ID` | YouTube OAuth Client ID |
| `YT_CLIENT_SECRET` | YouTube OAuth Client Secret |
| `YT_REFRESH_TOKEN` | YouTube Refresh Token |

## 파일 구조
```
feedscan_pipeline/
├── main.py                          # 메인 파이프라인
├── requirements.txt                 # Python 의존성
├── backgrounds/                     # 배경 이미지 5장
│   ├── bg1.png
│   ├── bg2.png
│   ├── bg3.png
│   ├── bg4.png
│   └── bg5.png
├── .github/workflows/daily.yml      # GitHub Actions 크론
└── README.md
```

## 비용
- GitHub Actions: 무료 (월 2,000분)
- Google Cloud TTS: 무료 (월 100만 글자)
- OpenAI GPT-4o: ~$0.01/일
- YouTube/Threads/X API: 무료
- **총 월간 비용: ~$0.30**
