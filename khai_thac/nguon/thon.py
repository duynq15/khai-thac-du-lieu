"""Gom tên thôn, tổ dân phố của một xã từ chính trang riêng của xã.

Lưu ý: nhà nước chưa có API/danh mục thôn công khai (các API chỉ tới cấp xã).
Nên phải đọc trang xã — độ phủ tuỳ từng xã, có nơi không đăng. Vì vậy kết quả
luôn ở dạng ĐỀ XUẤT để cán bộ duyệt, và có đường nhập tay/Excel cho nơi thiếu.
"""

from __future__ import annotations

import re
from collections import Counter

from ..text import chuan_hoa
from . import trang_xa

# "thôn X", "tổ dân phố X", "khu phố X" — bắt tên ngay sau từ khoá
_TEN = re.compile(
    r"(?:thôn|tổ dân phố|tổ DP|khu phố|ấp|bản)\s+([^\W\d_][\w]*(?:\s+[^\W\d_][\w]*){0,3})",
    re.UNICODE,
)
# "các thôn: A, B, C" / "gồm các thôn A; B"
_DANH_SACH = re.compile(
    r"(?:các\s+)?(?:thôn|tổ dân phố|khu phố)\s*(?:gồm|:)??\s*([^\n.;]{8,400})",
    re.IGNORECASE,
)

# Từ không phải tên thôn (đứng sau "thôn" trong cụm như "trưởng thôn", "nhà văn hoá thôn")
_TU_LOAI = {
    "truong", "pho", "nha", "van", "hoa", "can", "bo", "doan", "hoi", "chi", "thanh",
    "nien", "nong", "dan", "cong", "an", "quan", "su", "y", "te", "giao", "duc", "khuyen",
    "hoc", "to", "chuc", "bi", "thu", "chu", "tich", "uy", "ban", "mat", "tran", "phu",
    "nu", "cuu", "chien", "binh", "nguoi", "cao", "tuoi", "cua", "va", "cac", "mot",
    "tren", "duoi", "ngoai", "trong", "khac", "moi", "nay", "do", "da", "se",
    "phan", "hop", "tac", "xa", "gcn", "dkkd", "bao", "tin", "lien", "tp", "thi",
    "tran", "xa", "huyen", "tinh", "thi", "tran", "khu", "vuc", "diem", "tuyen",
}


def _ten_hop_le(chuoi: str) -> str | None:
    """Giữ các chữ đầu viết hoa liền nhau, bỏ từ loại, giới hạn 3 chữ."""
    ten: list[str] = []
    for w in chuoi.split():
        w = w.strip(".,;:()")
        if not w or not w[:1].isupper():
            break
        chuan = chuan_hoa(w)
        # Bỏ từ loại, từ viết tắt (TP, GCN, ĐKKD) và từ quá ngắn
        if chuan in _TU_LOAI or len(w) < 2 or (w.isupper() and len(w) <= 4):
            break
        ten.append(w)
        if len(ten) >= 3:
            break
    if not ten:
        return None
    ten_chuoi = " ".join(ten).strip()
    if len(ten_chuoi) < 2 or chuan_hoa(ten_chuoi) in _TU_LOAI:
        return None
    return ten_chuoi


def boc_ten_thon(van_ban: str) -> Counter:
    """Trả Counter tên thôn ứng viên trong một đoạn văn bản."""
    dem: Counter = Counter()

    for m in _TEN.finditer(van_ban):
        ten = _ten_hop_le(m.group(1))
        if ten:
            dem[ten] += 1

    for m in _DANH_SACH.finditer(van_ban):
        for phan in re.split(r"[,;/]|\s+và\s+", m.group(1)):
            ten = _ten_hop_le(phan.strip(" \t-–"))
            if ten:
                dem[ten] += 1

    return dem


def thu_thap(xa: dict, *, so_trang: int = 3, mien: str | None = None) -> list[dict]:
    """Gom thôn của một xã. Trả [{'ten', 'so_lan', 'nguon_url'}], xếp theo số lần."""
    ten = xa["ten"]
    tinh = xa.get("tinh_ten")
    mien = mien or trang_xa.mien_gov(ten, tinh)
    if not mien:
        return []

    dem: Counter = Counter()
    nguon: dict[str, str] = {}
    for url, vb in trang_xa.gom_trang(mien, gioi_han=so_trang):
        for ten_thon, so_lan in boc_ten_thon(vb).items():
            dem[ten_thon] += so_lan
            nguon.setdefault(ten_thon, url)

    return [
        {"ten": ten_thon, "so_lan": so_lan, "nguon_url": nguon.get(ten_thon), "nguon_ten": mien}
        for ten_thon, so_lan in dem.most_common()
    ]
