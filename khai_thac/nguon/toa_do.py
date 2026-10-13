"""Toạ độ theo tên, qua Photon (OpenStreetMap). Bắt buộc ghi nguồn ODbL."""

from __future__ import annotations

import re

from ..http import json_goi
from ..text import chuan_hoa

PHOTON = "https://photon.komoot.io/api/"

# Bounding box lãnh thổ Việt Nam (đất liền + đảo chính)
VN_LAT = (8.0, 24.5)
VN_LON = (102.0, 110.5)

_LOAI_DIEM_DAN = {"locality", "district", "city", "village", "town", "municipality", "suburb"}
_TIEN_TO = re.compile(r"^(Xã|Phường|Thị trấn|Đặc khu|Tỉnh|Thành phố|TP\.?)\s+", re.IGNORECASE)
# Tên không phải điểm dân cư: bỏ, trừ khi khớp đúng tên đơn vị
_RAC = ("trường", "đường", "chùa", "đền", "nhà", "công ty", "khách", "bệnh viện",
        "chợ", "ga ", "sân bay", "khu công nghiệp", "siêu thị", "ngân hàng",
        "ubnd", "ủy ban", "uỷ ban", "trạm", "bưu điện", "cầu ", "nút giao",
        "ring road", "tuyến", "dự án")


def trong_viet_nam(lat: float, lon: float) -> bool:
    return VN_LAT[0] <= lat <= VN_LAT[1] and VN_LON[0] <= lon <= VN_LON[1]


def _ten_goc(ten: str) -> str:
    return chuan_hoa(_TIEN_TO.sub("", ten or ""))


def tra(ten_don_vi: str, tinh: str | None = None) -> dict | None:
    """Trả {'lat', 'lon', 'ten_osm', 'anh_xa_osm', 'nguon_ma', 'nguon_url'} hoặc None."""
    # Photon hiểu sai khi query có tiền tố "Xã/Phường" và "Thành phố/Tỉnh"
    ten_sach = _TIEN_TO.sub("", ten_don_vi or "").strip() or ten_don_vi
    tinh_sach = _TIEN_TO.sub("", (tinh or "")).strip()
    cau = f"{ten_sach} {tinh_sach}".strip()
    du = json_goi(PHOTON, params={"q": cau, "limit": 8})
    if not du:
        return None

    goc = _ten_goc(ten_don_vi)
    tinh_chuan = chuan_hoa(tinh_sach)
    ung_vien: list[tuple[int, dict]] = []

    for ft in du.get("features") or []:
        p = ft.get("properties") or {}
        if (p.get("countrycode") or "").upper() != "VN":
            continue
        toa = (ft.get("geometry") or {}).get("coordinates") or []
        if len(toa) != 2:
            continue
        lon, lat = float(toa[0]), float(toa[1])
        if not trong_viet_nam(lat, lon):
            continue

        ten_osm = chuan_hoa(p.get("name") or "")
        ten_goc_osm = _ten_goc(p.get("name") or "")
        khop_dung = bool(goc) and goc == ten_goc_osm
        if not khop_dung and any(
            ten_goc_osm.startswith(chuan_hoa(r)) or chuan_hoa(r) in ten_goc_osm for r in _RAC
        ):
            continue

        diem = 0
        if khop_dung:
            diem += 6
        elif goc and goc in ten_osm:
            diem += 3
        if (p.get("type") or "") in _LOAI_DIEM_DAN:
            diem += 2
        if tinh_chuan and tinh_chuan in chuan_hoa(p.get("city") or ""):
            diem += 1

        ung_vien.append((diem, {
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "ten_osm": p.get("name"),
            "anh_xa_osm": " – ".join(
                x for x in [p.get("name"), p.get("district"), p.get("city")] if x
            ),
            "nguon_ma": "photon_osm",
            "nguon_url": "https://www.openstreetmap.org/",
            "_diem": diem,
        }))

    if not ung_vien:
        return None
    ung_vien.sort(key=lambda x: x[0], reverse=True)
    ket_qua = ung_vien[0][1]
    ket_qua.pop("_diem", None)
    return ket_qua
