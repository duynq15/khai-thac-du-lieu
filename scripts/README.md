# scripts/

Script một lần đã dùng để ghi/kiểm dữ liệu (chuyển từ /tmp/kt). Chạy từ gốc repo:
`.venv/bin/python scripts/<tep>.py`. Tệp trung gian/cache (trang web, PDF, wiki_cache.json…)
nằm ở `du_lieu/tam_kt/` (không vào git).

- `nap_*.py`: đã thay thế, chỉ giữ để tra lịch sử. Các lượt ghi thẳng của chúng đã chuyển sang
  `du_lieu/nguon_tay/<ma>.json` bằng `chuyen_nguon_tay.py`, nạp lại qua `khai-thac nap-tay`, và
  dòng cũ đánh `trang_thai='bo'`. Nguồn mới: chỉ viết tệp `nguon_tay` (lối ghi duy nhất);
  `diem_tin` suy từ `muc` + `canh_bao` (`models.diem_theo_muc`), không đặt tay.
- `chuyen_nguon_tay.py`: đọc DB (không ghi), xuất các lượt ghi thẳng cũ thành tệp `nguon_tay`.
- `hn_tb190.py`, `hp_tb190.py`, `wiki_anh*.py`, `ct360.py`: dựng tệp `nguon_tay` từ văn bản/trang đã tải.
- `don_*.py`, `bo_loi.py`: đánh dấu `trang_thai='bo'` (không xoá) cho bản ghi rác.
- `cham_diem.py`: chấm gói bàn giao mới nhất (độ phủ, hạng nguồn, theo nhóm).

Kiểm JSON ↔ Excel: `uv run khai-thac kiem-xuat` (mã thoát 1 nếu lệch).
