"""Nguồn có cấu trúc khai báo trong config/nguon/<tỉnh>.yaml (loai: bang).

Một nguồn `bang` là danh sách dòng (JSON API, bảng HTML, PDF/Excel), mỗi dòng ứng với
một xã. Cấu hình chỉ cần nói: lấy dòng ở đâu (`url`, `duong_dan`), cột nào là tên/mã
xã (`khoa_xa`), cột nào là trường nào (`cot`). Không phải viết code cho từng tỉnh.

    - ma: tinhthanhpho_xa
      loai: bang
      dinh_dang: json                       # json | html | pdf | xlsx
      url: https://www.tinhthanhpho.com/api/v1/new-provinces/{tinh_ma}/wards?limit=500
      duong_dan: data                       # json: khoá chứa danh sách dòng
      khoa_xa: {ma: code}                   # hoặc {ten: "Tên đơn vị"} → ghép tên→mã trong tỉnh
      cot: {dien_tich_km2: area_km2, dan_so: population, tru_so: hq_address}
      nhom: hanh_chinh_dan_cu
      muc: A
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from .. import cau_hinh
from ..http import goi, json_goi
from ..models import DAT, KetQua, Luot
from ..store import Kho
from ..text import chuan_hoa


def _so(v):
    """API '198.59' / '12403' / VN '48,68', '118.183' / 48.68 -> số; không phải số -> None.

    ponytail: chuỗi một dấu chấm + đúng 3 số lẻ ('118.183') coi là hàng nghìn kiểu Việt;
    API trả diện tích 3 số lẻ (vd '12.345' km²) sẽ đọc sai → nguồn đó nên trả số, không trả chuỗi.
    """
    if isinstance(v, (int, float)):
        return v
    try:
        return float(v) if "." in str(v) and "," not in str(v) and str(v).count(".") == 1 \
            and len(str(v).split(".")[1]) != 3 else int(str(v))
    except ValueError:
        pass  # chuỗi kiểu Việt: '48,68', '118.183' → doc_so
    from ..quy_trinh import doc_so

    so = doc_so(str(v)) if v not in (None, "") else None
    return int(so) if so is not None and so == int(so) else so


def _dong_json(cfg: dict, tinh_ma: str) -> list[dict]:
    du = json_goi(cfg["url"].format(tinh_ma=tinh_ma), timeout=60.0)
    for k in str(cfg.get("duong_dan") or "").split("."):
        if k and isinstance(du, dict):
            du = du.get(k)
    return du if isinstance(du, list) else []


def _dong_bang(cfg: dict, tinh_ma: str) -> list[dict]:
    """HTML/PDF/Excel → dòng {tiêu đề cột: ô}, dòng tiêu đề là dòng đầu có đủ các cột cần."""
    from .phap_ly import doc_bang

    url = cfg["url"].format(tinh_ma=tinh_ma)
    if cfg["dinh_dang"] == "html":
        from bs4 import BeautifulSoup

        r = goi(url, timeout=60.0)
        soup = BeautifulSoup(r.text, "lxml") if r is not None and r.status_code == 200 else None
        # ponytail: không xử lý rowspan/colspan; bảng gộp ô thì khai báo dinh_dang pdf/xlsx bản gốc
        bang = [{"rows": [[o.get_text(" ", strip=True) for o in tr.find_all(["td", "th"])]
                          for tr in t.find_all("tr")]} for t in (soup.find_all("table") if soup else [])]
    else:
        r = goi(url, timeout=120.0)
        if r is None or r.status_code != 200:
            return []
        with tempfile.NamedTemporaryFile(suffix="." + cfg["dinh_dang"], delete=False) as f:
            f.write(r.content)
        bang = doc_bang(Path(f.name))

    can = [chuan_hoa(c) for c in [*cfg["khoa_xa"].values(), *cfg["cot"].values()]]
    dong: list[dict] = []
    for b in bang:
        rows = b["rows"]
        for i, row in enumerate(rows[:15]):
            tieu_de = [chuan_hoa(c) for c in row]
            if all(any(c in t for t in tieu_de) for c in can):
                for r_ in rows[i + 1:]:
                    dong.append({c: next((r_[j] for j, t in enumerate(tieu_de) if chuan_hoa(c) in t
                                          and j < len(r_)), None)
                                 for c in [*cfg["khoa_xa"].values(), *cfg["cot"].values()]})
                break
    return dong


def nap(kho: Kho, cfg: dict, tinh_ma: str) -> dict:
    """Chạy một nguồn `bang` cho một tỉnh. Trả {'so_xa', 'so_truong', 'khong_khop'}."""
    dong = _dong_json(cfg, tinh_ma) if cfg.get("dinh_dang", "json") == "json" else _dong_bang(cfg, tinh_ma)

    xa = {r["ma"]: r for r in kho.tim_don_vi(cap="xa", tinh_ma=tinh_ma)}
    bd = kho.ban_do_ma(tinh_ma)
    kieu = {t["khoa"]: t.get("kieu", "van_ban")
            for nh in cau_hinh.ds_nhom("xa") for t in cau_hinh.ds_truong("xa", nh)}
    nhom_cua = {t["khoa"]: nh for nh in cau_hinh.ds_nhom("xa") for t in cau_hinh.ds_truong("xa", nh)}

    luot = Luot(ma=f"nguon-{cfg['ma']}-{tinh_ma}-{datetime.now():%Y%m%d-%H%M%S}",
                pham_vi=f"tỉnh {tinh_ma}", nhom_du_lieu=cfg["ma"],
                bat_dau=datetime.now().isoformat(timespec="seconds"), nguon=[cfg["ma"]])
    ket: list[KetQua] = []
    khong_khop: list[str] = []
    url = cfg["url"].format(tinh_ma=tinh_ma)
    for d in dong:
        if "ma" in cfg["khoa_xa"]:
            ma = str(d.get(cfg["khoa_xa"]["ma"]) or "").zfill(5)
        else:
            ma = Kho.tim_ma_xa(bd, d.get(cfg["khoa_xa"]["ten"]) or "")
        if ma not in xa:
            khong_khop.append(str(d.get(next(iter(cfg["khoa_xa"].values())))))
            continue
        for truong, cot in cfg["cot"].items():
            gt = d.get(cot)
            if kieu.get(truong) == "so":
                gt = _so(gt)
            if gt in (None, "", [], {}):
                continue
            ket.append(KetQua(
                don_vi_ma=ma, don_vi_ten=xa[ma]["ten"], cap="xa",
                nhom=cfg.get("nhom") or nhom_cua.get(truong, "khac"), truong=truong,
                gia_tri=gt, kieu=kieu.get(truong, "van_ban"),
                nguon_ma=cfg["ma"], nguon_ten=cfg.get("ten") or cfg["ma"], nguon_url=url,
                nguon_muc=cfg.get("muc", "C"), trich_doan=f"{cot} = {d.get(cot)}",
                diem_tin={"A": 90, "B": 75}.get(cfg.get("muc"), 60), trang_thai=DAT,
                nam_du_lieu=cfg.get("nam"),
            ))
    kho.ghi_ket_qua(ket, luot.ma)
    luot.ket_thuc = datetime.now().isoformat(timespec="seconds")
    luot.so_don_vi = len({k.don_vi_ma for k in ket})
    luot.so_ket_qua = luot.so_dat = len(ket)
    kho.ghi_luot(luot)
    return {"so_xa": luot.so_don_vi, "so_truong": len(ket), "khong_khop": khong_khop}
