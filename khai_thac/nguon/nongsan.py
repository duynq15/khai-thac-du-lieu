"""Cào Sàn nông sản Hải Phòng (nongsan.haiphong.gov.vn) — có địa chỉ theo xã.

Trang sản phẩm ghi "Địa chỉ: …, Xã <tên> - Thành phố Hải Phòng" → khớp được xã mới,
kèm tên sản phẩm + chủ thể. Dữ liệu cào thật → đưa vào CHỜ DUYỆT, lưu URL trang.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import html_goi
from ..models import KetQua, Luot
from ..store import Kho

GOC = "https://nongsan.haiphong.gov.vn"
NGUON_MA = "nongsan_haiphong"
NGUON_TEN = "Sàn nông sản Hải Phòng"

_RE_DIA_CHI = re.compile(
    r"(?:Xã|Phường|Thị trấn)\s+([A-ZĐ][^\W\d_]+(?:\s+[A-ZĐ][^\W\d_]+){0,4})", re.UNICODE
)
_RE_CHU_THE = re.compile(
    r"(?:Nhà cung cấp|Tên cơ sở|Chủ thể|Cơ sở sản xuất)[:\s]*\n?([^\n]{3,70})"
)


def danh_muc() -> list[str]:
    h = html_goi(GOC + "/danh-muc-san-pham/san-pham-ocop", thu_lai=2, timeout=25.0)
    if not h:
        return []
    soup = BeautifulSoup(h, "lxml")
    ds = []
    for a in soup.find_all("a", href=True):
        if "/danh-muc-san-pham/" in a["href"] and a["href"] != "/danh-muc-san-pham":
            ds.append(urljoin(GOC, a["href"]))
    return list(dict.fromkeys(ds))


def san_pham(cat: str, toi_da: int = 200) -> list[str]:
    h = html_goi(cat, thu_lai=2, timeout=25.0)
    if not h:
        return []
    soup = BeautifulSoup(h, "lxml")
    ds = []
    for a in soup.find_all("a", href=True):
        if "/san-pham/" in a["href"] and "/danh-muc-san-pham/" not in a["href"]:
            ds.append(urljoin(GOC, a["href"]))
    return list(dict.fromkeys(ds))[:toi_da]


def chi_tiet(url: str) -> dict | None:
    h = html_goi(url, thu_lai=2, timeout=25.0)
    if not h:
        return None
    soup = BeautifulSoup(h, "lxml")

    # Tên sản phẩm: <title> có dấu (dạng "Chổi chít Lý Đỏ - Dữ liệu …")
    ten = ""
    if soup.title and soup.title.string:
        ten = soup.title.string.split(" - ")[0].strip()
    if not ten:
        ten = url.rstrip("/").split("/")[-1].replace("-", " ")

    for t in soup(["script", "style", "nav", "footer", "header"]):
        t.decompose()
    vb = soup.get_text("\n", strip=True)

    # Xã: chỉ lấy trong dòng "Địa chỉ:" (tránh nhặt nhầm footer)
    m = re.search(r"Địa chỉ[:\s]*([^\n]{5,160})", vb)
    xa = _RE_DIA_CHI.search(m.group(1)) if m else None
    ct = _RE_CHU_THE.search(vb)
    return {
        "url": url,
        "ten": ten.strip()[:120],
        "xa": xa.group(1).strip() if xa else None,
        "chu_the": ct.group(1).strip()[:60] if ct else None,
    }


def nap(kho: Kho, *, tinh_ma: str | None = "31", gioi_han: int | None = None) -> dict:
    khop = kho.ban_do_ma(tinh_ma)
    ma2ten = {r["ma"]: r["ten"] for r in kho.tim_don_vi(cap="xa", tinh_ma=tinh_ma)}

    luot = Luot(ma=f"nongsan-{__import__('datetime').datetime.now():%Y%m%d-%H%M%S}",
                pham_vi=f"tinh {tinh_ma}" if tinh_ma else "toan_quoc", nhom_du_lieu="ocop",
                bat_dau=__import__("datetime").datetime.now().isoformat(timespec="seconds"))
    kho.ghi_luot(luot)

    gom: dict[str, list[dict]] = {}
    da_xet = 0
    from datetime import datetime

    def _ghi() -> None:
        ket = [KetQua(
            don_vi_ma=ma, don_vi_ten=ma2ten.get(ma, ""), cap="xa",
            nhom="kinh_te_van_hoa", truong="ocop", gia_tri=[x["ten"] for x in ds],
            kieu="danh_sach", nguon_ma=NGUON_MA, nguon_ten=NGUON_TEN, nguon_url=ds[0]["url"],
            nguon_muc="A", trich_doan=ds[0]["url"], diem_tin=75, trang_thai="cho_duyet",
        ) for ma, ds in gom.items()]
        if ket:
            kho.ghi_ket_qua(ket, luot.ma)

    for cat in danh_muc():
        for url in san_pham(cat):
            if gioi_han and da_xet >= gioi_han:
                break
            da_xet += 1
            sp = chi_tiet(url)
            if not sp or not sp["xa"]:
                continue
            ma = Kho.tim_ma_xa(khop, sp["xa"])
            if not ma:
                continue
            nhan = sp["ten"]
            if sp["chu_the"]:
                nhan = f"{nhan} ({sp['chu_the']})"
            gom.setdefault(ma, []).append({"ten": nhan, "url": sp["url"]})
            print(f"  [{da_xet}] {sp['xa']} · {sp['ten'][:45]}", flush=True)
        _ghi()   # ghi ngay sau mỗi danh mục — dừng giữa chừng không mất

    _ghi()
    luot.ket_thuc = datetime.now().isoformat(timespec="seconds")
    luot.so_ket_qua = len(gom)
    kho.ghi_luot(luot)
    return {"xem": da_xet, "san_pham": sum(len(v) for v in gom.values()), "xã": len(gom)}
