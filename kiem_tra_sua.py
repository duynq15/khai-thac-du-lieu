"""Tự kiểm phần sửa 13/10 (không cần mạng, không cần Ollama): uv run python kiem_tra_sua.py"""

from khai_thac import cau_hinh
from khai_thac.nguon import danh_muc, trinh_duyet
from khai_thac.quy_trinh import MA_THOAT_KHOI_DONG_LAI, chuan_ban_ghi
from khai_thac.trich_xuat.ollama import _prompt, _tach_du

# Bản ghi di tích: bỏ bản ghi không tên / tên không có trong nguồn (LLM bịa)
vb = "Đình Đài Bi thờ An Dương Vương, xếp hạng di tích quốc gia năm 1994."
ds, bo = chuan_ban_ghi([{"ten": "Đình Đài Bi", "xep_hang": "Quốc gia", "loai": None},
                        {"ten": "Chùa Bịa"}, {"loai": "Đình"}, ""], vb)
assert ds == [{"ten": "Đình Đài Bi", "xep_hang": "Quốc gia"}] and bo == ["Chùa Bịa"], (ds, bo)
assert chuan_ban_ghi([], vb) == (None, [])

# Prompt liệt kê đúng thuộc tính bản ghi; năm số liệu chỉ nhận số hợp lệ
p = _prompt(vb, cau_hinh.ds_truong("xa", "di_tich"))
assert '"di_tich_xep_hang": [{"ten"' in p and '"thuoc_thon"' in p
r = _tach_du({"ket_qua": [{"khoa": "a", "gia_tri": 1, "nam": 2024}, {"khoa": "b", "nam": "x"}]})
assert r["a"]["nam"] == 2024 and r["b"]["nam"] is None

# Phạm vi nhập đơn vị cũ
assert danh_muc._pham_vi("Xã Uy Nỗ (phần còn lại sau khi sáp nhập vào xã Thư Lâm)") == "mot_phan"
assert danh_muc._pham_vi("Xã Cổ Loa") == "toan_bo"

# Trường màn hình đã có trong cấu hình
khoa = lambda cap, nhom: {t["khoa"] for t in cau_hinh.ds_truong(cap, nhom)}
assert "so_ho" in khoa("xa", "hanh_chinh_dan_cu")
assert "don_vi_cu_chi_tiet" in khoa("xa", "sap_xep_2025")
assert {"mat_do_dan_so"} <= khoa("tinh", "thong_tin_chung")
assert {"cac_xom", "anh_thon"} <= khoa("thon", "thong_tin_chung")

# Tắt trình duyệt cho pha LLM; mã thoát khớp với chay_lai() trong các script .sh
trinh_duyet.tat()
assert not trinh_duyet.san_sang()
assert MA_THOAT_KHOI_DONG_LAI == 75
for sh in ("dieu-phoi.sh", "chay-qua-dem.sh", "chay-mot-tinh.sh"):
    s = open(sh, encoding="utf-8").read()
    assert '"$rc" -ne 75' in s and "--khong-trinh-duyet" in s, sh

print("OK")
