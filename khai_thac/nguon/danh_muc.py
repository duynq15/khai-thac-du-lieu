"""Nguồn danh mục đơn vị hành chính (lớp 1 — độ tin cao).

Gom từ hai nguồn mở độc lập rồi đối chiếu tên với nhau, nên một nguồn sai vẫn
phát hiện được:

  * provinces.open-api.vn/api/v2  — danh sách 34 tỉnh + 3.321 xã/phường (mã BNV)
  * 34tinhthanh.com               — danh sách đơn vị cũ hợp thành (NQ 202/2025)
  * tinhthanhpho.com              — diện tích, dân số, mã bưu chính, toạ độ tâm tỉnh
"""

from __future__ import annotations

from ..http import json_goi
from ..models import DonVi
from ..text import bam_chuoi, chi_so

OPEN_API = "https://provinces.open-api.vn/api/v2"
TINHTHANH34 = "https://34tinhthanh.com/api"
TINHTHANHPHO = "https://www.tinhthanhpho.com/api/v1"

CAN_CU_MAC_DINH = "Nghị quyết 202/2025/QH15"
NGAY_HIEU_LUC = "2025-07-01"


def _loai_xa(division_type: str) -> str:
    d = (division_type or "").lower()
    if "phường" in d:
        return "phuong"
    if "đặc khu" in d:
        return "dac_khu"
    return "xa"


def nap_tinh() -> list[DonVi]:
    """34 tỉnh/thành, kèm số liệu và lịch sử hợp nhất từ tinhthanhpho."""
    ds: list[DonVi] = []
    tho = json_goi(f"{OPEN_API}/p/") or []
    them = {str(t.get("code")): t for t in (json_goi(f"{TINHTHANHPHO}/new-provinces?limit=100") or {}).get("data", [])}

    for t in tho:
        ma_int = t.get("code")
        ma = f"{int(ma_int):02d}"
        ten = t.get("name") or ""
        pho = them.get(ma) or {}
        dt = (t.get("division_type") or "")
        loai = "thanh_pho" if "thành phố" in dt else "tinh"
        don = DonVi(
            ma=ma,
            ten=ten,
            loai=loai,
            codename=t.get("codename"),
            so_don_vi_cu=len(pho.get("merged_from") or []) or None,
            can_cu_phap_ly=(pho.get("legal_refs") or [{}])[0].get("number") if pho.get("legal_refs") else CAN_CU_MAC_DINH,
            ngay_hieu_luc=NGAY_HIEU_LUC,
            nguon=["open_api_v2", "tinhthanhpho"] + (["tinhthanh34"] if pho else []),
        )
        ds.append(don)
    return ds


def _don_vi_cu_theo_tinh(province_code: str) -> dict[str, dict]:
    """Đọc /api/wards của 34tinhthanh, trả về {mã xã: {đơn vị cũ, tên}}."""
    kq: dict[str, dict] = {}
    du = json_goi(f"{TINHTHANH34}/wards", params={"province_code": province_code})
    if not isinstance(du, list):
        return kq
    for w in du:
        ma = chi_so(str(w.get("ward_code") or ""))
        if ma:
            kq[ma] = {
                "ten": w.get("ward_name"),
                "cu": list(w.get("old_units") or []),
            }
    return kq


def nap_xa(province_codes: list[str] | None = None) -> list[DonVi]:
    """3.321 xã/phường; nếu truyền province_codes thì chỉ lấy các tỉnh đó."""
    tho = json_goi(f"{OPEN_API}/w/") or []
    tinh_theo_ma = {f"{int(p['code']):02d}": p["name"] for p in (json_goi(f"{OPEN_API}/p/") or [])}

    muon = set(province_codes) if province_codes else None

    # Đối chiếu đơn vị cũ theo từng tỉnh cần lấy (chỉ gọi cho tỉnh được yêu cầu)
    don_vi_cu: dict[str, dict] = {}
    for ma_tinh in (muon or tinh_theo_ma.keys()):
        don_vi_cu.update(_don_vi_cu_theo_tinh(ma_tinh))

    ds: list[DonVi] = []
    for w in tho:
        tinh_ma_int = w.get("province_code")
        tinh_ma = f"{int(tinh_ma_int):02d}" if tinh_ma_int is not None else None
        if muon and tinh_ma not in muon:
            continue
        ma = f"{int(w['code']):05d}"
        cu = don_vi_cu.get(ma, {})
        ten_34 = (cu.get("ten") or "").strip()
        khop = None
        if ten_34:
            khop = bam_chuoi(ten_34) == bam_chuoi(w.get("name") or "")
        ds.append(
            DonVi(
                ma=ma,
                ten=w.get("name") or "",
                loai=_loai_xa(w.get("division_type") or ""),
                tinh_ma=tinh_ma,
                tinh_ten=tinh_theo_ma.get(tinh_ma or ""),
                codename=w.get("codename"),
                don_vi_cu_hop_thanh=cu.get("cu") or [],
                so_don_vi_cu=len(cu.get("cu") or []) or None,
                can_cu_phap_ly=CAN_CU_MAC_DINH,
                ngay_hieu_luc=NGAY_HIEU_LUC,
                nguon=["open_api_v2", "tinhthanh34"] if cu else ["open_api_v2"],
                khop_da_nguon=khop,
            )
        )
    return ds


# ------------------------------------------------- chi tiết đơn vị cũ (trang xã, tra cứu 2 chiều)
_HUYEN_CU: dict[int, str] = {}


def _ten_huyen_cu(ma_huyen: int | None) -> str | None:
    if ma_huyen is None:
        return None
    if not _HUYEN_CU:
        for h in json_goi(f"{OPEN_API.replace('/v2', '/v1')}/d/") or []:
            _HUYEN_CU[h["code"]] = h["name"]
    return _HUYEN_CU.get(ma_huyen)


def _pham_vi(chuoi: str) -> str:
    """'Xã Uy Nỗ (phần còn lại sau khi sáp nhập…)' -> 'mot_phan'."""
    c = chuoi.lower()
    return "mot_phan" if ("phần còn lại" in c or "một phần" in c) else "toan_bo"


def chi_tiet_don_vi_cu(ma_xa: str, ds_cu: list[str]) -> list[dict]:
    """[{ten, huyen_cu, tinh_cu_ma, pham_vi}] cho mỗi đơn vị cũ hợp thành xã mới.

    Huyện cũ lấy từ open-api (to-legacies → district_code), phạm vi Toàn bộ/Một phần
    từ chuỗi NQ của 34tinhthanh. Ghép theo tên đã chuẩn hoá (bỏ phần trong ngoặc).
    """
    cu = json_goi(f"{OPEN_API}/w/{int(ma_xa)}/to-legacies/") or []
    theo_ten = {bam_chuoi(c["name"]): c for c in cu}
    kq = []
    for s in ds_cu:
        ten = s.split("(")[0].strip()
        c = theo_ten.pop(bam_chuoi(ten), None)
        kq.append({
            "ten": ten,
            "huyen_cu": _ten_huyen_cu(c.get("district_code")) if c else None,
            "tinh_cu_ma": f"{c['province_code']:02d}" if c else None,
            "pham_vi": _pham_vi(s),
        })
    # Đơn vị open-api có mà 34tinhthanh không liệt kê: vẫn ghi, đánh dấu chưa rõ phạm vi
    for c in theo_ten.values():
        kq.append({"ten": c["name"], "huyen_cu": _ten_huyen_cu(c.get("district_code")),
                   "tinh_cu_ma": f"{c['province_code']:02d}", "pham_vi": None})
    return kq


# ------------------------------------------------- số liệu cấp tỉnh (trang tỉnh)
_TINH: dict[str, dict] = {}


def so_lieu_tinh(ma: str) -> dict:
    """Số liệu một tỉnh mới từ tinhthanhpho (gọi API một lần cho cả 34 tỉnh)."""
    if not _TINH:
        cu = {f"{int(p['code']):02d}": p["name"]
              for p in json_goi(f"{OPEN_API.replace('/v2', '/v1')}/p/") or []}
        for t in (json_goi(f"{TINHTHANHPHO}/new-provinces?limit=100") or {}).get("data", []):
            dt = float(t["area_km2"]) if t.get("area_km2") else None
            ds = t.get("population")
            _TINH[f"{int(t['code']):02d}"] = {
                "dien_tich_km2": dt,
                "dan_so": ds,
                "mat_do_dan_so": round(ds / dt) if ds and dt else None,
                "nam_so_lieu": t.get("stats_year"),
                "tram_so_dien_thoai": ", ".join(t.get("area_codes") or []) or None,
                "bien_so_xe": ", ".join(t.get("plate_codes") or []) or None,
                "tru_so_ubnd": t.get("hq_address"),
                "tinh_cu_hop_thanh": [cu.get(m, m) for m in t.get("merged_from") or []],
                "can_cu_phap_ly": t.get("legal_ref"),
                "so_don_vi_hanh_chinh": t.get("ward_count"),
            }
    return _TINH.get(ma, {})

# ------------------------------------------------- căn cứ pháp lý từng xã (NQ UBTVQH sắp xếp cấp xã)
_NQ_XA: dict[str, dict] = {}
_DA_NAP_NQ: set[str] = set()

def nq_xa(ma_xa: str, tinh_ma: str | None) -> dict:
    """{number, title, date, effective_date, url} của NQ UBTVQH thành lập xã (tinhthanhpho legal_refs)."""
    if tinh_ma and tinh_ma not in _DA_NAP_NQ:
        _DA_NAP_NQ.add(tinh_ma)
        for w in (json_goi(f"{TINHTHANHPHO}/new-provinces/{tinh_ma}/wards", params={"limit": 500}) or {}).get("data", []):
            if w.get("legal_refs"):
                _NQ_XA[str(w["code"])] = w["legal_refs"][0]
    return _NQ_XA.get(ma_xa, {})

def ten_don_vi_cu(ma_xa: str) -> list[str]:
    """Tên đơn vị cũ theo open-api to-legacies — dự phòng khi 34tinhthanh không liệt kê."""
    return [c["name"] for c in json_goi(f"{OPEN_API}/w/{int(ma_xa)}/to-legacies/") or []]
