"""HRD-Net 오픈API로 학원 훈련과정을 받아 courses.json을 갱신합니다.
- 키는 GitHub Secrets(HRD_KEY)에서만 읽습니다. 파일에 키를 적지 마세요.
- 수업 시간·반 이름 등 API에 없는 값은 기존 값을 그대로 유지합니다.
- 새 회차는 같은 과정(id)의 기존 정보를 이어받습니다.
"""
import json, os, sys, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("HRD_KEY", "").strip()
INST = "500042799200"          # 훈련기관 ID (index.html의 INST와 같음)
ORGAN = "온코딩"                # 훈련기관명 검색어
API = "https://hrd.work24.go.kr/jsp/HRDP/HRDPO00/HRDPOA60/HRDPOA60_1.jsp"
KST = timezone(timedelta(hours=9))
today = datetime.now(KST).date()

def call(params):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "ignore")

def fetch(organ):
    out, page = [], 1
    while page <= 20:
        p = {"returnType": "XML", "authKey": KEY, "outType": "1", "pageNum": page, "pageSize": 100,
             "srchTraStDt": today.strftime("%Y%m%d"),
             "srchTraEndDt": (today + timedelta(days=240)).strftime("%Y%m%d"),
             "srchTraArea1": "26", "sort": "ASC", "sortCol": "2"}
        if organ:
            p["srchTraOrganNm"] = organ
        root = ET.fromstring(call(p).strip())
        err = root.findtext("e") or root.findtext("error")
        if err:
            raise RuntimeError(f"API 오류: {err}")
        items = root.findall(".//scn_list")
        for it in items:
            g = lambda t: (it.findtext(t) or "").strip()
            out.append({"id": g("trprId"), "tme": g("trprDegr"), "title": g("title"),
                        "inst": g("trainstCstId"), "start": g("traStartDate"), "end": g("traEndDate")})
        total = int(root.findtext("scn_cnt") or 0)
        if page * 100 >= total or not items:
            break
        page += 1
    return [c for c in out if c["inst"] == INST and c["id"] and c["tme"]]

def main():
    if not KEY:
        sys.exit("HRD_KEY 비밀값이 없습니다.")
    api = fetch(ORGAN) or fetch(None)
    if not api:
        print("API에서 학원 과정을 하나도 찾지 못했습니다. 데이터는 바꾸지 않습니다.")
        return
    with open("courses.json", encoding="utf-8") as f:
        data = json.load(f)
    courses = data.get("courses", [])
    by_key = {(c["id"], str(c["tme"])): c for c in courses}
    by_id = {}
    for c in courses:
        by_id.setdefault(c["id"], c)

    changed, added, unmatched = [], [], []
    api_keys = set()
    for a in api:
        k = (a["id"], a["tme"]); api_keys.add(k)
        if k in by_key:
            c = by_key[k]
            for f in ("start", "end"):
                if a[f] and c.get(f) != a[f]:
                    changed.append(f"{c['name']} {c['tme']}회차 {f}: {c.get(f)} → {a[f]}"); c[f] = a[f]
        elif a["id"] in by_id:
            new = dict(by_id[a["id"]]); new.update({"tme": a["tme"], "start": a["start"], "end": a["end"]})
            courses.append(new); by_key[k] = new
            added.append(f"{new['name']} {a['tme']}회차 ({a['start']} 개강)")
        else:
            unmatched.append(a)

    # 고용24에서 사라진(폐강 등) 앞으로의 회차는 목록에서 뺍니다
    removed = []
    for c in list(courses):
        k = (c["id"], str(c["tme"]))
        if c.get("start", "") >= today.isoformat() and k not in api_keys:
            courses.remove(c); removed.append(f"{c['name']} {c['tme']}회차")

    # 1년 넘게 지난 회차는 정리 (새 회차 정보 이어받기용으로 그 전까지는 보관)
    cutoff = (today - timedelta(days=365)).isoformat()
    courses[:] = [c for c in courses if c.get("start", "") >= cutoff]
    courses.sort(key=lambda c: c.get("start", ""))

    data["courses"] = courses
    data["unmatched"] = [{"title": u["title"], "start": u["start"], "end": u["end"]} for u in unmatched]
    if changed or added or removed or data.get("_last_unmatched") != len(unmatched):
        data["updated"] = today.isoformat()
    data["_last_unmatched"] = len(unmatched)
    with open("courses.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2); f.write("\n")

    print(f"API 학원 과정 {len(api)}건")
    for t, xs in (("날짜 변경", changed), ("새 회차 추가", added), ("목록에서 제외", removed)):
        for x in xs: print(f"- {t}: {x}")
    for u in unmatched:
        print(f"- 확인 필요(처음 보는 과정, 수업 시간 등 직접 입력 필요): {u['title']} {u['start']}")

if __name__ == "__main__":
    main()
