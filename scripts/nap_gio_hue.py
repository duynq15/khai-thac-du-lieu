"""Back up DB, then add verified contact values (email/chu_tich from commune portals) and
Hai Phong city-wide office hours (TB 233/TB-UBND) — only where the export has no value."""
import sys, json, glob, shutil, time
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from datetime import datetime
from khai_thac.store import Kho
from khai_thac.models import KetQua, Luot

d = json.load(open(sorted(glob.glob(G + "/du_lieu/ban_giao/ban_giao_*.json"))[-1], encoding="utf-8"))
u_by = {u["ma"]: u for u in d["don_vi"]}
trong = lambda ma, k: u_by[ma]["truong"].get(k, {}).get("gia_tri") is None

LE_OLD = [  # (ma, truong, gia_tri, kieu, url, trich_doan)
    ("20455", "email", "taygiaing@danang.gov.vn", "email", "https://taygiang.danang.gov.vn", "Email: taygiaing@danang.gov.vn"),
    ("20506", "email", "thuongduc@danang.gov.vn", "email", "https://thuongduc.danang.gov.vn", "Email: thuongduc@danang.gov.vn"),
    ("20506", "chu_tich_ubnd", "Phan Trung Phi", "van_ban", "https://thuongduc.danang.gov.vn",
     "Trưởng ban Ban biên tập: Đồng chí Phan Trung Phi - Chủ tịch UBND Xã."),
    ("25843", "email", "taynam@tphcm.gov.vn", "email", "https://taynam.hochiminhcity.gov.vn", "Email: taynam@tphcm.gov.vn"),
    ("26743", "email", "benthanh@tphcm.gov.vn", "email", "https://phuongbenthanh.gov.vn", "Email: benthanh@tphcm.gov.vn"),
]
LE = []
HP_URL = "http://antruong.haiphong.gov.vn/tiep-can-thong-tin/thong-bao-gio-lam-viec-cua-cac-co-quan-thanh-pho-hai-phong-767803"
HP_TD = ("Buổi sáng: 7 giờ 30 phút đến 12 giờ 00 phút; Buổi chiều: 13 giờ 30 phút đến 17 giờ 00 phút "
         "(Áp dụng từ thứ Hai đến thứ Sáu hàng tuần)")
HUE_URL = "https://hue.gov.vn/Chuyen-trang/Chuyen-trang-cai-cach-hanh-chinh/Chi-tiet/tb/Quy-dinh-thoi-gian-lam-viec-hanh-chinh-tren-dia-ban-thanh-pho-Hue-785592"
HUE_TD = "Mùa đông (từ tháng 10 đến tháng 3 năm sau), buổi sáng vẫn làm việc từ 7 giờ 30 đến 11 giờ 30; buổi chiều từ 13 giờ đến 17 giờ."
HUE_GT = "Mùa đông (tháng 10 – tháng 3): sáng 7:30–11:30, chiều 13:00–17:00"
HP_GT = "Thứ Hai – Thứ Sáu: sáng 7:30–12:00, chiều 13:30–17:00"

db = G + "/du_lieu/khai_thac.sqlite"
shutil.copy2(db, G + f"/du_lieu/sao_luu/khai_thac_{time.strftime('%Y%m%d_%H%M%S')}_truoc_nap_gio_hue.sqlite")
k = Kho(db)
luot = Luot(ma=f"gio-hue-{datetime.now():%Y%m%d-%H%M%S}", pham_vi="6tp", nhom_du_lieu="hanh_chinh_dan_cu",
            bat_dau=datetime.now().isoformat(timespec="seconds"))
kq = []
for ma, tr, gt, kieu, url, td in LE:
    if trong(ma, tr):
        kq.append(KetQua(don_vi_ma=ma, don_vi_ten=u_by[ma]["ten"], cap="xa", nhom="hanh_chinh_dan_cu", truong=tr,
                         gia_tri=gt, kieu=kieu, nguon_ma="cong_xa", nguon_ten="Cổng thông tin điện tử " + u_by[ma]["ten"],
                         nguon_url=url, nguon_muc="B", trich_doan=td, diem_tin=75, canh_bao=[], nam_du_lieu=2025))
for u in d["don_vi"]:
    if False and u["tinh_ma"] == "31" and u["cap"] == "xa" and trong(u["ma"], "gio_lam_viec"):
        kq.append(KetQua(don_vi_ma=u["ma"], don_vi_ten=u["ten"], cap="xa", nhom="hanh_chinh_dan_cu", truong="gio_lam_viec",
                         gia_tri=HP_GT, kieu="van_ban", nguon_ma="hp_tb233",
                         nguon_ten="Thông báo giờ làm việc của các cơ quan TP Hải Phòng (TB 233/TB-UBND)",
                         nguon_url=HP_URL, nguon_muc="B", trich_doan=HP_TD, diem_tin=70,
                         canh_bao=["Giờ làm việc chung toàn TP theo TB 233/TB-UBND ngày 29/7/2025, áp dụng từ 01/8/2025; xã có thể có lịch tiếp dân riêng"],
                         nam_du_lieu=2025))
for u in d["don_vi"]:
    if u["tinh_ma"] == "46" and u["cap"] == "xa" and trong(u["ma"], "gio_lam_viec"):
        kq.append(KetQua(don_vi_ma=u["ma"], don_vi_ten=u["ten"], cap="xa", nhom="hanh_chinh_dan_cu", truong="gio_lam_viec",
                         gia_tri=HUE_GT, kieu="van_ban", nguon_ma="hue_qd4010",
                         nguon_ten="Quy định thời gian làm việc hành chính trên địa bàn TP Huế (QĐ 4010/QĐ-UBND)",
                         nguon_url=HUE_URL, nguon_muc="B", trich_doan=HUE_TD, diem_tin=70,
                         canh_bao=["Giờ chung toàn TP Huế theo QĐ 4010/QĐ-UBND, hiệu lực 01/01/2026, áp dụng từ cấp thành phố đến cấp xã; mùa hè (tháng 4–9) giờ khác"],
                         nam_du_lieu=2026))
luot.ket_thuc = datetime.now().isoformat(timespec="seconds"); luot.so_don_vi = len({x.don_vi_ma for x in kq})
luot.so_ket_qua = k.ghi_ket_qua(kq, luot.ma); luot.nguon = ["hue_qd4010"]; k.ghi_luot(luot)
import collections; print("ghi", len(kq), collections.Counter(x.truong for x in kq))
