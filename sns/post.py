#!/usr/bin/env python3
"""렉스노트 인스타그램 자동 게시. queue.json에서 오늘(한국 시각) 몫을 찾아 올린다.
사용: python3 sns/post.py [--date YYYY-MM-DD] [--slot morning|evening] [--dry] [--check]
오전 몫은 slot 없음 또는 "morning", 저녁 몫(생활 법률상식)은 slot "evening".
토큰: 환경 변수 INSTAGRAM_ACCESS_TOKEN (시스템 사용자 토큰, 만료 없음)
페이스북: 같은 토큰으로 me/accounts에 페이지가 보이면 그 페이지에도 같은 글·미디어를 올린다.
사진·영상은 GitHub Pages 공개 주소에서 인스타그램이 가져간다(먼저 push 되어 있어야 함)."""
import json, os, sys, time, urllib.request, urllib.parse, datetime
IG = "17841461039387412"          # lex__note
API = "https://graph.facebook.com/v21.0"
BASE = "https://wbbf.github.io/lexnote/sns/"
HERE = os.path.dirname(os.path.abspath(__file__))
QF = os.path.join(HERE, "queue.json")

def call(method, path, **params):
    tok = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip().strip('"').strip("'")
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        url += "?" + data.decode(); data = None
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"API 오류 {e.code}: {e.read().decode()[:500]}")

def fb_page():
    """시스템 사용자에게 연결된 페이스북 페이지(id, 페이지 토큰). 없으면 None."""
    try:
        d = call("GET", "me/accounts", fields="id,name,access_token").get("data", [])
    except SystemExit:
        return None
    return (d[0]["id"], d[0]["access_token"], d[0]["name"]) if d else None

def fb_publish(page, item):
    """같은 미디어·글을 페이스북 페이지에도 올린다. 실패해도 인스타 게시는 유지."""
    pid, ptok, _ = page
    url = BASE + urllib.parse.quote(item["file"])
    if item["type"] == "REELS":
        params = dict(file_url=url, description=item["caption"], access_token=ptok); path = f"{pid}/videos"
    else:
        params = dict(url=url, message=item["caption"], access_token=ptok); path = f"{pid}/photos"
    req = urllib.request.Request(f"{API}/{path}", data=urllib.parse.urlencode(params).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r: return json.load(r).get("id")
    except urllib.error.HTTPError as e:
        print(f"페이스북 게시 실패 {e.code}: {e.read().decode()[:300]}"); return None

def publish(item):
    url = BASE + urllib.parse.quote(item["file"])
    if item["type"] == "REELS":
        c = call("POST", f"{IG}/media", media_type="REELS", video_url=url, caption=item["caption"], share_to_feed="true",
                 thumb_offset=str(item.get("thumb_ms", 10000)))   # 표지: 내용이 다 나온 10초 지점
    elif item["type"] == "STORIES":            # 스토리: 세로 이미지 한 장(글 없음)
        c = call("POST", f"{IG}/media", media_type="STORIES", image_url=url)
    else:
        c = call("POST", f"{IG}/media", image_url=url, caption=item["caption"])
    cid = c["id"]
    for _ in range(60):                       # 최대 10분 처리 대기
        s = call("GET", cid, fields="status_code,status")
        if s.get("status_code") == "FINISHED": break
        if s.get("status_code") in ("ERROR", "EXPIRED"): raise SystemExit(f"처리 실패: {s}")
        time.sleep(10)
    else: raise SystemExit("처리 시간 초과")
    m = call("POST", f"{IG}/media_publish", creation_id=cid)
    info = call("GET", m["id"], fields="permalink,timestamp")
    return m["id"], info.get("permalink")

def main():
    args = sys.argv[1:]
    if "--check" in args:                    # 토큰 점검: 값은 출력하지 않고 계정 조회만
        tok = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip().strip('"').strip("'")
        print(f"토큰 길이 {len(tok)}, 형태 {'정상(EA로 시작)' if tok.startswith('EA') else '이상'}")
        r = call("GET", IG, fields="username")
        print("토큰 정상: 계정", r.get("username"))
        pg = fb_page(); print("페이스북 페이지:", pg[2] if pg else "연결 안 됨(인스타만 게시)"); return
    today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime("%Y-%m-%d")
    if "--date" in args: today = args[args.index("--date") + 1]
    slot = args[args.index("--slot") + 1] if "--slot" in args else "morning"
    q = json.load(open(QF, encoding="utf-8"))
    todo = [x for x in q if x["date"] == today and x["status"] == "pending"
            and x.get("slot", "morning") == slot]
    if not todo:
        left = [x["date"] for x in q if x["status"] == "pending" and x.get("slot", "morning") == slot]
        print(f"{today} {slot}: 올릴 것 없음. 남은 예약 {len(left)}건 {left[:3]}"); return
    page = None if "--dry" in args else fb_page()
    for x in todo:
        if "--dry" in args: print("올릴 예정:", x["file"]); continue
        mid, link = publish(x)
        x.update(status="posted", media_id=mid, permalink=link,
                 posted_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        print("게시 완료:", x["file"], link)
        if page and x["type"] != "STORIES":
            fid = fb_publish(page, x)
            if fid: x["fb_id"] = fid; print("페이스북 게시 완료:", fid)
    json.dump(q, open(QF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    left = sum(1 for x in q if x["status"] == "pending")
    print(f"남은 예약 {left}건")

if __name__ == "__main__": main()
