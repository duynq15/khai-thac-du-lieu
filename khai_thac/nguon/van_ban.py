"""Tải một trang web chính thống và rút phần văn bản chính."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..http import html_goi

_TACH_DONG = re.compile(r"\n{3,}")
_KHOANG_TRANG = re.compile(r"[ \t]{2,}")


def _dai_tu_chon(soup: BeautifulSoup) -> list[str]:
    return [
        "article", "main",
        "[role=main]", ".entry-content", ".post-content", ".article-content",
        "#content", ".content", ".detail-content", ".news-detail",
        ".MainStructure", ".ContentBanner", ".main-content", ".detail",
    ]


def rut_van_ban(html: str, *, toi_da: int = 20000) -> str:
    soup = BeautifulSoup(html, "lxml")
    for the in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "aside"]):
        the.decompose()

    ung_vien: list = []
    for chon in _dai_tu_chon(soup):
        ung_vien.extend(soup.select(chon))

    # Lấy ứng viên nhiều chữ nhất; nếu tất cả đều ít chữ thì lấy khối div lớn nhất
    ung_vien = [u for u in ung_vien if u]
    if ung_vien:
        khoi = max(ung_vien, key=lambda t: len(t.get_text(strip=True)))
    else:
        khoi = None

    if not khoi or len(khoi.get_text(strip=True)) < 300:
        ung_vien_div = soup.find_all(["div", "section"])
        if ung_vien_div:
            lon = max(ung_vien_div, key=lambda t: len(t.get_text(strip=True)))
            if len(lon.get_text(strip=True)) > len(khoi.get_text(strip=True) if khoi else ""):
                khoi = lon

    khoi = khoi or soup.body or soup
    van_ban = khoi.get_text("\n", strip=True)
    van_ban = _TACH_DONG.sub("\n\n", van_ban)
    van_ban = _KHOANG_TRANG.sub(" ", van_ban)
    return van_ban[:toi_da]


def doc_trang(url: str) -> dict | None:
    from .. import cache

    trong_cache = cache.lay(url)
    if trong_cache is not None:
        return {"url": url, "van_ban": trong_cache}

    html = html_goi(url)
    if not html:
        return None
    van_ban = rut_van_ban(html)
    if len(van_ban) < 100:
        return None
    cache.luu(url, van_ban)
    return {"url": url, "van_ban": van_ban}
