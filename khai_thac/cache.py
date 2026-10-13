"""Cache trang đã tải.

Một xã thường được bóc cho nhiều nhóm dữ liệu (giới thiệu, hành chính, lịch sử,
di tích…). Không cache thì mỗi nhóm lại mở lại đúng trang gov đó — vừa chậm vừa
dễ bị chặn. Cache giúp: nạp một lần, dùng cho mọi nhóm; chạy lại (resume) không
phải tải lại; và tra được nguồn khi cần đối chiếu.

Xoá cache khi muốn lấy bản mới: `khai-thac tinh --lam-moi` hoặc xoá tay thư mục.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .store import DU_LIEU

THU_MUC = DU_LIEU / "cache_trang"
_dung = True


def dat_dung_cache(bat: bool) -> None:
    global _dung
    _dung = bat


def _tep(url: str) -> Path:
    return THU_MUC / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".txt")


def lay(url: str) -> str | None:
    if not _dung:
        return None
    p = _tep(url)
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return None
    return None


def luu(url: str, van_ban: str) -> None:
    if not _dung or not van_ban:
        return
    THU_MUC.mkdir(parents=True, exist_ok=True)
    try:
        _tep(url).write_text(van_ban, encoding="utf-8")
    except OSError:
        pass


def xoa_het() -> int:
    if THU_MUC.is_dir():
        n = len(list(THU_MUC.glob("*.txt")))
        shutil.rmtree(THU_MUC)
        return n
    return 0
