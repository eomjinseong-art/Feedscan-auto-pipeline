"""
Feedscan AI 일일 자동화 파이프라인 (GitHub Actions용)
전체 흐름: 데이터 수집 → GPT 선정/생성 → TTS → 이미지 합성 → 자막 → FFmpeg → YouTube 업로드 → Threads/X 시간차 게시

RUN_MODE:
- full: 영상 제작 + YouTube 업로드 + 글감1 게시 (오전 8시)
- post2: 글감2 게시 (오후 2시)
- post3: 글감3 게시 (오후 8시)
"""
import os, json, time, base64, subprocess, math, sys, random, textwrap
from datetime import datetime
import requests
from requests_oauthlib import OAuth1
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import sheets

# === 환경 변수 ===
RUN_MODE = os.environ.get("RUN_MODE", "full")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE")
GCP_TTS_KEY = os.environ.get("GCP_TTS_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = "m3gJBS8OofDJfycyA2Ip"  # 태형
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
    if isinstance(data, dict):
        kr_videos = data.get("kr_shorts_top10", [])
        if not kr_videos:
            kr_videos = data.get("kr_videos_top10", [])
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
채널 컨셉: AI 기술을 활용한 다양한 돈벌이를 연구합니다. AI 기술을 활용한 다양한 콘텐츠의 성공/실패/위험을 균형 있게 다루는 정보 채널 (무조건 돈 번다는 톤 금지)

그 콘텐츠를 바탕으로 다음을 작성해 주세요:

1. TikTok 나레이션 스크립트 (약 60초 분량, 아래 흐름을 반드시 따르되 라벨/구분 표시 없이 자연스럽게 이어지는 문장으로 작성)
   - 흐름: 궁금증을 끄는 도입 → 의문 제기 → 단서 제시 → 새로운 의문 제기 → 단서 제시 → 반전 또는 결론 → 시청자에게 질문
   - 흔한 실수인 "도입 → 설명 → 설명 → 설명 → 끝" 구조는 절대 금지 (평면적 나열 금지, 반드시 의문-단서 구조로 긴장감 유지)
   - 톤: 밝고 에너지 있는 정보 전달자
   - 위 흐름의 마지막 "질문" 다음에 아래 마무리 멘트를 고정으로 붙일 것:
     "다른 사람들은 어떻게 AI로 돈을 벌고 있는지 프로필 링크를 보시면 확인하실 수 있습니다. 매일 AI로 돈버는 이야기를 제가 직접 전해드립니다. 오늘도 당신은 멋집니다."
   - 맞춤법 완벽하게
2. Threads/X 글감 3개
   - 톤: "~라고 들었는데 이거 진짜야?", "~라는데 이게 말이 돼?", "해본 사람 있어?" 식의 화제를 던지는 톤
   - 해시태그 절대 사용 금지
3. YouTube Shorts 제목 (40자 이내, #Shorts 포함)
4. YouTube 설명문 (2~3줄 + 콘텐츠 내용에 맞춘 해시태그 정확히 2개)
5. 뱃지 텍스트: 예시 문구를 그대로 쓰지 말고, 이 콘텐츠의 핵심을 가장 잘 압축해서 설명하는 짧은 문구를 매번 새로 생성
6. 핵심 요약 3단계: 이 콘텐츠의 핵심을 3단계로 요약 (각 단계는 제목 + 한줄 설명)

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
  "badge": "#1 TODAY",
  "summary_steps": [
    {{"step": 1, "title": "단계1 제목", "desc": "단계1 설명"}},
    {{"step": 2, "title": "단계2 제목", "desc": "단계2 설명"}},
    {{"step": 3, "title": "단계3 제목", "desc": "단계3 설명"}}
  ],
  "main_title": "메인 제목 (2줄, 각 줄 10자 이내)",
  "sub_info": "조회수 000,000"
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
        result["views"] = videos[idx].get("views", 0)
    print(f"  선정: {result['topic']}")
    return result

# === 3. TTS 생성 (ElevenLabs 우선 - 태형 보이스, 실패 시 구글 TTS 폴백) ===
def generate_tts(text):
    print("[3/7] TTS 생성 중 (ElevenLabs - 태형)...")
    audio_bytes = None

    if ELEVENLABS_API_KEY:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "speed": 1.1
                }
            }
        )
        if resp.status_code == 200:
            audio_bytes = resp.content
        else:
            print(f"  ElevenLabs 실패({resp.status_code}): {resp.text[:200]}")
            print("  구글 TTS(Chirp3-HD)로 폴백 시도...")

    if audio_bytes is None:
        resp = requests.post(
            f"https://texttospeech.googleapis.com/v1beta1/text:synthesize?key={GCP_TTS_KEY}",
            json={
                "input": {"text": text},
                "voice": {"languageCode": "ko-KR", "name": "ko-KR-Chirp3-HD-Puck"},
                "audioConfig": {"audioEncoding": "MP3", "speakingRate": 1.2}
            }
        )
        if resp.status_code != 200:
            print(f"  Chirp3-HD 실패, Neural2-C 폴백 시도...")
            resp = requests.post(
                f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GCP_TTS_KEY}",
                json={
                    "input": {"text": text},
                    "voice": {"languageCode": "ko-KR", "name": "ko-KR-Neural2-C"},
                    "audioConfig": {"audioEncoding": "MP3", "speakingRate": 1.35, "pitch": 2.0}
                }
            )
            if resp.status_code != 200:
                print(f"  TTS 실패: {resp.text[:200]}")
                return None
        audio_bytes = base64.b64decode(resp.json()["audioContent"])

    audio_path = f"{WORK_DIR}/narration.mp3"
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)
    
    # 앞뒤 1초 무음 추가
    padded_path = f"{WORK_DIR}/narration_padded.mp3"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-t", "1", "-i", "anullsrc=r=24000:cl=mono",
        "-i", audio_path,
        "-f", "lavfi", "-t", "1", "-i", "anullsrc=r=24000:cl=mono",
        "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[out]",
        "-map", "[out]", padded_path
    ], capture_output=True)
    
    final_audio = padded_path if os.path.exists(padded_path) else audio_path
    
    dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", final_audio
    ]).decode().strip())
    print(f"  생성 완료: {dur:.1f}초")
    return final_audio, dur

# === 4. 포디움 디자인 이미지 생성 ===
def generate_images(content):
    print("[4/7] 포디움 디자인 이미지 생성 중...")
    bg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backgrounds")
    
    # 폰트 설정
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    try:
        font_badge = ImageFont.truetype(font_path, 42)
        font_title = ImageFont.truetype(font_path, 72)
        font_sub = ImageFont.truetype(font_path, 48)
        font_step_num = ImageFont.truetype(font_path, 56)
        font_step_title = ImageFont.truetype(font_path, 44)
        font_step_desc = ImageFont.truetype(font_path, 36)
        font_info = ImageFont.truetype(font_path, 32)
    except:
        font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"
        try:
            font_badge = ImageFont.truetype(font_path, 42)
            font_title = ImageFont.truetype(font_path, 72)
            font_sub = ImageFont.truetype(font_path, 48)
            font_step_num = ImageFont.truetype(font_path, 56)
            font_step_title = ImageFont.truetype(font_path, 44)
            font_step_desc = ImageFont.truetype(font_path, 36)
            font_info = ImageFont.truetype(font_path, 32)
        except:
            print("  폰트를 찾을 수 없습니다.")
            font_badge = font_title = font_sub = font_step_num = font_step_title = font_step_desc = font_info = ImageFont.load_default()
    
    badge = content.get("badge", "#1 TODAY")
    main_title = content.get("main_title", content.get("topic", "AI 부업"))
    views = content.get("views", 0)
    sub_info = content.get("sub_info", f"조회수 {views:,}")
    summary_steps = content.get("summary_steps", [])
    
    images = []
    
    # === 씬 1: 포디움 + 뱃지 + 메인 제목 (고정 표지 이미지 cover.png 사용) ===
    bg_path = os.path.join(bg_dir, "cover.png")
    if not os.path.exists(bg_path):
        bg_path = os.path.join(bg_dir, "bg2.png")
    img = Image.open(bg_path).convert("RGBA").resize((1080, 1920))
    draw = ImageDraw.Draw(img)
    
    # 뱃지 (상단 중앙, 빨간/금색 배경)
    badge_bbox = draw.textbbox((0, 0), badge, font=font_badge)
    badge_w = badge_bbox[2] - badge_bbox[0]
    badge_h = badge_bbox[3] - badge_bbox[1]
    badge_x = (1080 - badge_w - 40) // 2
    badge_y = 120
    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + badge_w + 40, badge_y + badge_h + 20],
        radius=12, fill=(220, 50, 50)
    )
    draw.text((badge_x + 20, badge_y + 8), badge, font=font_badge, fill=(255, 255, 255))
    
    # 메인 제목 (중앙)
    title_lines = main_title.split("\n") if "\n" in main_title else [main_title]
    y = 350
    for line in title_lines[:3]:
        line_bbox = draw.textbbox((0, 0), line, font=font_title)
        line_w = line_bbox[2] - line_bbox[0]
        draw.text(((1080 - line_w) // 2, y), line, font=font_title, fill=(255, 215, 0))
        y += 100
    
    # 조회수 정보
    info_bbox = draw.textbbox((0, 0), sub_info, font=font_info)
    info_w = info_bbox[2] - info_bbox[0]
    draw.text(((1080 - info_w) // 2, y + 30), sub_info, font=font_info, fill=(200, 200, 200))
    
    out_path = f"{WORK_DIR}/scene_0.png"
    img.save(out_path)
    images.append(out_path)
    
    # === 씬 2: 핵심 요약 3단계 (bg3.png 사용 - 블루 사이버) ===
    bg_path = os.path.join(bg_dir, "bg3.png")
    if not os.path.exists(bg_path):
        bg_path = os.path.join(bg_dir, "bg1.png")
    img = Image.open(bg_path).convert("RGBA").resize((1080, 1920))
    draw = ImageDraw.Draw(img)
    
    # 상단 제목
    header = "핵심 요약 3단계"
    header_bbox = draw.textbbox((0, 0), header, font=font_sub)
    header_w = header_bbox[2] - header_bbox[0]
    draw.text(((1080 - header_w) // 2, 180), header, font=font_sub, fill=(255, 215, 0))
    
    # 3단계 카드
    y = 380
    for i, step in enumerate(summary_steps[:3]):
        # 번호 원
        circle_x = 120
        circle_y = y + 10
        draw.ellipse([circle_x - 30, circle_y - 30, circle_x + 30, circle_y + 30], fill=(255, 215, 0))
        num_text = str(step.get("step", i + 1))
        num_bbox = draw.textbbox((0, 0), num_text, font=font_step_num)
        num_w = num_bbox[2] - num_bbox[0]
        draw.text((circle_x - num_w // 2, circle_y - 28), num_text, font=font_step_num, fill=(0, 0, 0))
        
        # 제목
        step_title = step.get("title", "")
        draw.text((180, y - 15), step_title, font=font_step_title, fill=(255, 255, 255))
        
        # 설명
        step_desc = step.get("desc", "")
        draw.text((180, y + 45), step_desc, font=font_step_desc, fill=(180, 180, 180))
        
        y += 180
    
    out_path = f"{WORK_DIR}/scene_1.png"
    img.save(out_path)
    images.append(out_path)
    
    # === 씬 3: 결론/CTA (bg5.png 사용 - 퍼플 네온) ===
    bg_path = os.path.join(bg_dir, "bg5.png")
    if not os.path.exists(bg_path):
        bg_path = os.path.join(bg_dir, "bg2.png")
    img = Image.open(bg_path).convert("RGBA").resize((1080, 1920))
    draw = ImageDraw.Draw(img)
    
    # CTA 텍스트
    cta_lines = [
        "더 자세한 분석은",
        "프로필 링크에서",
        "확인하세요"
    ]
    y = 300
    for line in cta_lines:
        line_bbox = draw.textbbox((0, 0), line, font=font_title)
        line_w = line_bbox[2] - line_bbox[0]
        draw.text(((1080 - line_w) // 2, y), line, font=font_title, fill=(255, 255, 255))
        y += 110
    
    # 하단 채널명
    channel = "FeedScan AI"
    ch_bbox = draw.textbbox((0, 0), channel, font=font_sub)
    ch_w = ch_bbox[2] - ch_bbox[0]
    draw.text(((1080 - ch_w) // 2, y + 80), channel, font=font_sub, fill=(255, 215, 0))
    
    out_path = f"{WORK_DIR}/scene_2.png"
    img.save(out_path)
    images.append(out_path)
    
    print(f"  {len(images)}장 생성 완료 (포디움 디자인)")
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
Style: Default,Noto Sans CJK KR,40,&H00FFFFFF,&H000000FF,&H00000000,&HC0000000,-1,0,0,0,100,100,0,0,3,2,0,2,70,150,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    current = 1.0  # 앞 1초 무음 이후 시작
    effective_duration = duration - 2.0  # 앞뒤 1초씩 제외
    
    for sentence in sentences:
        dur = (len(sentence) / total_chars) * effective_duration
        start = f"{int(current//3600)}:{int((current%3600)//60):02d}:{current%60:05.2f}"
        end_t = current + dur
        end = f"{int(end_t//3600)}:{int((end_t%3600)//60):02d}:{end_t%60:05.2f}"
        
        # 16자 줄바꿈 (폰트 축소로 인해 줄당 더 많은 글자 수용 가능)
        text = ""
        for idx in range(0, len(sentence), 16):
            text += sentence[idx:idx+16] + "\\N"
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
def upload_youtube(video_path, title, description, thumbnail_path=None):
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
    
    if upload_resp.status_code != 200:
        print(f"  업로드 실패: {upload_resp.text[:200]}")
        return None

    vid = upload_resp.json().get("id")
    print(f"  업로드 완료: https://youtube.com/shorts/{vid}")

    # 썸네일(표지) 업로드
    if thumbnail_path and os.path.exists(thumbnail_path):
        with open(thumbnail_path, "rb") as f:
            thumb_resp = requests.post(
                f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "image/png"
                },
                data=f.read()
            )
        if thumb_resp.status_code == 200:
            print("  썸네일(표지) 업로드 완료")
        else:
            print(f"  썸네일 업로드 실패(영상 업로드는 정상): {thumb_resp.text[:200]}")

    return vid

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
    
    if RUN_MODE == "generate":
        # 새벽 시간대: 콘텐츠 생성 후 시트에 기록만 (렌더링/업로드 없음)
        if sheets.today_row_exists():
            print("오늘자 행이 이미 시트에 존재합니다. 중복 생성을 방지하기 위해 종료합니다.")
            sys.exit(0)

        videos = fetch_daily_data()
        if not videos:
            print("데이터 없음. 종료.")
            sys.exit(1)

        content = generate_content(videos)
        sheets.append_draft_row(content, content.get("source_url", ""))
        print("\n시트에 초안 기록 완료 (Status=Approved, 자동승인)")

    elif RUN_MODE == "preview":
        # 미리보기: 시트에서 오늘의 Approved 행을 읽어 TTS+영상 합성까지만 진행
        # 유튜브 업로드/SNS 게시/시트 Published 처리는 하지 않음 (테스트 전용)
        row = sheets.find_today_approved_unpublished_row()
        if not row:
            print("오늘 미리볼 대상 행을 찾을 수 없습니다 (generate 모드가 먼저 실행되었는지 확인 필요). 종료.")
            sys.exit(1)

        content = dict(row["scene_data"])
        content["narration"] = row["narration"]
        content["topic"] = row["topic"]

        print(f"\n[미리보기] 나레이션 텍스트:\n{content['narration']}\n")

        # 3. TTS
        tts_result = generate_tts(content["narration"])
        if not tts_result:
            sys.exit(1)
        audio_path, duration = tts_result
        print(f"[미리보기] 음성 길이: {duration:.1f}초")

        # 4. 포디움 디자인 이미지
        images = generate_images(content)

        # 5. 자막
        ass_path = generate_subtitles(content["narration"], duration)

        # 6. 영상 합성
        video_path = render_video(images, audio_path, ass_path, duration)
        if not video_path:
            sys.exit(1)

        # 결과물을 GitHub Actions Artifact로 남기기 위해 outputs 폴더에 복사
        preview_dir = os.path.join(os.getcwd(), "preview_output")
        os.makedirs(preview_dir, exist_ok=True)
        preview_path = os.path.join(preview_dir, "preview.mp4")
        subprocess.run(["cp", video_path, preview_path])
        print(f"\n[미리보기 완료] {preview_path}")
        print("업로드/게시는 진행되지 않았습니다. Actions 실행 결과 하단 Artifacts에서 preview.mp4를 다운로드해 확인하세요.")

    elif RUN_MODE == "full":
        # 오전 8시: 시트에서 오늘의 Approved & 미발행 행을 읽어와 렌더링/업로드
        row = sheets.find_today_approved_unpublished_row()
        if not row:
            print("오늘 발행 대상 행을 찾을 수 없습니다 (generate 모드가 먼저 실행되었는지 확인 필요). 종료.")
            sys.exit(1)

        content = dict(row["scene_data"])
        content["narration"] = row["narration"]
        content["topic"] = row["topic"]

        # 3. TTS
        tts_result = generate_tts(content["narration"])
        if not tts_result:
            sys.exit(1)
        audio_path, duration = tts_result

        # 4. 포디움 디자인 이미지
        images = generate_images(content)

        # 5. 자막
        ass_path = generate_subtitles(content["narration"], duration)

        # 6. 영상 합성
        video_path = render_video(images, audio_path, ass_path, duration)
        if not video_path:
            sys.exit(1)

        # 7. YouTube 업로드
        vid = upload_youtube(video_path, content.get("yt_title", row["topic"]), content.get("yt_desc", ""), thumbnail_path=images[0])
        if not vid:
            print("업로드 실패로 시트 갱신을 건너뜁니다.")
            sys.exit(1)

        video_url = f"https://youtube.com/shorts/{vid}"
        sheets.mark_published(row["row_num"], video_url)

        # 8. 글감1 게시
        print("\n글감1 게시 중...")
        post_single(row["tx1"])

    elif RUN_MODE == "post2":
        print("글감2 게시 중...")
        row = sheets.find_today_published_row()
        if not row:
            print("오늘 발행된 행을 찾을 수 없습니다. 종료.")
            sys.exit(1)
        post_single(row["tx2"])

    elif RUN_MODE == "post3":
        print("글감3 게시 중...")
        row = sheets.find_today_published_row()
        if not row:
            print("오늘 발행된 행을 찾을 수 없습니다. 종료.")
            sys.exit(1)
        post_single(row["tx3"])
    
    print("\n" + "=" * 50)
    print("완료!")
    print("=" * 50)
