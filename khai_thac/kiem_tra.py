"""Kiểm tra giá trị khai thác trước khi cho vào hàng chờ duyệt.

Kết quả: (trang_thai, diem_tin, ly_do_loi, canh_bao). Quy tắc lấy từ cấu hình
trường (`kiem_tra: [...]`), bối cảnh truyền vào gồm đoạn chứng minh và toàn văn
nguồn để đối chiếu.
"""

from __future__ import annotations

import re
from datetime import date

from .nguon.toa_do import trong_viet_nam
from .text import chuan_hoa

_NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
_DIEN_THOAI = re.compile(r"^(?:\+84|0)\d{8,10}$")
# Từ chỉ có trong tiêu đề tin/thông báo, không có trong giá trị thật của trường hồ sơ xã
_TIN = re.compile(r"hội nghị|tập huấn|thông báo|đối thoại|chỉ đạo|tuyên truyền|triển khai|trao tặng|"
                  r"niêm yết|tiếp công dân|giao hữu|rộn ràng|đại hội|kỳ họp|tuyên dương|lấy ý kiến|chào cờ",
                  re.IGNORECASE)
# Chữ cố định của khung cổng TTĐT (chân trang, menu, khẩu hiệu) bóc nhầm thành nội dung
_KHUNG_CONG = re.compile(r"^(cổng thông tin|văn phòng ủy ban|chịu trách nhiệm|quyết định|nhanh chóng, thuận tiện)",
                         re.IGNORECASE)

def la_tieu_de_tin(gia_tri, *, xet_chu_hoa: bool = True) -> bool:
    """Giá trị là tiêu đề tin/câu "không có thông tin" bóc nhầm từ trang chủ cổng xã."""
    if isinstance(gia_tri, dict):
        gia_tri = gia_tri.get("ten") or ""
    if isinstance(gia_tri, list):
        # Phần tử danh sách (tên làng nghề, lễ hội) hay viết hoa thật → chỉ xét từ khoá
        return any(la_tieu_de_tin(x, xet_chu_hoa=False) for x in gia_tri)
    if not isinstance(gia_tri, str) or len(gia_tri) > 300:
        return False
    if chuan_hoa(gia_tri).startswith("khong co thong tin") or _TIN.search(gia_tri):
        return True
    chu = [c for c in gia_tri if c.isalpha()]
    return xet_chu_hoa and len(chu) >= 20 and sum(c.isupper() for c in chu) > 0.7 * len(chu)



def _diem_tru(diem: int, tru: int) -> int:
    return max(0, diem - tru)


def kiem(
    truong_cfg: dict,
    gia_tri,
    *,
    trich_doan: str | None = None,
    nguon_van_ban: str | None = None,
    boi_canh: dict | None = None,
) -> tuple[str, int, str | None, list[str]]:
    boi_canh = boi_canh or {}
    quy_tac = truong_cfg.get("kiem_tra") or []
    diem = 100
    canh_bao: list[str] = []

    if gia_tri in (None, "", [], {}):
        if truong_cfg.get("bat_buoc"):
            return "loi", 0, "Trường bắt buộc nhưng chưa có giá trị", canh_bao
        return "thieu", 0, None, canh_bao

    if la_tieu_de_tin(gia_tri):
        return "loi", 0, "Tiêu đề tin/thông báo, không phải giá trị của trường", canh_bao

    for qt in quy_tac:
        if qt == "khong_rong":
            if not str(gia_tri).strip():
                return "loi", 0, "Giá trị rỗng", canh_bao

        elif qt == "trong_danh_sach":
            hop_le = truong_cfg.get("gia_tri_cho_phep") or []
            if hop_le and gia_tri not in hop_le:
                return "loi", 0, f"Giá trị ngoài danh sách cho phép: {gia_tri}", canh_bao

        elif qt == "ma_dvhc":
            so = str(gia_tri)
            if not so.isdigit() or not (2 <= len(so) <= 6):
                return "loi", 10, f"Mã ĐVHC không hợp lệ: {so}", canh_bao

        elif qt == "ngay":
            if not (isinstance(gia_tri, str) and _NGAY.match(gia_tri)):
                return "loi", 10, f"Ngày sai định dạng (cần YYYY-MM-DD): {gia_tri}", canh_bao
            y = int(str(gia_tri)[:4])
            if not (1900 <= y <= date.today().year + 1):
                canh_bao.append(f"Năm bất thường: {y}")
                diem = _diem_tru(diem, 20)

        elif qt == "so_duong":
            try:
                if float(gia_tri) <= 0:
                    return "loi", 20, f"Phải là số dương: {gia_tri}", canh_bao
            except (TypeError, ValueError):
                return "loi", 20, f"Không phải số: {gia_tri}", canh_bao

        elif qt == "so_khong_am":
            try:
                if float(gia_tri) < 0:
                    return "loi", 20, f"Không được âm: {gia_tri}", canh_bao
            except (TypeError, ValueError):
                return "loi", 20, f"Không phải số: {gia_tri}", canh_bao

        elif qt == "email":
            if not _EMAIL.match(str(gia_tri)):
                return "loi", 20, f"Email không hợp lệ: {gia_tri}", canh_bao

        elif qt == "dien_thoai":
            so = re.sub(r"[\s.\-()]", "", str(gia_tri))
            if so.startswith(("1800", "1900")):   # tổng đài chung (vd 18001260 của Đà Nẵng), không phải số xã
                return "loi", 0, f"Số tổng đài, không phải số UBND xã: {gia_tri}", canh_bao
            if not _DIEN_THOAI.match(so):
                canh_bao.append(f"Số điện thoại chưa chuẩn: {gia_tri}")
                diem = _diem_tru(diem, 30)

        elif qt == "url":
            if not str(gia_tri).startswith(("http://", "https://")):
                return "loi", 20, f"URL không hợp lệ: {gia_tri}", canh_bao

        elif qt == "trong_viet_nam":
            if isinstance(gia_tri, dict) and "lat" in gia_tri:
                if not trong_viet_nam(float(gia_tri["lat"]), float(gia_tri["lon"])):
                    return "loi", 0, f"Toạ độ ngoài lãnh thổ: {gia_tri}", canh_bao

        elif qt == "trong_tinh":
            # bbox khai báo trong config/nguon/<tỉnh>.yaml; tỉnh chưa khai báo thì bỏ qua
            tinh = boi_canh.get("tinh_ten", "")
            bb = boi_canh.get("bbox")
            if bb and isinstance(gia_tri, dict) and "lat" in gia_tri:
                lat0, lat1, lon0, lon1 = bb
                if not (lat0 <= float(gia_tri["lat"]) <= lat1 and lon0 <= float(gia_tri["lon"]) <= lon1):
                    canh_bao.append(f"Toạ độ nằm ngoài bbox tỉnh {tinh}")
                    diem = _diem_tru(diem, 25)

        elif qt == "ho_ten":
            # Họ tên người: 2–5 từ viết hoa đầu, không chứa chức danh / câu văn
            g = str(gia_tri).strip()
            w = g.split()
            if (not 2 <= len(w) <= 5 or not all(x[:1].isupper() for x in w)
                    or any(t in g.lower() for t in ("chủ tịch", "ubnd", "phường", "xã ", "thành phố", "ban "))):
                return "loi", 0, "Không phải họ tên người (chức danh/câu văn)", canh_bao

        elif qt == "co_trich_dan":
            if nguon_van_ban and trich_doan:
                if chuan_hoa(trich_doan) and chuan_hoa(trich_doan) not in chuan_hoa(nguon_van_ban):
                    return "loi", 5, "Trích dẫn không xuất hiện trong nguồn (nghi bịa)", canh_bao
            elif not trich_doan:
                canh_bao.append("Thiếu trích dẫn chứng minh")
                diem = _diem_tru(diem, 40)

        elif qt == "cau_dien_giai":
            # Trường diễn giải (diên cách, nguồn gốc tên) phải là câu: tên đơn vị trơn, email,
            # tiêu đề menu hay chữ chân trang cổng xã không phải giá trị
            g = str(gia_tri).strip()
            if len(g.split()) < 7 or "@" in g or _KHUNG_CONG.match(g):
                return "loi", 0, "Không phải câu diễn giải (tên đơn vị/menu/chân trang cổng)", canh_bao

        elif qt == "do_dai_toi_da_800":
            if len(str(gia_tri)) > 800:
                canh_bao.append(f"Vượt 800 ký tự ({len(str(gia_tri))})")
                diem = _diem_tru(diem, 10)

        elif qt == "co_nguon_anh":
            if not boi_canh.get("nguon_url"):
                canh_bao.append("Ảnh chưa ghi nguồn")
                diem = _diem_tru(diem, 50)

    trang_thai = "dat" if diem >= 60 else "loi"
    return trang_thai, diem, None, canh_bao


def doi_chieu_da_nguon(gia_tri_a, gia_tri_b) -> bool:
    """Hai nguồn khớp nhau sau khi chuẩn hoá (dùng cho mã/tên ĐVHC)."""
    return chuan_hoa(str(gia_tri_a)) == chuan_hoa(str(gia_tri_b))
