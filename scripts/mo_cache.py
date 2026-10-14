"""Map cached pages to communes via known URLs (nguon_url in DB + portal roots), then regex-scan
for email / phone / working hours / chairman on each commune's OWN portal pages. Read-only."""
import sys, json, re, hashlib, os, collections
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from urllib.parse import urlparse
from khai_thac.store import Kho
k = Kho(G + "/du_lieu/khai_thac.sqlite")
d = json.load(open(sorted(__import__("glob").glob(G + "/du_lieu/ban_giao/ban_giao_*.json"))[-1], encoding="utf-8"))
cong = json.load(open(G + "/du_lieu/cong_xa.json", encoding="utf-8"))
C = G + "/du_lieu/cache_trang/"
urls = {r[0] for r in k.conn.execute("SELECT DISTINCT nguon_url FROM ket_qua WHERE nguon_url LIKE 'http%'")}
urls |= {u for u in cong.values() if isinstance(u, str)}
urls |= {u.rstrip("/") + "/" for u in list(urls)} | {u.rstrip("/") for u in list(urls)}
co = {}
for u in urls:
    p = C + hashlib.sha1(u.encode()).hexdigest() + ".txt"
    if os.path.exists(p): co[u] = p
print("url có cache", len(co), "/ file", len(os.listdir(C)))
mien = lambda u: urlparse(u).netloc.lower().removeprefix("www.")
theo_mien = collections.defaultdict(list)
for u, p in co.items(): theo_mien[mien(u)].append(p)
thieu = collections.Counter(); tim = collections.Counter(); mau = collections.defaultdict(list)
EM = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.vn\b")
GIO = re.compile(r"(?i)(thời gian làm việc|giờ làm việc)[^\n]{0,200}")
CT = re.compile(r"(?i)chủ tịch (?:ủy|uỷ) ban nhân dân[^\n:]{0,40}[:\-–]\s*(?:ông|bà)?\s*([A-ZÀ-Ỹ][^\n,.;()]{5,30})")
for u in d["don_vi"]:
    if u["tinh_ma"] not in ("01", "31", "46", "48", "79", "92"): continue
    cu = cong.get(u["ma"])
    if not isinstance(cu, str): continue
    pages = theo_mien.get(mien(cu), [])
    txt = "\n".join(open(p, encoding="utf-8").read() for p in pages)
    for tr, rx in (("email", EM), ("gio_lam_viec", GIO), ("chu_tich", CT)):
        if u["truong"].get(tr, {}).get("gia_tri") is None:
            thieu[tr] += 1
            m = rx.search(txt)
            if m: tim[tr] += 1; mau[tr].append((u["ma"], u["tinh_ma"], m.group(0)[:120]))
print("thiếu", dict(thieu)); print("tìm thấy", dict(tim))
for t, v in mau.items():
    print(t); [print("  ", x) for x in v[:15]]
print("---")
ten = {u["ma"]: u["ten"] for u in d["don_vi"]}
for ma, _, em in mau["email"]:
    for p in theo_mien.get(mien(cong[ma]), []):
        t = open(p, encoding="utf-8").read(); i = t.find(em)
        if i >= 0: print(ma, ten[ma], cong[ma], "|", t[max(0, i - 150):i + 60].replace("\n", " / ")); break
print("=== GIO")
for ma, _, g in mau["gio_lam_viec"]:
    for p in theo_mien.get(mien(cong[ma]), []):
        t = open(p, encoding="utf-8").read(); m = GIO.search(t)
        if m:
            url = next(u for u, pp in co.items() if pp == p)
            print(ma, ten[ma], url, "|", t[m.start():m.start() + 500].replace("\n", " / ")); break
