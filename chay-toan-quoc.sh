#!/usr/bin/env bash
# Chạy khai thác toàn quốc song song nhiều luồng (mỗi luồng một tiến trình riêng).
#   ./chay-toan-quoc.sh [so-luong] [nhom] [them-co]
# Ví dụ:
#   ./chay-toan-quoc.sh 6
#   ./chay-toan-quoc.sh 4 thong_tin_chung --dung-proxy
#
# Mỗi luồng một Chrome + một phần đơn vị (shard K/N). SQLite bật WAL nên ghi
# song song được. Theo dõi bằng:  uv run khai-thac tien-do
set -u

N="${1:-6}"
NHOM="${2:-thong_tin_chung}"
shift 2 2>/dev/null || true
THEM="$*"

mkdir -p logs
echo "Chạy $N luồng cho nhóm '$NHOM' ${THEM:+(cờ: $THEM)}"

pids=()
for k in $(seq 0 $((N - 1))); do
  uv run khai-thac xa --nhom "$NHOM" --toan-quoc --shard "$k/$N" $THEM \
    > "logs/shard-$k.log" 2>&1 &
  pids+=($!)
  echo "  luồng $k/$N -> logs/shard-$k.log (pid ${pids[-1]})"
done

echo "Đang chạy. Xem tiến độ: uv run khai-thac tien-do"
wait
echo "Tất cả luồng đã xong."
