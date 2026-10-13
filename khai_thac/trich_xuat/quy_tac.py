"""Trích xuất bằng quy tắc (chạy được cả khi không có LLM)."""

from __future__ import annotations

import re

from ..text import rut_gon

_CAU = re.compile(r"(?<=[.!?…])\s+|\n+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_DIEN_THOAI = re.compile(r"(?:\+84|0)\d(?:[\s.\-]?\d){7,9}")
# "Chủ tịch UBND ...: Nguyễn Văn A" / "Chủ tịch UBND xã là ông Nguyễn Văn A"
_CHU_TICH = re.compile(
    r"chủ tịch\s+ubnd[^:\n]{0,40}?(?::|là)\s*(?:ông|bà|đồng chí)?\s*([A-ZĐ][^\W\d_]+(?:\s+[A-ZĐ][^\W\d_]+){1,3})",
    re.IGNORECASE,
)
# Dạng chân trang: "Nguyễn Văn A - Chủ tịch UBND xã …"
_CHU_TICH_TRUOC = re.compile(
    r"([A-ZĐ][^\W\d_]+(?:\s+[A-ZĐ][^\W\d_]+){1,3})\s*[-–]\s*chủ tịch\s+ubnd",
    re.IGNORECASE,
)
_BI_THU = re.compile(
    r"bí thư\s+(?:đảng\s+uỷ|đảng ủy)[^:\n]{0,30}?(?::|là)\s*(?:ông|bà|đồng chí)?\s*([A-ZĐ][^\W\d_]+(?:\s+[A-ZĐ][^\W\d_]+){1,3})",
    re.IGNORECASE,
)


def tach_cau(van_ban: str) -> list[str]:
    return [c.strip() for c in _CAU.split(van_ban or "") if c.strip()]


def cau_chua(van_ban: str, *tu_khoa: str) -> str | None:
    for cau in tach_cau(van_ban):
        chu = cau.lower()
        if all(t.lower() in chu for t in tu_khoa):
            return rut_gon(cau, 400)
    return None


def tim_email(van_ban: str) -> str | None:
    m = _EMAIL.search(van_ban or "")
    return m.group(0) if m else None


def tim_dien_thoai(van_ban: str) -> str | None:
    for m in _DIEN_THOAI.finditer(van_ban or ""):
        so = re.sub(r"[\s.\-]", "", m.group(0))
        if 9 <= len(so) <= 11:
            return so
    return None


RAC = ("trang chủ", "giới thiệu", "liên hệ", "sitemap", "thông tin liên hệ",
       "bản đồ", "tìm kiếm", "đăng nhập", "tin mới", "xem tiếp", "trước", "sau")


def boc_gioi_thieu(van_ban: str, ten_don_vi: str | None = None,
                   toi_da: int = 800) -> tuple[str, str] | None:
    """Lấy các câu mở đầu làm giới thiệu, trả (giới thiệu, câu chứng minh).

    Ưu tiên câu nhắc đúng tên đơn vị (thường là câu dẫn của bài), rồi mới tới
    các câu dài kế tiếp; bỏ dòng điều hướng và dòng quá ngắn.
    """
    from ..text import chuan_hoa

    cau = tach_cau(van_ban)
    ung_vien: list[str] = []
    for c in cau:
        chu = c.strip()
        if len(chu) < 60 or chu.lower().startswith(RAC):
            continue
        ung_vien.append(chu)

    if not ung_vien:
        return None

    moc = 0
    if ten_don_vi:
        ten_chuan = chuan_hoa(ten_don_vi)
        for i, c in enumerate(ung_vien):
            if ten_chuan and ten_chuan in chuan_hoa(c):
                moc = i
                break

    gom: list[str] = []
    for c in ung_vien[moc:]:
        gom.append(c)
        if sum(len(x) for x in gom) >= toi_da:
            break
    gioi_thieu = rut_gon(" ".join(gom), toi_da)
    return gioi_thieu, rut_gon(gom[0], 300)


def boc_theo_truong(van_ban: str, truong: str) -> tuple[str, str] | None:
    """Bóc một trường đơn giản bằng từ khoá. Trả (giá trị, câu chứng minh).

    Trường liên hệ/chức danh chỉ nhận câu ngắn (dạng dòng chân trang), tránh
    nhận nhầm câu dài trong bài có nhắc từ khoá cho có.
    """
    TU_KHOA = {
        "nguon_goc_ten_xa": ("nguồn gốc", "tên"),
        "ten_nom": ("tên nôm",),
        "nguon_goc_ten_lang": ("nguồn gốc", "làng"),
        "tich_lang": ("tích", "làng"),
        "chu_tich_ubnd": ("chủ tịch ubnd",),
        "tru_so": ("địa chỉ",),
        "gio_lam_viec": ("giờ làm việc",),
        "nha_van_hoa": ("nhà văn hoá",),
    }
    NGAN = {"chu_tich_ubnd", "tru_so", "gio_lam_viec", "nha_van_hoa"}

    tu_khoa = TU_KHOA.get(truong)
    if not tu_khoa:
        return None

    # Chủ tịch UBND: bắt tên theo mẫu (sau từ khoá, hoặc trước từ khoá ở chân trang)
    if truong == "chu_tich_ubnd":
        for mau in (_CHU_TICH_TRUOC, _CHU_TICH):
            for m in mau.finditer(van_ban):
                ten = m.group(1).strip()
                # IGNORECASE làm [A-ZĐ] khớp cả chữ thường → tự kiểm: mọi từ phải viết hoa đầu
                if all(w[0].isupper() for w in ten.split()):
                    return ten, rut_gon(m.group(0), 200)

    for cau in tach_cau(van_ban):
        chu = cau.lower()
        if not all(t in chu for t in tu_khoa):
            continue
        if truong in NGAN and len(cau) > 240:
            continue
        return rut_gon(cau, 300), rut_gon(cau, 300)
    return None
