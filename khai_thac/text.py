"""Tiện ích văn bản tiếng Việt."""

from __future__ import annotations

import re
import unicodedata

_KHOANG_TRANG = re.compile(r"\s+")
_KHONG_PHAI_CHU = re.compile(r"[^a-z0-9\s-]")
_SO_KY_TU_CO_DINH = re.compile(r"[^0-9]")

def bo_dau(chu: str) -> str:
    """Bỏ dấu tiếng Việt: 'Xã Đông Anh' -> 'Xa Dong Anh'."""
    chu = str(chu if chu is not None else "").replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", chu)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def chuan_hoa(chu: str) -> str:
    """Chuẩn hoá để so trùng: bỏ dấu, thường, gọn khoảng trắng, bỏ ký tự lạ."""
    chu = unicodedata.normalize("NFC", str(chu if chu is not None else ""))
    chu = bo_dau(chu.lower())
    chu = _KHOANG_TRANG.sub(" ", chu)
    return _KHONG_PHAI_CHU.sub("", chu).strip()


def bam_chuoi(chu: str) -> str:
    """Khoá so trùng đã chuẩn hoá."""
    return _KHOANG_TRANG.sub(" ", chuan_hoa(chu)).strip()


def slug(chu: str) -> str:
    """'Xã Đông Anh' -> 'xa-dong-anh'."""
    chu = chuan_hoa(chu)
    return _KHOANG_TRANG.sub("-", chu.replace(" ", "-")).strip("-")


def chi_so(chu: str) -> str:
    """Giữ lại chỉ chữ số: 'Mã 00454' -> '00454'."""
    return _SO_KY_TU_CO_DINH.sub("", chu or "")


def rut_gon(chu: str, n: int = 280) -> str:
    chu = _KHOANG_TRANG.sub(" ", (chu or "").strip())
    return chu if len(chu) <= n else chu[: n - 1].rstrip() + "…"


def la_chu_hoa_dau(chu: str) -> bool:
    return bool(chu) and chu[0].isupper()


def tach_danh_sach(chu: str) -> list[str]:
    """Tách chuỗi 'A; B, C và D' thành ['A', 'B', 'C', 'D']."""
    phan = re.split(r"[;\n]|,\s+|\s+và\s+", chu or "")
    return [p.strip(" \t\r\n.-–—") for p in phan if p and p.strip(" \t\r\n.-–—")]
