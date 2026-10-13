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

# Cổng riêng của từng xã, khoá theo MÃ đơn vị (tên trùng giữa các tỉnh: "Phường Hương
# Trà" ở cả Huế và Đà Nẵng). Dò tìm kiếm chậm và dễ bị chặn nên nhớ lại kết quả.
TEP_CACHE = DU_LIEU / "cong_xa.json"


def _doc_cache() -> dict:
    if TEP_CACHE.is_file():
        try:
            return json.loads(TEP_CACHE.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def _ghi_cache(ma: str, mien: str | None) -> None:
    cache = _doc_cache()
    cache[ma] = mien
    TEP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TEP_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def _rut(ten: str) -> str:
    goc = lam_slug(ten)                                   # xa-dong-anh
    return re.sub(r"^(xa|phuong|thi-tran|dac-khu)-", "", goc).replace("-", "")  # donganh


def _thu_mien(url: str) -> bool:
    """Kiểm tra tên miền có sống không (GET nhẹ)."""
    from ..http import goi

    try:
        r = goi(url, thu_lai=1, timeout=10.0)
    except Exception:
        return False
    return r is not None and r.status_code == 200 and "/error" not in str(r.url)


def _doan_theo_mau(don_vi: dict) -> list[str]:
    """Ứng viên từ mẫu `cong_xa.mau` của tỉnh, ví dụ 'https://{slug}.hue.gov.vn'.

    {slug} = tên bỏ tiền tố (donganh), {loai} = xa | phuong | dackhu.
    """
    from .. import cau_hinh

    loai = {"phuong": "phuong", "dac_khu": "dackhu"}.get(don_vi.get("loai"), "xa")
    mau = cau_hinh.nguon_tinh(don_vi.get("tinh_ma")).get("cong_xa", {}).get("mau") or []
    return [m.format(slug=_rut(don_vi["ten"]), loai=loai) for m in ([mau] if isinstance(mau, str) else mau)]


def mien_gov(don_vi: dict, *, mac_dinh: str | None = None) -> str | None:
    """Cổng *.gov.vn của một xã: cache theo mã → mẫu cấu hình của tỉnh → tìm kiếm."""
    ma, ten = don_vi["ma"], don_vi["ten"]
    if mac_dinh:
        _ghi_cache(ma, mac_dinh)
        return mac_dinh

    cache = _doc_cache()
    if ma in cache:
        return cache[ma]  # None = đã dò, không có cổng → khỏi dò lại

    for doan in _doan_theo_mau(don_vi):
        if _thu_mien(doan):
            _ghi_cache(ma, doan)
            return doan

    # Tìm kiếm (không dùng dấu ngoặc kép — Brave trả rác khi có ngoặc). Chỉ nhận host
    # chứa slug tên xã để không lấy nhầm cổng tỉnh/xã khác.
    rut = _rut(ten)
    tinh = don_vi.get("tinh_ten") or ""
    for r in tim(f"{ten} {tinh}".strip(), so_luong=10):
        host = (urlparse(r["url"]).netloc or "").lower()
        if host.endswith(".gov.vn") and rut and rut in host.replace("-", ""):
            _ghi_cache(ma, f"https://{host}")
            return f"https://{host}"
    _ghi_cache(ma, None)
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
