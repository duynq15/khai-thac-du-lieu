"""Xuất kết quả ra JSON (bàn giao) và Excel (xem/duyệt tay)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .models import KetQua
from .store import DU_LIEU

GOC_BAN_GIAO = DU_LIEU / "ban_giao"

# Ký tự không hợp lệ cho Excel (điều khiển, nhị phân) — loại bỏ trước khi ghi
_KY_TU_XAU = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sach_o(v):
    """Làm sạch giá trị ô: bỏ ký tự điều khiển/nhị phân, cắt bớt nếu quá dài."""
    if v is None:
        return None
    if isinstance(v, str):
        return _KY_TU_XAU.sub(" ", v)[:32000]
    return v


def _don_vi_dict(k: KetQua) -> dict:
    return {
        "gia_tri": k.gia_tri,
        "kieu": k.kieu,
        "nguon": {
            "ma": k.nguon_ma,
            "ten": k.nguon_ten,
            "url": k.nguon_url,
            "muc": k.nguon_muc,
        },
        "trich_doan": k.trich_doan,
        "diem_tin": k.diem_tin,
        "trang_thai": k.trang_thai,
        "ly_do_loi": k.ly_do_loi,
        "canh_bao": k.canh_bao,
        "nam_du_lieu": k.nam_du_lieu,
    }


def xuat_json(ds: list[KetQua], duong_dan: Path | str | None = None) -> Path:
    gom: dict[str, dict] = {}
    for k in ds:
        gom.setdefault(k.don_vi_ma, {
            "don_vi": {"ma": k.don_vi_ma, "ten": k.don_vi_ten, "cap": k.cap},
            "nhom": {},
        })
        gom[k.don_vi_ma]["nhom"].setdefault(k.nhom, {})[k.truong] = _don_vi_dict(k)

    goi = {
        "xuat_luc": datetime.now().isoformat(timespec="seconds"),
        "so_don_vi": len(gom),
        "so_truong": len(ds),
        "don_vi": list(gom.values()),
    }
    duong_dan = Path(duong_dan) if duong_dan else (
        GOC_BAN_GIAO / f"khai_thac_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    duong_dan.write_text(json.dumps(goi, ensure_ascii=False, indent=2), encoding="utf-8")
    return duong_dan


COT = ["Đơn vị", "Mã", "Cấp", "Nhóm", "Trường", "Giá trị", "Nguồn (mục)",
       "Nguồn URL", "Điểm tin", "Trạng thái", "Cảnh báo", "Trích đoạn"]

_TEN_SHEET_XAU = re.compile(r"[\\/?*\[\]:]")


def _ban_do_tinh() -> tuple[dict, dict]:
    """Đọc kho: mã đơn vị -> (mã tỉnh, tên tỉnh) để gom sheet theo tỉnh."""
    import sqlite3

    from .store import MAC_DINH_DB

    ma2tinh: dict[str, str] = {}
    ma2ten: dict[str, str] = {}
    try:
        c = sqlite3.connect(str(MAC_DINH_DB))
        for ma, tinh_ma, tinh_ten in c.execute("SELECT ma, tinh_ma, tinh_ten FROM don_vi"):
            if tinh_ma:
                ma2tinh[ma] = tinh_ma
            if tinh_ten:
                ma2ten[ma] = tinh_ten
        c.close()
    except Exception:
        pass
    return ma2tinh, ma2ten


def _ghi_dau_trang(ws) -> None:
    ws.append(COT)
    for c in range(1, len(COT) + 1):
        o = ws.cell(row=1, column=c)
        o.font = Font(bold=True, color="FFFFFF")
        o.fill = PatternFill("solid", fgColor="1F4E79")
    for cot, rong in zip("ABCDEFGHIJKL", [28, 8, 6, 20, 22, 50, 26, 40, 9, 12, 30, 50]):
        ws.column_dimensions[cot].width = rong
    ws.freeze_panes = "A2"


def _dong(k: KetQua) -> list:
    gt = k.gia_tri if isinstance(k.gia_tri, str) else json.dumps(k.gia_tri, ensure_ascii=False)
    return [_sach_o(x) for x in [
        k.don_vi_ten, k.don_vi_ma, k.cap, k.nhom, k.truong, gt,
        f"{k.nguon_ten or ''} ({k.nguon_muc or ''})".strip(),
        k.nguon_url, k.diem_tin, k.trang_thai,
        "; ".join(k.canh_bao), k.trich_doan,
    ]]


def xuat_excel(ds: list[KetQua], duong_dan: Path | str | None = None) -> Path:
    """Mỗi tỉnh/thành một sheet, theo thứ tự mã tỉnh."""
    ma2tinh, ma2ten = _ban_do_tinh()

    # Gom theo tỉnh; giữ cả mã tỉnh để sắp xếp
    gom: dict[str, list[KetQua]] = {}
    ma_tinh: dict[str, str] = {}
    for k in ds:
        if k.cap == "tinh":
            ten, mt = k.don_vi_ten, k.don_vi_ma
        else:
            ten = ma2ten.get(k.don_vi_ma) or "(không rõ tỉnh)"
            mt = ma2tinh.get(k.don_vi_ma) or "zz"
        gom.setdefault(ten, []).append(k)
        ma_tinh.setdefault(ten, mt)

    wb = Workbook()
    wb.remove(wb.active)
    for ten in sorted(gom, key=lambda t: (ma_tinh.get(t, "zz"), t)):
        ws = wb.create_sheet(title=_TEN_SHEET_XAU.sub(" ", ten)[:31])
        _ghi_dau_trang(ws)
        for k in gom[ten]:
            ws.append(_dong(k))
    if not wb.sheetnames:
        wb.create_sheet(title="Ket qua")

    duong_dan = Path(duong_dan) if duong_dan else (
        GOC_BAN_GIAO / f"khai_thac_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    )
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    wb.save(duong_dan)
    return duong_dan
