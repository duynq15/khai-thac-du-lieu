"""Đọc cấu hình trường dữ liệu và sổ đăng ký nguồn."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

GOC = Path(__file__).resolve().parent.parent
THU_MUC_CFG = GOC / "config"


@lru_cache(maxsize=1)
def truong_du_lieu() -> dict:
    with open(THU_MUC_CFG / "truong_du_lieu.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def nguon() -> dict:
    with open(THU_MUC_CFG / "nguon.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def ho_so_chay() -> dict:
    """Hồ sơ chạy (config/chay.yaml)."""
    with open(THU_MUC_CFG / "chay.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def lay_ho_so(*duong: str, mac_dinh=None):
    """Đọc giá trị lồng nhau trong hồ sơ chạy: lay_ho_so('mang', 'he_so_jitter')."""
    nut = ho_so_chay()
    for k in duong:
        if not isinstance(nut, dict) or k not in nut:
            return mac_dinh
        nut = nut[k]
    return nut


def ds_truong(cap: str, nhom: str) -> list[dict]:
    """Danh sách trường của một nhóm ở một cấp."""
    cap_cfg = truong_du_lieu().get("cap", {}).get(cap, {})
    return (cap_cfg.get("nhom", {}).get(nhom, {}) or {}).get("truong", [])


def nhan_nhom(cap: str, nhom: str) -> str:
    cap_cfg = truong_du_lieu().get("cap", {}).get(cap, {})
    return ((cap_cfg.get("nhom", {}).get(nhom, {}) or {}).get("nhan")) or nhom


def ds_nhom(cap: str) -> list[str]:
    return list((truong_du_lieu().get("cap", {}).get(cap, {}).get("nhom", {}) or {}).keys())


def thong_tin_nguon(ma: str) -> dict:
    for n in nguon().get("nguon", []):
        if n["ma"] == ma:
            return n
    return {}
