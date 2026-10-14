"""Tải PDF gốc 6 NQ UBTVQH sắp xếp ĐVHC cấp xã (từ vanban.chinhphu.vn)."""
import re, sys, pathlib
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from khai_thac.http import html_goi, goi
D = pathlib.Path(G + "/du_lieu/nguon_tay/nq_2025")
NQ = {"01": ("1656", 214008), "31": ("1669", 213980), "46": ("1675", 213995),
      "48": ("1659", 213991), "79": ("1685", 214007), "92": ("1668", 213982)}
for t, (so, doc) in NQ.items():
    p = D / f"{so}.pdf"
    if p.exists(): print(t, "có", p.stat().st_size); continue
    h = html_goi(f"https://vanban.chinhphu.vn/?pageid=27160&docid={doc}")
    u = re.findall(r'href="([^"]+\.pdf)"', h or "", re.I)
    print(t, u)
    if u:
        r = goi(u[0], timeout=120)
        if r is not None and r.status_code == 200: p.write_bytes(r.content); print("  ", len(r.content))
import pdfplumber; print("pdfplumber ok")
