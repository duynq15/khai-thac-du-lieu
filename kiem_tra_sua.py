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
for sh in ("dieu-phoi.sh",):
    s = open(sh, encoding="utf-8").read()
    assert '"$rc" -ne 75' in s and "--khong-trinh-duyet" in s, sh

# --- refactor nguồn theo tỉnh ---
import tempfile
from pathlib import Path

from khai_thac.models import DonVi
from khai_thac.nguon import bang, trang_xa
from khai_thac.quy_trinh import _doan_quanh_ten
from khai_thac.store import Kho

with tempfile.TemporaryDirectory() as d:
    kho = Kho(Path(d) / "t.sqlite")
    # Tên trùng giữa 2 tỉnh: phải ra đúng mã theo tỉnh
    kho.ghi_don_vi([DonVi("19996", "Phường Hương Trà", "phuong", tinh_ma="46"),
                    DonVi("20350", "Phường Hương Trà", "phuong", tinh_ma="48"),
                    DonVi("00454", "Xã Đông Anh", "xa", tinh_ma="01",
                          don_vi_cu_hop_thanh=["Xã Uy Nỗ (phần còn lại sau khi sáp nhập vào xã Thư Lâm)"])])
    assert Kho.tim_ma_xa(kho.ban_do_ma("46"), "Hương Trà") == "19996"
    assert Kho.tim_ma_xa(kho.ban_do_ma("48"), "Phường Hương Trà") == "20350"
    assert Kho.tim_ma_xa(kho.ban_do_ma("01"), "Uy Nỗ") == "00454"   # tên cũ -> xã mới

    # Nguồn bang: bảng HTML ghép theo tên, số kiểu Việt
    html = ("<table><tr><th>STT</th><th>Tên đơn vị</th><th>Diện tích (km²)</th><th>Dân số</th></tr>"
            "<tr><td>1</td><td>Phường Hương Trà</td><td>48,68</td><td>118.183</td></tr>"
            "<tr><td>2</td><td>Xã Không Có</td><td>1</td><td>2</td></tr></table>")
    import khai_thac.nguon.bang as b
    b.goi = lambda url, **k: type("R", (), {"status_code": 200, "text": html})()
    r = bang.nap(kho, {"ma": "t_bang", "loai": "bang", "dinh_dang": "html", "url": "http://x/{tinh_ma}",
                       "khoa_xa": {"ten": "Tên đơn vị"}, "cot": {"dien_tich_km2": "Diện tích", "dan_so": "Dân số"},
                       "muc": "A"}, "46")
    assert r["so_xa"] == 1 and r["khong_khop"] == ["Xã Không Có"], r
    gt = {x["truong"]: x["gia_tri"] for x in kho.lay_ket_qua(don_vi_ma="19996")}
    assert gt == {"dien_tich_km2": "48.68", "dan_so": "118183"}, gt
    assert kho.truong_da_dat("19996") == {"dien_tich_km2", "dan_so"}
    assert not kho.truong_da_dat("20350")                               # không lan sang tỉnh khác

    # Nhiều cột → một trường toa_do {lat, lon}
    import json, khai_thac.http as _http
    du_lieu_json = {"data": [{"code": "19996", "centroid_lat": 16.4, "centroid_lng": 107.6}]}
    _http.goi = lambda url, **k: type("R", (), {"status_code": 200, "text": "",
                                                "json": lambda self=None: du_lieu_json})()
    bang.nap(kho, {"ma": "t_toa_do", "loai": "bang", "dinh_dang": "json", "url": "http://x/{tinh_ma}",
                   "duong_dan": "data", "khoa_xa": {"ma": "code"},
                   "cot": {"ranh_gioi_vi_tri": ["centroid_lat", "centroid_lng"]}, "muc": "B"}, "46")
    toa_do = kho.lay_ket_qua(don_vi_ma="19996", nhom="thong_tin_chung")
    assert [(json.loads(x["gia_tri"]), x["kieu"]) for x in toa_do if x["truong"] == "ranh_gioi_vi_tri"] \
        == [({"lat": 16.4, "lon": 107.6}, "toa_do")]

# Cổng xã theo mẫu của tỉnh; tỉnh chưa cấu hình → không đoán bừa
assert trang_xa._doan_theo_mau({"ma": "x", "ten": "Phường Vỹ Dạ", "loai": "phuong", "tinh_ma": "46"}) \
    == ["https://vyda.hue.gov.vn"]
assert trang_xa._doan_theo_mau({"ma": "x", "ten": "Xã A", "loai": "xa", "tinh_ma": "99"}) == []
assert bang._so("198.59") == 198.59 and bang._so("118.183") == 118183 and bang._so("48,68") == 48.68

# Trang cấp tỉnh: chỉ đoạn quanh tên xã
vb = "x" * 900 + " Đình Cổ Loa thuộc xã Đông Anh. " + "y" * 900 + " xã Thư Lâm."
d = _doan_quanh_ten(vb, "Xã Đông Anh", rong=100)
assert "Cổ Loa" in d and "Thư Lâm" not in d and _doan_quanh_ten(vb, "Xã Mê Linh") == ""

# Nạp tay: tên cũ kèm quận khớp khi cả ngoặc trùng; tên trần trùng nhiều nơi thì bỏ
import json as _json

from khai_thac.nguon import tay

with tempfile.TemporaryDirectory() as d:
    kho = Kho(Path(d) / "t.sqlite")
    kho.ghi_don_vi([DonVi("26506", "Phường Vũng Tàu", "phuong", tinh_ma="79",
                          don_vi_cu_hop_thanh=["Phường 5 (thành phố Vũng Tàu)", "Phường 1"]),
                    DonVi("26740", "Phường Sài Gòn", "phuong", tinh_ma="79",
                          don_vi_cu_hop_thanh=["Phường 5", "Phường 1"])])
    p = Path(d) / "x.json"
    p.write_text(_json.dumps({"ma": "t", "ten": "t", "url": "http://x", "muc": "B", "tinh_ma": "79",
                              "dong": [{"ten_xa": "Phường 5 (thành phố Vũng Tàu)", "truong": {"dan_so": 1},
                                        "trich_doan": "z"},
                                       {"ten_xa": "Phường 9 (thành phố Vũng Tàu)", "truong": {"dan_so": 9},
                                        "trich_doan": "z"}]},
                             ensure_ascii=False), encoding="utf-8")
    tay.nap_tep(kho, p)
    assert [x["gia_tri"] for x in kho.lay_ket_qua(don_vi_ma="26506")] == ["1"]
    assert not kho.lay_ket_qua(don_vi_ma="26740")

print("OK")

