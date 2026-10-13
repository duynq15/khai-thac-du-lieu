#!/usr/bin/env bash
# Cào TOÀN BỘ dữ liệu cho MỘT tỉnh/thành (mã BNV).
# Thứ tự: cào nóng cache (nhiều luồng) → rồi LLM (1 luồng) → OCOP → thôn → xuất.
# Chạy lại được: phần đã xong tự bỏ qua.
#
#   ./chay-mot-tinh.sh <ma-tinh> [so-luong-cao] [them-co]
# Ví dụ:
#   ./chay-mot-tinh.sh 31
#   ./chay-mot-tinh.sh 01 6
#   ./chay-mot-tinh.sh 31 6 --dung-proxy
set -u

T="${1:?Thiếu mã tỉnh, ví dụ: ./chay-mot-tinh.sh 31}"
shift
if [[ "${1:-}" =~ ^[0-9]+$ ]]; then N="$1"; shift; else N=6; fi
THEM="$*"
mkdir -p logs
# Tiến trình tự thoát mã 75 khi một xã quá giờ (tránh treo Playwright) → gọi lại, resume tiếp.
chay_lai() { while :; do "$@"; rc=$?; [ "$rc" -ne 75 ] && return "$rc"; done; }
BAT_DAU=$SECONDS

echo "=== Tỉnh $T · ${N} luồng cào ${THEM:+($THEM)} ==="
[ -z "${BRAVE_API_KEY:-}" ] && echo "⚠ Chưa có BRAVE_API_KEY (tìm kiếm sẽ lùi về scrape, dễ bị chặn)"

# 0) Bảo đảm danh mục đã có (rất nhanh, tự bỏ qua nếu đã nạp)
echo "--- [0/5] Bảo đảm danh mục ---"
uv run khai-thac danh-muc --tinh "$T" --nhanh >/dev/null 2>&1 || true

# 1) PHA CÀO — nóng cache + nhóm không-LLM, nhiều luồng
echo "--- [1/5] Cào (không LLM), ${N} luồng ---"
for k in $(seq 0 $((N - 1))); do
  chay_lai uv run khai-thac tinh --ma "$T" --khong-llm \
    --nhom thong_tin_chung,sap_xep_2025,hanh_chinh_dan_cu \
    --shard "$k/$N" $THEM > "logs/t$T-cao-$k.log" 2>&1 &
done
wait
uv run khai-thac thong-ke --tinh-ma "$T" | head -3

# 2) PHA OLLAMA — nội dung, 1 luồng (đọc cache). Dừng rồi chạy lại sẽ TIẾP đúng chỗ.
echo "--- [2/5] Ollama (nội dung), 1 luồng ---"
chay_lai uv run khai-thac tinh --ma "$T" --shard 0/1 --khong-trinh-duyet \
  --nhom hanh_chinh_dan_cu,lich_su_dia_danh,di_tich,le_hoi,kinh_te_van_hoa,con_nguoi \
  > "logs/t$T-ollama.log" 2>&1
tail -1 "logs/t$T-ollama.log"

# 3) OCOP / đặc sản (hiện hỗ trợ mạnh Hải Phòng = 31)
echo "--- [3/5] OCOP/đặc sản ---"
uv run khai-thac nongsan --tinh-ma "$T" > "logs/t$T-ocop.log" 2>&1 || true

# 4) Thôn / tổ dân phố
echo "--- [4/5] Thôn/TDP ---"
uv run khai-thac thon --tinh-ma "$T" --xuat > "logs/t$T-thon.log" 2>&1 || true

# 5) Thống kê + xuất bàn giao
echo "--- [5/5] Thống kê & xuất ---"
uv run khai-thac thong-ke --tinh-ma "$T"
uv run khai-thac xuat --dinh-dang excel
uv run khai-thac xuat --dinh-dang json

echo "=== XONG tỉnh $T · mất $(( (SECONDS - BAT_DAU) / 60 )) phút ==="
