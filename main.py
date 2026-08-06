"""
Feedscan AI 일일 자동화 파이프라인 (GitHub Actions용)
전체 흐름: 데이터 수집 → GPT 선정/생성 → TTS → 이미지 합성 → 자막 → FFmpeg → YouTube 업로드 → Threads/X 시간차 게시

RUN_MODE:
- full: 영상 제작 + YouTube 업로드 + 글감1 게시 (오전 8시)
- post2: 글감2 게시 (오후 2시)
- post3: 글감3 게시 (오후 8시)
"""
import os, json, time, base64, subprocess, math, sys
from datetime import datetime
import requests
from requests_oauthlib import OAuth1
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

# === 환경 변수 ===
RUN_MODE = os.environ.get("RUN_MODE", "full")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE")
GCP_TTS_KEY = os.environ.get("GCP_TTS_KEY")
THREADS_TOKEN = os.environ.get("THREADS_TOKEN")
THREADS_USER_ID = "28052334294453354"
X_CONSUMER_KEY = os.environ.get("X_CONSUMER_KEY")
X_CONSUMER_SECRET = os.environ.get("X_CONSUMER_SECRET")
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.environ.get("X_ACCESS_SECRET")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")

WORK_DIR = "/tmp/feedscan_render"
DATA_FILE = "/tmp/feedscan_today.json"
os.makedirs(WORK_DIR, exist_ok=True)

client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)

# === 1. 데이터 수집 ===
def fetch_daily_data():
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"https://aimoneyscanner.vercel.app/data/daily/{today}.json"
    print(f"[1/7] 데이터 수집: {url}")
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"  오늘 데이터 없음, 어제 데이터 시도...")
        from datetime import timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        url = f"https://aimoneyscanner.vercel.app/data/daily/{yesterday}.json"
        resp = requests.get(url)
    
    if resp.status_code != 200:
        print("  데이터를 가져올 수 없습니다.")
        return []
    
    data = resp.json()
    # JSON 구조: {"date": ..., "kr_shorts_top10": [...], "videos_top10": [...]}
    if isinstance(data, dict):
        kr_videos = data.get("kr_shorts_top10", [])
        if not kr_videos:
            kr_videos = data.get("videos_top10", [])
        if not kr_videos:
            kr_videos = data.get("shorts_top10", [])
    else:
        kr_videos = [v for v in data if isinstance(v, dict)][:10]
    
    kr_videos = kr_videos[:10]
    print(f"  {len(kr_videos)}개 콘텐츠 확인")
    return kr_videos

# === 2. GPT 콘텐츠 선정 및 생성 ===
def generate_content(videos):
    print("[2/7] GPT 콘텐츠 선정 및 생성 중...")
    
    videos_str = ""
    for i, v in enumerate(videos):
        title = v.get('title_ko', v.get('title', ''))
        method = v.get('method', v.get('method_en', ''))
        principle = v.get('principle', v.get('principle_en', ''))
        views = v.get('views', 0)
        videos_str += f"[{i+1}] 제목: {title}\n    수익화 방법: {method}\n    원리: {principle}\n    조회수: {views}\n\n"
        
    prompt = f"""다음은 오늘자 AI 부업 관련 인기 영상 탑10 목록입니다:

{videos_str}

이 중에서 가장 흥미롭고 사람들의 반응을 이끌어낼 만한 "진짜 괜찮은 콘텐츠 딱 1개"를 선정해 주세요.
채널 컨셉: 부업의 성공/실패/위험을 균형 있게 다루는 정보 채널 (무조건 돈 번다는 톤 금지)

그 콘텐츠를 바탕으로 다음을 작성해 주세요:

1. TikTok 나레이션 스크립트 (약 25~30초 분량, 5~6문장)
   - 톤: 밝고 에너지 있는 정보 전달자
   - 마무리 멘트 고정: "이런 정보 제가 매일 분석해드립니다. 더욱 자세한 내용은 프로필 링크에 가득합니다. 오늘도 당신은 멋집니다."
   - 맞춤법 완벽하게
2. Threads/X 글감 3개
   - 톤: "~라고 들었는데 이거 진짜야?", "~라는데 이게 말이 돼?", "해본 사람 있어?" 식의 화제를 던지는 톤
   - 해시태그 절대 사용 금지
3. YouTube Shorts 제목 (40자 이내, #Shorts 포함)
4. YouTube 설명문 (2~3줄 + 해시태그 5개)

반드시 아래 JSON 형식으로만 응답:
{{
  "selected_index": 1,
  "topic": "주제 요약 (10자 이내)",
  "narration": "틱톡 나레이션 전체",
  "tx1": "글감1",
  "tx2": "글감2", 
  "tx3": "글감3",
  "yt_title": "유튜브 제목 #Shorts",
  "yt_desc": "유튜브 설명문",
  "scene_titles": [["씬1 줄1", "씬1 줄2"], ["씬2 줄1", "씬2 줄2"], ["씬3 줄1", "씬3 줄2", "씬3 줄3"], ["씬4 줄1", "씬4 줄2"], ["씬5 줄1", "씬5 줄2"]]
}}"""
    
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a viral content creator. Always respond in valid JSON only."},
            {"role": "user", "content": prompt}
        ]
    )
    
    result = json.loads(response.choices[0].message.content)
    idx = result.get("selected_index", 1) - 1
    if idx < len(videos):
        result["source_url"] = f"https://youtube.com/watch?v={videos[idx].get('video_id', '')}"
    print(f"  선정: {result['topic']}")
    return result

# === 3. TTS 생성 ===
def generate_tts(text):
    print("[3/7] TTS 생성 중 (Google Cloud Neural2-C)...")
    resp = requests.post(
        f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GCP_TTS_KEY}",
        json={
            "input": {"text": text},
            "voice": {"languageCode": "ko-KR", "name": "ko-KR-Neural2-C"},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": 1.25, "pitch": 2.0}
        }
    )
    if resp.status_code != 200:
        print(f"  TTS 실패: {resp.text[:200]}")
        return None
    
    audio_path = f"{WORK_DIR}/narration.mp3"
    with open(audio_path, "wb") as f:
        f.write(base64.b64decode(resp.json()["audioContent"]))
    
    dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]).decode().strip())
    print(f"  생성 완료: {dur:.1f}초")
    return audio_path, dur

# === 4. 이미지 생성 ===
def generate_images(scene_titles):
    print("[4/7] 이미지 생성 중...")
    bg_files = ["bg1.png", "bg2.png", "bg3.png", "bg4.png", "bg5.png"]
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    
    try:
        font_main = ImageFont.truetype(font_path, 100)
        font_sub = ImageFont.truetype(font_path, 65)
    except:
        font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"
        try:
            font_main = ImageFont.truetype(font_path, 100)
            font_sub = ImageFont.truetype(font_path, 65)
        except:
            print("  폰트를 찾을 수 없습니다. 기본 폰트 사용.")
            font_main = ImageFont.load_default()
            font_sub = font_main
    
    images = []
    bg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backgrounds")
    
    for i, titles in enumerate(scene_titles):
        bg_path = os.path.join(bg_dir, bg_files[i % 5])
        img = Image.open(bg_path).convert("RGBA").resize((1080, 1920))
        draw = ImageDraw.Draw(img)
        
        y = 300
        for j, line in enumerate(titles):
            font = font_main if j == 0 else font_sub
            draw.text((100, y), line, font=font, fill=(255, 255, 255))
            y += 140 if j == 0 else 100
        
        out_path = f"{WORK_DIR}/scene_{i}.png"
        img.save(out_path)
        images.append(out_path)
    
    print(f"  {len(images)}장 생성 완료")
    return images

# === 5. 자막 생성 ===
def generate_subtitles(narration, duration):
    print("[5/7] 자막 생성 중...")
    sentences = [s.strip() for s in narration.replace(".", ".\n").split("\n") if s.strip()]
    total_chars = sum(len(s) for s in sentences)
    
    ass = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans CJK KR,56,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,70,150,500,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    current = 0
    for sentence in sentences:
        dur = (len(sentence) / total_chars) * duration
        start = f"{int(current//3600)}:{int((current%3600)//60):02d}:{current%60:05.2f}"
        end_t = current + dur
        end = f"{int(end_t//3600)}:{int((end_t%3600)//60):02d}:{end_t%60:05.2f}"
        
        # 12자 줄바꿈
        text = ""
        for idx in range(0, len(sentence), 12):
            text += sentence[idx:idx+12] + "\\N"
        text = text.rstrip("\\N")
        
        ass += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"
        current = end_t
    
    ass_path = f"{WORK_DIR}/subtitle.ass"
    with open(ass_path, "w") as f:
        f.write(ass)
    return ass_path

# === 6. FFmpeg 합성 ===
def render_video(images, audio_path, ass_path, duration):
    print("[6/7] 영상 합성 중...")
    time_per_scene = duration / len(images)
    
    cmd = ["ffmpeg", "-y"]
    for img in images:
        cmd.extend(["-loop", "1", "-t", str(time_per_scene), "-i", img])
    cmd.extend(["-i", audio_path])
    
    n = len(images)
    fc = ""
    for i in range(n):
        fc += f"[{i}:v]scale=1080:1920,setsar=1[v{i}]; "
    fc += "".join([f"[v{i}]" for i in range(n)]) + f"concat=n={n}:v=1:a=0[cv]; "
    fc += f"[cv]ass={ass_path}[outv]"
    
    output = f"{WORK_DIR}/final.mp4"
    cmd.extend([
        "-filter_complex", fc,
        "-map", "[outv]", "-map", f"{n}:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", output
    ])
    
    subprocess.run(cmd, capture_output=True)
    if os.path.exists(output):
        print(f"  합성 완료: {output}")
        return output
    else:
        print("  합성 실패!")
        return None

# === 7. YouTube 업로드 ===
def upload_youtube(video_path, title, description):
    print("[7/7] YouTube 업로드 중...")
    
    token_resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": YT_CLIENT_ID,
        "client_secret": YT_CLIENT_SECRET,
        "refresh_token": YT_REFRESH_TOKEN,
        "grant_type": "refresh_token"
    })
    if token_resp.status_code != 200:
        print(f"  토큰 갱신 실패: {token_resp.text[:200]}")
        return None
    
    access_token = token_resp.json()["access_token"]
    filesize = os.path.getsize(video_path)
    
    init_resp = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(filesize)
        },
        json={
            "snippet": {
                "title": title,
                "description": description,
                "tags": ["AI부업", "부업추천", "feedscanai", "피드스캔", "챗GPT"],
                "categoryId": "22"
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        }
    )
    
    if init_resp.status_code != 200:
        print(f"  업로드 초기화 실패: {init_resp.text[:200]}")
        return None
    
    upload_url = init_resp.headers.get("Location")
    with open(video_path, "rb") as f:
        upload_resp = requests.put(upload_url, headers={"Content-Type": "video/mp4"}, data=f)
    
    if upload_resp.status_code == 200:
        vid = upload_resp.json().get("id")
        print(f"  업로드 완료: https://youtube.com/shorts/{vid}")
        return vid
    else:
        print(f"  업로드 실패: {upload_resp.text[:200]}")
        return None

# === 소셜 게시 (1개만) ===
def post_single(text):
    """글감 1개를 Threads + X에 게시"""
    auth = OAuth1(X_CONSUMER_KEY, X_CONSUMER_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)
    
    # Threads
    if THREADS_TOKEN:
        resp = requests.post(
            f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
            params={"media_type": "TEXT", "text": text, "access_token": THREADS_TOKEN}
        )
        if resp.status_code == 200:
            cid = resp.json().get("id")
            time.sleep(3)
            requests.post(
                f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish",
                params={"creation_id": cid, "access_token": THREADS_TOKEN}
            )
            print(f"  [Threads] 게시 완료")
    
    # X
    if X_CONSUMER_KEY:
        resp = requests.post(
            "https://api.twitter.com/2/tweets",
            auth=auth, json={"text": text}, headers={"Content-Type": "application/json"}
        )
        if resp.status_code == 201:
            print(f"  [X] 게시 완료")

# === 메인 ===
if __name__ == "__main__":
    print("=" * 50)
    print(f"Feedscan AI 파이프라인 | 모드: {RUN_MODE}")
    print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)
    
    if RUN_MODE == "full":
        # === 오전 8시: 전체 실행 (영상 + 글감1) ===
        
        # 1. 데이터 수집
        videos = fetch_daily_data()
        if not videos:
            print("데이터 없음. 종료.")
            sys.exit(1)
        
        # 2. GPT 콘텐츠 생성
        content = generate_content(videos)
        
        # 오후 2시, 8시에 사용할 글감을 저장
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"tx1": content["tx1"], "tx2": content["tx2"], "tx3": content["tx3"]}, f, ensure_ascii=False)
        
        # GitHub Actions 아티팩트로 저장 (다음 실행에서 사용)
        # 대안: 글감을 Google Sheets에 기록하고 나중에 읽어오기
        
        # 3. TTS
        tts_result = generate_tts(content["narration"])
        if not tts_result:
            sys.exit(1)
        audio_path, duration = tts_result
        
        # 4. 이미지
        images = generate_images(content["scene_titles"])
        
        # 5. 자막
        ass_path = generate_subtitles(content["narration"], duration)
        
        # 6. 영상 합성
        video_path = render_video(images, audio_path, ass_path, duration)
        if not video_path:
            sys.exit(1)
        
        # 7. YouTube 업로드
        upload_youtube(video_path, content["yt_title"], content["yt_desc"])
        
        # 8. 글감1 게시
        print("\n글감1 게시 중...")
        post_single(content["tx1"])
        
    elif RUN_MODE == "post2":
        # === 오후 2시: 글감2만 게시 ===
        # 오전에 생성한 글감을 가져와야 함
        # GitHub Actions는 실행마다 환경이 초기화되므로, 다시 생성
        print("글감2 생성 및 게시 중...")
        videos = fetch_daily_data()
        if not videos:
            sys.exit(1)
        content = generate_content(videos)
        post_single(content["tx2"])
        
    elif RUN_MODE == "post3":
        # === 오후 8시: 글감3만 게시 ===
        print("글감3 생성 및 게시 중...")
        videos = fetch_daily_data()
        if not videos:
            sys.exit(1)
        content = generate_content(videos)
        post_single(content["tx3"])
    
    print("\n" + "=" * 50)
    print("완료!")
    print("=" * 50)
