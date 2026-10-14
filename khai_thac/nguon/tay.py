"""Nạp danh sách đã tách sẵn (người/agent tách từ trang chính thống) — du_lieu/nguon_tay/*.json.

Mỗi tệp: {"ma", "ten", "url", "muc", "tinh_ma"?, "nam"?, "canh_bao"?,
          "dong": [{"ten_xa", "ma_xa"?, "tinh_cu"?, "tinh_ma"?, "truong": {khoá: giá trị}, "trich_doan",
                    "url"?, "nguon_ten"?, "nam"?, "canh_bao"?}]}
Khoá của dòng ghi đè khoá cùng nghĩa của tệp (ten → nguon_ten). diem_tin suy từ muc + canh_bao
(models.diem_theo_muc) — đây là lối ghi duy nhất cho dữ liệu tách tay, không ghi thẳng DB.
Tên xã có thể là tên CŨ (trước 7/2025) — ghép qua Kho.ban_do_ma (tên cũ → xã mới) trong
phạm vi tỉnh mới; tinh_cu giúp chọn tỉnh mới khi tệp gom nhiều tỉnh.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .. import cau_hinh
from ..models import DAT, KetQua, Luot, diem_theo_muc
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


_BO_TIEN_TO = re.compile(r"^(xã|phường|thị trấn|đặc khu)\s+", re.IGNORECASE)
_BO_NGOAC = re.compile(r"\s*\([^)]*\)")   # "Phường Bến Thành (Quận 1)" → "Phường Bến Thành"


def _dau(s: str) -> str:
    """Chuẩn hoá giữ dấu: NFC, chữ thường, gọn khoảng trắng."""
    return " ".join(unicodedata.normalize("NFC", str(s or "")).lower().split())


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
    dung_dau: dict[str, dict] = {}
    ten_xa: dict[str, str] = {}
    gom: dict[tuple[str, str], dict] = {}   # (mã xã, khoá) → {gia_tri, trich_doan[], url}
    khong_khop: list[str] = []

    for d in cfg.get("dong", []):
        tinh = d.get("tinh_ma") or _tinh_moi(d.get("tinh_cu"), cfg.get("tinh_ma"))
        if not tinh or not d.get("ten_xa"):
            khong_khop.append(d.get("ten_xa") or "(trống)")
            continue
        if tinh not in ban_do:
            ban_do[tinh] = kho.ban_do_ma(tinh)
            ds = kho.tim_don_vi(tinh_ma=tinh, cap="xa")
            ten_xa.update({r["ma"]: r["ten"] for r in ds})
            # Khớp đúng dấu trước: chuan_hoa bỏ dấu làm trùng "Thanh An"/"Thạnh An", "Cẩm Giang"/"Cẩm Giàng"
            dung_dau[tinh] = {_dau(t): r["ma"] for r in ds for t in (r["ten"], _BO_TIEN_TO.sub("", r["ten"]))}
            # Tên CŨ không có trong tên mới ("Phường Bến Thành" của 26743): chỉ nhận khi
            # tên đó ứng với đúng MỘT đơn vị mới, tránh "Phường 1" của nhiều quận khác nhau.
            ung: dict[str, set[str]] = {}
            for r in kho.conn.execute(
                    "SELECT ma, don_vi_cu_hop_thanh FROM don_vi WHERE tinh_ma = ?"
                    " AND don_vi_cu_hop_thanh IS NOT NULL", (tinh,)):
                for ten in json.loads(r[1] or "[]"):
                    k = _dau(_BO_NGOAC.sub(" ", ten))
                    ung.setdefault(k, set()).add(r[0])
                    ca = _dau(ten)   # nguồn ghi kèm quận ("Phường 5 (thành phố Vũng Tàu)")
                    if ca != k:
                        ung.setdefault(ca, set()).add(r[0])
            for k, ma_set in ung.items():
                if len(ma_set) == 1:
                    dung_dau[tinh].setdefault(k, next(iter(ma_set)))
        ten_can = _BO_NGOAC.sub(" ", d["ten_xa"])   # nguồn hay ghi kèm "(Quận 1)"
        ma = (d.get("ma_xa") if d.get("ma_xa") in ten_xa else None) or (dung_dau[tinh].get(_dau(d["ten_xa"])) or dung_dau[tinh].get(_dau(_BO_TIEN_TO.sub("", d["ten_xa"])))
              or dung_dau[tinh].get(_dau(ten_can)) or dung_dau[tinh].get(_dau(_BO_TIEN_TO.sub("", ten_can)))
              or Kho.tim_ma_xa(ban_do[tinh], d["ten_xa"]))
        if not ma:
            khong_khop.append(d["ten_xa"])
            continue
        for khoa, gt in (d.get("truong") or {}).items():
            if khoa not in kieu or gt in (None, "", [], {}):
                continue
            o = gom.setdefault((ma, khoa), {"gia_tri": [] if kieu[khoa][0] in ("danh_sach", "ban_ghi") else None,
                                           "trich": [], "url": d.get("url") or cfg["url"],
                                           "ten": d.get("nguon_ten") or cfg.get("ten") or cfg["ma"],
                                           "nam": d.get("nam", cfg.get("nam")),
                                           "canh_bao": d.get("canh_bao", cfg.get("canh_bao")) or []})
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
    ket = [KetQua(
        don_vi_ma=ma, don_vi_ten=ten_xa.get(ma, ""), cap="xa", nhom=kieu[khoa][1], truong=khoa,
        gia_tri=o["gia_tri"], kieu=kieu[khoa][0],
        nguon_ma=cfg["ma"], nguon_ten=o["ten"], nguon_url=o["url"], nguon_muc=cfg.get("muc", "C"),
        # một trích đoạn giữ nguyên; gộp nhiều dòng thì cắt 600 ký tự
        trich_doan=(o["trich"][0] if len(o["trich"]) == 1 else " … ".join(o["trich"])[:600]) or None,
        diem_tin=diem_theo_muc(cfg.get("muc"), o["canh_bao"]), trang_thai=DAT,
        canh_bao=o["canh_bao"], nam_du_lieu=o["nam"],
    ) for (ma, khoa), o in gom.items()]
    kho.ghi_ket_qua(ket, luot.ma)
    luot.ket_thuc = datetime.now().isoformat(timespec="seconds")
    luot.so_don_vi = len({k.don_vi_ma for k in ket})
    luot.so_ket_qua = luot.so_dat = len(ket)
    kho.ghi_luot(luot)
    return {"tep": p.name, "so_xa": luot.so_don_vi, "so_truong": len(ket), "khong_khop": khong_khop}


def nap_tat_ca(kho: Kho, chi: list[str] | None = None) -> list[dict]:
    return [nap_tep(kho, p) for p in sorted(THU_MUC.glob("*.json")) if not chi or p.stem in chi]
