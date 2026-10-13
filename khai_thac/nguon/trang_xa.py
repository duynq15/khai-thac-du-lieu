"""Đọc trang riêng của một xã (thường dựng bằng JavaScript)."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from ..store import DU_LIEU
from ..text import slug as lam_slug
from . import trinh_duyet, van_ban
from .tim_kiem import tim

# Đường dẫn hay có danh sách cán bộ / thôn trên trang xã
DUONG_DAN_HUU_ICH = ("/", "/thong-bao", "/tin-tuc", "/doi-song-xa-hoi", "/van-hoa-xa-hoi")

# Cache tên miền đã dò được: {tên đơn vị: tên miền}. Dò tìm kiếm chậm và dễ bị
# chặn nên nhớ lại để lần sau khỏi gọi.
TEP_CACHE = DU_LIEU / "mien_gov.json"


def _doc_cache() -> dict:
    if TEP_CACHE.is_file():
        try:
            return json.loads(TEP_CACHE.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def _ghi_cache(ten: str, mien: str) -> None:
    cache = _doc_cache()
    cache[ten] = mien
    TEP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TEP_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _rut(ten: str) -> str:
    goc = lam_slug(ten)                                   # xa-dong-anh
    return re.sub(r"^(xa|phuong|thi-tran|dac-khu)-", "", goc).replace("-", "")  # donganh


def mien_tu_ket_qua(ten: str, ket_qua: list[dict]) -> str | None:
    """Suy tên miền gov của đơn vị từ danh sách kết quả tìm kiếm có sẵn."""
    rut = _rut(ten)
    for r in ket_qua:
        host = (urlparse(r["url"]).netloc or "").lower()
        if host.endswith(".gov.vn") and rut and rut in host.replace("-", ""):
            return f"https://{host}"
    return None


def _tinh_slug(tinh: str | None) -> str:
    """'Thành phố Hải Phòng' -> 'haiphong'."""
    s = lam_slug(tinh or "")
    return re.sub(r"^(thanh-pho|tinh|tp)-", "", s).replace("-", "")


def _thu_mien(url: str) -> bool:
    """Kiểm tra tên miền có sống không (GET nhẹ)."""
    from ..http import goi

    try:
        r = goi(url, thu_lai=1, timeout=10.0)
    except Exception:
        return False
    return r is not None and r.status_code == 200


def mien_gov(ten: str, tinh: str | None = None, *, mac_dinh: str | None = None,
             ket_qua: list[dict] | None = None) -> str | None:
    """Dò tên miền *.gov.vn của đơn vị. Đọc cache trước; rồi ĐOÁN theo mẫu
    <tên-xã>.<tỉnh>.gov.vn; cuối cùng mới tìm kiếm."""
    if mac_dinh:
        _ghi_cache(ten, mac_dinh)
        return mac_dinh

    cache = _doc_cache()
    if cache.get(ten):
        return cache[ten]

    # 1) Đoán theo mẫu (nhanh, chắc): donganh.hanoi.gov.vn, thanhdong.haiphong.gov.vn
    rut = _rut(ten)
    tinh_slug = _tinh_slug(tinh)
    if rut and tinh_slug:
        doan = f"https://{rut}.{tinh_slug}.gov.vn"
        if _thu_mien(doan):
            _ghi_cache(ten, doan)
            return doan

    # 2) Từ kết quả tìm kiếm có sẵn
    if ket_qua:
        mien = mien_tu_ket_qua(ten, ket_qua)
        if mien:
            _ghi_cache(ten, mien)
            return mien

    # 3) Tìm kiếm (không dùng dấu ngoặc kép — Brave trả rác khi có ngoặc)
    truy_van = f"{ten} {tinh}".strip() if tinh else ten
    for r in tim(truy_van, so_luong=10):
        host = (urlparse(r["url"]).netloc or "").lower()
        if host.endswith(".gov.vn") and rut and rut in host.replace("-", ""):
            mien = f"https://{host}"
            _ghi_cache(ten, mien)
            return mien
    return None


def doc(url: str) -> str | None:
    """Tải một trang: cache → HTTP tĩnh (nhanh) → trình duyệt chỉ khi trang SPA ít chữ."""
    from .. import cache

    trong_cache = cache.lay(url)
    if trong_cache is not None:
        return trong_cache

    # 1) HTTP tĩnh trước — nhanh hơn nhiều so với mở trình duyệt
    t = van_ban.doc_trang(url)
    chu = t["van_ban"] if t else None

    # 2) Quá ít chữ (SPA/JS nặng) mới mở trình duyệt
    if (not chu or len(chu) < 600) and trinh_duyet.san_sang():
        t2 = trinh_duyet.doc_trang(url)
        if t2 and len(t2["van_ban"]) > len(chu or ""):
            chu = t2["van_ban"]

    if chu:
        cache.luu(url, chu)
    return chu


def gom_trang(mien: str | None, duong_dan: tuple[str, ...] = DUONG_DAN_HUU_ICH,
              gioi_han: int = 3) -> list[tuple[str, str]]:
    """Tải vài trang của một xã, trả [(url, văn bản)]."""
    if not mien:
        return []
    ds: list[tuple[str, str]] = []
    for duong in duong_dan:
        if len(ds) >= gioi_han:
            break
        url = mien.rstrip("/") + duong
        van_ban_trang = doc(url)
        if van_ban_trang and len(van_ban_trang) >= 200:
            ds.append((url, van_ban_trang))
    return ds


TEP_CHUYEN_MUC = DU_LIEU / "chuyen_muc.json"

# Từ khoá nhận diện trang chuyên mục nội dung trên trang xã
_TU_KHOA = (
    "di tich", "di tích", "van hoa", "văn hoá", "văn hóa", "lich su", "lịch sử",
    "le hoi", "lễ hội", "truyen thong", "truyền thống", "danh nhan", "danh nhân",
    "lang nghe", "làng nghề", "khoa bang", "khoa bảng", "gioi thieu", "giới thiệu",
    "tin tuc", "tin tức", "van nghe", "du lich", "du lịch",
)


def _doc_cache_cm() -> dict:
    if TEP_CHUYEN_MUC.is_file():
        try:
            return json.loads(TEP_CHUYEN_MUC.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def chuyen_muc(mien: str | None, *, toi_da: int = 6) -> list[str]:
    """Dò các trang chuyên mục (di tích, lễ hội, lịch sử…) trên trang xã.

    Đọc menu của trang chủ rồi lọc liên kết cùng tên miền khớp từ khoá. Kết quả
    được nhớ vào du_lieu/chuyen_muc.json để khỏi dò lại.
    """
    if not mien:
        return []
    cache = _doc_cache_cm()
    if mien in cache:
        return cache[mien]
    if not trinh_duyet.san_sang():
        return []

    from urllib.parse import urljoin

    from bs4 import BeautifulSoup

    html = trinh_duyet.lay_html(mien)
    ket: list[str] = []
    if html:
        soup = BeautifulSoup(html, "lxml")
        host = urlparse(mien).netloc
        da = set()
        for a in soup.find_all("a", href=True):
            chu = (a.get_text() or "").strip().lower()
            href = a["href"]
            if not any(k in chu or k.replace(" ", "-") in href.lower() for k in _TU_KHOA):
                continue
            u = urljoin(mien, href)
            if urlparse(u).netloc != host or u in da:
                continue
            da.add(u)
            ket.append(u)
            if len(ket) >= toi_da:
                break
    cache[mien] = ket
    TEP_CHUYEN_MUC.parent.mkdir(parents=True, exist_ok=True)
    TEP_CHUYEN_MUC.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return ket
