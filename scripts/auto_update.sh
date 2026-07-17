#!/bin/bash
# =============================================================================
# سكربت التحديث التلقائي لـ Omni Medical Suite
# =============================================================================
# يقوم بـ:
# - تحديث المستودعات من GitHub يومياً
# - فحص تحديثات الحزم شهرياً
# - إعادة تشغيل الخدمات بعد التحديث
# - إرسال إشعارات بالتحديثات
# =============================================================================

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# الألوان
# ─────────────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# ─────────────────────────────────────────────────────────────────────────────
# المتغيرات
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR="$HOME/omni-medical-suite"
REPOS_DIR="$BASE_DIR/repos"
LOGS_DIR="$BASE_DIR/logs"
CONFIGS_DIR="$BASE_DIR/configs"
VENV_DIR="$BASE_DIR/venv"

LOG_FILE="$LOGS_DIR/update_$(date +%Y%m%d_%H%M%S).log"
UPDATE_LOCK="$BASE_DIR/.update_lock"

# ─────────────────────────────────────────────────────────────────────────────
# دوال المساعدة
# ─────────────────────────────────────────────────────────────────────────────
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[تحذير]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[خطأ]${NC} $1" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${CYAN}[معلومة]${NC} $1" | tee -a "$LOG_FILE"
}

# ─────────────────────────────────────────────────────────────────────────────
# التحقق من القفل
# ─────────────────────────────────────────────────────────────────────────────
check_lock() {
    if [ -f "$UPDATE_LOCK" ]; then
        PID=$(cat "$UPDATE_LOCK" 2>/dev/null)
        if ps -p "$PID" > /dev/null 2>&1; then
            error "تحديث آخر قيد التشغيل (PID: $PID). إنهاء."
            exit 1
        else
            warn "قفل قديم موجود. إزالته..."
            rm -f "$UPDATE_LOCK"
        fi
    fi

    echo $$ > "$UPDATE_LOCK"
    trap 'rm -f "$UPDATE_LOCK"' EXIT
}

# ─────────────────────────────────────────────────────────────────────────────
# تحديث المستودعات
# ─────────────────────────────────────────────────────────────────────────────
update_repositories() {
    info "جارٍ تحديث المستودعات..."

    if [ ! -d "$REPOS_DIR" ]; then
        error "مجلد المستودعات غير موجود: $REPOS_DIR"
    fi

    cd "$REPOS_DIR"

    updated_count=0
    failed_count=0

    for repo in */; do
        if [ -d "$repo/.git" ]; then
            log "جارٍ تحديث $repo..."
            cd "$repo"

            # حفظ التغييرات المحلية
            git stash push -m "auto-update-stash-$(date +%Y%m%d)" 2>/dev/null || true

            # جلب التحديثات
            if git fetch origin; then
                # التحقق من وجود تحديثات
                LOCAL=$(git rev-parse HEAD)
                REMOTE=$(git rev-parse origin/main 2>/dev/null || git rev-parse origin/master 2>/dev/null)

                if [ "$LOCAL" != "$REMOTE" ]; then
                    log "  ↳ تحديثات جديدة متوفرة في $repo"

                    # محاولة الدمج
                    if git pull origin main 2>/dev/null || git pull origin master 2>/dev/null; then
                        log "  ✅ تم تحديث $repo بنجاح"
                        updated_count=$((updated_count + 1))
                    else
                        warn "  ⚠️ تعذر دمج التحديثات في $repo. قد يكون هناك تعارض."
                        failed_count=$((failed_count + 1))
                    fi
                else
                    log "  ✓ $repo محدث بالفعل"
                fi
            else
                warn "  ⚠️ تعذر جلب التحديثات لـ $repo"
                failed_count=$((failed_count + 1))
            fi

            cd "$REPOS_DIR"
        fi
    done

    log "📊 ملخص تحديث المستودعات: $updated_count محدث، $failed_count فشل"

    return $failed_count
}

# ─────────────────────────────────────────────────────────────────────────────
# تحديث حزم Python
# ─────────────────────────────────────────────────────────────────────────────
update_python_packages() {
    info "جارٍ فحص تحديثات حزم Python..."

    if [ ! -f "$BASE_DIR/requirements.txt" ]; then
        warn "ملف requirements.txt غير موجود. تخطي تحديث الحزم."
        return 0
    fi

    source "$VENV_DIR/bin/activate"

    # إنشاء نسخة احتياطية
    pip freeze > "$LOGS_DIR/pip_backup_$(date +%Y%m%d).txt"

    # تحديث الحزم
    if pip install --upgrade -r "$BASE_DIR/requirements.txt" 2>&1 | tee -a "$LOG_FILE"; then
        log "✅ تم تحديث حزم Python"
    else
        warn "⚠️ بعض الحزم لم يتم تحديثها"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# تحديث نظام Manjaro
# ─────────────────────────────────────────────────────────────────────────────
update_system_packages() {
    info "جارٍ فحص تحديثات النظام..."

    # فحص إذا كان الوقت مناسباً (مر شهر على آخر تحديث)
    last_system_update="$BASE_DIR/.last_system_update"

    if [ -f "$last_system_update" ]; then
        last_date=$(cat "$last_system_update")
        days_since=$(( ( $(date +%s) - $(date -d "$last_date" +%s 2>/dev/null || echo 0) ) / 86400 ))

        if [ "$days_since" -lt 30 ]; then
            log "⏭️ آخر تحديث للنظام قبل $days_since يوم. تخطي."
            return 0
        fi
    fi

    # تحديث النظام
    if sudo pacman -Syu --noconfirm 2>&1 | tee -a "$LOG_FILE"; then
        log "✅ تم تحديث حزم النظام"
        date +%Y-%m-%d > "$last_system_update"
    else
        warn "⚠️ بعض حزم النظام لم يتم تحديثها"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# إعادة تشغيل الخدمات
# ─────────────────────────────────────────────────────────────────────────────
restart_services() {
    info "جارٍ إعادة تشغيل الخدمات..."

    # التحقق من وجود خدمات
    if systemctl --user is-active omni-medical &>/dev/null; then
        systemctl --user restart omni-medical
        log "✅ تم إعادة تشغيل خدمة omni-medical"
    fi

    if systemctl --user is-active omni-medical-logger.timer &>/dev/null; then
        systemctl --user restart omni-medical-logger.timer
        log "✅ تم إعادة تشغيل مؤقت التسجيل"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# إرسال إشعار
# ─────────────────────────────────────────────────────────────────────────────
send_notification() {
    local message="$1"

    # إشعار سطح المكتب
    if command -v notify-send &> /dev/null; then
        notify-send -i application-pdf "Omni Medical Suite" "$message" 2>/dev/null || true
    fi

    # إشعار سجل النظام
    logger -t omni-medical "$message" 2>/dev/null || true
}

# ─────────────────────────────────────────────────────────────────────────────
# تنظيف السجلات القديمة
# ─────────────────────────────────────────────────────────────────────────────
cleanup_logs() {
    info "جارٍ تنظيف السجلات القديمة..."

    # حذف سجلات التحديث الأقدم من 30 يوم
    find "$LOGS_DIR" -name "update_*.log" -type f -mtime +30 -delete 2>/dev/null || true

    # حذف سجلات الأخطاء الأقدم من 90 يوم
    find "$LOGS_DIR/errors" -name "errors_*.jsonl" -type f -mtime +90 -delete 2>/dev/null || true

    # حذف سجلات الإجراءات الأقدم من 90 يوم
    find "$LOGS_DIR/user_actions" -name "actions_*.jsonl" -type f -mtime +90 -delete 2>/dev/null || true

    log "✅ تم تنظيف السجلات القديمة"
}

# ─────────────────────────────────────────────────────────────────────────────
# الدالة الرئيسية
# ─────────────────────────────────────────────────────────────────────────────
main() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║     Omni Medical Suite - سكربت التحديث التلقائي             ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    log "بدء التحديث في $(date)"

    check_lock
    update_repositories
    update_python_packages
    update_system_packages
    restart_services
    cleanup_logs

    log "اكتمل التحديث في $(date)"

    send_notification "تم تحديث Omni Medical Suite بنجاح"

    echo -e "${GREEN}${BOLD}✅ اكتمل التحديث بنجاح!${NC}"
}

# ─────────────────────────────────────────────────────────────────────────────
# تشغيل
# ─────────────────────────────────────────────────────────────────────────────
case "${1:-}" in
    --repos|-r)
        check_lock
        update_repositories
        ;;
    --packages|-p)
        check_lock
        update_python_packages
        ;;
    --system|-s)
        check_lock
        update_system_packages
        ;;
    --cleanup|-c)
        cleanup_logs
        ;;
    --help|-h)
        echo "الاستخدام: $0 [خيار]"
        echo ""
        echo "الخيارات:"
        echo "  --repos, -r     تحديث المستودعات فقط"
        echo "  --packages, -p  تحديث حزم Python فقط"
        echo "  --system, -s    تحديث النظام فقط"
        echo "  --cleanup, -c   تنظيف السجلات القديمة"
        echo "  --help, -h      عرض هذه الرسالة"
        echo ""
        echo "بدون خيارات: تشغيل التحديث الكامل"
        ;;
    *)
        main
        ;;
esac
