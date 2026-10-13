"""Điều phối khai thác: nguồn → trích xuất → kiểm tra → kết quả."""

from __future__ import annotations

import json
import re
import signal
import sqlite3
from datetime import datetime

from . import cau_hinh
from .kiem_tra import kiem
from .models import DAT, LOI, THIEU, DonVi, KetQua, Luot
from .nguon import danh_muc, thon, toa_do, trang_xa, van_ban, wikipedia
from .nguon.tim_kiem import NguonBiChan, tim_theo_mau, xep_muc
from .store import Kho
from .text import chuan_hoa, slug as lam_slug, tach_danh_sach
from .trich_xuat import quy_tac
from .trich_xuat import ollama

MAU_TIM = (
    '"{don_vi}" "{tinh}" giới thiệu',
    '"{don_vi}" site:gov.vn',
    '"{don_vi}" giới thiệu lịch sử',
)


MA_THOAT_KHOI_DONG_LAI = 75  # script thấy mã này thì gọi lại lệnh (resume)

class HetGio(Exception):
    """Một đơn vị chạy quá lâu (thường do trình duyệt treo) — bỏ qua để chạy tiếp."""


def _bao_het_gio(signum, frame):  # noqa: ARG001
    raise HetGio("quá thời gian")


def _dat_bao_thuc(giay: int) -> None:
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _bao_het_gio)
        signal.alarm(giay)


def _tat_bao_thuc() -> None:
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)


def _tinh_ngan(tinh: str | None) -> str:
    """'Thành phố Hà Nội' -> 'Hà Nội'."""
    if not tinh:
        return ""
    for tien_to in ("Thành phố ", "Tỉnh ", "TP. ", "TP "):
        if tinh.startswith(tien_to):
            return tinh[len(tien_to):].strip()
    return tinh


def _dung_cap(tieu_de: str | None, loai: str | None) -> bool:
    """Trang nguồn có đúng cấp hành chính của đơn vị không.

    Xã mới lập không được lấy số liệu của huyện cũ cùng tên (khác thực thể).
    """
    if not tieu_de:
        return True
    chu = tieu_de.lower()
    if loai in ("xa", "phuong", "dac_khu"):
        return not any(x in chu for x in ("huyện", "quận"))
    return True


# ------------------------------------------------------------------ tiện ích
def doc_so(chuoi: str) -> float | None:
    """'12.345 người' -> 12345.0 ; '5,6 km²' -> 5.6"""
    if chuoi is None:
        return None
    if isinstance(chuoi, (int, float)):
        return float(chuoi)
    m = re.search(r"\d[\d.\s]*(?:,\d+)?", str(chuoi))
    if not m:
        return None
    so = m.group(0).replace(" ", "")
    # 12.345 -> 12345 (dấu chấm là phân cách nghìn); 5,6 -> 5.6 (dấu phẩy là thập phân)
    if "," in so:
        so = so.replace(".", "").replace(",", ".")
    else:
        so = so.replace(".", "")
    try:
        return float(so)
    except ValueError:
        return None


def _loai_nhan(loai: str) -> str:
    return {"xa": "Xã", "phuong": "Phường", "dac_khu": "Đặc khu",
            "tinh": "Tỉnh", "thanh_pho": "Thành phố"}.get(loai, loai)


# ------------------------------------------------------- nguồn văn bản
def _doan_quanh_ten(van_ban: str, ten: str, *, rong: int = 600) -> str:
    """Các đoạn ±rong ký tự quanh mỗi lần nhắc tên xã (bỏ tiền tố); không nhắc → ''.

    So khớp không dấu nhưng cắt trên văn bản gốc (bo_dau giữ nguyên độ dài chuỗi).
    """
    from .text import bo_dau

    ten_rut = re.sub(r"^(Xã|Phường|Đặc khu)\s+", "", ten)
    goc, tim = bo_dau(van_ban.lower()), bo_dau(ten_rut.lower())
    khoang: list[list[int]] = []
    for m in re.finditer(re.escape(tim), goc):
        a, b = max(0, m.start() - rong), m.end() + rong
        if khoang and a <= khoang[-1][1]:
            khoang[-1][1] = b
        else:
            khoang.append([a, b])
    return "\n…\n".join(van_ban[a:b] for a, b in khoang)[:6000]


def gom_nguon_van_ban(don_vi: sqlite3.Row | dict, *, so_trang_gov: int = 4) -> list[dict]:
    """Gom văn bản nguồn cho một đơn vị: trang riêng của đơn vị + Wikipedia + báo chí.

    Ưu tiên trang *.gov.vn của chính đơn vị (footer có trụ sở, điện thoại, email,
    lãnh đạo). Trang đó dựng bằng JavaScript nên mở bằng trình duyệt.
    """
    ten = don_vi["ten"]
    tinh = don_vi["tinh_ten"]
    tinh_ngan = _tinh_ngan(tinh)
    nguons: list[dict] = []

    # 1) Trang chính thống của đơn vị (nguồn A).
    #    mien_gov đọc CACHE trước → nếu đã biết tên miền thì KHÔNG cần tìm kiếm.
    mien = trang_xa.mien_gov(dict(don_vi))
    if mien:
        for duong in ("", "/gioi-thieu"):
            url = mien.rstrip("/") + duong
            vb = trang_xa.doc(url)
            if vb and len(vb) >= 300:
                nguons.append({
                    "nguon_ma": "govvn", "nguon_ten": f"Trang TTĐT {ten}",
                    "url": url, "muc": "A", "van_ban": vb,
                })
        # Thêm các trang chuyên mục (di tích, văn hoá, lịch sử, lễ hội…) — nơi có nội dung
        for url in trang_xa.chuyen_muc(mien)[:4]:
            if any(n["url"] == url for n in nguons):
                continue
            vb = trang_xa.doc(url)
            if vb and len(vb) >= 300:
                nguons.append({
                    "nguon_ma": "govvn", "nguon_ten": f"Chuyên mục {ten}",
                    "url": url, "muc": "A", "van_ban": vb,
                })

    # 1b) Trang cấp tỉnh khai báo `loai: van_ban` trong config/nguon/<tỉnh>.yaml (danh mục
    #     di tích, lễ hội…): chỉ lấy đoạn quanh tên xã này để LLM không gán nhầm sang xã khác.
    for n in cau_hinh.nguon_tinh(dict(don_vi).get("tinh_ma")).get("nguon", []):
        if n.get("loai") != "van_ban":
            continue
        doan = _doan_quanh_ten(trang_xa.doc(n["url"]) or "", ten)
        if doan:
            nguons.append({"nguon_ma": n["ma"], "nguon_ten": n.get("ten") or n["ma"],
                           "url": n["url"], "muc": n.get("muc", "B"), "van_ban": doan})

    # 2) Wikipedia (bỏ trang nói về cấp khác, tránh gán nhầm dữ liệu huyện cũ cho xã mới)
    bai = wikipedia.doc_bai(ten, tinh)
    if bai and _dung_cap(bai["title"], dict(don_vi).get("loai")):
        nguons.append({
            "nguon_ma": "wikipedia_vi", "nguon_ten": "Wikipedia tiếng Việt",
            "url": bai["url"], "muc": "C", "van_ban": bai["extract"],
        })

    # 3) Chỉ tìm kiếm thêm khi CHƯA có trang chính thống (đỡ phụ thuộc DDG, đỡ bị chặn)
    so_gov = sum(1 for n in nguons if n["muc"] in ("A", "B"))
    ung_vien: list[dict] = []
    if so_gov < so_trang_gov:
        ung_vien = tim_theo_mau(ten, tinh_ngan, *MAU_TIM)
        if not ung_vien:
            from .nguon.tim_kiem import tim
            ung_vien = tim(f"{ten} {tinh_ngan} giới thiệu", so_luong=8)

        for r in ung_vien:
            if so_gov >= so_trang_gov:
                break
            muc = xep_muc(r["url"])
            if muc == "LOAI":
                continue
            if any(n["url"] == r["url"] for n in nguons):
                continue
            if muc == "C" and any(n["muc"] == "C" for n in nguons):
                continue

            # Trang A/B dựng bằng JS: nếu bản tĩnh quá ít chữ thì mở bằng trình duyệt
            trang = van_ban.doc_trang(r["url"])
            vb = trang["van_ban"] if trang else None
            if (not vb or len(vb) < 400) and muc in ("A", "B"):
                vb = trang_xa.doc(r["url"]) or vb
            if not vb:
                continue

            nguons.append({
                "nguon_ma": "govvn" if muc in ("A", "B") else "nguon_khac",
                "nguon_ten": r["tieu_de"][:80] or r["url"],
                "url": r["url"], "muc": muc, "van_ban": vb,
            })
            if muc in ("A", "B"):
                so_gov += 1

    nguons.sort(key=lambda n: {"A": 0, "B": 1, "C": 2}[n["muc"]])
    return nguons


def _tu_danh_muc_tinh(truong: str, d: dict):
    """Trường cấp tỉnh tính được từ danh mục + số liệu tinhthanhpho + kho (không LLM)."""
    sl = danh_muc.so_lieu_tinh(d["ma"])
    if truong in sl and truong != "so_don_vi_hanh_chinh":
        return sl[truong]
    if truong in ("so_don_vi_hanh_chinh", "co_cau_don_vi", "tong_don_vi_cu"):
        kho = Kho()
        try:
            dem = dict(kho.conn.execute(
                "SELECT loai, COUNT(*) FROM don_vi WHERE tinh_ma = ? GROUP BY loai", (d["ma"],)))
            cu = kho.conn.execute(
                "SELECT SUM(so_don_vi_cu) FROM don_vi WHERE tinh_ma = ? AND loai != 'thon'",
                (d["ma"],)).fetchone()[0]
        finally:
            kho.dong()
        if truong == "co_cau_don_vi":
            return {"phuong": dem.get("phuong", 0), "xa": dem.get("xa", 0),
                    "dac_khu": dem.get("dac_khu", 0)}
        if truong == "tong_don_vi_cu":
            return cu
        so = sum(dem.get(k, 0) for k in ("xa", "phuong", "dac_khu"))
        return so or sl.get("so_don_vi_hanh_chinh")
    return None

def chuan_ban_ghi(gia_tri, nguon_van_ban: str | None) -> tuple[list[dict] | None, list[str]]:
    """Đưa về [{ten, ...}]; bỏ bản ghi không tên hoặc tên không có trong nguồn (LLM bịa).

    Trả (bản ghi giữ lại hoặc None, tên bị bỏ).
    """
    if isinstance(gia_tri, (str, dict)):
        gia_tri = [gia_tri]
    ds = []
    for x in gia_tri if isinstance(gia_tri, list) else []:
        x = {"ten": x} if isinstance(x, str) else x
        if isinstance(x, dict) and str(x.get("ten") or "").strip():
            ds.append({k: v for k, v in x.items() if v not in (None, "", "null")})
    bo: list[str] = []
    if nguon_van_ban:
        goc = chuan_hoa(nguon_van_ban)
        bo = [x["ten"] for x in ds if chuan_hoa(x["ten"]) not in goc]
        ds = [x for x in ds if x["ten"] not in bo]
    return (ds or None), bo

# ------------------------------------------------------- sinh từng trường
def _tu_danh_muc(truong: str, don_vi: sqlite3.Row | dict):
    """Giá trị lấy thẳng từ danh mục (không cần mạng)."""
    d = dict(don_vi)
    if d.get("loai") in ("tinh", "thanh_pho"):
        tinh = _tu_danh_muc_tinh(truong, d)
        if tinh is not None:
            return tinh
    if truong == "ten":
        return d["ten"]
    if truong == "loai":
        return _loai_nhan(d["loai"])
    if truong in ("ma_dvhc", "ma"):
        return d["ma"]
    if truong == "truc_thuoc_tinh":
        return d["tinh_ten"]
    if truong in ("ngay_thanh_lap", "ngay_hieu_luc"):
        return d.get("ngay_hieu_luc")
    if truong in ("don_vi_cu_hop_thanh",):
        return d.get("don_vi_cu_hop_thanh") or []
    if truong == "don_vi_cu_chi_tiet":
        return danh_muc.chi_tiet_don_vi_cu(d["ma"], d.get("don_vi_cu_hop_thanh") or []) or None
    if truong == "so_don_vi_cu":
        return d.get("so_don_vi_cu")
    if truong == "can_cu_phap_ly":
        return d.get("can_cu_phap_ly")
    return None


def _boc_quy_tac(truong_cfg: dict, nguons: list[dict], *, ten_don_vi: str | None = None):
    """Bóc trường bằng QUY TẮC tất định (không gọi LLM). Trả (giá trị, nguon, trich)."""
    khoa = truong_cfg["khoa"]
    for n in nguons:
        vb = n["van_ban"]
        if khoa == "gioi_thieu":
            r = quy_tac.boc_gioi_thieu(vb, ten_don_vi)
        elif khoa == "email":
            gt = quy_tac.tim_email(vb)
            r = (gt, gt) if gt else None
        elif khoa == "dien_thoai":
            gt = quy_tac.tim_dien_thoai(vb)
            r = (gt, gt) if gt else None
        else:
            r = quy_tac.boc_theo_truong(vb, khoa)
        if r:
            return r[0], n, r[1]
    return None, None, None


def _boc_llm_hang_loat(cho_llm: list[dict], nguons: list[dict], dung_llm: bool) -> dict:
    """Gọi LLM MỘT lần cho tất cả trường cần — nhanh hơn gọi từng trường rất nhiều.

    Trả {khoa: (gia_tri, nguon, trich_doan)}.
    """
    if not dung_llm or not cho_llm or not nguons or not ollama.san_sang():
        return {}
    con_lai = list(cho_llm)
    ket_qua: dict = {}
    model = cau_hinh.lay_ho_so("llm", "model", mac_dinh=ollama.MODEL_MAC_DINH)
    # Đọc lần lượt các nguồn (kể cả trang chuyên mục) cho tới khi bóc đủ
    for n in nguons[:3]:
        if not con_lai:
            break
        du = ollama.boc(n["van_ban"], con_lai, model=model, timeout=90.0)
        for t in list(con_lai):
            k = t["khoa"]
            o = du.get(k)
            if o and o.get("gia_tri") not in (None, "", []):
                ket_qua[k] = (o["gia_tri"], {**n, "nam": o.get("nam")}, o.get("trich_doan"))
                con_lai.remove(t)
    return ket_qua



def khai_thac_don_vi(don_vi: sqlite3.Row | dict, nhom: str, *, cap: str = "xa",
                     dung_llm: bool = True, boi_canh_chung: dict | None = None,
                     nguons: list[dict] | None = None,
                     llm_da_boc: dict | None = None,
                     bo_qua: set[str] = frozenset()) -> list[KetQua]:
    """bo_qua: trường đã có giá trị đạt từ nguồn có cấu trúc (`khai-thac nguon`) — không bóc lại."""
    truong_ds = [t for t in cau_hinh.ds_truong(cap, nhom) if t["khoa"] not in bo_qua]
    d = dict(don_vi)
    # Giải mã các cột JSON (danh sách đơn vị cũ, danh sách nguồn)
    for cot in ("don_vi_cu_hop_thanh", "nguon"):
        if isinstance(d.get(cot), str):
            try:
                import json as _json
                d[cot] = _json.loads(d[cot])
            except ValueError:
                d[cot] = []
    boi_canh = {"tinh_ten": d.get("tinh_ten"), **(boi_canh_chung or {})}

    # Chỉ gom nguồn mạng nếu nhóm có trường cần (cách lấy llm/nhập tay).
    # Nếu đã có nguồn truyền vào (bóc nhiều nhóm từ một lần nạp) thì dùng lại.
    can_mang = any(t.get("cach_lay") in ("llm", "nhap_tay") for t in truong_ds)
    if nguons is None:
        nguons = gom_nguon_van_ban(d) if can_mang else []

    # Bước 1: giải bằng danh mục / toạ độ / quy tắc tất định
    giai: dict[str, tuple] = {}
    cho_llm: list[dict] = []
    for t in truong_ds:
        khoa = t["khoa"]
        tu = _tu_danh_muc(khoa, d)
        if tu is not None:
            giai[khoa] = (tu, None, None)
            continue
        if khoa == "ranh_gioi_vi_tri":
            toa = toa_do.tra(d["ten"], d.get("tinh_ten"))
            if toa:
                gia = {"lat": toa["lat"], "lon": toa["lon"], "ten_osm": toa["ten_osm"]}
                nguon = {"nguon_ma": "photon_osm", "nguon_ten": "Photon (OpenStreetMap)",
                         "url": toa["nguon_url"], "muc": "C"}
                giai[khoa] = (gia, nguon, None)
            continue
        if t.get("cach_lay") in ("llm", "nhap_tay") and nguons:
            r = _boc_quy_tac(t, nguons, ten_don_vi=d["ten"])
            if r[0] is not None:
                giai[khoa] = r
                continue
        if t.get("cach_lay") == "llm":
            cho_llm.append(t)

    # Bước 2: MỘT lần gọi LLM cho tất cả trường còn thiếu (nhanh hơn từng trường).
    # Nếu đã bóc sẵn từ trước (gộp nhiều nhóm) thì chỉ lấy phần của nhóm này.
    if llm_da_boc is not None:
        khoa_nhom = {t["khoa"] for t in truong_ds}
        giai.update({k: v for k, v in llm_da_boc.items() if k in khoa_nhom})
    else:
        giai.update(_boc_llm_hang_loat(cho_llm, nguons, dung_llm))

    # Bước 3: dựng kết quả theo đúng thứ tự trường
    kq: list[KetQua] = []
    for t in truong_ds:
        khoa = t["khoa"]
        # Pha CÀO (--khong-llm): bỏ qua hẳn trường LLM để pha sau nhặt lại
        if not dung_llm and t.get("cach_lay") == "llm":
            continue
        gia_tri, nguon, trich = giai.get(khoa, (None, None, None))
        tu_danh_muc = _tu_danh_muc(khoa, d)

        # Chuẩn hoá kiểu
        if gia_tri is not None:
            if t.get("kieu") == "so" and not isinstance(gia_tri, (int, float)) \
                    and not isinstance(gia_tri, (list, dict)):
                so = doc_so(gia_tri)
                gia_tri = int(so) if so is not None and so == int(so) else so
            if t.get("kieu") == "danh_sach" and isinstance(gia_tri, str):
                tach = tach_danh_sach(gia_tri)
                gia_tri = tach if len(tach) > 1 else gia_tri
            if t.get("kieu") == "ban_ghi" and t.get("cach_lay") == "llm":
                gia_tri, bo = chuan_ban_ghi(gia_tri, (nguon or {}).get("van_ban"))

        nguon_van_ban = nguon.get("van_ban") if nguon else None
        trang_thai, diem, ly_do, canh_bao = kiem(
            t, gia_tri, trich_doan=trich, nguon_van_ban=nguon_van_ban, boi_canh=boi_canh,
        )
        if t.get("kieu") == "ban_ghi" and t.get("cach_lay") == "llm" and bo:
            canh_bao.append(f"Bỏ {len(bo)} bản ghi không có tên trong nguồn: {', '.join(bo)[:200]}")

        kq.append(KetQua(
            don_vi_ma=d["ma"], don_vi_ten=d["ten"], cap=cap, nhom=nhom, truong=khoa,
            gia_tri=gia_tri, kieu=t.get("kieu", "van_ban"),
            nguon_ma=(nguon or {}).get("nguon_ma") or ("danh_muc" if tu_danh_muc is not None else None),
            nguon_ten=(nguon or {}).get("nguon_ten") or ("Danh mục ĐVHC" if tu_danh_muc is not None else None),
            nguon_url=(nguon or {}).get("url"),
            nguon_muc=(nguon or {}).get("muc") or ("A" if tu_danh_muc is not None else None),
            trich_doan=trich, diem_tin=diem, trang_thai=trang_thai if trang_thai in (DAT, LOI) else THIEU,
            ly_do_loi=ly_do, canh_bao=canh_bao, nam_du_lieu=(nguon or {}).get("nam"),
        ))
    return kq


# ------------------------------------------------------------------ lô
def chay_danh_muc(kho: Kho, *, province_codes: list[str] | None = None) -> dict:
    luot = Luot(ma=f"danhmuc-{datetime.now():%Y%m%d-%H%M%S}", pham_vi="quoc_gia",
                nhom_du_lieu="danh_muc", bat_dau=datetime.now().isoformat(timespec="seconds"))
    tinh = danh_muc.nap_tinh()
    xa = danh_muc.nap_xa(province_codes)
    kho.ghi_don_vi(tinh + xa)
    luot.ket_thuc = datetime.now().isoformat(timespec="seconds")
    luot.so_don_vi = len(tinh) + len(xa)
    luot.nguon = ["open_api_v2", "tinhthanh34", "tinhthanhpho"]
    kho.ghi_luot(luot)
    return {"so_tinh": len(tinh), "so_xa": len(xa)}


def chay_nhom(kho: Kho, nhom: str, *, ten: str | None = None, ma: str | None = None,
              tinh: str | None = None, cap: str = "xa", dung_llm: bool = True,
              tinh_ma: str | None = None, bo_qua_da_co: bool = False,
              gioi_han: int | None = None, so_moi_lo: int = 0,
              nghi_giua_lo: float = 0.0, chia: tuple[int, int] | None = None) -> list[KetQua]:
    import time as _time

    ds_don_vi = kho.tim_don_vi(ten=ten, ma=ma, tinh_ten=tinh, cap=cap, tinh_ma=tinh_ma,
                               bo_qua_nhom=(nhom if bo_qua_da_co else None), gioi_han=gioi_han,
                               chia=chia)
    nhan_chia = f"-{chia[1]}of{chia[0]}" if chia else ""
    luot = Luot(ma=f"{nhom}-{datetime.now():%Y%m%d-%H%M%S}{nhan_chia}",
                pham_vi=ten or tinh or tinh_ma or "tat_ca", nhom_du_lieu=nhom,
                bat_dau=datetime.now().isoformat(timespec="seconds"))
    kho.ghi_luot(luot)  # ghi ngay để thấy lượt đang chạy
    tat_ca: list[KetQua] = []
    for i, dv in enumerate(ds_don_vi, 1):
        try:
            kq = khai_thac_don_vi(dv, nhom, cap=cap, dung_llm=dung_llm)
        except NguonBiChan as e:
            print(f"  ⚠ {e} — dừng luồng, chạy tiếp sau (đã lưu tới {dv['ten']})", flush=True)
            break
        tat_ca.extend(kq)
        # Ghi NGAY từng đơn vị: thấy được tiến độ và không mất nếu dừng giữa chừng
        kho.ghi_ket_qua(kq, luot.ma)
        so_dat = sum(1 for k in kq if k.trang_thai == DAT)
        print(f"  [{i}/{len(ds_don_vi)}] {dv['ten']}: {so_dat}/{len(kq)} trường đạt", flush=True)
        _ghi_tien_trinh(luot.ma, nhom, i, len(ds_don_vi), dv["ten"], len(tat_ca), chia)
        # Nghỉ giữa các lô để tránh gọi liên tục bị chặn
        if so_moi_lo and nghi_giua_lo and i % so_moi_lo == 0 and i < len(ds_don_vi):
            print(f"  … nghỉ {nghi_giua_lo:.0f}s sau lô {i // so_moi_lo}", flush=True)
            _time.sleep(nghi_giua_lo)
    luot.ket_thuc = datetime.now().isoformat(timespec="seconds")
    luot.so_don_vi = len(ds_don_vi)
    luot.so_ket_qua = len(tat_ca)
    luot.so_dat = sum(1 for k in tat_ca if k.trang_thai == DAT)
    luot.nguon = ["open_api_v2", "tinhthanh34", "wikipedia_vi", "photon_osm", "govvn"]
    kho.ghi_ket_qua(tat_ca, luot.ma)
    kho.ghi_luot(luot)
    return tat_ca


def _ghi_tien_trinh(luot_ma: str, nhom: str, i: int, tong: int, ten_don_vi: str,
                    so_ket_qua: int, chia: tuple[int, int] | None = None) -> None:
    """Ghi một dòng tiến độ để lệnh `tien-do` đọc được khi đang chạy.

    Mỗi shard ghi tệp riêng để nhiều tiến trình không ghi đè nhau.
    """
    from .store import DU_LIEU

    p = DU_LIEU / (f"tien_trinh_{chia[1]}of{chia[0]}.json" if chia else "tien_trinh.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({
            "luot_ma": luot_ma, "nhom": nhom, "da_xong": i, "tong": tong,
            "don_vi_cuoi": ten_don_vi, "so_ket_qua": so_ket_qua,
            "shard": (f"{chia[1]}/{chia[0]}" if chia else None),
            "cap_nhat": datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def chay_thon(kho: Kho, *, ten: str | None = None, ma: str | None = None,
              tinh: str | None = None, so_trang: int = 3, mien: str | None = None,
              tinh_ma: str | None = None) -> list[DonVi]:
    """Crawl danh sách thôn/tổ dân phố của các xã từ trang riêng của xã."""
    ds_xa = kho.tim_don_vi(ten=ten, ma=ma, tinh_ten=tinh, tinh_ma=tinh_ma, cap="xa")
    luot = Luot(ma=f"thon-{datetime.now():%Y%m%d-%H%M%S}",
                pham_vi=ten or tinh or tinh_ma or "tat_ca", nhom_du_lieu="thon",
                bat_dau=datetime.now().isoformat(timespec="seconds"))
    ket_qua: list[DonVi] = []

    for xa in ds_xa:
        ung_vien = thon.thu_thap(dict(xa), so_trang=so_trang, mien=mien)
        print(f"  {xa['ten']}: {len(ung_vien)} thôn ứng viên")
        for o in ung_vien:
            ket_qua.append(DonVi(
                ma=f"{xa['ma']}-{lam_slug(o['ten'])}",
                ten=o["ten"] if o["ten"].lower().startswith(("thôn", "tổ dân phố", "khu phố"))
                else "Thôn " + o["ten"],
                loai="thon",
                tinh_ma=xa["tinh_ma"],
                tinh_ten=xa["tinh_ten"],
                parent_ma=xa["ma"],
                nguon=["trang_xa"],
            ))

    kho.ghi_don_vi(ket_qua)
    luot.ket_thuc = datetime.now().isoformat(timespec="seconds")
    luot.so_don_vi = len(ds_xa)
    luot.so_ket_qua = len(ket_qua)
    luot.nguon = ["trang_xa", "govvn"]
    kho.ghi_luot(luot)
    return ket_qua


# Nhóm dữ liệu cấp xã chạy theo tỉnh (mặc định). Nhóm chỉ dùng danh mục thì rẻ,
# nhóm cần mạng thì tốn — xem NHOM_CAN_MANG.
NHOM_XA = [
    "thong_tin_chung", "sap_xep_2025", "hanh_chinh_dan_cu", "lich_su_dia_danh",
    "di_tich", "le_hoi", "kinh_te_van_hoa", "con_nguoi",
]
NHOM_CAN_MANG = {
    "thong_tin_chung", "hanh_chinh_dan_cu", "lich_su_dia_danh",
    "di_tich", "le_hoi", "kinh_te_van_hoa", "con_nguoi",
}


def chay_tinh(kho: Kho, tinh_ma: str, *, nhom: list[str] | None = None,
              chia: tuple[int, int] | None = None, gioi_han: int | None = None,
              dung_llm: bool = True, bo_qua_da_co: bool = True,
              so_moi_lo: int = 0, nghi_giua_lo: float = 0.0) -> list[KetQua]:
    """Cào TOÀN BỘ nhóm cho mọi xã/phường của một tỉnh.

    Mỗi xã chỉ nạp nguồn văn bản MỘT lần rồi bóc tất cả nhóm từ nguồn đó — tránh
    mở lại trang gov nhiều lần và giảm nguy cơ bị chặn.
    """
    import time as _time

    nhom_list = nhom or NHOM_XA
    can_mang = any(n in NHOM_CAN_MANG for n in nhom_list)
    nhom_key = ",".join(sorted(nhom_list))

    ds_xa = kho.tim_don_vi(tinh_ma=tinh_ma, cap="xa", chia=chia, gioi_han=gioi_han)
    if bo_qua_da_co:
        da = kho.da_xu_ly_ds(nhom_key)
        if da:
            truoc = len(ds_xa)
            ds_xa = [dv for dv in ds_xa if dv["ma"] not in da]
            print(f"  (đã xong {truoc - len(ds_xa)} xã từ lần trước · còn {len(ds_xa)})", flush=True)
    nhan_chia = f"-{chia[1]}of{chia[0]}" if chia else ""
    luot = Luot(ma=f"tinh-{tinh_ma}-{datetime.now():%Y%m%d-%H%M%S}{nhan_chia}",
                pham_vi=f"tỉnh {tinh_ma}", nhom_du_lieu=",".join(nhom_list),
                bat_dau=datetime.now().isoformat(timespec="seconds"))
    kho.ghi_luot(luot)

    tat_ca: list[KetQua] = []
    GIO_MOI_XA = int(cau_hinh.lay_ho_so("mang", "gio_moi_don_vi", mac_dinh=180) or 180)
    for i, dv in enumerate(ds_xa, 1):
        try:
            _dat_bao_thuc(GIO_MOI_XA)
            nguons = gom_nguon_van_ban(dict(dv)) if can_mang else []
            # Gộp mọi trường LLM của các nhóm để gọi LLM MỘT lần cho cả xã
            truong_llm: list[dict] = []
            da_co: set[str] = set()
            # Trường LLM đã có giá trị đạt hạng A/B (nguồn có cấu trúc, cổng xã) → LLM chỉ lấp chỗ trống
            khoa_llm = {t["khoa"] for nh in nhom_list for t in cau_hinh.ds_truong("xa", nh)
                        if t.get("cach_lay") == "llm"}
            da_co_cau_truc = khoa_llm & kho.truong_da_dat(
                dv["ma"], muc=("A", "B"), tru_nguon=("nhap_tay_de_xuat", "de_an_sap_xep_hp"))
            for nh in nhom_list:
                for t in cau_hinh.ds_truong("xa", nh):
                    if t.get("cach_lay") == "llm" and t["khoa"] not in da_co | da_co_cau_truc:
                        da_co.add(t["khoa"])
                        truong_llm.append(t)
            llm_da_boc = _boc_llm_hang_loat(truong_llm, nguons, dung_llm) if truong_llm else {}
            kq_xa: list[KetQua] = []
            for nh in nhom_list:
                kq_xa += khai_thac_don_vi(dv, nh, nguons=nguons, dung_llm=dung_llm,
                                          llm_da_boc=llm_da_boc, bo_qua=da_co_cau_truc)
        except HetGio:
            # Báo thức cắt ngang Playwright làm hỏng pipe tới driver: gọi close() lúc này
            # là treo vĩnh viễn (EPIPE). Thoát hẳn, script gọi lại sẽ chạy tiếp.
            # ponytail: xã quá giờ bị đánh dấu xong để không lặp vô hạn; chạy lại riêng
            # bằng `khai-thac xa --ma <mã> --lam-lai` khi cần.
            kho.danh_dau_da_xu_ly(nhom_key, dv["ma"])
            print(f"  ⏱ {dv['ten']} ({dv['ma']}): quá {GIO_MOI_XA}s, bỏ qua — khởi động lại tiến trình",
                  flush=True)
            import os

            os._exit(MA_THOAT_KHOI_DONG_LAI)
        except NguonBiChan as e:
            _tat_bao_thuc()
            print(f"  ⚠ {e} — dừng luồng, chạy tiếp sau (đã lưu tới {dv['ten']})", flush=True)
            break
        except Exception as e:
            _tat_bao_thuc()
            # Một xã lỗi (trang/LLM) không được làm chết cả luồng
            print(f"  ✗ {dv['ten']}: lỗi {type(e).__name__}: {e}", flush=True)
            continue
        _tat_bao_thuc()
        kho.ghi_ket_qua(kq_xa, luot.ma)
        kho.danh_dau_da_xu_ly(nhom_key, dv["ma"])   # đánh dấu để chạy lại tiếp đúng chỗ
        tat_ca += kq_xa
        so_dat = sum(1 for k in kq_xa if k.trang_thai == DAT)
        print(f"  [{i}/{len(ds_xa)}] {dv['ten']}: {so_dat}/{len(kq_xa)} trường đạt", flush=True)
        _ghi_tien_trinh(luot.ma, "tinh-" + tinh_ma, i, len(ds_xa), dv["ten"], len(tat_ca), chia)
        if so_moi_lo and nghi_giua_lo and i % so_moi_lo == 0 and i < len(ds_xa):
            print(f"  … nghỉ {nghi_giua_lo:.0f}s sau lô {i // so_moi_lo}", flush=True)
            _time.sleep(nghi_giua_lo)

    luot.ket_thuc = datetime.now().isoformat(timespec="seconds")
    luot.so_don_vi = len(ds_xa)
    luot.so_ket_qua = len(tat_ca)
    luot.so_dat = sum(1 for k in tat_ca if k.trang_thai == DAT)
    luot.nguon = ["open_api_v2", "tinhthanh34", "wikipedia_vi", "photon_osm", "govvn"]
    kho.ghi_luot(luot)
    return tat_ca
