"""Bóc dữ liệu từ văn bản pháp lý gốc (PDF/Excel) — Đề án sắp xếp ĐVHC, phụ lục Nghị quyết.

Khác với cào web, ở đây bằng chứng là chính tệp văn bản: mỗi giá trị gắn
  * mã băm SHA-256 của tệp gốc,
  * vị trí cụ thể (trang/sheet, dòng),
nên máy kiểm chứng được và cán bộ mở đúng tệp để đối chiếu.

Dùng: uv run khai-thac phap-ly --tep <duong-dan> [--tinh-ma 31]
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..models import DAT, KetQua, Luot
from ..store import Kho
from ..text import bo_dau, chuan_hoa

NGUON_MA = "vbpl_chinh_thong"
NGUON_TEN = "Văn bản pháp lý (Đề án/Nghị quyết sắp xếp ĐVHC)"


def bam_sha256(tep: str | Path) -> str:
    h = hashlib.sha256()
    with open(tep, "rb") as f:
        for khoi in iter(lambda: f.read(1 << 20), b""):
            h.update(khoi)
    return h.hexdigest()


def _so(chuoi: str) -> float | None:
    """'1.234,5' -> 1234.5 ; '15,6' -> 15.6 ; '48.200' -> 48200."""
    if chuoi is None:
        return None
    m = re.search(r"\d[\d.\s]*(?:,\d+)?", str(chuoi))
    if not m:
        return None
    s = m.group(0).replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


# ------------------------------------------------------------- đọc bảng
def _bang_excel(tep: Path) -> list[dict]:
    from openpyxl import load_workbook

    kq: list[dict] = []
    wb = load_workbook(tep, read_only=True, data_only=True)
    for ws in wb.worksheets:
        rows = [[("" if c is None else str(c)) for c in row] for row in ws.iter_rows(values_only=True)]
        if any(any(x.strip() for x in r) for r in rows):
            kq.append({"vi_tri": f"sheet '{ws.title}'", "rows": rows})
    wb.close()
    return kq


def _bang_pdf(tep: Path) -> list[dict]:
    try:
        import pdfplumber
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "Chưa cài pdfplumber. Chạy: uv sync --extra pdf"
        ) from e

    kq: list[dict] = []
    with pdfplumber.open(tep) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            for j, bang in enumerate(page.extract_tables() or [], 1):
                rows = [[("" if c is None else str(c)) for c in row] for row in bang]
                if rows:
                    kq.append({"vi_tri": f"trang {i}, bảng {j}", "rows": rows})
    return kq


def doc_bang(tep: Path) -> list[dict]:
    duoi = tep.suffix.lower()
    if duoi in (".xlsx", ".xlsm", ".xls"):
        return _bang_excel(tep)
    if duoi == ".pdf":
        return _bang_pdf(tep)
    raise SystemExit(f"Không hỗ trợ định dạng: {duoi}")


# --------------------------------------------------- nhận diện cột
_COT = {
    "ten": ("tên đơn vị", "tên xã", "tên phường", "đơn vị hành chính", "tên đvhc"),
    "dien_tich": ("diện tích", "dt tự nhiên", "diện tích tự nhiên"),
    "dan_so": ("dân số", "quy mô dân số", "nhân khẩu"),
    "tru_so": ("trụ sở", "phương án trụ sở", "nơi làm việc", "địa chỉ trụ sở"),
}


def _tim_cot(rows: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    """Tìm dòng tiêu đề và chỉ số cột cho từng trường."""
    for i, row in enumerate(rows[:15]):
        ch = [chuan_hoa(c) for c in row]
        cot: dict[str, int] = {}
        for truong, tu_khoa in _COT.items():
            for j, c in enumerate(ch):
                if any(k in c for k in (chuan_hoa(t) for t in tu_khoa)):
                    cot[truong] = j
                    break
        if "ten" in cot and ("dien_tich" in cot or "dan_so" in cot):
            return i, cot
    return None


def _khop(kho: Kho, tinh_ma: str | None) -> dict[str, str]:
    """Bản đồ tên chuẩn hoá -> mã đơn vị (có cả bản bỏ tiền tố)."""
    bd: dict[str, str] = {}
    for row in kho.tim_don_vi(tinh_ma=tinh_ma, cap="xa"):
        ma, ten = row["ma"], row["ten"]
        bd[chuan_hoa(ten)] = ma
        bd[chuan_hoa(re.sub(r"^(Xã|Phường|Đặc khu|Thị trấn|Tỉnh|Thành phố)\s+", "", ten))] = ma
    return bd


def nap(kho: Kho, tep: str | Path, *, tinh_ma: str | None = None) -> dict:
    tep = Path(tep)
    if not tep.is_file():
        raise SystemExit(f"Không thấy tệp: {tep}")

    bam = bam_sha256(tep)
    bang = doc_bang(tep)
    ma2ten = {r["ma"]: r["ten"] for r in kho.tim_don_vi(cap="xa")}
    khop = _khop(kho, tinh_ma)

    luot = Luot(ma=f"phap-ly-{bam[:8]}", pham_vi=str(tep.name),
                nhom_du_lieu="phap_ly", bat_dau=__import__("datetime").datetime.now().isoformat(timespec="seconds"))
    kho.ghi_luot(luot)

    ket: list[KetQua] = []
    so_dong = 0
    khong_khop: list[str] = []

    for bang_ in bang:
        vitri = bang_["vi_tri"]
        rows = bang_["rows"]
        dau = _tim_cot(rows)
        if not dau:
            continue
        i_dau, cot = dau
        for k, row in enumerate(rows[i_dau + 1:], start=i_dau + 2):
            if cot["ten"] >= len(row):
                continue
            ten = row[cot["ten"]].strip()
            if not ten or _so(ten) is not None:
                continue
            ma = khop.get(chuan_hoa(ten)) or khop.get(chuan_hoa(ten.replace("Phường ", "").replace("Xã ", "")))
            if not ma:
                khong_khop.append(ten)
                continue
            trich = f"{NGUON_TEN} · {vitri} · dòng {k} · sha256:{bam[:12]}"
            for truong, kieu in (("dien_tich_km2", "so"), ("dan_so", "so"), ("tru_so", "van_ban")):
                j = cot.get({"dien_tich_km2": "dien_tich", "dan_so": "dan_so", "tru_so": "tru_so"}[truong])
                if j is None or j >= len(row) or not str(row[j]).strip():
                    continue
                gt = _so(row[j]) if kieu == "so" else row[j].strip()
                if gt is None:
                    continue
                ket.append(KetQua(
                    don_vi_ma=ma, don_vi_ten=ma2ten.get(ma, ten), cap="xa",
                    nhom="hanh_chinh_dan_cu",
                    truong=truong, gia_tri=gt, kieu=kieu,
                    nguon_ma=NGUON_MA, nguon_ten=NGUON_TEN, nguon_url=tep.name,
                    nguon_muc="A", trich_doan=trich, diem_tin=100, trang_thai=DAT,
                ))
                so_dong += 1

    kho.ghi_ket_qua(ket, luot.ma)
    luot.ket_thuc = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    luot.so_ket_qua = len(ket)
    luot.so_dat = len(ket)
    kho.ghi_luot(luot)
    return {"tep": tep.name, "sha256": bam, "so_bang": len(bang), "so_ket_qua": len(ket),
            "khong_khop": khong_khop}
