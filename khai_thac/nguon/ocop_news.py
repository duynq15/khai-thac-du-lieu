"""Bóc sản phẩm OCOP từ TIN CÔNG BỐ / Quyết định công nhận (nhiều địa phương).

Nhiều TP không có "sàn nông sản" dạng danh mục; sản phẩm OCOP được nêu trong
bài công bố theo mẫu: "Tên sản phẩm của Chủ thể (phường/xã …)". Module này đọc
các bài đó, bóc (tên SP, chủ thể, xã) rồi khớp xã mới.

Nguồn là tin/báo chính thống → mức B, đưa vào CHỜ DUYỆT.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..http import html_goi
from ..models import KetQua, Luot
from ..store import Kho
from ..text import chuan_hoa, rut_gon

NGUON_MA = "ocop_news"
NGUON_TEN = "Tin công bố OCOP"

# "Tên sản phẩm của Chủ thể (phường/xã …)" — bắt cả "của" và dấu "-"
_MAU = re.compile(
    r"([^\n;•\-]{4,90}?)\s+(?:của|do)\s+([^\n(]{3,80}?)\s*\(([^)]*(?:xã|phường|thị trấn)[^)]*)\)",
    re.IGNORECASE,
)
_RE_XA = re.compile(r"(?:xã|phường|thị trấn)\s+([A-ZĐ][^\W\d_]+(?:\s+[A-ZĐ][^\W\d_]+){0,4})")


def boc(text: str) -> list[dict]:
    ket = []
    for m in _MAU.finditer(text):
        ten = re.sub(r"\s+", " ", m.group(1)).strip(" -,.;")
        chu_the = re.sub(r"\s+", " ", m.group(2)).strip(" -,.;")
        xa = _RE_XA.search(m.group(3))
        if ten and xa:
            ket.append({"ten": ten, "chu_the": chu_the, "xa": xa.group(1).strip()})
    return ket


def _khop(kho: Kho, tinh_ma: str | None) -> dict[str, str]:
    bd = dict(kho.ban_do_ten_cu(tinh_ma))
    for row in kho.tim_don_vi(tinh_ma=tinh_ma, cap="xa"):
        ten = row["ten"]
        bd[chuan_hoa(ten)] = row["ma"]
        bd[chuan_hoa(re.sub(r"^(Xã|Phường|Đặc khu|Thị trấn)\s+", "", ten))] = row["ma"]
    return bd


def nap_url(kho: Kho, url: str, *, tinh_ma: str | None = None) -> dict:
    h = html_goi(url, thu_lai=2, timeout=30.0)
    if not h:
        return {"url": url, "san_pham": 0, "xã": 0}
    soup = BeautifulSoup(h, "lxml")
    for t in soup(["script", "style", "nav", "footer", "header"]):
        t.decompose()
    text = soup.get_text("\n", strip=True)

    khop = _khop(kho, tinh_ma)
    ma2ten = {r["ma"]: r["ten"] for r in kho.tim_don_vi(cap="xa")}
    gom: dict[str, list[str]] = {}
    for sp in boc(text):
        ma = (khop.get(chuan_hoa(sp["xa"])) or khop.get(chuan_hoa("Xã " + sp["xa"]))
              or khop.get(chuan_hoa("Phường " + sp["xa"])))
        if ma:
            gom.setdefault(ma, []).append(f"{sp['ten']} ({sp['chu_the']})")

    luot = Luot(ma=f"ocop-news-{__import__('datetime').datetime.now():%Y%m%d-%H%M%S}",
                pham_vi=url, nhom_du_lieu="ocop",
                bat_dau=__import__("datetime").datetime.now().isoformat(timespec="seconds"))
    kho.ghi_luot(luot)
    ket = [KetQua(don_vi_ma=ma, don_vi_ten=ma2ten.get(ma, ""), cap="xa",
                  nhom="kinh_te_van_hoa", truong="ocop", gia_tri=ds, kieu="danh_sach",
                  nguon_ma=NGUON_MA, nguon_ten=NGUON_TEN, nguon_url=url, nguon_muc="B",
                  trich_doan=rut_gon(url, 200), diem_tin=60, trang_thai="cho_duyet")
           for ma, ds in gom.items()]
    kho.ghi_ket_qua(ket, luot.ma)
    return {"url": url, "san_pham": sum(len(v) for v in gom.values()), "xã": len(gom)}
