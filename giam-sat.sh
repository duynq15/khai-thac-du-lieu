#!/usr/bin/env bash
# GIÁM SÁT cho bộ điều phối qua đêm.
#   - Nếu dieu-phoi.sh chết (chưa xong) -> khởi động lại (resume)
#   - In nhịp mỗi 90s kèm độ phủ từng tỉnh
#   - Dừng khi xong, hoặc hết hạn 6h
# KHÔNG cắt tiến trình đang chạy (việc treo để `timeout` trong dieu-phoi.sh lo,
# vì cắt theo mtime dễ cắt oan lúc chuyển pha).
set -u
cd "$(dirname "$0")" || exit 1
LOG="logs/giam-sat.out"
DS="${1:-31 01 48 79 92 46}"
HAN="$(( $(date +%s) + 6*3600 ))"
log(){ echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

log "=== GIÁM SÁT bật · [$DS] ==="
while true; do
  if grep -q "HOÀN TẤT" logs/dieu-phoi.out 2>/dev/null; then log "✓ HOÀN TẤT"; break; fi

  if ! pgrep -f "dieu-phoi.sh" >/dev/null; then
    log "⚠ dieu-phoi.sh không chạy → khởi động lại (resume)"
    setsid nohup ./dieu-phoi.sh "$DS" 6 >> logs/dieu-phoi.run 2>&1 < /dev/null &
    sleep 5
  fi

  do_phu="$(python3 - <<'PY' 2>/dev/null
import sqlite3
c=sqlite3.connect("du_lieu/khai_thac.sqlite")
for ma,nm in [('31','HP'),('01','HN'),('48','DN'),('79','HCM'),('92','CT'),('46','Hue')]:
    tong=c.execute("SELECT count(*) FROM don_vi WHERE tinh_ma=? AND loai IN ('xa','phuong','dac_khu')",(ma,)).fetchone()[0]
    # Phủ thật: xã có ≥1 trường nội dung (nhóm LLM) ĐẠT từ nguồn cào được — không tính danh mục/nhập tay đề xuất
    n=c.execute("""SELECT count(DISTINCT don_vi_ma) FROM ket_qua WHERE trang_thai='dat'
        AND nhom IN ('lich_su_dia_danh','di_tich','le_hoi','kinh_te_van_hoa','con_nguoi')
        AND nguon_ma NOT IN ('nhap_tay_de_xuat','de_an_sap_xep_hp','danh_muc')
        AND don_vi_ma IN (SELECT ma FROM don_vi WHERE tinh_ma=?)""",(ma,)).fetchone()[0]
    print(f"{nm}:{n}/{tong}",end=" ")
print()
PY
)"
  log "nhịp · $(pgrep -fc 'khai-thac tinh' 2>/dev/null || echo 0) proc · $(tail -1 logs/dieu-phoi.out 2>/dev/null | sed 's/.*] //')"
  log "       phủ: ${do_phu}"

  [ "$(date +%s)" -ge "$HAN" ] && { log "⏰ hết hạn 6h"; break; }
  sleep 90
done
log "=== GIÁM SÁT kết thúc ==="
