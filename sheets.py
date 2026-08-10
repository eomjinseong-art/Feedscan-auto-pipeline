"""
Google Sheets 연동 헬퍼
컬럼 순서(고정): A Status | B Source URL | C Topic | D 나레이션 | E 글감1 | F 글감2 | G 글감3 | H Scene Data(JSON) | I Video URL | J 실행일자
"""
import os
import json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
WORKSHEET_NAME = "Pipeline_v2"

COL_STATUS = 1
COL_SOURCE_URL = 2
COL_TOPIC = 3
COL_NARRATION = 4
COL_TX1 = 5
COL_TX2 = 6
COL_TX3 = 7
COL_SCENE_DATA = 8
COL_VIDEO_URL = 9
COL_RUN_DATE = 10


def _get_worksheet():
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        raise RuntimeError("GOOGLE_SHEETS_CREDENTIALS 환경변수가 없습니다.")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sh = client.open_by_key(SHEET_ID)
    return sh.worksheet(WORKSHEET_NAME)


def today_row_exists():
    """오늘 날짜로 이미 생성된 행이 있는지 확인 (중복 생성 방지)"""
    ws = _get_worksheet()
    today = datetime.now().strftime("%Y-%m-%d")
    run_dates = ws.col_values(COL_RUN_DATE)
    return today in run_dates


def append_draft_row(content, source_url):
    """generate 단계: 새 행 추가, Status=Approved로 바로 기록 (자동승인)"""
    ws = _get_worksheet()
    today = datetime.now().strftime("%Y-%m-%d")
    scene_data = json.dumps({
        "badge": content.get("badge", ""),
        "main_title": content.get("main_title", ""),
        "sub_info": content.get("sub_info", ""),
        "summary_steps": content.get("summary_steps", []),
        "yt_title": content.get("yt_title", ""),
        "yt_desc": content.get("yt_desc", ""),
    }, ensure_ascii=False)

    row = [
        "Approved",           # A Status - 자동승인
        source_url,           # B Source URL
        content.get("topic", ""),      # C Topic
        content.get("narration", ""),  # D 나레이션
        content.get("tx1", ""),        # E 글감1
        content.get("tx2", ""),        # F 글감2
        content.get("tx3", ""),        # G 글감3
        scene_data,            # H Scene Data
        "",                     # I Video URL - 아직 비움
        today,                   # J 실행일자
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    print(f"  시트에 새 행 기록 완료 (Status=Approved, 실행일자={today})")


def find_today_approved_unpublished_row():
    """publish 단계: 오늘 날짜 + Approved + Video URL 비어있는 행 찾기"""
    ws = _get_worksheet()
    today = datetime.now().strftime("%Y-%m-%d")
    all_values = ws.get_all_values()

    for idx, row in enumerate(all_values[1:], start=2):  # 1행은 헤더
        if len(row) < 10:
            row = row + [""] * (10 - len(row))
        status = row[COL_STATUS - 1]
        video_url = row[COL_VIDEO_URL - 1]
        run_date = row[COL_RUN_DATE - 1]
        if run_date == today and status == "Approved" and not video_url:
            return {
                "row_num": idx,
                "source_url": row[COL_SOURCE_URL - 1],
                "topic": row[COL_TOPIC - 1],
                "narration": row[COL_NARRATION - 1],
                "tx1": row[COL_TX1 - 1],
                "tx2": row[COL_TX2 - 1],
                "tx3": row[COL_TX3 - 1],
                "scene_data": json.loads(row[COL_SCENE_DATA - 1]) if row[COL_SCENE_DATA - 1] else {},
            }
    return None


def find_today_published_row():
    """post2/post3 단계: 오늘 이미 발행 완료된(Video URL 채워진) 행 찾기"""
    ws = _get_worksheet()
    today = datetime.now().strftime("%Y-%m-%d")
    all_values = ws.get_all_values()

    for idx, row in enumerate(all_values[1:], start=2):
        if len(row) < 10:
            row = row + [""] * (10 - len(row))
        video_url = row[COL_VIDEO_URL - 1]
        run_date = row[COL_RUN_DATE - 1]
        if run_date == today and video_url:
            return {
                "row_num": idx,
                "tx1": row[COL_TX1 - 1],
                "tx2": row[COL_TX2 - 1],
                "tx3": row[COL_TX3 - 1],
            }
    return None


def mark_published(row_num, video_url):
    """publish 단계 완료 후: Status=Published, Video URL 기록"""
    ws = _get_worksheet()
    ws.update_cell(row_num, COL_STATUS, "Published")
    ws.update_cell(row_num, COL_VIDEO_URL, video_url)
    print(f"  시트 {row_num}행 갱신 완료 (Status=Published, Video URL 기록)")
