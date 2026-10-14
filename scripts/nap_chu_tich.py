"""Back up DB, then add chu_tich_ubnd from the 30/06/2025 press lists (Tuổi Trẻ / VietNamNet / PLO), only for empty cells.
trich_doan = verbatim page slice from the unit name to the end of the chairman's name."""
import re, sys, json, glob, shutil, time, collections, unicodedata
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from datetime import datetime
from khai_thac.store import Kho
from khai_thac.models import KetQua, Luot
N = lambda s: unicodedata.normalize("NFC", s)
SRC = {"92": ("https://tuoitre.vn/danh-sach-bi-thu-chu-tich-ubnd-103-xa-phuong-cua-tp-can-tho-moi-20250630181053043.htm",
              "Tuổi Trẻ – Danh sách bí thư, chủ tịch UBND 103 xã, phường TP Cần Thơ mới", "ct"),
       "46": ("https://vietnamnet.vn/danh-sach-40-bi-thu-chu-tich-phuong-xa-moi-cua-tp-hue-2416579.html",
              "VietNamNet – Danh sách 40 bí thư, chủ tịch phường, xã mới của TP Huế", "hue"),
       "48": ("https://plo.vn/danh-sach-lanh-dao-chu-chot-94-phuong-xa-dac-khu-tai-tp-da-nang-moi-post857949.html",
              "Pháp Luật TP.HCM – Danh sách lãnh đạo chủ chốt 94 phường, xã, đặc khu TP Đà Nẵng mới", "dn")}
txt = {k: N(open(f"{G}/du_lieu/tam_kt/web/{v[2]}.txt").read()) for k, v in SRC.items()}
moi = json.load(open(G + "/du_lieu/tam_kt/chu_tich_moi.json"))
kq, bo = [], []
for r in moi:
    t, ten, ct = txt[r["tinh"]], N(r["ten"]), N(r["chu_tich"])
    j = t.find(ct)
    i = t.rfind(ten.split(" ", 1)[1], 0, j) if j >= 0 else -1      # nearest unit mention before the name
    if i < 0 or j - i > 300: bo.append((r["ten"], ct)); continue
    i = max(t.rfind(" ", 0, i - len(ten.split(" ", 1)[0]) - 1) + 1, 0)  # include "Phường"/"Xã" prefix
    td = t[i:j + len(ct)].strip()
    if r["tinh"] == "46":
        m = re.match(r".{0,80}?Chủ tịch UBND (phường|xã)", t[j:])
        if not m: bo.append((r["ten"], ct)); continue
        td = re.sub(r"\s+", " ", t[i:j + m.end()]).strip()
    url, nten, _ = SRC[r["tinh"]]
    kq.append(KetQua(don_vi_ma=r["ma"], don_vi_ten=r["ten"], cap="xa", nhom="hanh_chinh_dan_cu", truong="chu_tich_ubnd",
                     gia_tri=ct, kieu="van_ban", nguon_ma="bao_ds_chu_tich_2025", nguon_ten=nten, nguon_url=url,
                     nguon_muc="B", trich_doan=td, diem_tin=70,
                     canh_bao=["Theo danh sách công bố ngày 30/6/2025" + (" (cột: Đơn vị | Bí thư Đảng ủy | Chủ tịch UBND)" if r["tinh"] == "92" else
                               " (thứ tự: Bí thư – Phó Bí thư – Chủ tịch UBND)" if r["tinh"] == "48" else "") + "; nhân sự có thể đã thay đổi"],
                     nam_du_lieu=2025))
if "--thu" in sys.argv:
    for x in kq[:3] + kq[-12:-9] + kq[-3:]: print(x.don_vi_ten, "|", x.gia_tri, "|", x.trich_doan)
    print(len(kq), "bo", bo); sys.exit()
db = G + "/du_lieu/khai_thac.sqlite"
shutil.copy2(db, G + f"/du_lieu/sao_luu/khai_thac_{time.strftime('%Y%m%d_%H%M%S')}_truoc_nap_chu_tich.sqlite")
k = Kho(db)
luot = Luot(ma=f"chutich-bao-{datetime.now():%Y%m%d-%H%M%S}", pham_vi="6tp", nhom_du_lieu="hanh_chinh_dan_cu",
            bat_dau=datetime.now().isoformat(timespec="seconds"))
luot.ket_thuc = datetime.now().isoformat(timespec="seconds"); luot.so_don_vi = len(kq)
luot.so_ket_qua = k.ghi_ket_qua(kq, luot.ma); luot.nguon = ["bao_ds_chu_tich_2025"]; k.ghi_luot(luot)
print("ghi", len(kq), collections.Counter(x.don_vi_ma[:2] for x in kq), "bo", bo)
