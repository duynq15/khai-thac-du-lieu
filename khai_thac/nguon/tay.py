"""Nạp danh sách đã tách sẵn (người/agent tách từ trang chính thống) — du_lieu/nguon_tay/*.json.

Mỗi tệp: {"ma", "ten", "url", "muc", "tinh_ma"?, "nam"?,
          "dong": [{"ten_xa", "tinh_cu"?, "truong": {khoá: giá trị}, "trich_doan", "url"?}]}
Tên xã có thể là tên CŨ (trước 7/2025) — ghép qua Kho.ban_do_ma (tên cũ → xã mới) trong
phạm vi tỉnh mới; tinh_cu giúp chọn tỉnh mới khi tệp gom nhiều tỉnh.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .. import cau_hinh
from ..models import DAT, KetQua, Luot
from ..store import DU_LIEU, Kho
from ..text import chuan_hoa

THU_MUC = DU_LIEU / "nguon_tay"

# Tỉnh cũ (trước 7/2025) → tỉnh mới, cho 6 TP trực thuộc TW
TINH_CU_SANG_MOI = {
    "ha noi": "01", "hai phong": "31", "hai duong": "31",
    "da nang": "48", "quang nam": "48",
    "ho chi minh": "79", "tp hcm": "79", "tphcm": "79", "binh duong": "79", "ba ria vung tau": "79",
    "ba ria - vung tau": "79",
    "can tho": "92", "hau giang": "92", "soc trang": "92",
    "hue": "46", "thua thien hue": "46",
}


def _tinh_moi(tinh_cu: str | None, mac_dinh: str | None) -> str | None:
    t = chuan_hoa(tinh_cu or "").replace("thanh pho ", "").replace("tinh ", "").strip()
    for k, v in TINH_CU_SANG_MOI.items():
        if k in t:
            return v
    return mac_dinh


def nap_tep(kho: Kho, p: Path) -> dict:
    cfg = json.loads(p.read_text(encoding="utf-8"))
    kieu = {t["khoa"]: (t.get("kieu", "van_ban"), nh)
            for nh in cau_hinh.ds_nhom("xa") for t in cau_hinh.ds_truong("xa", nh)}
    ban_do: dict[str, dict] = {}
    ten_xa: dict[str, str] = {}
    gom: dict[tuple[str, str], dict] = {}   # (mã xã, khoá) → {gia_tri, trich_doan[], url}
    khong_khop: list[str] = []

    for d in cfg.get("dong", []):
        tinh = _tinh_moi(d.get("tinh_cu"), cfg.get("tinh_ma"))
        if not tinh or not d.get("ten_xa"):
            khong_khop.append(d.get("ten_xa") or "(trống)")
            continue
        if tinh not in ban_do:
            ban_do[tinh] = kho.ban_do_ma(tinh)
            ten_xa.update({r["ma"]: r["ten"] for r in kho.tim_don_vi(tinh_ma=tinh, cap="xa")})
        ma = Kho.tim_ma_xa(ban_do[tinh], d["ten_xa"])
        if not ma:
            khong_khop.append(d["ten_xa"])
            continue
        for khoa, gt in (d.get("truong") or {}).items():
            if khoa not in kieu or gt in (None, "", [], {}):
                continue
            o = gom.setdefault((ma, khoa), {"gia_tri": [] if kieu[khoa][0] in ("danh_sach", "ban_ghi") else None,
                                           "trich": [], "url": d.get("url") or cfg["url"]})
            if isinstance(o["gia_tri"], list):   # nhiều dòng cùng xã (vd nhiều di tích) → gộp
                for x in (gt if isinstance(gt, list) else [gt]):
                    if x not in o["gia_tri"]:
                        o["gia_tri"].append(x)
            elif o["gia_tri"] is None:
                o["gia_tri"] = gt
            if d.get("trich_doan") and len(o["trich"]) < 3:
                o["trich"].append(d["trich_doan"])

    luot = Luot(ma=f"tay-{cfg['ma']}-{datetime.now():%Y%m%d-%H%M%S}", pham_vi=cfg["ma"],
                nhom_du_lieu="nguon_tay", bat_dau=datetime.now().isoformat(timespec="seconds"), nguon=[cfg["ma"]])
    diem = {"A": 90, "B": 75}.get(cfg.get("muc"), 60)
    ket = [KetQua(
        don_vi_ma=ma, don_vi_ten=ten_xa.get(ma, ""), cap="xa", nhom=kieu[khoa][1], truong=khoa,
        gia_tri=o["gia_tri"], kieu=kieu[khoa][0],
        nguon_ma=cfg["ma"], nguon_ten=cfg.get("ten") or cfg["ma"], nguon_url=o["url"],
        nguon_muc=cfg.get("muc", "C"), trich_doan=" … ".join(o["trich"])[:600] or None,
        diem_tin=diem, trang_thai=DAT, nam_du_lieu=cfg.get("nam"),
    ) for (ma, khoa), o in gom.items()]
    kho.ghi_ket_qua(ket, luot.ma)
    luot.ket_thuc = datetime.now().isoformat(timespec="seconds")
    luot.so_don_vi = len({k.don_vi_ma for k in ket})
    luot.so_ket_qua = luot.so_dat = len(ket)
    kho.ghi_luot(luot)
    return {"tep": p.name, "so_xa": luot.so_don_vi, "so_truong": len(ket), "khong_khop": khong_khop}


def nap_tat_ca(kho: Kho, chi: list[str] | None = None) -> list[dict]:
    return [nap_tep(kho, p) for p in sorted(THU_MUC.glob("*.json")) if not chi or p.stem in chi]
