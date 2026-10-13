"""Kho làm việc SQLite: danh mục, kết quả khai thác và nhật ký lượt chạy."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import DonVi, KetQua, Luot

GOC = Path(__file__).resolve().parent.parent
DU_LIEU = GOC / "du_lieu"
MAC_DINH_DB = DU_LIEU / "khai_thac.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS don_vi (
    ma TEXT PRIMARY KEY,
    ten TEXT NOT NULL,
    loai TEXT NOT NULL,
    tinh_ma TEXT,
    tinh_ten TEXT,
    parent_ma TEXT,
    codename TEXT,
    don_vi_cu_hop_thanh TEXT,
    so_don_vi_cu INTEGER,
    can_cu_phap_ly TEXT,
    ngay_hieu_luc TEXT,
    nguon TEXT,
    khop_da_nguon INTEGER
);

CREATE TABLE IF NOT EXISTS ket_qua (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    luot_ma TEXT,
    don_vi_ma TEXT,
    don_vi_ten TEXT,
    cap TEXT,
    nhom TEXT,
    truong TEXT,
    gia_tri TEXT,
    kieu TEXT,
    nguon_ma TEXT,
    nguon_ten TEXT,
    nguon_url TEXT,
    nguon_muc TEXT,
    trich_doan TEXT,
    diem_tin INTEGER,
    trang_thai TEXT,
    ly_do_loi TEXT,
    canh_bao TEXT,
    UNIQUE (luot_ma, don_vi_ma, nhom, truong)
);

CREATE TABLE IF NOT EXISTS luot (
    ma TEXT PRIMARY KEY,
    pham_vi TEXT,
    nhom_du_lieu TEXT,
    bat_dau TEXT,
    ket_thuc TEXT,
    so_don_vi INTEGER,
    so_ket_qua INTEGER,
    so_dat INTEGER,
    nguon TEXT
);

-- Đánh dấu (nhóm + đơn vị) đã xử lý xong để chạy lại TIẾP ĐÚNG CHỖ DỪNG
CREATE TABLE IF NOT EXISTS da_xu_ly (
    nhom_key TEXT,
    don_vi_ma TEXT,
    luc TEXT,
    PRIMARY KEY (nhom_key, don_vi_ma)
);

CREATE INDEX IF NOT EXISTS idx_ket_qua_don_vi ON ket_qua (don_vi_ma, nhom);
CREATE INDEX IF NOT EXISTS idx_ket_qua_trang_thai ON ket_qua (trang_thai);
"""


def _json_hay_chuoi(v):
    return json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v


class Kho:
    def __init__(self, duong_dan: Path | str | None = MAC_DINH_DB):
        if not duong_dan:
            duong_dan = MAC_DINH_DB
        self.duong_dan = Path(duong_dan)
        self.duong_dan.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.duong_dan))
        self.conn.row_factory = sqlite3.Row
        # WAL + chờ khoá: cho phép nhiều tiến trình (shard) cùng ghi
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.executescript(SCHEMA)
        # Nâng cấp kho cũ: thêm cột parent_ma nếu chưa có
        cot = {r[1] for r in self.conn.execute("PRAGMA table_info(don_vi)")}
        if "parent_ma" not in cot:
            self.conn.execute("ALTER TABLE don_vi ADD COLUMN parent_ma TEXT")
        if "nam_du_lieu" not in {r[1] for r in self.conn.execute("PRAGMA table_info(ket_qua)")}:
            self.conn.execute("ALTER TABLE ket_qua ADD COLUMN nam_du_lieu INTEGER")
        self.conn.commit()

    # ---------------------------------------------------------------- danh mục
    def ghi_don_vi(self, ds: list[DonVi], *, ghi_de: bool = True) -> int:
        dong = [
            (
                d.ma, d.ten, d.loai, d.tinh_ma, d.tinh_ten, d.parent_ma, d.codename,
                json.dumps(d.don_vi_cu_hop_thanh, ensure_ascii=False),
                d.so_don_vi_cu, d.can_cu_phap_ly, d.ngay_hieu_luc,
                json.dumps(d.nguon, ensure_ascii=False),
                None if d.khop_da_nguon is None else int(d.khop_da_nguon),
            )
            for d in ds
        ]
        cach = "INSERT OR REPLACE" if ghi_de else "INSERT OR IGNORE"
        self.conn.executemany(
            """INSERT OR REPLACE INTO don_vi
                (ma, ten, loai, tinh_ma, tinh_ten, parent_ma, codename, don_vi_cu_hop_thanh,
                 so_don_vi_cu, can_cu_phap_ly, ngay_hieu_luc, nguon, khop_da_nguon)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""".replace("INSERT OR REPLACE", cach),
            dong,
        )
        self.conn.commit()
        return len(dong)

    # ------------------------------------------------------------------ danh mục
    LOAI_THEO_CAP = {
        "xa": ("xa", "phuong", "dac_khu"),
        "tinh": ("tinh", "thanh_pho"),
        "thon": ("thon",),
    }

    def tim_don_vi(self, *, ten: str | None = None, ma: str | None = None,
                   tinh_ten: str | None = None, cap: str = "xa",
                   loai: str | None = None, parent_ma: str | None = None,
                   bo_qua_nhom: str | None = None, bo_qua_nhoms: list[str] | None = None,
                   gioi_han: int | None = None,
                   tinh_ma: str | None = None, chia: tuple[int, int] | None = None) -> list[sqlite3.Row]:
        q = "SELECT * FROM don_vi WHERE 1=1"
        p: list = []
        if loai:
            q += " AND loai = ?"
            p.append(loai)
        elif cap in self.LOAI_THEO_CAP:
            ds_loai = self.LOAI_THEO_CAP[cap]
            q += " AND loai IN (%s)" % ",".join("?" * len(ds_loai))
            p.extend(ds_loai)
        if parent_ma:
            q += " AND parent_ma = ?"
            p.append(parent_ma)
        if tinh_ma:
            q += " AND tinh_ma = ?"
            p.append(tinh_ma)
        if ma:
            q += " AND ma = ?"
            p.append(ma)
        if ten:
            q += " AND ten LIKE ?"
            p.append(f"%{ten}%")
        if tinh_ten:
            q += " AND tinh_ten LIKE ?"
            p.append(f"%{tinh_ten}%")
        if chia:
            n, k = chia
            q += " AND (rowid % ?) = ?"
            p.extend([n, k])
        if bo_qua_nhom:
            q += (" AND ma NOT IN (SELECT don_vi_ma FROM ket_qua"
                  " WHERE nhom = ? AND trang_thai = 'dat')")
            p.append(bo_qua_nhom)
        if bo_qua_nhoms:
            ds_nhom = list(bo_qua_nhoms)
            # Bỏ qua xã đã CHẠY QUA đủ các nhóm này (có bản ghi), không xét đạt hay không
            q += (" AND ma NOT IN (SELECT don_vi_ma FROM ket_qua"
                  " WHERE nhom IN (%s)"
                  " GROUP BY don_vi_ma HAVING COUNT(DISTINCT nhom) = ?)"
                  % ",".join("?" * len(ds_nhom)))
            p.extend(ds_nhom + [len(ds_nhom)])
        q += " ORDER BY tinh_ma, ten"
        if gioi_han:
            q += " LIMIT ?"
            p.append(gioi_han)
        return self.conn.execute(q, p).fetchall()

    def dem_don_vi(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM don_vi").fetchone()[0]

    def ban_do_ten_cu(self, tinh_ma: str | None = None) -> dict[str, str]:
        """Bản đồ: tên đơn vị CŨ (đã bỏ tiền tố, chuẩn hoá) -> mã xã/phường MỚI.

        Nếu truyền tinh_ma thì chỉ lấy đơn vị thuộc tỉnh đó (tránh khớp nhầm
        sang tỉnh khác khi tên cũ trùng/na ná).
        """
        import re as _re

        from .text import chuan_hoa

        # mã đơn vị hợp lệ (lọc theo tỉnh nếu có)
        hop_le: set[str] | None = None
        if tinh_ma:
            hop_le = {r[0] for r in self.conn.execute(
                "SELECT ma FROM don_vi WHERE tinh_ma = ?", (tinh_ma,))}

        out: dict[str, str] = {}
        for ma, cu in self.conn.execute(
            "SELECT ma, don_vi_cu_hop_thanh FROM don_vi WHERE don_vi_cu_hop_thanh IS NOT NULL"
        ):
            if hop_le is not None and ma not in hop_le:
                continue
            try:
                ds = json.loads(cu or "[]")
            except ValueError:
                ds = []
            for ten in ds:
                k = chuan_hoa(_re.sub(r"^(Xã|Phường|Thị trấn|Đặc khu)\s+", "", str(ten)))
                k = k.split("phan con lai")[0].strip()
                if k:
                    out.setdefault(k, ma)
        return out

    def ban_do_ma(self, tinh_ma: str | None = None) -> dict[str, str]:
        """Tên (cũ hoặc mới, có/không tiền tố, đã chuẩn hoá) -> mã xã MỚI của một tỉnh.

        Dùng chung cho mọi nguồn ghép dữ liệu theo tên xã. Luôn truyền tinh_ma: tên
        trùng giữa các tỉnh (Phường Hương Trà ở Huế và Đà Nẵng) chỉ phân biệt được theo tỉnh.
        """
        import re as _re

        from .text import chuan_hoa

        bd = dict(self.ban_do_ten_cu(tinh_ma))
        for row in self.tim_don_vi(tinh_ma=tinh_ma, cap="xa"):
            bd[chuan_hoa(row["ten"])] = row["ma"]
            bd[chuan_hoa(_re.sub(r"^(Xã|Phường|Đặc khu|Thị trấn)\s+", "", row["ten"]))] = row["ma"]
        return bd

    @staticmethod
    def tim_ma_xa(ban_do: dict[str, str], ten: str) -> str | None:
        """Tra mã xã từ tên trong nguồn ('Đông Anh', 'Xã Đông Anh', 'phường X')."""
        from .text import chuan_hoa

        ten = str(ten or "").strip()
        for k in (ten, "Xã " + ten, "Phường " + ten):
            ma = ban_do.get(chuan_hoa(k))
            if ma:
                return ma
        return None

    # ---------------------------------------------------------------- lượt
    def ghi_luot(self, luot: Luot) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO luot
               (ma, pham_vi, nhom_du_lieu, bat_dau, ket_thuc, so_don_vi, so_ket_qua, so_dat, nguon)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (luot.ma, luot.pham_vi, luot.nhom_du_lieu, luot.bat_dau, luot.ket_thuc,
             luot.so_don_vi, luot.so_ket_qua, luot.so_dat,
             json.dumps(luot.nguon, ensure_ascii=False)),
        )
        self.conn.commit()

    # ---------------------------------------------------------------- kết quả
    def ghi_ket_qua(self, ds: list[KetQua], luot_ma: str | None = None) -> int:
        dong = []
        for k in ds:
            gia_tri = k.gia_tri if isinstance(k.gia_tri, str) else json.dumps(k.gia_tri, ensure_ascii=False)
            dong.append((
                luot_ma, k.don_vi_ma, k.don_vi_ten, k.cap, k.nhom, k.truong, gia_tri, k.kieu,
                k.nguon_ma, k.nguon_ten, k.nguon_url, k.nguon_muc, k.trich_doan,
                k.diem_tin, k.trang_thai, k.ly_do_loi,
                json.dumps(k.canh_bao, ensure_ascii=False), k.nam_du_lieu,
            ))
        self.conn.executemany(
            """INSERT OR REPLACE INTO ket_qua
               (luot_ma, don_vi_ma, don_vi_ten, cap, nhom, truong, gia_tri, kieu,
                nguon_ma, nguon_ten, nguon_url, nguon_muc, trich_doan, diem_tin,
                trang_thai, ly_do_loi, canh_bao, nam_du_lieu)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            dong,
        )
        self.conn.commit()
        return len(dong)

    def lay_ket_qua(self, *, don_vi_ma: str | None = None, nhom: str | None = None,
                    trang_thai: str | None = None, luot_ma: str | None = None,
                    moi_nhat: bool = False) -> list[sqlite3.Row]:
        q = "SELECT * FROM ket_qua WHERE 1=1"
        p: list = []
        for cot, gia in (("don_vi_ma", don_vi_ma), ("nhom", nhom),
                         ("trang_thai", trang_thai), ("luot_ma", luot_ma)):
            if gia:
                q += f" AND {cot} = ?"
                p.append(gia)
        if moi_nhat:
            # Mỗi trường của mỗi đơn vị chỉ lấy bản ghi mới nhất, tránh trùng giữa các lượt
            q += (" AND id IN (SELECT MAX(id) FROM ket_qua"
                  " GROUP BY don_vi_ma, nhom, truong)")
        q += " ORDER BY don_vi_ten, nhom, id"
        return self.conn.execute(q, p).fetchall()

    def dong(self) -> None:
        self.conn.close()

    # ------------------------------------------------- đánh dấu đã xử lý
    def da_xu_ly_ds(self, nhom_key: str) -> set[str]:
        """Tập mã đơn vị đã xử lý xong cho một tổ hợp nhóm."""
        return {r[0] for r in self.conn.execute(
            "SELECT don_vi_ma FROM da_xu_ly WHERE nhom_key = ?", (nhom_key,))}

    def danh_dau_da_xu_ly(self, nhom_key: str, ma: str) -> None:
        from datetime import datetime

        self.conn.execute(
            "INSERT OR IGNORE INTO da_xu_ly (nhom_key, don_vi_ma, luc) VALUES (?,?,?)",
            (nhom_key, ma, datetime.now().isoformat(timespec="seconds")))
        self.conn.commit()
