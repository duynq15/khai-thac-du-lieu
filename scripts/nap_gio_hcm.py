"""Back up DB, then add TP.HCM office hours from QĐ 67/2017/QĐ-UBND, only for communes formed
entirely from pre-2025 TP.HCM units (tinh_cu_ma 79) and lacking gio_lam_viec."""
import sys, json, glob, shutil, time
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from datetime import datetime
from khai_thac.store import Kho
from khai_thac.models import KetQua, Luot

URL = ("https://pgdquan10.hcm.edu.vn/thong-tin-phap-luat/-quyet-dinh-so-672017qd-ubnd-ngay-29-thang-12-nam-2017"
       "-cua-chu-tich-uy-ban-nhan/ctmb/43930/259874")
TD = ("Đối với các cơ quan hành chính nhà nước, giờ làm việc b uổi sáng từ 7 giờ 30 phút đến 11 giờ 30 phút "
      "và buổi chiều từ 13 giờ đến 17 giờ.")
GT = "Sáng 7:30–11:30, chiều 13:00–17:00"
d = json.load(open(sorted(glob.glob(G + "/du_lieu/ban_giao/ban_giao_*.json"))[-1], encoding="utf-8"))
kq = []
for u in d["don_vi"]:
    t = u["truong"]; ct = t["don_vi_cu_chi_tiet"]["gia_tri"] or []
    if u["tinh_ma"] != "79" or t["gio_lam_viec"]["gia_tri"] is not None or not ct \
            or any(x.get("tinh_cu_ma") not in ("79", None) for x in ct) \
            or not any(x.get("tinh_cu_ma") == "79" for x in ct):
        continue
    kq.append(KetQua(don_vi_ma=u["ma"], don_vi_ten=u["ten"], cap="xa", nhom="hanh_chinh_dan_cu", truong="gio_lam_viec",
                     gia_tri=GT, kieu="van_ban", nguon_ma="hcm_qd67_2017",
                     nguon_ten="QĐ 67/2017/QĐ-UBND TP.HCM (quy tắc ứng xử, giờ làm việc cơ quan hành chính)",
                     nguon_url=URL, nguon_muc="B", trich_doan=TD, diem_tin=60,
                     canh_bao=["Giờ chung cơ quan hành chính TP.HCM theo QĐ 67/2017; UBND xã/phường có thể điều chỉnh, kiểm tra lại cổng phường"],
                     nam_du_lieu=2017))
print("se ghi", len(kq))
if "--thu" in sys.argv:
    sys.exit()
db = G + "/du_lieu/khai_thac.sqlite"
shutil.copy2(db, G + f"/du_lieu/sao_luu/khai_thac_{time.strftime('%Y%m%d_%H%M%S')}_truoc_nap_gio_hcm.sqlite")
k = Kho(db)
luot = Luot(ma=f"gio-hcm-{datetime.now():%Y%m%d-%H%M%S}", pham_vi="79", nhom_du_lieu="hanh_chinh_dan_cu",
            bat_dau=datetime.now().isoformat(timespec="seconds"))
luot.ket_thuc = datetime.now().isoformat(timespec="seconds"); luot.so_don_vi = len(kq)
luot.so_ket_qua = k.ghi_ket_qua(kq, luot.ma); luot.nguon = ["hcm_qd67_2017"]; k.ghi_luot(luot)
print("ghi", luot.so_ket_qua)
