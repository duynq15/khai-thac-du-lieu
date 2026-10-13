"""Đọc bài Wikipedia tiếng Việt (nguồn mở, dùng bóc giới thiệu và lịch sử)."""

from __future__ import annotations

from ..http import json_goi

API = "https://vi.wikipedia.org/w/api.php"


def _bai(tua_de: str) -> dict | None:
    du = json_goi(
        API,
        params={
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "format": "json",
            "redirects": 1,
            "titles": tua_de,
        },
    )
    if not du:
        return None
    trang = (du.get("query") or {}).get("pages") or {}
    if not trang:
        return None
    mot = next(iter(trang.values()))
    noi = mot.get("extract") or ""
    if not noi.strip():
        return None
    return {"title": mot.get("title"), "extract": noi}


def doc_bai(ten_don_vi: str, tinh: str | None = None) -> dict | None:
    """Thử vài cách gọi tên để tránh trang định hướng.

    Trả {'title', 'extract', 'url', 'nguon_ma'} hoặc None.
    """
    ung_vien = [f"{ten_don_vi}, {tinh}"] if tinh else []
    ung_vien += [ten_don_vi, ten_don_vi.replace("Phường ", ""), ten_don_vi.replace("Xã ", "")]
    for tua in dict.fromkeys(ung_vien):
        bai = _bai(tua)
        if not bai:
            continue
        # Trang định hướng: extract rất ngắn và chứa "có thể là"
        if "có thể là" in bai["extract"][:200].lower():
            continue
        return {
            "title": bai["title"],
            "extract": bai["extract"],
            "url": "https://vi.wikipedia.org/wiki/" + (bai["title"] or tua).replace(" ", "_"),
            "nguon_ma": "wikipedia_vi",
        }
    return None
