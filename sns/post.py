#!/usr/bin/env python3
"""렉스노트 인스타그램 자동 게시. queue.json에서 오늘(한국 시각) 몫을 찾아 올린다.
사용: python3 sns/post.py [--date YYYY-MM-DD] [--slot morning|evening] [--dry] [--check]
오전 몫은 slot 없음 또는 "morning", 저녁 몫(생활 법률상식)은 slot "evening".
토큰: 환경 변수 INSTAGRAM_ACCESS_TOKEN (시스템 사용자 토큰, 만료 없음)
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

def publish(item):
    url = BASE + urllib.parse.quote(item["file"])
    if item["type"] == "REELS":
        c = call("POST", f"{IG}/media", media_type="REELS", video_url=url, caption=item["caption"], share_to_feed="true")
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
        print(f"토큰 길이 {len(tok)}, 앞 3글자 형태 {'EAA' if tok.startswith('EAA') else '다름'}")
        r = call("GET", IG, fields="username")
        print("토큰 정상: 계정", r.get("username")); return
    today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime("%Y-%m-%d")
    if "--date" in args: today = args[args.index("--date") + 1]
    slot = args[args.index("--slot") + 1] if "--slot" in args else "morning"
    q = json.load(open(QF, encoding="utf-8"))
    todo = [x for x in q if x["date"] == today and x["status"] == "pending"
            and x.get("slot", "morning") == slot]
    if not todo:
        left = [x["date"] for x in q if x["status"] == "pending" and x.get("slot", "morning") == slot]
        print(f"{today} {slot}: 올릴 것 없음. 남은 예약 {len(left)}건 {left[:3]}"); return
    for x in todo:
        if "--dry" in args: print("올릴 예정:", x["file"]); continue
        mid, link = publish(x)
        x.update(status="posted", media_id=mid, permalink=link,
                 posted_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        print("게시 완료:", x["file"], link)
    json.dump(q, open(QF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    left = sum(1 for x in q if x["status"] == "pending")
    print(f"남은 예약 {left}건")

if __name__ == "__main__": main()
