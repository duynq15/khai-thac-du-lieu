"""Mô hình dữ liệu dùng chung trong bộ khai thác."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# Trạng thái của một kết quả trường
DAT = "dat"          # đạt kiểm tra, sẵn sàng vào hàng chờ duyệt
LOI = "loi"          # không đạt kiểm tra
THIEU = "thieu"      # nguồn không có, cần nhập tay
CHO_DUYET = "cho_duyet"
DA_DUYET = "da_duyet"
TU_CHOI = "tu_choi"


def diem_theo_muc(muc: str | None, canh_bao: list | None = None) -> int:
    """Độ tin suy từ hạng nguồn (A 90, B 75, khác 60); có cảnh báo (giá trị chung toàn TP,
    câu ghép từ trường khác…) trừ 10. Nguồn nạp tay/bảng dùng chung, không đặt điểm tuỳ ý."""
    return {"A": 90, "B": 75}.get(muc, 60) - (10 if canh_bao else 0)


@dataclass
class DonVi:
    """Một đơn vị hành chính trong danh mục."""

    ma: str
    ten: str
    loai: str                       # xa | phuong | dac_khu | tinh | thanh_pho | thon
    tinh_ma: str | None = None
    tinh_ten: str | None = None
    parent_ma: str | None = None    # đơn vị cha (thôn thuộc xã nào)
    codename: str | None = None
    # Sắp xếp 2025
    don_vi_cu_hop_thanh: list[str] = field(default_factory=list)
    so_don_vi_cu: int | None = None
    can_cu_phap_ly: str | None = None
    ngay_hieu_luc: str | None = None
    # Nguồn đã dùng (mã nguồn)
    nguon: list[str] = field(default_factory=list)
    # Đối chiếu đa nguồn: có khớp tên giữa các nguồn không
    khop_da_nguon: bool | None = None

    def __post_init__(self) -> None:
        # chuẩn hoá loại đơn vị về khoá nội bộ
        lo = (self.loai or "").lower()
        if lo.startswith("phường") or lo == "phuong":
            self.loai = "phuong"
        elif lo.startswith("đặc khu") or lo == "dac_khu":
            self.loai = "dac_khu"
        elif lo.startswith("xã") or lo == "xa":
            self.loai = "xa"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KetQua:
    """Một trường dữ liệu khai thác được cho một đơn vị."""

    don_vi_ma: str
    don_vi_ten: str
    cap: str
    nhom: str
    truong: str
    gia_tri: Any
    kieu: str = "van_ban"
    nguon_ma: str | None = None
    nguon_ten: str | None = None
    nguon_url: str | None = None
    nguon_muc: str | None = None          # A | B | C
    trich_doan: str | None = None         # câu chứng minh trong nguồn
    diem_tin: int = 0                     # 0..100
    trang_thai: str = DAT
    ly_do_loi: str | None = None
    canh_bao: list[str] = field(default_factory=list)
    nam_du_lieu: int | None = None        # năm của số liệu (màn duyệt mâu thuẫn)
    boc_boi: str | None = None            # "llm" nếu giá trị do LLM bóc (đo đóng góp pha LLM)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Luot:
    """Một lần chạy khai thác, để biết đã lấy gì, khi nào, nguồn nào."""

    ma: str
    pham_vi: str
    nhom_du_lieu: str
    bat_dau: str
    ket_thuc: str | None = None
    so_don_vi: int = 0
    so_ket_qua: int = 0
    so_dat: int = 0
    nguon: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
