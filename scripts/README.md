# scripts/

Script một lần đã dùng để ghi/kiểm dữ liệu (chuyển từ /tmp/kt). Chạy từ gốc repo:
`.venv/bin/python scripts/<tep>.py`. Tệp trung gian/cache (trang web, PDF, wiki_cache.json…)
nằm ở `du_lieu/tam_kt/` (không vào git).

- `nap_*.py`: sao lưu DB rồi ghi thẳng `ket_qua` (chỉ ô đang trống). Nguồn mới nên viết thành
  `du_lieu/nguon_tay/<ma>.json` và nạp bằng `khai-thac nap-tay` thay vì thêm script kiểu này.
- `hn_tb190.py`, `hp_tb190.py`, `wiki_anh*.py`, `ct360.py`: dựng tệp `nguon_tay` từ văn bản/trang đã tải.
- `don_*.py`, `bo_loi.py`: đánh dấu `trang_thai='bo'` (không xoá) cho bản ghi rác.
- `cham_diem.py`: chấm gói bàn giao mới nhất (độ phủ, hạng nguồn, theo nhóm).

Kiểm JSON ↔ Excel: `uv run khai-thac kiem-xuat` (mã thoát 1 nếu lệch).
