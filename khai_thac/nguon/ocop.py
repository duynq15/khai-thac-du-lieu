"""Cào danh bạ sản phẩm OCOP từ Cổng OCOP Quốc gia (ocop.gov.vn).

Cổng chỉ chạy HTTP (không HTTPS). Sản phẩm liệt kê theo danh mục:
    /san-pham/<loại>  →  /san-pham/<loại>/<slug>.html
Mỗi trang chi tiết có tên sản phẩm + mô tả (thường nêu địa danh xã/huyện/tỉnh)
và hạng sao. Dữ liệu là cào thật → đưa vào hàng CHỜ DUYỆT, kèm URL sản phẩm.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import html_goi
from ..models import KetQua, Luot
from ..store import Kho
from ..text import chuan_hoa, rut_gon

GOC = "http://ocop.gov.vn"
NGUON_MA = "ocop_gov"
NGUON_TEN = "Cổng OCOP Quốc gia"

_RE_XA = re.compile(
    r"(?:xã|phường|thị trấn)\s+([A-ZĐ][^\W\d_]+(?:\s+[A-ZĐ][^\W\d_]+){0,4})"
)
_RE_TINH = re.compile(r"(?:tỉnh|thành phố)\s+([A-ZĐ][^\W\d_]+(?:\s+[A-ZĐ][^\W\d_]+){0,4})")
_RE_SAO = re.compile(r"(\d)\s*sao", re.IGNORECASE)


def _van_ban(url: str) -> str | None:
    h = html_goi(url, thu_lai=2, timeout=25.0)
    if not h:
        return None
    soup = BeautifulSoup(h, "lxml")
    for t in soup(["script", "style", "nav", "footer", "header"]):
        t.decompose()
    return soup.get_text("\n", strip=True)


def danh_muc() -> list[str]:
    h = html_goi(GOC + "/san-pham", thu_lai=2, timeout=25.0)
    if not h:
        return []
    soup = BeautifulSoup(h, "lxml")
    ds = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.fullmatch(r"/san-pham/[a-z0-9-]+", href) and href != "/san-pham":
            ds.append(href)
    return list(dict.fromkeys(ds))


def _san_pham_trong_danh_muc(cat: str, toi_da: int, so_trang: int = 1) -> list[str]:
    ds: list[str] = []
    for p in range(1, so_trang + 1):
        h = html_goi(f"{GOC}{cat}?page={p}", thu_lai=2, timeout=25.0)
        if not h:
            break
        soup = BeautifulSoup(h, "lxml")
        truoc = len(ds)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.match(r"/san-pham/[a-z0-9-]+/[a-z0-9-]+\.html$", href):
                ds.append(urljoin(GOC, href))
        ds = list(dict.fromkeys(ds))
        if len(ds) == truoc:      # trang không thêm sản phẩm mới -> hết
            break
        if toi_da and len(ds) >= toi_da:
            break
    return ds[:toi_da] if toi_da else ds


def _chi_tiet(url: str) -> dict | None:
    h = html_goi(url, thu_lai=2, timeout=25.0)
    if not h:
        return None
    soup = BeautifulSoup(h, "lxml")
    tieu_de = ""
    # Tên sản phẩm: thẻ <a> trỏ đúng sản phẩm này (thường in HOA), hoặc <h1>
    slug = url.rstrip("/").split("/")[-1]

    def _la_ten(tag):
        return (tag.name == "a" and slug in (tag.get("href") or "")
                and len(tag.get_text(strip=True)) > 4)

    a = soup.find(_la_ten)
    if a:
        tieu_de = a.get_text(strip=True)
    if not tieu_de:
        h1 = soup.find(["h1", "h2"])
        tieu_de = h1.get_text(strip=True) if h1 else ""
    if not tieu_de and soup.title and soup.title.string:
        tieu_de = soup.title.string.split("|")[0].strip()
    for t in soup(["script", "style", "nav", "footer", "header"]):
        t.decompose()
    van_ban = soup.get_text("\n", strip=True)
    xa = _RE_XA.search(van_ban)
    tinh = _RE_TINH.search(van_ban)
    sao = _RE_SAO.search(van_ban)
    return {
        "url": url,
        "ten": tieu_de,
        "xa": xa.group(1).strip() if xa else None,
        "tinh": tinh.group(1).strip() if tinh else None,
        "sao": int(sao.group(1)) if sao else None,
        "mo_ta": rut_gon(van_ban, 300),
    }


def _khop(kho: Kho, tinh_ma: str | None) -> dict[str, str]:
    bd: dict[str, str] = dict(kho.ban_do_ten_cu(tinh_ma))  # tên cũ -> xã mới
    for row in kho.tim_don_vi(tinh_ma=tinh_ma, cap="xa"):
        ten = row["ten"]
        bd[chuan_hoa(ten)] = row["ma"]
        bd[chuan_hoa(re.sub(r"^(Xã|Phường|Đặc khu|Thị trấn)\s+", "", ten))] = row["ma"]
    return bd


def nap(kho: Kho, *, tinh_ma: str | None = None, toi_da_moi_danh_muc: int = 200,
        so_trang_moi_danh_muc: int = 15, gioi_han: int | None = None) -> dict:
    khop = _khop(kho, tinh_ma)
    ma2ten = {r["ma"]: r["ten"] for r in kho.tim_don_vi(cap="xa")}

    luot = Luot(ma=f"ocop-{__import__('datetime').datetime.now():%Y%m%d-%H%M%S}",
                pham_vi=f"tinh {tinh_ma}" if tinh_ma else "toan_quoc", nhom_du_lieu="ocop",
                bat_dau=__import__("datetime").datetime.now().isoformat(timespec="seconds"))
    kho.ghi_luot(luot)

    # Gom sản phẩm theo xã
    gom: dict[str, list[dict]] = {}
    so_sp = 0
    da_xet = 0
    for cat in danh_muc():
        for url in _san_pham_trong_danh_muc(cat, toi_da_moi_danh_muc, so_trang_moi_danh_muc):
            if gioi_han and da_xet >= gioi_han:
                break
            da_xet += 1
            sp = _chi_tiet(url)
            if not sp or not sp["xa"]:
                continue
            ma = khop.get(chuan_hoa(sp["xa"])) or khop.get(chuan_hoa("Xã " + sp["xa"])) or \
                khop.get(chuan_hoa("Phường " + sp["xa"]))
            if not ma:
                continue
            nhan = sp["ten"]
            if sp["sao"]:
                nhan = f"{nhan} ({sp['sao']} sao)"
            gom.setdefault(ma, []).append({"ten": nhan, "url": sp["url"]})

    ket: list[KetQua] = []
    for ma, ds in gom.items():
        ket.append(KetQua(
            don_vi_ma=ma, don_vi_ten=ma2ten.get(ma, ""), cap="xa",
            nhom="kinh_te_van_hoa", truong="ocop",
            gia_tri=[x["ten"] for x in ds], kieu="danh_sach",
            nguon_ma=NGUON_MA, nguon_ten=NGUON_TEN, nguon_url=ds[0]["url"],
            nguon_muc="A", trich_doan=rut_gon(ds[0]["url"], 200),
            diem_tin=70, trang_thai="cho_duyet",
        ))
        so_sp += len(ds)

    kho.ghi_ket_qua(ket, luot.ma)
    from datetime import datetime

    luot.ket_thuc = datetime.now().isoformat(timespec="seconds")
    luot.so_ket_qua = len(ket)
    kho.ghi_luot(luot)
    return {"xem": da_xet, "san_pham": so_sp, "xã": len(ket)}
