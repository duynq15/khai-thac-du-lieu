"""Back up DB, then compose `nguon_goc_ten_xa` (name kept from a pre-2025 unit) for communes lacking it, ONLY from verified
fields (NQ UBTVQH can_cu_phap_ly + don_vi_cu_chi_tiet from the legacy-mapping API)."""
import re, sys, json, glob, shutil, time
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from datetime import datetime
from khai_thac.store import Kho
from khai_thac.models import KetQua, Luot

d = json.load(open(sorted(glob.glob(G + "/du_lieu/ban_giao/ban_giao_*.json"))[-1], encoding="utf-8"))
thu = "--thu" in sys.argv
kq = []
bo = lambda s: re.sub(r"^(Phường|Xã|Đặc khu|Thị trấn|Quận|Huyện|Thị xã|Thành phố)\s+", "", s or "", flags=re.I).strip()
for u in d["don_vi"]:
    t = u["truong"]
    ct, cc = t["don_vi_cu_chi_tiet"]["gia_tri"], t["can_cu_phap_ly"]["gia_tri"]
    if t["nguon_goc_ten_xa"]["gia_tri"] is not None or not ct or not cc:
        continue
    n = bo(u["ten"]).lower()
    xa = [x for x in ct if bo(x["ten"]).lower() == n]
    hu = sorted({x["huyen_cu"] for x in ct if bo(x.get("huyen_cu")).lower() == n})
    if xa:
        x = xa[0]
        gt = (f"Tên gọi {bo(u['ten'])} được giữ theo tên {x['ten']}"
              + (f" ({x['huyen_cu']})" if x.get("huyen_cu") else "")
              + f", một trong các đơn vị hành chính trước khi sắp xếp theo {cc.split(':')[0]}.")
    elif hu:
        gt = (f"Tên gọi {bo(u['ten'])} được giữ theo tên {hu[0]}, đơn vị hành chính cấp huyện cũ "
              f"của các đơn vị được sắp xếp theo {cc.split(':')[0]}.")
    else:
        continue
    trich = cc + " | " + "; ".join(f"{x['ten']} ({x.get('huyen_cu')})" for x in ct)
    kq.append(KetQua(don_vi_ma=u["ma"], don_vi_ten=u["ten"], cap="xa", nhom="lich_su_dia_danh", truong="nguon_goc_ten_xa",
                     gia_tri=gt, kieu="van_ban", nguon_ma="tong_hop_danh_muc",
                     nguon_ten="Tổng hợp từ NQ UBTVQH sắp xếp cấp xã và bảng đơn vị cũ hợp thành",
                     nguon_url=t["can_cu_phap_ly"]["nguon"]["url"], nguon_muc="B", trich_doan=trich[:1000], diem_tin=65,
                     canh_bao=["Chỉ đối chiếu tên mới với tên đơn vị cũ; chưa có giải nghĩa địa danh"],
                     nam_du_lieu=2025))
print("se ghi", len(kq)); print(kq[0].gia_tri); print(kq[-1].gia_tri)
print(min(len(x.gia_tri.split()) for x in kq), "tu min")
if thu:
    sys.exit()
db = G + "/du_lieu/khai_thac.sqlite"
shutil.copy2(db, G + f"/du_lieu/sao_luu/khai_thac_{time.strftime('%Y%m%d_%H%M%S')}_truoc_nap_ngt.sqlite")
k = Kho(db)
luot = Luot(ma=f"nguongocten-tonghop-{datetime.now():%Y%m%d-%H%M%S}", pham_vi="6tp", nhom_du_lieu="lich_su_dia_danh",
            bat_dau=datetime.now().isoformat(timespec="seconds"))
luot.ket_thuc = datetime.now().isoformat(timespec="seconds"); luot.so_don_vi = len(kq)
luot.so_ket_qua = k.ghi_ket_qua(kq, luot.ma); luot.nguon = ["tong_hop_danh_muc"]; k.ghi_luot(luot)
print("ghi", luot.so_ket_qua)
