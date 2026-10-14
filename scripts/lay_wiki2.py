"""Tải phần mở đầu bài Wikipedia GỘP 20 tiêu đề/lượt (exintro) — nhanh hơn gọi từng bài.
Ghi vào wiki_cache.json cùng định dạng doc_bai; không ghi DB."""
import sys, json, os
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from khai_thac.store import Kho
from khai_thac.http import json_goi
from khai_thac.quy_trinh import _dung_cap
F = G + "/du_lieu/tam_kt/wiki_cache.json"
cache = json.load(open(F)) if os.path.exists(F) else {}
k = Kho(G + "/du_lieu/khai_thac.sqlite")
co = {r[0] for r in k.conn.execute("SELECT DISTINCT don_vi_ma FROM ket_qua WHERE truong='gioi_thieu' AND trang_thai='dat'")}
ten_tinh = {r[0]: r[1] for r in k.conn.execute("SELECT ma, ten FROM don_vi")}
xa = [dict(r) for t in ("01", "31", "46", "48", "79", "92") for r in k.tim_don_vi(tinh_ma=t, cap="xa")]
can = [x for x in xa if x["ma"] not in co and x["ma"] not in cache]
print("cần", len(can), flush=True)

def ung_vien(x):
    t, tinh = x["ten"], ten_tinh.get(x.get("tinh_ma")) or ""
    ngan = tinh.replace("Thành phố ", "")
    return list(dict.fromkeys([f"{t}, {ngan}", f"{t}, {tinh}", f"{t} ({ngan})", t]))

def tra(tieu_de):
    """{tiêu đề hỏi: (tiêu đề thật, đoạn mở đầu)}"""
    kq = {}
    for i in range(0, len(tieu_de), 20):
        lo = tieu_de[i:i + 20]
        du = json_goi("https://vi.wikipedia.org/w/api.php", params={
            "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "exlimit": 20,
            "redirects": 1, "format": "json", "titles": "|".join(lo)}) or {}
        q = du.get("query") or {}
        doi = {m["from"]: m["to"] for m in q.get("normalized", []) + q.get("redirects", [])}
        trang = {p.get("title"): p.get("extract") or "" for p in (q.get("pages") or {}).values()}
        for t in lo:
            that = doi.get(doi.get(t, t), doi.get(t, t))
            if trang.get(that, "").strip():
                kq[t] = (that, trang[that])
    return kq

tat_ca = [t for x in can for t in ung_vien(x)]
bai = tra(tat_ca)
for x in can:
    cache[x["ma"]] = None
    for t in ung_vien(x):
        if t in bai and "có thể là" not in bai[t][1][:200].lower() and _dung_cap(bai[t][0], x.get("loai")):
            cache[x["ma"]] = {"title": bai[t][0], "extract": bai[t][1], "nguon_ma": "wikipedia_vi",
                              "url": "https://vi.wikipedia.org/wiki/" + bai[t][0].replace(" ", "_")}
            break
json.dump(cache, open(F, "w"), ensure_ascii=False)
print("có bài", sum(1 for v in cache.values() if v), "/", len(cache))
