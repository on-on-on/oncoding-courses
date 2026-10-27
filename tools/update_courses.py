#!/usr/bin/env python3
"""고용24에서 학원 국비과정을 읽어 courses.json을 만든다 (표준 라이브러리만 사용).
사용: python3 update_courses.py [출력경로]   기본 출력: ../courses.json
"""
import urllib.request, urllib.parse, http.cookiejar, datetime, re, json, sys, os, html as H

INST_NAME = "온코딩컴퓨터학원"
INST_ID = "500042799200"
BASE = "https://www.work24.go.kr"
W = "월화수목금토일"

# 고용24 제목 → (크게 보일 이름, 작은 설명)
NAME_RULES = [
    (r"전산세무회계", ("전산세무회계", "전산회계 1급 + 전산세무 2급")),
    (r"전산세무\s*2급", ("전산세무 2급", "자격증 취득과정")),
    (r"전산회계\s*1급", ("전산회계 1급", "자격증 취득과정")),
    (r"한글.*엑셀.*파워포인트|ITQ", ("한글·엑셀·파워포인트", "ITQ 자격증 취득과정")),
    (r"컴퓨터활용능력\s*2급", ("컴퓨터활용능력 2급", "필기·실기 자격증 취득과정")),
    (r"컴퓨터활용능력\s*1급", ("컴퓨터활용능력 1급", "필기·실기 자격증 취득과정")),
]

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", "Mozilla/5.0 (compatible; course-updater)")]

def get(url, data=None):
    if data is not None:
        data = urllib.parse.urlencode(data).encode()
    with op.open(url, data=data, timeout=40) as r:
        return r.read().decode("utf-8", "ignore")

def text(s):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", s))).strip()

def search(today):
    end = today.replace(year=today.year + 1)
    p = {"dghtSe":"A","traingMthCd":"A","endDate":end.strftime("%Y%m%d"),"trng_prd":"A","pageSize":"50",
         "startDate_datepicker":today.isoformat(),"totamtSuptYn":"A","keyword":"","area":"00|전국 전체","orderKey":"2",
         "srchType":"all_type","crseTracseSe":"A|훈련유형 전체","trng_type":"A","pageId":"2","noTrngPay":"Y",
         "endDate_datepicker":end.isoformat(),"pageOrder":"2ASC","startDate":today.strftime("%Y%m%d"),"tracseTme":"3",
         "keyword2":"온코딩","orderBy":"ASC","currentTab":"1","pageRow":"50","keywordTrngNm":"온코딩","keywordType":"1",
         "totTraingTime":"A","i2":"A","programMenuIdentification":"EBG020000510010","pageIndex":"1","action":"trnnCrsInfPost.do"}
    h = get(BASE + "/hr/a/a/1100/trnnCrsInf.do?" + urllib.parse.urlencode(p))
    starts = [m.start() for m in re.finditer(r'<h3 class="t3_sb[^"]*">\s*<a[^>]*fn_viewTracseInfo\(', h)]
    out, seen = [], set()
    for k, s in enumerate(starts):
        m = re.search(r"fn_viewTracseInfo\('(\w+)','(\d+)','(\w+)','(\d+)'\);\"\s*>\s*(.*?)</a>", h[s:s + 2000], re.S)
        if not m or m.group(4) != INST_ID or (m.group(1), m.group(2)) in seen:
            continue
        seen.add((m.group(1), m.group(2)))
        after = text(h[s:starts[k + 1] if k + 1 < len(starts) else s + 12000])
        d = re.search(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", after)
        n = re.search(r"(\d+)일,\s*총\s*(\d+)시간", after)
        if not d or not n:
            continue
        out.append({"id": m.group(1), "tme": m.group(2), "title": text(m.group(5)),
                    "start": d.group(1), "end": d.group(2), "days": int(n.group(1)), "hours": int(n.group(2))})
    return out

def timetable(c, day, token):
    h = get(BASE + "/hr/a/a/3100/selectTimtblDetailList.do",
            {"tracseId": c["id"], "tracseTme": c["tme"], "traingDe": day.strftime("%Y%m%d"), "_csrf": token})
    m = re.search(r"훈련시간\s*(\d{2}:\d{2})\s*~\s*(\d{2}:\d{2})", text(h))
    return (m.group(1), m.group(2)) if m else None

def enrich(c):
    det = get(f"{BASE}/hr/a/a/3100/selectTracseDetl.do?tracseId={c['id']}&tracseTme={c['tme']}&crseTracseSe=C0061&trainstCstmrId={INST_ID}")
    tk = re.search(r'name="_csrf"\s+content="([^"]+)"', det) or re.search(r'content="([^"]+)"\s+name="_csrf"', det)
    token = tk.group(1) if tk else ""
    s = datetime.date.fromisoformat(c["start"])
    first = timetable(c, s, token)
    days = set()
    for i in range(7):
        dd = s + datetime.timedelta(days=i)
        if dd > datetime.date.fromisoformat(c["end"]):
            break
        if i == 0 and first or (i and timetable(c, dd, token)):
            days.add(dd.weekday())
    if days == {0, 1, 2, 3, 4}: dow = "월–금"
    elif days == {5}: dow = "토요일"
    elif days == {6}: dow = "일요일"
    else: dow = "·".join(W[x] for x in sorted(days)) or ""
    time = f"{first[0]} – {first[1]}" if first else ""
    if days and days <= {5, 6}: slot = "토요반" if 5 in days else "일요반"
    elif first: slot = "오전반" if first[0] < "12:00" else "오후반"
    else: slot = ""
    name, sub = next((v for p, v in NAME_RULES if re.search(p, c["title"])), (re.sub(r"^\[[^\]]*\]\s*", "", c["title"]), ""))
    return {"id": c["id"], "tme": c["tme"], "name": name, "sub": sub, "start": c["start"], "end": c["end"],
            "days": c["days"], "hours": c["hours"], "dow": dow, "time": time, "slot": slot}

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "courses.json")
    today = datetime.date.today()
    rows = [enrich(c) for c in search(today) if c["start"] >= today.isoformat()]
    rows.sort(key=lambda r: (r["start"], r["name"]))
    if not rows:
        print("과정 0개 — 고용24 응답을 확인하세요. 파일을 바꾸지 않습니다."); sys.exit(2)
    data = {"updated": today.isoformat(), "courses": rows}
    old = None
    if os.path.exists(out):
        try: old = json.load(open(out, encoding="utf-8")).get("courses")
        except Exception: pass
    if old == rows:
        print("변경 없음"); return
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"갱신: {len(rows)}개 과정 → {out}")
    for r in rows: print(f" - {r['start']} {r['name']} ({r['slot']} {r['dow']} {r['time']})")

if __name__ == "__main__":
    main()
