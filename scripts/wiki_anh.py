"""Find each commune's own vi.wikipedia article (intro must say it is a xã/phường/đặc khu of the NEW
province) and take its lead image (pageimage) as anh_bia. Read-only; writes du_lieu/tam_kt/wiki_anh.json."""
import json, glob, re, sys, time, urllib.request, urllib.parse, unicodedata
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
TINH = {"01": "Hà Nội", "31": "Hải Phòng", "46": "Huế", "48": "Đà Nẵng", "79": "Hồ Chí Minh", "92": "Cần Thơ"}
NFC = lambda s: unicodedata.normalize("NFC", s)
def q(**kw):
    kw.update(action="query", format="json", formatversion=2)
    u = "https://vi.wikipedia.org/w/api.php?" + urllib.parse.urlencode(kw)
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "khai-thac-du-lieu/1.0 (https://github.com/duynq15; research)"}), timeout=40))
        except Exception as e:
            print("retry", e, file=sys.stderr); time.sleep(15 * (i + 1))
d = json.load(open(sorted(glob.glob(G + "/du_lieu/ban_giao/ban_giao_*.json"))[-1], encoding="utf-8"))
dv = [u for u in d["don_vi"] if u["truong"].get("anh_bia", {}).get("gia_tri") is None]
cand = {}
for u in dv:
    ten = NFC(re.sub(r"^(Xã|Phường|Đặc khu)\s+", "", u["ten"])); loai = u["ten"].split()[0].lower()
    loai = "đặc khu" if u["ten"].startswith("Đặc khu") else loai
    tp = TINH[u["tinh_ma"]]; tps = "Thành phố Hồ Chí Minh" if u["tinh_ma"] == "79" else tp
    cand[u["ma"]] = [f"{ten} ({loai})", f"{ten}, {tp}", f"{ten}, {tps}", f"{ten} ({loai}), {tp}", f"{ten} ({loai}), {tps}", ten]
titles = sorted({t for v in cand.values() for t in v})
pages = {}
for i in range(0, len(titles), 20):
    r = q(prop="pageimages|extracts|info", inprop="url", exintro=1, explaintext=1, exchars=400, exlimit=20, piprop="original|name",
          redirects=1, titles="|".join(titles[i:i + 20]))["query"]
    alias = {x["from"]: x["to"] for x in r.get("normalized", []) + r.get("redirects", [])}
    byt = {p["title"]: p for p in r["pages"] if "missing" not in p}
    for t in titles[i:i + 20]:
        a = t
        for _ in range(3): a = alias.get(a, a)
        if a in byt: pages[t] = byt[a]
    time.sleep(2)
BAD = re.compile(r"(?i)(location|map|bản_đồ|ban_do|flag|logo|coat|huy_hieu|seal|blank|\.svg$)")
out, ko = {}, []
for u in dv:
    ten = NFC(re.sub(r"^(Xã|Phường|Đặc khu)\s+", "", u["ten"])); loai = "đặc khu" if u["ten"].startswith("Đặc khu") else u["ten"].split()[0].lower()
    rx = re.compile(rf"^{re.escape(ten)}\b[^.]{{0,120}}?là một {loai} (?:thuộc|trực thuộc) (?:thành phố|tỉnh|Thành phố) {re.escape(TINH[u['tinh_ma']])}")
    hit = next((pages[t] for t in cand[u["ma"]] if t in pages and rx.search(NFC(pages[t].get("extract", "")))), None)
    if not hit: ko.append(u["ma"]); continue
    img = hit.get("original", {}).get("source"); name = hit.get("pageimage")
    if not img or BAD.search(name or ""): ko.append(u["ma"]); continue
    sent = NFC(hit["extract"]).split("\n")[0]
    sent = sent[:sent.find(".", rx.search(NFC(hit["extract"])).end()) + 1] or sent[:300]
    out[u["ma"]] = {"ten_xa": u["ten"], "tinh_ma": u["tinh_ma"], "anh": img, "file": name, "url": hit["fullurl"], "trich": sent}
print("thiếu ảnh", len(dv), "có", len(out))
json.dump(out, open(G + "/du_lieu/tam_kt/wiki_anh.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
import collections; print(collections.Counter(v["tinh_ma"] for v in out.values()))
for v in list(out.values())[:6]: print(v)
