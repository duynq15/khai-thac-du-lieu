#!/usr/bin/env bash
# Cào TOÀN BỘ dữ liệu theo TỪNG tỉnh/thành phố.
# Mỗi tỉnh chia N luồng; xong tỉnh này mới sang tỉnh kế. Chạy lại tự bỏ qua xã đã đủ nhóm.
#   ./chay-theo-tinh.sh [so-luong] [them-co]
# Ví dụ:
#   ./chay-theo-tinh.sh 4
#   ./chay-theo-tinh.sh 4 --dung-proxy
# Theo dõi: uv run khai-thac tien-do
set -u

N="${1:-4}"
shift 1 2>/dev/null || true
THEM="$*"

mkdir -p logs
codes=$(python3 -c "import sqlite3;print(' '.join(r[0] for r in sqlite3.connect('du_lieu/khai_thac.sqlite').execute(\"SELECT ma FROM don_vi WHERE loai IN ('tinh','thanh_pho') AND ma IS NOT NULL ORDER BY ma\")))")

echo "Sẽ chạy ${N} luồng/tỉnh cho: $codes"
for ma in $codes; do
  echo "== Tỉnh $ma =="
  for k in $(seq 0 $((N - 1))); do
    uv run khai-thac tinh --ma "$ma" --shard "$k/$N" $THEM \
      > "logs/tinh-$ma-$k.log" 2>&1 &
  done
  wait
  echo "   xong tỉnh $ma"
done
echo "Hoàn tất toàn quốc."
