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

# Nguồn nhập tay chưa có văn bản gốc đối chiếu (dữ liệu HP gõ tay cũ): đánh dấu da_kiem_chung = false
NGUON_CHUA_KIEM = {"nhap_tay_de_xuat", "de_an_sap_xep_hp"}

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


def dung_goi(ds: list[KetQua]) -> dict:
    """Gói bàn giao — NGUỒN DUY NHẤT cho cả JSON và Excel (Excel chỉ trình bày lại gói này).

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
    return goi


def xuat_json(ds: list[KetQua], duong_dan: Path | str | None = None, goi: dict | None = None) -> Path:
    """JSON bàn giao cho hệ thống (cấu trúc: xem dung_goi và BAN_GIAO.md)."""
    goi = goi or dung_goi(ds)
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
                                                               x.get("tinh_cu_ma") and f"mã tỉnh cũ {x['tinh_cu_ma']}",
                                                               pv.get(x.get("pham_vi"), x.get("pham_vi"))])) for x in gt)
        return "; ".join(str(x) for x in gt)
    if isinstance(gt, dict):
        if "lat" in gt:
            return f"{gt['lat']}, {gt['lon']}"
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
        ["• Ô trống = chưa có thông tin. Nền vàng = cần cán bộ duyệt (chờ duyệt/chưa kiểm chứng). Nền cam = không đạt kiểm tra."],
        ["• File Excel trình bày đúng dữ liệu trong file JSON cùng lần xuất (cùng đơn vị, cùng trường, cùng giá trị)."],
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
    for o in ("A4", "A11", "A16"):
        ws[o].font = Font(bold=True)
    ws.column_dimensions["A"].width = 110


_NEN_LOI = PatternFill("solid", fgColor="F8CBAD")    # không đạt kiểm tra
CAP_NHAN = {"tinh": "Tỉnh/Thành phố", "xa": "Xã/Phường", "thon": "Thôn/Tổ dân phố"}
LOAI_NHAN = {"xa": "Xã", "phuong": "Phường", "dac_khu": "Đặc khu", "tinh": "Tỉnh", "thanh_pho": "Thành phố",
             "thon": "Thôn"}


def _co(v: dict) -> bool:
    return v["gia_tri"] is not None


def _sheet_tong_hop(wb: Workbook, goi: dict) -> None:
    """Đếm đúng như trong JSON: một trường 'có' khi gia_tri khác null; tách theo trạng thái."""
    ws = wb.create_sheet("Tổng hợp")
    dau = ["Cấp", "Mã tỉnh", "Tỉnh/Thành phố", "Số đơn vị", "Ô có giá trị", "Đạt", "Chờ duyệt", "Lỗi",
           "Tổng ô", "Tỉ lệ đạt"]
    ws.append(dau)
    for c in range(1, len(dau) + 1):
        ws.cell(row=1, column=c).font, ws.cell(row=1, column=c).fill = _CHU_DAU, _NEN_DAU
    gom: dict[tuple, list] = {}
    for u in goi["don_vi"]:
        gom.setdefault((u["cap"], u["tinh_ma"] or "", u["tinh_ten"] or u["ten"]), []).append(u)
    for (cap, mt, tt), ds in sorted(gom.items(), key=lambda x: (["tinh", "xa", "thon"].index(x[0][0]), x[0][1])):
        o = [v for u in ds for v in u["truong"].values()]
        dem = {s_: sum(1 for v in o if v["trang_thai"] == s_ and _co(v)) for s_ in ("dat", "cho_duyet", "loi")}
        ws.append([CAP_NHAN[cap], mt, tt, len(ds), sum(_co(v) for v in o), dem["dat"], dem["cho_duyet"],
                   dem["loi"], len(o), f"{dem['dat'] / len(o):.0%}" if o else "-"])
    for i, w in enumerate([14, 8, 24, 10, 12, 8, 10, 8, 9, 10], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "D2"


def _sheet_don_vi(wb: Workbook, ten_sheet: str, ds: list[dict], truong: list[dict]) -> None:
    """Mỗi đơn vị một dòng; mỗi trường trong schema một cột — đúng khoá và giá trị như JSON."""
    ws = wb.create_sheet(_TEN_SHEET_XAU.sub(" ", ten_sheet)[:31])
    co_dinh = ["Mã", "Tên đơn vị", "Loại", "Thuộc"]
    ws.append([""] * len(co_dinh) + [t["nhan_nhom"] for t in truong])
    ws.append(co_dinh + [t["nhan"] for t in truong])
    c = len(co_dinh) + 1
    for nhom in dict.fromkeys(t["nhan_nhom"] for t in truong):
        n = sum(1 for t in truong if t["nhan_nhom"] == nhom)
        if n > 1:
            ws.merge_cells(start_row=1, start_column=c, end_row=1, end_column=c + n - 1)
        o = ws.cell(row=1, column=c)
        o.font, o.fill, o.alignment = Font(bold=True, color="1F4E79"), _NEN_NHOM, Alignment(horizontal="center")
        c += n
    for col in range(1, len(co_dinh) + len(truong) + 1):
        o = ws.cell(row=2, column=col)
        o.font, o.fill, o.alignment = _CHU_DAU, _NEN_DAU, Alignment(wrap_text=True, vertical="center")

    for u in sorted(ds, key=lambda x: x["ma"]):
        hang = [u["ma"], u["ten"], LOAI_NHAN.get(u["loai"], u["loai"]), u["tinh_ten"] if u["cap"] != "tinh" else None]
        to: list[tuple[int, PatternFill]] = []
        for i, t in enumerate(truong):
            v = u["truong"][t["khoa"]]
            hang.append(_sach_o(_hien_thi(v["gia_tri"], t["kieu"])))
            if _co(v) and v["trang_thai"] == "loi":
                to.append((len(co_dinh) + i + 1, _NEN_LOI))
            elif _co(v) and (v["trang_thai"] == "cho_duyet" or v["canh_bao"]
                             or (v["nguon"] and not v["nguon"]["da_kiem_chung"])):
                to.append((len(co_dinh) + i + 1, _NEN_CHO))
        ws.append(hang)
        r = ws.max_row
        for col, nen in to:
            ws.cell(row=r, column=col).fill = nen
        for col in range(1, len(hang) + 1):
            ws.cell(row=r, column=col).alignment = Alignment(wrap_text=True, vertical="top")

    rong = {"van_ban": 28, "ban_ghi": 40, "danh_sach": 30, "so": 12, "ngay": 12, "ma_so": 10,
            "dien_thoai": 16, "email": 26, "url": 28, "toa_do": 20, "anh": 20}
    for i, w in enumerate([8, 24, 9, 18] + [rong.get(t["kieu"], 20) for t in truong], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[2].height = 45
    ws.freeze_panes = "C3"
    ws.auto_filter.ref = f"A2:{get_column_letter(len(co_dinh) + len(truong))}{ws.max_row}"


def _sheet_nguon(wb: Workbook, goi: dict) -> None:
    """Mọi ô có giá trị trong JSON (kể cả lỗi/chờ duyệt) — một dòng, kèm nguồn và bằng chứng."""
    ws = wb.create_sheet("Nguồn & bằng chứng")
    dau = ["Tỉnh/Thành phố", "Mã", "Tên đơn vị", "Thông tin", "Giá trị", "Trạng thái", "Độ tin nguồn",
           "Đã kiểm chứng", "Tên nguồn", "Đường link", "Câu gốc (bằng chứng)", "Năm số liệu", "Lý do lỗi / cảnh báo"]
    ws.append(dau)
    for c in range(1, len(dau) + 1):
        ws.cell(row=1, column=c).font, ws.cell(row=1, column=c).fill = _CHU_DAU, _NEN_DAU
    for u in goi["don_vi"]:
        for t in goi["schema"][u["cap"]]:
            v = u["truong"][t["khoa"]]
            if not _co(v):
                continue
            n = v["nguon"] or {}
            ws.append([_sach_o(x) for x in [
                u["tinh_ten"] or u["ten"], u["ma"], u["ten"], t["nhan"], _hien_thi(v["gia_tri"], t["kieu"]),
                TRANG_THAI_NHAN.get(v["trang_thai"], v["trang_thai"]), MUC_NHAN.get(n.get("muc"), n.get("muc")),
                ("Có" if n.get("da_kiem_chung") else "Chưa") if n else None,
                n.get("ten"), n.get("url"), v["trich_doan"], v["nam_du_lieu"],
                "; ".join(filter(None, [v["ly_do_loi"], *v["canh_bao"]])) or None,
            ]])
            if v["trang_thai"] == "loi":
                ws.cell(row=ws.max_row, column=6).fill = _NEN_LOI
    for i, w in enumerate([16, 8, 22, 22, 36, 11, 20, 12, 28, 40, 60, 10, 30], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:M{ws.max_row}"


def xuat_excel(ds: list[KetQua], duong_dan: Path | str | None = None, goi: dict | None = None) -> Path:
    """Excel trình bày ĐÚNG gói JSON: Hướng dẫn · Tổng hợp · một sheet mỗi tỉnh (đơn vị cấp xã)
    · sheet cấp tỉnh/thôn nếu gói có · Nguồn & bằng chứng (mọi ô có giá trị)."""
    goi = goi or dung_goi(ds)
    theo: dict[tuple, list] = {}
    for u in goi["don_vi"]:
        khoa = ("0", "Cấp tỉnh") if u["cap"] == "tinh" else (
            ("2" + (u["tinh_ma"] or ""), f"Thôn – {u['tinh_ten']}") if u["cap"] == "thon"
            else ("1" + (u["tinh_ma"] or "zz"), u["tinh_ten"] or "(không rõ tỉnh)"))
        theo.setdefault(khoa, []).append(u)

    wb = Workbook()
    wb.remove(wb.active)
    _sheet_huong_dan(wb, datetime.now().strftime("%d/%m/%Y %H:%M"), len(goi["don_vi"]))
    _sheet_tong_hop(wb, goi)
    for (_, ten), ds_u in sorted(theo.items()):
        _sheet_don_vi(wb, ten, ds_u, goi["schema"][ds_u[0]["cap"]])
    _sheet_nguon(wb, goi)

    duong_dan = Path(duong_dan) if duong_dan else (
        GOC_BAN_GIAO / f"ban_giao_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    wb.save(duong_dan)
    return duong_dan


# ----------------------------------------------------------------------------- Kiểm khớp
def _la(v) -> list:
    """Mọi giá trị lá (bỏ rỗng/bool) của một giá trị JSON lồng nhau."""
    if isinstance(v, dict):
        return [x for vv in v.values() for x in _la(vv)]
    if isinstance(v, list):
        return [x for vv in v for x in _la(vv)]
    return [] if v in (None, "") or isinstance(v, bool) else [v]


def _chuan(s) -> str:
    return re.sub(r"[^0-9a-zà-ỹđ]", "", str(s).lower())


def _o_chua(x, o) -> bool:
    """Ô Excel `o` có thể hiện giá trị lá `x` của JSON không."""
    if isinstance(x, (int, float)):
        so = [float(m.replace(".", "").replace(",", ".")) if "," in m else float(m)
              for m in re.findall(r"-?\d[\d.,]*\d|\d", str(o))]
        if isinstance(o, (int, float)):
            so.append(float(o))
        return any(abs(m - x) < 1e-9 for m in so) or _chuan(x) in _chuan(o)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", str(x)):
        return "/".join(reversed(x.split("-"))) in str(o)
    return _chuan({"toan_bo": "toàn bộ", "mot_phan": "một phần"}.get(x, x)) in _chuan(o)


def kiem_xuat(tep_json: Path | None = None, tep_xlsx: Path | None = None) -> tuple[dict, dict]:
    """So từng ô: mọi giá trị JSON (cả lá lồng nhau) và nguồn của nó phải có ở sheet tỉnh và
    sheet "Nguồn & bằng chứng". Mặc định lấy cặp tệp mới nhất. Trả (đếm, ví dụ lệch)."""
    import collections
    from openpyxl import load_workbook

    tep_json = tep_json or sorted(GOC_BAN_GIAO.glob("ban_giao_*.json"))[-1]
    tep_xlsx = tep_xlsx or sorted(GOC_BAN_GIAO.glob("ban_giao_*.xlsx"))[-1]
    d = json.loads(Path(tep_json).read_text(encoding="utf-8"))
    wb = load_workbook(tep_xlsx, read_only=True)
    nhan = {t["khoa"]: t["nhan"] for t in d["schema"]["xa"]}
    nguon = {(r[1], r[3]): r for r in list(wb["Nguồn & bằng chứng"].iter_rows(values_only=True))[1:]}
    rong: dict = {}
    for ws in wb.worksheets[2:-1]:
        dong = list(ws.iter_rows(values_only=True))
        for r in dong[2:]:
            rong.update({(r[0], h): v for h, v in zip(dong[1], r)})
    dem, vd = collections.Counter(), collections.defaultdict(list)
    for u in d["don_vi"]:
        for k, t in u["truong"].items():
            khoa = (u["ma"], nhan.get(k, k))
            s = nguon.get(khoa)
            if t["gia_tri"] is None:
                dem["json rỗng, excel có"] += bool(s) or rong.get(khoa) not in (None, "")
                continue
            dem["ô"] += 1
            if not s:
                dem["thiếu dòng nguồn"] += 1
                continue
            ng = t.get("nguon") or {}
            la = _la(t["gia_tri"])
            for ten, ok in (("bảng rộng", all(_o_chua(x, rong.get(khoa)) for x in la)),
                            ("giá trị nguồn", all(_o_chua(x, s[4]) for x in la)),
                            ("trạng thái", bool(s[5])), ("tên nguồn", ng.get("ten") == s[8]),
                            ("url", ng.get("url") == s[9]),
                            ("trích đoạn", (t.get("trich_doan") or None) == (s[10] or None))):
                if not ok:
                    dem[ten] += 1
                    vd[ten].append((khoa, str(t["gia_tri"])[:60], str(s[4])[:60]))
    wb.close()
    return dict(dem), dict(vd)
