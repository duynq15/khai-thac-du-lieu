"""Tìm kiếm web: ưu tiên Brave Search API, lùi về DuckDuckGo/Bing khi không có khoá."""

from __future__ import annotations

import base64
import os
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from ..http import goi, html_goi

DDG = "https://lite.duckduckgo.com/lite/"
BING = "https://www.bing.com/search"
BRAVE = "https://api.search.brave.com/res/v1/web/search"

# Mỗi nguồn bị chặn thì tạm bỏ qua (giây) để không tốn thời gian thử lại
_chan_den: dict[str, float] = {}
COOLDOWN = 600.0


def khoa_brave() -> str | None:
    """Khoá Brave: ưu tiên biến môi trường, rồi tới config/chay.yaml."""
    k = (os.environ.get("BRAVE_API_KEY") or "").strip()
    if k:
        return k
    try:
        from .. import cau_hinh

        if not cau_hinh.lay_ho_so("tim_kiem", "dung_api", mac_dinh=True):
            return None
        k = (cau_hinh.lay_ho_so("tim_kiem", "brave_api_key", mac_dinh="") or "").strip()
        return k or None
    except Exception:
        return None


def _tim_brave(cau_hoi: str, so_luong: int) -> list[dict] | None:
    """Trả danh sách kết quả, hoặc None nếu không có khoá/lỗi (để lùi về scrape)."""
    key = khoa_brave()
    if not key:
        return None
    try:
        r = goi(
            BRAVE,
            params={"q": cau_hoi, "count": max(so_luong, 10)},
            headers={"X-Subscription-Token": key, "Accept": "application/json"},
            thu_lai=2,
            timeout=15.0,
        )
    except Exception:
        return None
    if r is None or r.status_code != 200:
        return None
    try:
        du = r.json()
    except ValueError:
        return None

    kq: list[dict] = []
    for it in (du.get("web") or {}).get("results") or []:
        url = it.get("url") or ""
        if url.startswith("http"):
            muc = xep_muc(url)
            if muc != "LOAI":
                kq.append({"tieu_de": it.get("title", ""), "url": url, "muc": muc})
        if len(kq) >= so_luong:
            break
    kq.sort(key=lambda x: {"A": 0, "B": 1, "C": 2}[x["muc"]])
    return kq


class NguonBiChan(Exception):
    """Nguồn tìm kiếm bị chặn (không phản hồi sau vài lần thử).

    Ném ra để luồng khai thác DỪNG SỚM thay vì retry hàng phút — giữ nguyên tiến
    độ đã lưu rồi chạy tiếp khi nguồn hồi.
    """


# Mục tiêu cấp nguồn (xem config/nguon.yaml)
MIEN_A = (".gov.vn", ".dcs.vn", ".chinhphu.vn", ".vnanet.vn")
MIEN_B = (
    "nhandan.vn", "vnanet.vn", "baochinhphu.vn", "vov.vn", "vnexpress.net", "dantri.com.vn",
    "baohaiphong.vn", "thhp.vn", "baohaiduong.vn", "hanoimoi.com.vn", "baoquangninh.vn",
    "vietnamnet.vn", "thanhnien.vn", "tuoitre.vn", "tienphong.vn", "laodong.vn",
    # Báo/đài 6 TP trực thuộc TW (tên miền sau sáp nhập báo chí 2025)
    "hanoimoi.vn", "kinhtedothi.vn", "baodanang.vn", "sggp.org.vn", "baocantho.com.vn",
    "huengaynay.vn", "hcmcpv.org.vn", "vietnamplus.vn", "baovanhoa.vn",
)
CHAN_TUYET_DOI = (
    "youtube.com", "youtu.be", "google.com", "baidu.com", "facebook.com", "threads.net",
    "instagram.com", "twitter.com", "x.com", "yahoo.co.jp", "yahoo.com", "poki.jp",
    "sftourismtips.com", "chillfont.vn", "amazon.com", "tiktok.com", "pinterest.com",
)


def xep_muc(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if any(m in host for m in CHAN_TUYET_DOI):
        return "LOAI"
    if any(host.endswith(m) for m in MIEN_A):
        return "A"
    if any(host.endswith(m) for m in MIEN_B) or re.search(r"bao[a-z0-9\-]+\.vn$", host):
        return "B"
    return "C"


def _giai_ma_ddg(url: str) -> str:
    """DDG lite bọc link trong /l/?uddg=<url thật>."""
    if "duckduckgo.com/l/" in url:
        q = parse_qs(urlparse(url).query)
        if q.get("uddg"):
            return unquote(q["uddg"][0])
    return url


def _giai_ma_bing(url: str) -> str:
    """Bing bọc link trong /ck/a?...&u=a1<base64>; giải mã về URL thật."""
    if "bing.com/ck/a" not in url:
        return url
    q = parse_qs(urlparse(url).query)
    u = (q.get("u") or [""])[0]
    if u.startswith("a1"):
        b = u[2:] + "=" * (-len(u[2:]) % 4)
        try:
            return base64.urlsafe_b64decode(b).decode("utf-8", "ignore")
        except Exception:
            return url
    return url


def _parse_ddg(html: str, so_luong: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    kq: list[dict] = []
    da_thay: set[str] = set()
    for a in soup.select("a.result-link"):
        url = _giai_ma_ddg(a.get("href") or "")
        if not url.startswith("http") or url in da_thay:
            continue
        da_thay.add(url)
        muc = xep_muc(url)
        if muc == "LOAI":
            continue
        kq.append({"tieu_de": a.get_text(strip=True), "url": url, "muc": muc})
        if len(kq) >= so_luong:
            break
    return kq


def _parse_bing(html: str, so_luong: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    kq: list[dict] = []
    da_thay: set[str] = set()
    for a in soup.select("li.b_algo h2 a, h2 a"):
        url = _giai_ma_bing((a.get("href") or "").strip())
        if not url.startswith("http") or url in da_thay:
            continue
        da_thay.add(url)
        muc = xep_muc(url)
        if muc == "LOAI":
            continue
        kq.append({"tieu_de": a.get_text(strip=True), "url": url, "muc": muc})
        if len(kq) >= so_luong:
            break
    return kq


# Các nguồn tìm kiếm, thử lần lượt (DDG trước, Bing dự phòng)
NGUON_TIM = ((DDG, _parse_ddg), (BING, _parse_bing))


def tim(cau_hoi: str, *, so_luong: int = 10) -> list[dict]:
    """Tìm kiếm: dùng Brave API nếu có khoá, không thì scrape (DDG/Bing).

    Nếu TẤT CẢ nguồn scrape đều không phản hồi thì NÉM NguonBiChan. Có phản hồi
    nhưng không kết quả thì trả [].
    """
    # 1) Brave Search API (ổn định, không bị chặn)
    kq = _tim_brave(cau_hoi, so_luong)
    if kq is not None:
        return kq

    # 2) Lùi về scrape
    gio = time.time()
    co_phan_hoi = False
    for url, parse in NGUON_TIM:
        if gio < _chan_den.get(url, 0):
            continue  # nguồn này đang trong thời gian tạm bỏ qua
        html = html_goi(url, params={"q": cau_hoi}, thu_lai=1, timeout=6.0)
        if html is None:
            _chan_den[url] = gio + COOLDOWN
            continue
        co_phan_hoi = True
        kq = [r for r in parse(html, so_luong) if r["url"].startswith("http")]
        if kq:
            kq.sort(key=lambda r: {"A": 0, "B": 1, "C": 2}[r["muc"]])
            return kq
    if not co_phan_hoi:
        raise NguonBiChan("Các nguồn tìm kiếm đều không phản hồi (nghi bị chặn)")
    return []


def tim_theo_mau(don_vi: str, tinh: str | None, *mau: str, du: int = 2) -> list[dict]:
    """Chạy các mẫu câu, gộp kết quả, DỪNG SỚM khi đã đủ nguồn chính thống A/B.

    Dừng sớm để đỡ gọi tìm kiếm nhiều lần — vừa nhanh vừa đỡ bị chặn.
    """
    gop: dict[str, dict] = {}
    for cau in mau:
        truy_van = cau.format(don_vi=don_vi, tinh=tinh or "")
        for r in tim(truy_van):
            gop.setdefault(r["url"], r)
        so_chinh_thong = sum(1 for r in gop.values() if r["muc"] in ("A", "B"))
        if so_chinh_thong >= du:
            break
    return sorted(gop.values(), key=lambda r: {"A": 0, "B": 1, "C": 2}[r["muc"]])
