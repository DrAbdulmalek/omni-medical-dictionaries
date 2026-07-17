#!/bin/bash
# =============================================================================
# سكربت التثبيت الشامل لـ Omni Medical Suite على Manjaro Linux
# =============================================================================
# يقوم بتثبيت جميع المستودعات من GitHub وإعداد نظام التسجيل المتقدم
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
NC='\033[0m' # No Color
BOLD='\033[1m'

# ─────────────────────────────────────────────────────────────────────────────
# المتغيرات العامة
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR="$HOME/omni-medical-suite"
REPOS_DIR="$BASE_DIR/repos"
DATA_DIR="$BASE_DIR/data"
LOGS_DIR="$BASE_DIR/logs"
FEEDBACK_DIR="$BASE_DIR/feedback"
SCRIPTS_DIR="$BASE_DIR/scripts"
CONFIGS_DIR="$BASE_DIR/configs"
SYSTEMD_DIR="$BASE_DIR/systemd"
VENV_DIR="$BASE_DIR/venv"

REPOS=(
    "https://github.com/Archive-Borrowed-Book-Downloader"
    "https://github.com/archive-hitti-extractor"
    "https://github.com/omni-medical-suite"
    "https://github.com/medical-glossary-collector"
)

LOG_FILE="$LOGS_DIR/install_$(date +%Y%m%d_%H%M%S).log"

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
    exit 1
}

info() {
    echo -e "${CYAN}[معلومة]${NC} $1" | tee -a "$LOG_FILE"
}

# ─────────────────────────────────────────────────────────────────────────────
# التحقق من المتطلبات
# ─────────────────────────────────────────────────────────────────────────────
check_requirements() {
    info "جارٍ التحقق من متطلبات النظام..."

    # التحقق من الذاكرة (الحد الأدنى 4GB)
    MEM_TOTAL=$(free -m | awk '/^Mem:/{print $2}')
    if [ "$MEM_TOTAL" -lt 4096 ]; then
        warn "الذاكرة المتوفرة ($MEM_TOTAL MB) أقل من 4GB المطلوبة. قد تواجه مشاكل في الأداء."
    else
        log "✅ الذاكرة الكافية: ${MEM_TOTAL}MB"
    fi

    # التحقق من المساحة (الحد الأدنى 10GB)
    DISK_AVAIL=$(df -BG "$HOME" | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "$DISK_AVAIL" -lt 10 ]; then
        error "المساحة المتوفرة ($DISK_AVAIL GB) أقل من 10GB المطلوبة."
    else
        log "✅ المساحة الكافية: ${DISK_AVAIL}GB"
    fi

    # التحقق من الإنترنت
    if ! ping -c 1 github.com &> /dev/null; then
        error "لا يوجد اتصال بالإنترنت. يرجى التحقق من الاتصال."
    else
        log "✅ اتصال الإنترنت متوفر"
    fi

    # التحقق من pacman
    if ! command -v pacman &> /dev/null; then
        error "pacman غير مثبت. هذا السكربت مصمم لـ Manjaro/Arch Linux فقط."
    fi

    log "✅ جميع المتطلبات الأساسية متوفرة"
}

# ─────────────────────────────────────────────────────────────────────────────
# إنشاء الهيكل التنظيمي
# ─────────────────────────────────────────────────────────────────────────────
create_structure() {
    info "جارٍ إنشاء هيكل المجلدات..."

    mkdir -p "$REPOS_DIR"
    mkdir -p "$DATA_DIR"
    mkdir -p "$LOGS_DIR"/{app,user_actions,errors,performance,feedback}
    mkdir -p "$FEEDBACK_DIR"/{corrections,training_data,suggestions}
    mkdir -p "$SCRIPTS_DIR"
    mkdir -p "$CONFIGS_DIR"
    mkdir -p "$SYSTEMD_DIR"

    log "✅ تم إنشاء الهيكل التنظيمي في $BASE_DIR"
}

# ─────────────────────────────────────────────────────────────────────────────
# تحديث النظام وتثبيت الحزم
# ─────────────────────────────────────────────────────────────────────────────
update_system() {
    info "جارٍ تحديث نظام Manjaro..."

    sudo pacman -Syu --noconfirm || warn "تعذر تحديث بعض الحزم"

    log "✅ تم تحديث النظام"
}

install_dependencies() {
    info "جارٍ تثبيت الاعتماديات..."

    # تثبيت الحزم الأساسية
    sudo pacman -S --needed --noconfirm         git         python         python-pip         python-virtualenv         tesseract         tesseract-data-ara         tesseract-data-eng         tesseract-data-fra         libtiff         libjpeg         zlib         freetype2         ffmpeg         poppler         imagemagick         curl         wget         jq         htop         nvtop         2>&1 | tee -a "$LOG_FILE"

    # تثبيت حزم Python الأساسية
    pip install --user --upgrade pip setuptools wheel

    log "✅ تم تثبيت الاعتماديات الأساسية"
}

# ─────────────────────────────────────────────────────────────────────────────
# استنساخ المستودعات
# ─────────────────────────────────────────────────────────────────────────────
clone_repositories() {
    info "جارٍ استنساخ المستودعات من GitHub..."

    cd "$REPOS_DIR"

    for repo_url in "${REPOS[@]}"; do
        repo_name=$(basename "$repo_url")

        if [ -d "$repo_name" ]; then
            warn "المستودع $repo_name موجود بالفعل. جارٍ التحديث..."
            cd "$repo_name"
            git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || warn "تعذر تحديث $repo_name"
            cd ..
        else
            log "جارٍ استنساخ $repo_name..."
            git clone "$repo_url" "$repo_name" || warn "تعذر استنساخ $repo_name"
        fi
    done

    log "✅ تم استنساخ/تحديث جميع المستودعات"
}

# ─────────────────────────────────────────────────────────────────────────────
# إنشاء البيئة الافتراضية
# ─────────────────────────────────────────────────────────────────────────────
setup_virtualenv() {
    info "جارٍ إنشاء البيئة الافتراضية..."

    if [ -d "$VENV_DIR" ]; then
        warn "البيئة الافتراضية موجودة بالفعل. سيتم إعادة إنشاؤها."
        rm -rf "$VENV_DIR"
    fi

    python -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"

    # تثبيت الاعتماديات Python
    pip install --upgrade pip

    # تثبيت الحزم المشتركة
    pip install         gradio         pytesseract         pillow         opencv-python         numpy         pandas         matplotlib         scikit-learn         torch         transformers         datasets         accelerate         psutil         GPUtil         requests         tqdm         rich         loguru         pydantic         fastapi         uvicorn         2>&1 | tee -a "$LOG_FILE"

    log "✅ تم إنشاء البيئة الافتراضية وتثبيت الحزم"
}

# ─────────────────────────────────────────────────────────────────────────────
# إعداد نظام التسجيل المتقدم
# ─────────────────────────────────────────────────────────────────────────────
setup_logging() {
    info "جارٍ إعداد نظام التسجيل المتقدم..."

    # نسخ سكربت التسجيل
    cat > "$SCRIPTS_DIR/advanced_logger.py" << 'LOGGER_EOF'
"""
نظام التسجيل المتقدم وجمع التصحيحات لـ Omni Medical Suite
"""
import json
import os
import time
import hashlib
import psutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import threading


@dataclass
class CorrectionEntry:
    """سجل تصحيح واحد"""
    timestamp: str
    original: str
    corrected: str
    correction_type: str  # ocr, translation, terminology, formatting
    context: Dict[str, Any]
    model_version: str
    user_id: Optional[str] = None
    confidence: float = 0.0
    page_number: Optional[int] = None
    document_id: Optional[str] = None
    language_pair: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class PerformanceMonitor:
    """مراقب أداء النظام"""

    def __init__(self, logs_dir: str):
        self.logs_dir = Path(logs_dir) / "performance"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]

    def get_metrics(self) -> Dict[str, Any]:
        """جمع مقاييس الأداء الحالية"""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory": {
                "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
                "percent": psutil.virtual_memory().percent
            },
            "disk": {
                "total_gb": round(psutil.disk_usage('/').total / (1024**3), 2),
                "free_gb": round(psutil.disk_usage('/').free / (1024**3), 2),
                "percent": psutil.disk_usage('/').percent
            }
        }

        # GPU metrics (if available)
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                metrics["gpu"] = [
                    {
                        "id": gpu.id,
                        "name": gpu.name,
                        "load_percent": gpu.load * 100,
                        "memory_used_mb": gpu.memoryUsed,
                        "memory_total_mb": gpu.memoryTotal,
                        "temperature": gpu.temperature
                    }
                    for gpu in gpus
                ]
        except Exception:
            pass

        return metrics

    def log_metrics(self):
        """تسجيل المقاييس في ملف"""
        metrics = self.get_metrics()
        log_file = self.logs_dir / f"performance_{datetime.now().strftime('%Y%m')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(metrics, ensure_ascii=False) + '\n')


class FeedbackCollector:
    """
    جامع التصحيحات والتغذية الراجعة
    """

    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir) if base_dir else Path.home() / "omni-medical-suite"
        self.feedback_dir = self.base_dir / "feedback"
        self.logs_dir = self.base_dir / "logs"

        # إنشاء المجلدات
        (self.feedback_dir / "corrections").mkdir(parents=True, exist_ok=True)
        (self.feedback_dir / "training_data").mkdir(parents=True, exist_ok=True)
        (self.feedback_dir / "suggestions").mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "user_actions").mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "errors").mkdir(parents=True, exist_ok=True)

        self.corrections_file = self.feedback_dir / "corrections" / f"corrections_{datetime.now().strftime('%Y%m')}.jsonl"
        self.improvement_pool = self.feedback_dir / "training_data" / "improvement_pool.jsonl"
        self.session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        self._lock = threading.Lock()

        self.performance_monitor = PerformanceMonitor(str(self.logs_dir))

    def log_user_action(self, action: str, details: Dict[str, Any] = None):
        """تسجيل إجراء المستخدم"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "action": action,
            "details": details or {}
        }

        log_file = self.logs_dir / "user_actions" / f"actions_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def log_correction(self, 
                      original: str,
                      corrected: str,
                      correction_type: str = "ocr",
                      context: Dict[str, Any] = None,
                      model_version: str = "unknown",
                      user_id: str = None,
                      confidence: float = 0.0,
                      page_number: int = None,
                      document_id: str = None,
                      language_pair: str = None):
        """
        تسجيل تصحيح من المستخدم

        Args:
            original: النص الأصلي (الخاطئ)
            corrected: النص المصحح
            correction_type: نوع التصحيح (ocr, translation, terminology, formatting)
            context: سياق إضافي
            model_version: إصدار النموذج المستخدم
            user_id: معرف المستخدم (اختياري)
            confidence: ثقة النموذج (0-1)
            page_number: رقم الصفحة
            document_id: معرف المستند
            language_pair: زوج اللغات (مثل "en-ar")
        """
        correction = CorrectionEntry(
            timestamp=datetime.now().isoformat(),
            original=original,
            corrected=corrected,
            correction_type=correction_type,
            context=context or {},
            model_version=model_version,
            user_id=user_id,
            confidence=confidence,
            page_number=page_number,
            document_id=document_id,
            language_pair=language_pair
        )

        with self._lock:
            # حفظ في سجل التصحيحات
            with open(self.corrections_file, 'a', encoding='utf-8') as f:
                f.write(correction.to_json() + '\n')

            # إضافة لمجموعة التحسين
            training_entry = {
                "input": original,
                "output": corrected,
                "type": correction_type,
                "context": context or {},
                "model_version": model_version,
                "timestamp": datetime.now().isoformat()
            }

            with open(self.improvement_pool, 'a', encoding='utf-8') as f:
                f.write(json.dumps(training_entry, ensure_ascii=False) + '\n')

        # تسجيل إجراء المستخدم
        self.log_user_action("correction_made", {
            "correction_type": correction_type,
            "model_version": model_version,
            "document_id": document_id
        })

        return correction

    def log_error(self, error_type: str, error_message: str, traceback: str = None, context: Dict = None):
        """تسجيل خطأ"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "error_type": error_type,
            "error_message": error_message,
            "traceback": traceback,
            "context": context or {}
        }

        log_file = self.logs_dir / "errors" / f"errors_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def log_suggestion(self, suggestion: str, category: str = "general", context: Dict = None):
        """تسجيل اقتراح من المستخدم"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "suggestion": suggestion,
            "category": category,
            "context": context or {}
        }

        log_file = self.feedback_dir / "suggestions" / f"suggestions_{datetime.now().strftime('%Y%m')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def get_correction_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات التصحيحات"""
        stats = {
            "total_corrections": 0,
            "by_type": {},
            "by_model": {},
            "by_date": {},
            "unique_documents": set()
        }

        if not self.corrections_file.exists():
            return stats

        with open(self.corrections_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    stats["total_corrections"] += 1

                    # حسب النوع
                    corr_type = entry.get("correction_type", "unknown")
                    stats["by_type"][corr_type] = stats["by_type"].get(corr_type, 0) + 1

                    # حسب النموذج
                    model = entry.get("model_version", "unknown")
                    stats["by_model"][model] = stats["by_model"].get(model, 0) + 1

                    # حسب التاريخ
                    date = entry["timestamp"][:10]  # YYYY-MM-DD
                    stats["by_date"][date] = stats["by_date"].get(date, 0) + 1

                    # المستندات
                    if entry.get("document_id"):
                        stats["unique_documents"].add(entry["document_id"])
                except json.JSONDecodeError:
                    continue

        stats["unique_documents"] = len(stats["unique_documents"])
        return stats

    def export_training_dataset(self, min_corrections: int = 50, output_file: str = None) -> str:
        """
        تصدير مجموعة بيانات التدريب

        Args:
            min_corrections: الحد الأدنى للتصحيحات قبل التصدير
            output_file: مسار ملف الإخراج (اختياري)

        Returns:
            مسار ملف مجموعة التدريب
        """
        if not self.improvement_pool.exists():
            return None

        # عدد الإدخالات
        count = 0
        with open(self.improvement_pool, 'r', encoding='utf-8') as f:
            for _ in f:
                count += 1

        if count < min_corrections:
            return None

        if not output_file:
            output_file = self.feedback_dir / "training_data" / f"dataset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

        # تصدير البيانات
        with open(self.improvement_pool, 'r', encoding='utf-8') as f_in:
            with open(output_file, 'w', encoding='utf-8') as f_out:
                for line in f_in:
                    f_out.write(line)

        # تفريغ مجموعة التحسين بعد التصدير
        open(self.improvement_pool, 'w').close()

        return str(output_file)

    def get_recent_corrections(self, limit: int = 10) -> List[Dict]:
        """الحصول على أحدث التصحيحات"""
        corrections = []

        if not self.corrections_file.exists():
            return corrections

        with open(self.corrections_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # آخر limit سطر
        for line in lines[-limit:]:
            try:
                corrections.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return corrections[::-1]  # عكس الترتيب (الأحدث أولاً)


# دالة مساعدة للحصول على نسخة واحدة
_feedback_collector = None

def get_feedback_collector(base_dir: str = None) -> FeedbackCollector:
    """الحصول على نسخة جامع التصحيحات (نمط Singleton)"""
    global _feedback_collector
    if _feedback_collector is None:
        _feedback_collector = FeedbackCollector(base_dir)
    return _feedback_collector


if __name__ == "__main__":
    # اختبار النظام
    fb = get_feedback_collector()

    # تسجيل تصحيح تجريبي
    fb.log_correction(
        original="diabetis mellitus",
        corrected="diabetes mellitus",
        correction_type="ocr",
        context={"page": 42, "language_pair": "en-ar"},
        model_version="tesseract_v5.3"
    )

    print("إحصائيات التصحيحات:")
    print(json.dumps(fb.get_correction_stats(), indent=2, ensure_ascii=False))

    print("\nمقاييس الأداء:")
    print(json.dumps(fb.performance_monitor.get_metrics(), indent=2, ensure_ascii=False))
LOGGER_EOF

    log "✅ تم إعداد نظام التسجيل المتقدم"
}

# ─────────────────────────────────────────────────────────────────────────────
# إنشاء سكربت التشغيل الرئيسي
# ─────────────────────────────────────────────────────────────────────────────
create_launcher() {
    info "جارٍ إنشاء سكربت التشغيل..."

    cat > "$BASE_DIR/omni-medical" << 'LAUNCHER_EOF'
#!/bin/bash
# سكربت تشغيل Omni Medical Suite

BASE_DIR="$HOME/omni-medical-suite"
source "$BASE_DIR/venv/bin/activate"

export PYTHONPATH="$BASE_DIR:$PYTHONPATH"
export TESSDATA_PREFIX="/usr/share/tessdata"

cd "$BASE_DIR/repos/omni-medical-suite"

# تشغيل مع مراقبة الأداء
python -m main "$@"
LAUNCHER_EOF

    chmod +x "$BASE_DIR/omni-medical"

    # إنشاء رابط رمزي في /usr/local/bin
    sudo ln -sf "$BASE_DIR/omni-medical" /usr/local/bin/omni-medical 2>/dev/null || warn "تعذر إنشاء الرابط الرمزي. استخدم ./omni-medical من مجلد المشروع"

    log "✅ تم إنشاء سكربت التشغيل"
}

# ─────────────────────────────────────────────────────────────────────────────
# إنشاء خدمات systemd
# ─────────────────────────────────────────────────────────────────────────────
setup_systemd() {
    info "جارٍ إعداد خدمات systemd..."

    # خدمة التطبيق الرئيسية
    cat > "$SYSTEMD_DIR/omni-medical.service" << 'SYSTEMD_EOF'
[Unit]
Description=Omni Medical Suite
After=network.target

[Service]
Type=simple
User=%I
WorkingDirectory=%h/omni-medical-suite
Environment="PATH=%h/omni-medical-suite/venv/bin:/usr/bin"
Environment="PYTHONPATH=%h/omni-medical-suite"
Environment="TESSDATA_PREFIX=/usr/share/tessdata"
ExecStart=%h/omni-medical-suite/venv/bin/python -m main
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
SYSTEMD_EOF

    # خدمة جمع البيانات الدورية
    cat > "$SYSTEMD_DIR/omni-medical-logger.service" << 'LOGGER_SERVICE_EOF'
[Unit]
Description=Omni Medical Suite Logger
After=network.target

[Service]
Type=oneshot
User=%I
WorkingDirectory=%h/omni-medical-suite
Environment="PATH=%h/omni-medical-suite/venv/bin:/usr/bin"
ExecStart=%h/omni-medical-suite/venv/bin/python -c "from scripts.advanced_logger import get_feedback_collector; fb=get_feedback_collector(); fb.performance_monitor.log_metrics()"
LOGGER_SERVICE_EOF

    cat > "$SYSTEMD_DIR/omni-medical-logger.timer" << 'LOGGER_TIMER_EOF'
[Unit]
Description=Omni Medical Suite Logger Timer

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
LOGGER_TIMER_EOF

    # نسخ الخدمات
    mkdir -p "$HOME/.config/systemd/user"
    cp "$SYSTEMD_DIR/"*.service "$HOME/.config/systemd/user/" 2>/dev/null || true
    cp "$SYSTEMD_DIR/"*.timer "$HOME/.config/systemd/user/" 2>/dev/null || true

    systemctl --user daemon-reload 2>/dev/null || warn "تعذر إعادة تحميل systemd"

    log "✅ تم إعداد خدمات systemd"
}

# ─────────────────────────────────────────────────────────────────────────────
# إنشاء اختصارات سطح المكتب
# ─────────────────────────────────────────────────────────────────────────────
create_desktop_entries() {
    info "جارٍ إنشاء اختصارات سطح المكتب..."

    mkdir -p "$HOME/.local/share/applications"

    cat > "$HOME/.local/share/applications/omni-medical.desktop" << 'DESKTOP_EOF'
[Desktop Entry]
Name=Omni Medical Suite
Comment=Medical Document Processing Suite
Exec=/usr/local/bin/omni-medical
Icon=application-pdf
Type=Application
Terminal=true
Categories=Office;Medical;
Keywords=OCR;Medical;Document;
DESKTOP_EOF

    chmod +x "$HOME/.local/share/applications/omni-medical.desktop"

    log "✅ تم إنشاء اختصارات سطح المكتب"
}

# ─────────────────────────────────────────────────────────────────────────────
# إنشاء ملف الإعدادات
# ─────────────────────────────────────────────────────────────────────────────
create_config() {
    info "جارٍ إنشاء ملف الإعدادات..."

    cat > "$CONFIGS_DIR/config.json" << 'CONFIG_EOF'
{
    "app_name": "Omni Medical Suite",
    "version": "1.0.0",
    "environment": "production",
    "logging": {
        "level": "INFO",
        "format": "json",
        "retention_days": 90,
        "max_file_size_mb": 100
    },
    "ocr": {
        "engine": "tesseract",
        "languages": ["ara", "eng", "fra"],
        "dpi": 300,
        "preprocessing": {
            "deskew": true,
            "denoise": true,
            "binarize": true
        }
    },
    "feedback": {
        "auto_export_threshold": 50,
        "export_format": "jsonl",
        "include_context": true,
        "anonymize": false
    },
    "performance": {
        "log_interval_minutes": 15,
        "alert_cpu_threshold": 90,
        "alert_memory_threshold": 85
    },
    "paths": {
        "base_dir": "~/omni-medical-suite",
        "repos": "~/omni-medical-suite/repos",
        "data": "~/omni-medical-suite/data",
        "logs": "~/omni-medical-suite/logs",
        "feedback": "~/omni-medical-suite/feedback"
    }
}
CONFIG_EOF

    log "✅ تم إنشاء ملف الإعدادات"
}

# ─────────────────────────────────────────────────────────────────────────────
# التحقق النهائي
# ─────────────────────────────────────────────────────────────────────────────
final_check() {
    info "جارٍ التحقق النهائي من التثبيت..."

    errors=0

    # التحقق من البيئة الافتراضية
    if [ ! -f "$VENV_DIR/bin/python" ]; then
        error "البيئة الافتراضية غير موجودة!"
        errors=$((errors + 1))
    fi

    # التحقق من Tesseract
    if ! command -v tesseract &> /dev/null; then
        error "Tesseract غير مثبت!"
        errors=$((errors + 1))
    fi

    # التحقق من المستودعات
    for repo_url in "${REPOS[@]}"; do
        repo_name=$(basename "$repo_url")
        if [ ! -d "$REPOS_DIR/$repo_name" ]; then
            warn "المستودع $repo_name غير موجود"
        fi
    done

    # التحقق من نظام التسجيل
    if [ ! -f "$SCRIPTS_DIR/advanced_logger.py" ]; then
        error "نظام التسجيل غير موجود!"
        errors=$((errors + 1))
    fi

    if [ $errors -eq 0 ]; then
        log "${GREEN}${BOLD}✅ تم التثبيت بنجاح!${NC}"
        echo ""
        echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${CYAN}║${NC}  ${BOLD}Omni Medical Suite - تم التثبيت بنجاح!${NC}                    ${CYAN}║${NC}"
        echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${YELLOW}للتشغيل:${NC}"
        echo -e "  ${GREEN}source $VENV_DIR/bin/activate${NC}"
        echo -e "  ${GREEN}omni-medical${NC}"
        echo ""
        echo -e "${YELLOW}للخدمات:${NC}"
        echo -e "  ${GREEN}systemctl --user start omni-medical${NC}"
        echo -e "  ${GREEN}systemctl --user enable omni-medical-logger.timer${NC}"
        echo ""
        echo -e "${YELLOW}للتحديث:${NC}"
        echo -e "  ${GREEN}$BASE_DIR/scripts/auto_update.sh${NC}"
        echo ""
        echo -e "${YELLOW}للتصحيحات والبيانات:${NC}"
        echo -e "  ${GREEN}$FEEDBACK_DIR${NC}"
        echo -e "  ${GREEN}$LOGS_DIR${NC}"
        echo ""
    else
        error "اكتشفت $errors خطأ/أخطاء. يرجى مراجعة السجلات في $LOG_FILE"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# الدالة الرئيسية
# ─────────────────────────────────────────────────────────────────────────────
main() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║      Omni Medical Suite - سكربت التثبيت الشامل              ║"
    echo "║              لـ Manjaro Linux / Arch Linux                   ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    log "بدء التثبيت في $(date)"

    check_requirements
    create_structure
    update_system
    install_dependencies
    clone_repositories
    setup_virtualenv
    setup_logging
    create_launcher
    setup_systemd
    create_desktop_entries
    create_config
    final_check

    log "اكتمل التثبيت في $(date)"
}

main "$@"
