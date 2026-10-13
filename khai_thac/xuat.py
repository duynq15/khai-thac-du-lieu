"""Xuất kết quả bàn giao.

- JSON: cho hệ thống tiếp nhận (mapping vào DB). Cấu trúc ổn định, có `schema` mô tả mọi
  trường (khoá, nhãn, kiểu, nhóm) và danh mục nguồn; mỗi giá trị kèm nguồn + bằng chứng.
- Excel: cho người đọc. Mỗi xã một dòng, cột là nhãn tiếng Việt; sheet "Hướng dẫn",
  "Tổng hợp", một sheet mỗi tỉnh, và sheet "Nguồn & bằng chứng" để đối chiếu.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import cau_hinh
from .models import KetQua
from .store import DU_LIEU

GOC_BAN_GIAO = DU_LIEU / "ban_giao"
PHIEN_BAN_SCHEMA = "1.0"

# Ký tự không hợp lệ cho Excel (điều khiển, nhị phân) — loại bỏ trước khi ghi
_KY_TU_XAU = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TEN_SHEET_XAU = re.compile(r"[\\/?*\[\]:]")

# Nguồn nhập tay chưa có văn bản gốc đối chiếu (dữ liệu HP gõ tay cũ): giữ trong JSON (cho_duyet),
# KHÔNG hiển thị trong Excel cho người đọc.
NGUON_CHUA_KIEM = {"nhap_tay_de_xuat", "de_an_sap_xep_hp"}
# Đã có ở cột cố định của sheet tỉnh → không lặp lại
COT_CO_DINH = {"ten", "loai", "ma_dvhc", "truc_thuoc_tinh"}

TRANG_THAI_NHAN = {"dat": "Đạt", "cho_duyet": "Chờ duyệt", "loi": "Lỗi", "thieu": "Thiếu"}
MUC_NHAN = {"A": "A – chính thống", "B": "B – báo chí/tổng hợp", "C": "C – tham khảo"}


# ----------------------------------------------------------------------------- chung
def _sach_o(v):
    """Làm sạch giá trị ô Excel: bỏ ký tự điều khiển, cắt bớt nếu quá dài."""
    if isinstance(v, str):
        return _KY_TU_XAU.sub(" ", v)[:32000]
    return v


def _gom_don_vi(ds: list[KetQua]) -> dict[str, dict[str, KetQua]]:
    """{mã đơn vị: {khoá trường: KetQua}} — mỗi trường một bản ghi (đã chọn tốt nhất ở kho)."""
    gom: dict[str, dict[str, KetQua]] = {}
    for k in ds:
        gom.setdefault(k.don_vi_ma, {})[k.truong] = k
    return gom


def _danh_muc_don_vi() -> dict[str, dict]:
    """Thông tin danh mục của mọi đơn vị trong kho (tên, loại, tỉnh) — để xuất cả xã chưa có trường."""
    import sqlite3

    from .store import MAC_DINH_DB

    c = sqlite3.connect(f"file:{MAC_DINH_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    out = {r["ma"]: dict(r) for r in c.execute(
        "SELECT ma, ten, loai, tinh_ma, tinh_ten, parent_ma FROM don_vi")}
    c.close()
    return out


def _cap_cua(loai: str | None) -> str:
    return {"tinh": "tinh", "thanh_pho": "tinh", "thon": "thon"}.get(loai or "", "xa")


def _cac_truong(cap: str) -> list[dict]:
    """Danh sách trường theo thứ tự cấu hình, kèm nhóm: [{khoa, nhan, kieu, nhom, nhan_nhom}]."""
    out = []
    for nh in cau_hinh.ds_nhom(cap):
        for t in cau_hinh.ds_truong(cap, nh):
            out.append({"khoa": t["khoa"], "nhan": t.get("nhan", t["khoa"]), "kieu": t.get("kieu", "van_ban"),
                        "thuoc_tinh": t.get("thuoc_tinh"), "nhom": nh, "nhan_nhom": cau_hinh.nhan_nhom(cap, nh),
                        "bat_buoc": bool(t.get("bat_buoc"))})
    return out


# ----------------------------------------------------------------------------- JSON
def _gia_tri_json(k: KetQua) -> dict:
    """Một trường trong JSON bàn giao. Giá trị rỗng → null (không ghi chuỗi 'null')."""
    gt = k.gia_tri if k.gia_tri not in ("", [], {}) else None
    return {
        "gia_tri": gt,
        "trang_thai": k.trang_thai,
        "diem_tin": k.diem_tin,
        "nam_du_lieu": k.nam_du_lieu,
        "nguon": {"ma": k.nguon_ma, "ten": k.nguon_ten, "url": k.nguon_url, "muc": k.nguon_muc,
                  "da_kiem_chung": k.nguon_ma not in NGUON_CHUA_KIEM}
                 if k.nguon_ma else None,
        "trich_doan": k.trich_doan,
        "ly_do_loi": k.ly_do_loi,
        "canh_bao": k.canh_bao or [],
    }


def xuat_json(ds: list[KetQua], duong_dan: Path | str | None = None) -> Path:
    """JSON bàn giao cho hệ thống.

    Cấu trúc (phiên bản schema 1.0):
      meta      – thời điểm xuất, phiên bản, số lượng, quy ước
      schema    – {cap: [{khoa, nhan, kieu, nhom, ...}]}: từ điển để map cột DB
      nguon     – danh mục nguồn đã dùng {ma: {ten, url, muc}}
      don_vi    – [{ma, ten, loai, cap, tinh_ma, tinh_ten, parent_ma, truong: {khoa: {...}}}]
    Mỗi đơn vị có ĐỦ mọi khoá của cấp đó; trường chưa có dữ liệu: gia_tri = null, trang_thai = "thieu".
    """
    gom = _gom_don_vi(ds)
    dm = _danh_muc_don_vi()
    schema = {cap: _cac_truong(cap) for cap in ("tinh", "xa", "thon")}

    nguon: dict[str, dict] = {}
    don_vi = []
    for ma in sorted(gom, key=lambda m: ((dm.get(m) or {}).get("tinh_ma") or "zz", m)):
        info = dm.get(ma) or {}
        cap = _cap_cua(info.get("loai")) if info else next(iter(gom[ma].values())).cap
        truong = {}
        for t in schema[cap]:
            k = gom[ma].get(t["khoa"])
            if k is None:
                truong[t["khoa"]] = {"gia_tri": None, "trang_thai": "thieu", "diem_tin": 0, "nam_du_lieu": None,
                                     "nguon": None, "trich_doan": None, "ly_do_loi": None, "canh_bao": []}
                continue
            truong[t["khoa"]] = _gia_tri_json(k)
            if k.nguon_ma and k.nguon_ma not in nguon:
                nguon[k.nguon_ma] = {"ten": k.nguon_ten, "url": k.nguon_url, "muc": k.nguon_muc}
        don_vi.append({
            "ma": ma, "ten": info.get("ten") or next(iter(gom[ma].values())).don_vi_ten,
            "loai": info.get("loai"), "cap": cap,
            "tinh_ma": info.get("tinh_ma") or (ma if cap == "tinh" else None),
            "tinh_ten": info.get("tinh_ten"), "parent_ma": info.get("parent_ma"),
            "truong": truong,
        })

    goi = {
        "meta": {
            "phien_ban_schema": PHIEN_BAN_SCHEMA,
            "xuat_luc": datetime.now().isoformat(timespec="seconds"),
            "so_don_vi": len(don_vi),
            "quy_uoc": {
                "ma": "Mã ĐVHC theo QĐ 19/2025/QĐ-TTg (tỉnh 2 số, xã 5 số) — dùng làm khoá chính",
                "trang_thai": {"dat": "đạt kiểm tra, dùng được", "cho_duyet": "cần người duyệt",
                               "loi": "không đạt kiểm tra (xem ly_do_loi)", "thieu": "chưa có dữ liệu"},
                "nguon.da_kiem_chung": "false = nhập tay chưa đối chiếu văn bản gốc, chỉ dùng sau khi duyệt",
                "nguon.muc": MUC_NHAN,
                "kieu": {"van_ban": "string", "so": "number", "ngay": "string YYYY-MM-DD",
                         "danh_sach": "array<string>", "ban_ghi": "array<object> theo thuoc_tinh",
                         "toa_do": "object {lat, lon}", "ma_so": "string", "email": "string",
                         "dien_thoai": "string", "url": "string", "anh": "string URL"},
                "trich_doan": "câu nguyên văn trong nguồn làm bằng chứng cho giá trị",
                "diem_tin": "0–100, độ tin của giá trị",
            },
        },
        "schema": schema,
        "nguon": nguon,
        "don_vi": don_vi,
    }
    duong_dan = Path(duong_dan) if duong_dan else (
        GOC_BAN_GIAO / f"ban_giao_{datetime.now():%Y%m%d_%H%M%S}.json")
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    duong_dan.write_text(json.dumps(goi, ensure_ascii=False, indent=2), encoding="utf-8")
    return duong_dan


# ----------------------------------------------------------------------------- Excel
_NEN_DAU = PatternFill("solid", fgColor="1F4E79")
_NEN_NHOM = PatternFill("solid", fgColor="DDEBF7")
_NEN_CHO = PatternFill("solid", fgColor="FFF2CC")   # chờ duyệt / cảnh báo
_CHU_DAU = Font(bold=True, color="FFFFFF")


def _hien_thi(gt, kieu: str):
    """Giá trị → chữ dễ đọc cho người dùng (không phải JSON)."""
    if gt in (None, "", [], {}):
        return None
    if kieu == "ban_ghi" and isinstance(gt, list):
        dong = []
        for x in gt:
            if isinstance(x, dict):
                phu = ", ".join(str(v) for k, v in x.items() if k != "ten" and v not in (None, ""))
                dong.append(f"• {x.get('ten', '')}" + (f" ({phu})" if phu else ""))
            else:
                dong.append(f"• {x}")
        return "\n".join(dong)
    if isinstance(gt, list):
        if gt and isinstance(gt[0], dict):   # đơn vị cũ chi tiết
            pv = {"toan_bo": "toàn bộ", "mot_phan": "một phần"}
            return "\n".join("• " + " · ".join(filter(None, [x.get("ten"), x.get("huyen_cu"),
                                                               pv.get(x.get("pham_vi"))])) for x in gt)
        return "; ".join(str(x) for x in gt)
    if isinstance(gt, dict):
        if "lat" in gt:
            return f"{gt['lat']:.5f}, {gt['lon']:.5f}"
        return "; ".join(f"{k}: {v}" for k, v in gt.items())
    if kieu == "ngay" and isinstance(gt, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", gt):
        y, m, d = gt.split("-")
        return f"{d}/{m}/{y}"
    return gt


def _sheet_huong_dan(wb: Workbook, xuat_luc: str, so_xa: int) -> None:
    ws = wb.create_sheet("Hướng dẫn")
    dong = [
        ["DỮ LIỆU KHAI THÁC – XÃ PHƯỜNG VIỆT NAM"],
        [f"Xuất lúc: {xuat_luc}   ·   Số xã/phường: {so_xa}"],
        [],
        ["Cách đọc"],
        ["• Sheet \"Tổng hợp\": mỗi tỉnh/thành một dòng – số xã và mức độ đầy đủ."],
        ["• Mỗi sheet tỉnh: mỗi xã/phường một dòng, mỗi thông tin một cột (tên cột tiếng Việt)."],
        ["• Ô trống = chưa có thông tin. Ô nền vàng = cần cán bộ duyệt lại trước khi dùng."],
        ["• Sheet \"Nguồn & bằng chứng\": với từng thông tin – lấy từ đâu (đường link), câu gốc làm bằng chứng."],
        [],
        ["Độ tin cậy của nguồn"],
        ["• A – chính thống: cổng *.gov.vn, văn bản nhà nước."],
        ["• B – báo chí, trang tổng hợp chính thống."],
        ["• C – nguồn mở khác (Wikipedia, bản đồ)."],
        [],
        ["Lưu ý"],
        ["• Dữ liệu do máy khai thác, mọi giá trị đều có câu gốc làm bằng chứng nhưng CHƯA được cán bộ duyệt."],
        ["• Số điện thoại, chủ tịch UBND có thể đã thay đổi – đối chiếu năm số liệu ở sheet Nguồn."],
    ]
    for d in dong:
        ws.append(d)
    ws["A1"].font = Font(bold=True, size=14, color="1F4E79")
    for o in ("A4", "A10", "A15"):
        ws[o].font = Font(bold=True)
    ws.column_dimensions["A"].width = 110


def _co_gia_tri(k: KetQua | None) -> bool:
    """Ô có hiển thị cho người đọc: đạt/chờ duyệt, có giá trị, nguồn đã kiểm chứng."""
    return (k is not None and k.trang_thai in ("dat", "cho_duyet") and k.gia_tri not in (None, "", [], {})
            and k.nguon_ma not in NGUON_CHUA_KIEM)


def _sheet_tong_hop(wb: Workbook, theo_tinh: dict, truong_xa: list[dict]) -> None:
    ws = wb.create_sheet("Tổng hợp")
    nhom_ds = list(dict.fromkeys(t["nhan_nhom"] for t in truong_xa))
    dau = ["Mã", "Tỉnh/Thành phố", "Số xã/phường", "Tỉ lệ thông tin đã có"] + [f"{n} (%)" for n in nhom_ds]
    ws.append(dau)
    for c in range(1, len(dau) + 1):
        ws.cell(row=1, column=c).font = _CHU_DAU
        ws.cell(row=1, column=c).fill = _NEN_DAU
        ws.cell(row=1, column=c).alignment = Alignment(wrap_text=True, vertical="center")
    for (ma_tinh, ten_tinh), xa in sorted(theo_tinh.items()):
        tong = co = 0
        theo_nhom = {n: [0, 0] for n in nhom_ds}
        for _, ks in xa:
            for t in truong_xa:
                ok = _co_gia_tri(ks.get(t["khoa"]))
                tong += 1
                co += ok
                theo_nhom[t["nhan_nhom"]][0] += ok
                theo_nhom[t["nhan_nhom"]][1] += 1
        ws.append([ma_tinh, ten_tinh, len(xa), f"{co / tong:.0%}" if tong else "-"]
                  + [f"{a / b:.0%}" if b else "-" for a, b in theo_nhom.values()])
    for i, rong in enumerate([6, 22, 12, 14] + [16] * len(nhom_ds), start=1):
        ws.column_dimensions[get_column_letter(i)].width = rong
    ws.row_dimensions[1].height = 45
    ws.freeze_panes = "C2"


def _sheet_tinh(wb: Workbook, ten_tinh: str, xa: list, truong_xa: list[dict]) -> None:
    ws = wb.create_sheet(_TEN_SHEET_XAU.sub(" ", ten_tinh)[:31])
    co_dinh = ["Mã xã", "Tên xã/phường", "Loại"]
    # Dòng 1: nhóm (gộp ô), dòng 2: tên cột
    ws.append([""] * len(co_dinh) + [t["nhan_nhom"] for t in truong_xa])
    ws.append(co_dinh + [t["nhan"] for t in truong_xa])
    c = len(co_dinh) + 1
    for nhom in dict.fromkeys(t["nhan_nhom"] for t in truong_xa):
        n = sum(1 for t in truong_xa if t["nhan_nhom"] == nhom)
        if n > 1:
            ws.merge_cells(start_row=1, start_column=c, end_row=1, end_column=c + n - 1)
        o = ws.cell(row=1, column=c)
        o.font, o.fill, o.alignment = Font(bold=True, color="1F4E79"), _NEN_NHOM, Alignment(horizontal="center")
        c += n
    for col in range(1, len(co_dinh) + len(truong_xa) + 1):
        o = ws.cell(row=2, column=col)
        o.font, o.fill = _CHU_DAU, _NEN_DAU
        o.alignment = Alignment(wrap_text=True, vertical="center")

    loai_nhan = {"xa": "Xã", "phuong": "Phường", "dac_khu": "Đặc khu"}
    for ma, ks in sorted(xa, key=lambda x: x[0]):
        ten = next((k.don_vi_ten for k in ks.values()), "")
        loai = ks.get("loai").gia_tri if ks.get("loai") else None
        hang = [ma, ten, loai_nhan.get(loai, loai)]
        cho = []
        for i, t in enumerate(truong_xa):
            k = ks.get(t["khoa"])
            if not _co_gia_tri(k):
                hang.append(None)
                continue
            hang.append(_sach_o(_hien_thi(k.gia_tri, t["kieu"])))
            if k.trang_thai == "cho_duyet" or k.canh_bao:
                cho.append(len(co_dinh) + i + 1)
        ws.append(hang)
        r = ws.max_row
        for col in cho:
            ws.cell(row=r, column=col).fill = _NEN_CHO
        for col in range(1, len(hang) + 1):
            ws.cell(row=r, column=col).alignment = Alignment(wrap_text=True, vertical="top")

    rong = {"van_ban": 28, "ban_ghi": 40, "danh_sach": 30, "so": 12, "ngay": 12, "ma_so": 10,
            "dien_thoai": 16, "email": 26, "url": 28, "toa_do": 20, "anh": 20}
    for i, w in enumerate([8, 24, 9] + [rong.get(t["kieu"], 20) for t in truong_xa], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[2].height = 45
    ws.freeze_panes = "C3"
    ws.auto_filter.ref = f"A2:{get_column_letter(len(co_dinh) + len(truong_xa))}{ws.max_row}"


def _sheet_nguon(wb: Workbook, theo_tinh: dict, truong_xa: list[dict]) -> None:
    ws = wb.create_sheet("Nguồn & bằng chứng")
    dau = ["Tỉnh/Thành phố", "Mã xã", "Tên xã/phường", "Thông tin", "Giá trị", "Trạng thái",
           "Độ tin nguồn", "Tên nguồn", "Đường link", "Câu gốc (bằng chứng)", "Năm số liệu", "Ghi chú"]
    ws.append(dau)
    for c in range(1, len(dau) + 1):
        ws.cell(row=1, column=c).font = _CHU_DAU
        ws.cell(row=1, column=c).fill = _NEN_DAU
    nhan = {t["khoa"]: (t["nhan"], t["kieu"]) for t in truong_xa}
    for (_, ten_tinh), xa in sorted(theo_tinh.items()):
        for ma, ks in sorted(xa, key=lambda x: x[0]):
            for khoa, (ten_truong, kieu) in nhan.items():
                k = ks.get(khoa)
                if not _co_gia_tri(k) or k.nguon_ma == "danh_muc":
                    continue
                ws.append([_sach_o(x) for x in [
                    ten_tinh, ma, k.don_vi_ten, ten_truong, _hien_thi(k.gia_tri, kieu),
                    TRANG_THAI_NHAN.get(k.trang_thai, k.trang_thai), MUC_NHAN.get(k.nguon_muc, k.nguon_muc),
                    k.nguon_ten, k.nguon_url, k.trich_doan, k.nam_du_lieu,
                    "; ".join(filter(None, [k.ly_do_loi, *k.canh_bao])) or None,
                ]])
    for i, w in enumerate([16, 8, 22, 22, 36, 11, 20, 28, 40, 60, 10, 30], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:L{ws.max_row}"


def xuat_excel(ds: list[KetQua], duong_dan: Path | str | None = None) -> Path:
    """Excel cho người đọc: Hướng dẫn · Tổng hợp · mỗi tỉnh một sheet · Nguồn & bằng chứng."""
    gom = _gom_don_vi(ds)
    dm = _danh_muc_don_vi()
    truong_xa = [t for t in _cac_truong("xa") if t["khoa"] not in COT_CO_DINH]

    theo_tinh: dict[tuple, list] = {}
    for ma, ks in gom.items():
        info = dm.get(ma) or {}
        if _cap_cua(info.get("loai")) != "xa":
            continue   # ponytail: Excel chỉ cấp xã; cấp tỉnh/thôn xem trong JSON
        theo_tinh.setdefault((info.get("tinh_ma") or "zz", info.get("tinh_ten") or "(không rõ tỉnh)"),
                             []).append((ma, ks))

    xuat_luc = datetime.now().strftime("%d/%m/%Y %H:%M")
    wb = Workbook()
    wb.remove(wb.active)
    _sheet_huong_dan(wb, xuat_luc, sum(len(v) for v in theo_tinh.values()))
    _sheet_tong_hop(wb, theo_tinh, truong_xa)
    for (_, ten_tinh), xa in sorted(theo_tinh.items()):
        _sheet_tinh(wb, ten_tinh, xa, truong_xa)
    _sheet_nguon(wb, theo_tinh, truong_xa)

    duong_dan = Path(duong_dan) if duong_dan else (
        GOC_BAN_GIAO / f"ban_giao_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    wb.save(duong_dan)
    return duong_dan
