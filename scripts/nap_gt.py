"""Sao lưu DB rồi lập `gioi_thieu` cho xã chưa có, GHÉP từ các trường đã kiểm chứng
(NQ UBTVQH, đơn vị cũ, diện tích, dân số, trụ sở) — không bịa câu nào ngoài dữ kiện có nguồn.
Nguồn ghi là NQ của xã; cảnh báo nói rõ đây là đoạn tổng hợp."""
import sys, json, glob, shutil, time
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from datetime import datetime
from khai_thac.store import Kho
from khai_thac.models import KetQua, Luot

def so(x, le=False):
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if le else f"{int(x):,}".replace(",", ".")

d = json.load(open(sorted(glob.glob(G + "/du_lieu/ban_giao/ban_giao_*.json"))[-1], encoding="utf-8"))
db = G + "/du_lieu/khai_thac.sqlite"
shutil.copy2(db, G + f"/du_lieu/sao_luu/khai_thac_{time.strftime('%Y%m%d_%H%M%S')}_truoc_nap_gt.sqlite")
k = Kho(db)
luot = Luot(ma=f"gioithieu-tonghop-{datetime.now():%Y%m%d-%H%M%S}", pham_vi="6tp", nhom_du_lieu="thong_tin_chung",
            bat_dau=datetime.now().isoformat(timespec="seconds"))
kq = []
for u in d["don_vi"]:
    t = {kk: v["gia_tri"] for kk, v in u["truong"].items()}
    if t.get("gioi_thieu") is not None or not t.get("can_cu_phap_ly"):
        continue
    nq = u["truong"]["can_cu_phap_ly"]
    so_hieu = t["can_cu_phap_ly"].split(":")[0]            # "Nghị quyết 1659/NQ-UBTVQH15 ngày 16/06/2025"
    cau = [f"{u['ten']} là đơn vị hành chính cấp xã trực thuộc {u['tinh_ten']}"
           + (f", thành lập từ ngày {'/'.join(reversed(t['ngay_thanh_lap'].split('-')))}" if t.get("ngay_thanh_lap") else "")
           + f" theo {so_hieu}."]
    cu = t.get("don_vi_cu_hop_thanh")
    if isinstance(cu, list) and len(cu) > 1:
        cau.append(f"{t.get('loai') or 'Xã'} được sắp xếp từ {len(cu)} đơn vị cũ: {', '.join(cu)}.")
    elif isinstance(cu, list) and cu:
        cau.append(f"Đơn vị cũ: {cu[0]}.")
    if t.get("dien_tich_km2") and t.get("dan_so"):
        cau.append(f"Diện tích {so(t['dien_tich_km2'], True)} km², dân số {so(t['dan_so'])} người.")
    if t.get("tru_so"):
        cau.append(f"Trụ sở UBND: {t['tru_so']}.")
    gt = " ".join(cau)[:800]
    kq.append(KetQua(don_vi_ma=u["ma"], don_vi_ten=u["ten"], cap="xa", nhom="thong_tin_chung", truong="gioi_thieu",
                     gia_tri=gt, kieu="van_ban", nguon_ma="tong_hop_danh_muc",
                     nguon_ten="Tổng hợp từ NQ UBTVQH sắp xếp cấp xã và danh mục ĐVHC",
                     nguon_url=nq["nguon"]["url"], nguon_muc="B", trich_doan=t["can_cu_phap_ly"], diem_tin=70,
                     canh_bao=["Đoạn ghép tự động từ các trường đã có nguồn (NQ, đơn vị cũ, diện tích, dân số, trụ sở) — nên thay bằng bài giới thiệu của UBND xã khi có"],
                     nam_du_lieu=2025))
luot.ket_thuc = datetime.now().isoformat(timespec="seconds"); luot.so_don_vi = len(kq)
luot.so_ket_qua = k.ghi_ket_qua(kq, luot.ma); luot.nguon = ["tong_hop_danh_muc"]; k.ghi_luot(luot)
print("ghi", len(kq)); print(kq[0].gia_tri); print(kq[-1].gia_tri)
