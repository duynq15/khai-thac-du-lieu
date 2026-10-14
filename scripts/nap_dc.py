"""Back up DB, then compose `dien_cach_hanh_chinh` for communes lacking it, ONLY from verified
fields (NQ UBTVQH can_cu_phap_ly + don_vi_cu_chi_tiet from the legacy-mapping API)."""
import sys, json, glob, shutil, time
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from datetime import datetime
from khai_thac.store import Kho
from khai_thac.models import KetQua, Luot

d = json.load(open(sorted(glob.glob(G + "/du_lieu/ban_giao/ban_giao_*.json"))[-1], encoding="utf-8"))
thu = "--thu" in sys.argv
kq = []
for u in d["don_vi"]:
    t = u["truong"]
    ct, cc = t["don_vi_cu_chi_tiet"]["gia_tri"], t["can_cu_phap_ly"]["gia_tri"]
    if t["dien_cach_hanh_chinh"]["gia_tri"] is not None or not ct or not cc:
        continue
    nhom = {}  # old district -> [unit text], insertion-ordered
    for x in ct:
        ten = ("một phần " if x.get("pham_vi") == "mot_phan" else "") + x["ten"]
        nhom.setdefault(x.get("huyen_cu") or "", []).append(ten)
    phan = [", ".join(v) + (f" ({h})" if h else "") for h, v in nhom.items()]
    so_hieu = cc.split(":")[0]
    ngay = t["ngay_thanh_lap"]["gia_tri"] or t["ngay_hieu_luc"]["gia_tri"]
    ngay = f" từ ngày {'/'.join(reversed(ngay.split('-')))}" if ngay else ""
    if len(ct) == 1 and ct[0].get("pham_vi") == "toan_bo":
        gt = f"Theo {so_hieu}, {u['ten']} được hình thành{ngay} trên cơ sở toàn bộ {phan[0]}, không nhập thêm đơn vị khác."
    else:
      gt = (f"Theo {so_hieu}, {u['ten']} được thành lập{ngay} trên cơ sở sắp xếp "
            f"{'toàn bộ diện tích tự nhiên, quy mô dân số của ' if all(x.get('pham_vi') == 'toan_bo' for x in ct) else ''}"
            + "; ".join(phan) + ".")
    trich = cc + " | " + "; ".join(f"{x['ten']} ({x.get('huyen_cu')}, {x.get('pham_vi')})" for x in ct)
    kq.append(KetQua(don_vi_ma=u["ma"], don_vi_ten=u["ten"], cap="xa", nhom="lich_su_dia_danh", truong="dien_cach_hanh_chinh",
                     gia_tri=gt[:800], kieu="van_ban", nguon_ma="tong_hop_danh_muc",
                     nguon_ten="Tổng hợp từ NQ UBTVQH sắp xếp cấp xã và bảng đơn vị cũ hợp thành",
                     nguon_url=t["can_cu_phap_ly"]["nguon"]["url"], nguon_muc="B", trich_doan=trich[:1000], diem_tin=70,
                     canh_bao=["Câu ghép tự động từ NQ sắp xếp 2025 và danh sách đơn vị cũ; chỉ phản ánh đợt sắp xếp 2025, chưa có lịch sử trước đó"],
                     nam_du_lieu=2025))
print("se ghi", len(kq)); print(kq[0].gia_tri); print(kq[-1].gia_tri)
print(min(len(x.gia_tri.split()) for x in kq), "tu min")
if thu:
    sys.exit()
db = G + "/du_lieu/khai_thac.sqlite"
shutil.copy2(db, G + f"/du_lieu/sao_luu/khai_thac_{time.strftime('%Y%m%d_%H%M%S')}_truoc_nap_dc.sqlite")
k = Kho(db)
luot = Luot(ma=f"diencach-tonghop-{datetime.now():%Y%m%d-%H%M%S}", pham_vi="6tp", nhom_du_lieu="lich_su_dia_danh",
            bat_dau=datetime.now().isoformat(timespec="seconds"))
luot.ket_thuc = datetime.now().isoformat(timespec="seconds"); luot.so_don_vi = len(kq)
luot.so_ket_qua = k.ghi_ket_qua(kq, luot.ma); luot.nguon = ["tong_hop_danh_muc"]; k.ghi_luot(luot)
print("ghi", luot.so_ket_qua)
