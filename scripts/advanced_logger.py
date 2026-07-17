"""
نظام التسجيل المتقدم وجمع التصحيحات لـ Omni Medical Suite
Advanced Logging & Feedback Collection System

الاستخدام:
    from advanced_logger import get_feedback_collector

    fb = get_feedback_collector()

    # تسجيل تصحيح
    fb.log_correction(
        original="diabetis mellitus",
        corrected="diabetes mellitus",
        correction_type="ocr",
        context={"page": 42, "language_pair": "en-ar"},
        model_version="tesseract_v5.3"
    )

    # تسجيل اقتراح
    fb.log_suggestion("أضف دعم اللغة التركية", category="feature")

    # تصدير بيانات التدريب
    dataset_path = fb.export_training_dataset(min_corrections=50)
"""

import json
import os
import time
import hashlib
import psutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict, field
import threading
import logging
from enum import Enum


class CorrectionType(Enum):
    """أنواع التصحيحات المدعومة"""
    OCR = "ocr"
    TRANSLATION = "translation"
    TERMINOLOGY = "terminology"
    FORMATTING = "formatting"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    OTHER = "other"


class LogLevel(Enum):
    """مستويات التسجيل"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class CorrectionEntry:
    """سجل تصحيح واحد من المستخدم"""
    timestamp: str
    original: str
    corrected: str
    correction_type: str
    context: Dict[str, Any]
    model_version: str
    user_id: Optional[str] = None
    confidence: float = 0.0
    page_number: Optional[int] = None
    document_id: Optional[str] = None
    language_pair: Optional[str] = None
    severity: str = "normal"  # low, normal, high, critical
    notes: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class UserAction:
    """سجل إجراء مستخدم"""
    timestamp: str
    session_id: str
    action: str
    details: Dict[str, Any]
    user_id: Optional[str] = None
    duration_ms: Optional[int] = None
    success: bool = True


@dataclass
class ErrorEntry:
    """سجل خطأ"""
    timestamp: str
    session_id: str
    error_type: str
    error_message: str
    traceback: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    severity: str = "error"
    resolved: bool = False


class PerformanceMonitor:
    """
    مراقب أداء النظام - يجمع مقاييس الأداء بشكل دوري
    """

    def __init__(self, logs_dir: str):
        self.logs_dir = Path(logs_dir) / "performance"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        self._running = False
        self._thread = None

    def get_metrics(self) -> Dict[str, Any]:
        """جمع مقاييس الأداء الحالية"""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "cpu": {
                "percent": psutil.cpu_percent(interval=0.5),
                "count_physical": psutil.cpu_count(logical=False),
                "count_logical": psutil.cpu_count(logical=True),
                "freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else None
            },
            "memory": {
                "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
                "used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
                "percent": psutil.virtual_memory().percent
            },
            "disk": {
                "total_gb": round(psutil.disk_usage('/').total / (1024**3), 2),
                "free_gb": round(psutil.disk_usage('/').free / (1024**3), 2),
                "used_gb": round(psutil.disk_usage('/').used / (1024**3), 2),
                "percent": psutil.disk_usage('/').percent
            },
            "network": {
                "bytes_sent": psutil.net_io_counters().bytes_sent,
                "bytes_recv": psutil.net_io_counters().bytes_recv
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
                        "load_percent": round(gpu.load * 100, 2),
                        "memory_used_mb": gpu.memoryUsed,
                        "memory_total_mb": gpu.memoryTotal,
                        "temperature": gpu.temperature
                    }
                    for gpu in gpus
                ]
        except Exception:
            pass

        # Process-specific metrics
        try:
            process = psutil.Process()
            metrics["process"] = {
                "pid": process.pid,
                "memory_mb": round(process.memory_info().rss / (1024**2), 2),
                "cpu_percent": process.cpu_percent(interval=0.5),
                "threads": process.num_threads()
            }
        except Exception:
            pass

        return metrics

    def log_metrics(self):
        """تسجيل المقاييس في ملف"""
        metrics = self.get_metrics()
        log_file = self.logs_dir / f"performance_{datetime.now().strftime('%Y%m')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(metrics, ensure_ascii=False) + '\n')

    def start_monitoring(self, interval_seconds: int = 900):
        """بدء المراقبة الدورية (افتراضياً كل 15 دقيقة)"""
        self._running = True

        def monitor_loop():
            while self._running:
                try:
                    self.log_metrics()
                except Exception as e:
                    logging.error(f"Error logging metrics: {e}")
                time.sleep(interval_seconds)

        self._thread = threading.Thread(target=monitor_loop, daemon=True)
        self._thread.start()

    def stop_monitoring(self):
        """إيقاف المراقبة الدورية"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)


class FeedbackCollector:
    """
    جامع التصحيحات والتغذية الراجعة المتقدم

    يقوم بـ:
    - تسجيل تصحيحات المستخدم
    - جمع اقتراحات التحسين
    - تسجيل أخطاء التطبيق
    - مراقبة أداء النظام
    - تصدير بيانات التدريب للنماذج
    """

    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir) if base_dir else Path.home() / "omni-medical-suite"
        self.feedback_dir = self.base_dir / "feedback"
        self.logs_dir = self.base_dir / "logs"

        # إنشاء المجلدات
        self._create_directories()

        # ملفات السجلات
        self.corrections_file = self.feedback_dir / "corrections" / f"corrections_{datetime.now().strftime('%Y%m')}.jsonl"
        self.improvement_pool = self.feedback_dir / "training_data" / "improvement_pool.jsonl"
        self.session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        self._lock = threading.Lock()

        # مراقب الأداء
        self.performance_monitor = PerformanceMonitor(str(self.logs_dir))

        # إعداد التسجيل القياسي
        self._setup_logging()

    def _create_directories(self):
        """إنشاء هيكل المجلدات"""
        dirs = [
            self.feedback_dir / "corrections",
            self.feedback_dir / "training_data",
            self.feedback_dir / "suggestions",
            self.logs_dir / "app",
            self.logs_dir / "user_actions",
            self.logs_dir / "errors",
            self.logs_dir / "performance",
            self.logs_dir / "feedback"
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def _setup_logging(self):
        """إعداد التسجيل القياسي"""
        log_file = self.logs_dir / "app" / f"app_{datetime.now().strftime('%Y%m%d')}.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("OmniMedical")

    def log_user_action(self, action: str, details: Dict[str, Any] = None, 
                       user_id: str = None, duration_ms: int = None, success: bool = True):
        """
        تسجيل إجراء المستخدم

        Args:
            action: نوع الإجراء (مثال: "document_uploaded", "ocr_performed")
            details: تفاصيل إضافية
            user_id: معرف المستخدم
            duration_ms: مدة الإجراء بالمللي ثانية
            success: هل نجح الإجراء
        """
        entry = UserAction(
            timestamp=datetime.now().isoformat(),
            session_id=self.session_id,
            action=action,
            details=details or {},
            user_id=user_id,
            duration_ms=duration_ms,
            success=success
        )

        log_file = self.logs_dir / "user_actions" / f"actions_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + '\n')

        self.logger.info(f"User action: {action}")

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
                      language_pair: str = None,
                      severity: str = "normal",
                      notes: str = "") -> CorrectionEntry:
        """
        تسجيل تصحيح من المستخدم

        Args:
            original: النص الأصلي (الخاطئ)
            corrected: النص المصحح
            correction_type: نوع التصحيح (ocr, translation, terminology, formatting, classification, extraction)
            context: سياق إضافي (صفحة، مستند، إلخ)
            model_version: إصدار النموذج المستخدم
            user_id: معرف المستخدم
            confidence: ثقة النموذج (0-1)
            page_number: رقم الصفحة
            document_id: معرف المستند
            language_pair: زوج اللغات (مثل "en-ar")
            severity: درجة الأهمية (low, normal, high, critical)
            notes: ملاحظات إضافية

        Returns:
            CorrectionEntry: كائن التصحيح المسجل
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
            language_pair=language_pair,
            severity=severity,
            notes=notes
        )

        with self._lock:
            # حفظ في سجل التصحيحات
            with open(self.corrections_file, 'a', encoding='utf-8') as f:
                f.write(correction.to_json() + '\n')

            # إضافة لمجموعة التحسين (بيانات التدريب)
            training_entry = {
                "input": original,
                "output": corrected,
                "type": correction_type,
                "context": context or {},
                "model_version": model_version,
                "timestamp": datetime.now().isoformat(),
                "language_pair": language_pair,
                "severity": severity
            }

            with open(self.improvement_pool, 'a', encoding='utf-8') as f:
                f.write(json.dumps(training_entry, ensure_ascii=False) + '\n')

        # تسجيل إجراء المستخدم
        self.log_user_action("correction_made", {
            "correction_type": correction_type,
            "model_version": model_version,
            "document_id": document_id,
            "severity": severity
        })

        self.logger.info(f"Correction logged: [{correction_type}] '{original}' -> '{corrected}'")

        return correction

    def log_error(self, error_type: str, error_message: str, 
                  traceback: str = None, context: Dict = None,
                  severity: str = "error"):
        """
        تسجيل خطأ

        Args:
            error_type: نوع الخطأ (مثال: "ocr_failed", "model_error")
            error_message: رسالة الخطأ
            traceback: تتبع المكدس
            context: سياق إضافي
            severity: درجة الخطأ (error, warning, critical)
        """
        entry = ErrorEntry(
            timestamp=datetime.now().isoformat(),
            session_id=self.session_id,
            error_type=error_type,
            error_message=error_message,
            traceback=traceback,
            context=context or {},
            severity=severity
        )

        log_file = self.logs_dir / "errors" / f"errors_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + '\n')

        self.logger.error(f"Error [{error_type}]: {error_message}")

    def log_suggestion(self, suggestion: str, category: str = "general", 
                       context: Dict = None, user_id: str = None):
        """
        تسجيل اقتراح من المستخدم

        Args:
            suggestion: نص الاقتراح
            category: فئة الاقتراح (feature, bug, improvement, general)
            context: سياق إضافي
            user_id: معرف المستخدم
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "suggestion": suggestion,
            "category": category,
            "context": context or {},
            "user_id": user_id
        }

        log_file = self.feedback_dir / "suggestions" / f"suggestions_{datetime.now().strftime('%Y%m')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        self.log_user_action("suggestion_submitted", {"category": category})
        self.logger.info(f"Suggestion logged: [{category}] {suggestion[:50]}...")

    def get_correction_stats(self, days: int = None) -> Dict[str, Any]:
        """
        الحصول على إحصائيات التصحيحات

        Args:
            days: عدد الأيام الأخيرة (None = الكل)

        Returns:
            Dict: إحصائيات شاملة
        """
        stats = {
            "total_corrections": 0,
            "by_type": {},
            "by_model": {},
            "by_date": {},
            "by_severity": {},
            "by_language_pair": {},
            "unique_documents": set(),
            "unique_users": set(),
            "average_confidence": 0.0,
            "confidence_sum": 0.0
        }

        if not self.corrections_file.exists():
            return self._format_stats(stats)

        cutoff_date = None
        if days:
            from datetime import timedelta
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()[:10]

        with open(self.corrections_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)

                    # فلترة حسب التاريخ
                    if cutoff_date and entry["timestamp"][:10] < cutoff_date:
                        continue

                    stats["total_corrections"] += 1

                    # حسب النوع
                    corr_type = entry.get("correction_type", "unknown")
                    stats["by_type"][corr_type] = stats["by_type"].get(corr_type, 0) + 1

                    # حسب النموذج
                    model = entry.get("model_version", "unknown")
                    stats["by_model"][model] = stats["by_model"].get(model, 0) + 1

                    # حسب التاريخ
                    date = entry["timestamp"][:10]
                    stats["by_date"][date] = stats["by_date"].get(date, 0) + 1

                    # حسب الأهمية
                    severity = entry.get("severity", "normal")
                    stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1

                    # حسب زوج اللغات
                    lang_pair = entry.get("language_pair", "unknown")
                    stats["by_language_pair"][lang_pair] = stats["by_language_pair"].get(lang_pair, 0) + 1

                    # المستندات والمستخدمين
                    if entry.get("document_id"):
                        stats["unique_documents"].add(entry["document_id"])
                    if entry.get("user_id"):
                        stats["unique_users"].add(entry["user_id"])

                    # الثقة
                    conf = entry.get("confidence", 0)
                    stats["confidence_sum"] += conf

                except (json.JSONDecodeError, KeyError):
                    continue

        if stats["total_corrections"] > 0:
            stats["average_confidence"] = round(stats["confidence_sum"] / stats["total_corrections"], 3)

        return self._format_stats(stats)

    def _format_stats(self, stats: Dict) -> Dict:
        """تنسيق الإحصائيات للعرض"""
        formatted = stats.copy()
        formatted["unique_documents"] = len(stats["unique_documents"])
        formatted["unique_users"] = len(stats["unique_users"])
        del formatted["confidence_sum"]
        return formatted

    def export_training_dataset(self, min_corrections: int = 50, 
                                output_file: str = None,
                                format_type: str = "jsonl") -> Optional[str]:
        """
        تصدير مجموعة بيانات التدريب

        يقوم بتصدير بيانات التصحيحات المجمعة لتدريب/تحسين النماذج.

        Args:
            min_corrections: الحد الأدنى للتصحيحات قبل التصدير
            output_file: مسار ملف الإخراج (اختياري)
            format_type: تنسيق الإخراج (jsonl, csv, json)

        Returns:
            str: مسار ملف مجموعة التدريب أو None إذا لم يكن هناك بيانات كافية
        """
        if not self.improvement_pool.exists():
            self.logger.warning("No improvement pool file found")
            return None

        # عدد الإدخالات
        count = 0
        entries = []
        with open(self.improvement_pool, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(line)
                    count += 1

        if count < min_corrections:
            self.logger.info(f"Not enough corrections ({count}/{min_corrections}) for export")
            return None

        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.feedback_dir / "training_data" / f"dataset_{timestamp}.{format_type}"
        else:
            output_file = Path(output_file)

        # تصدير البيانات حسب التنسيق
        if format_type == "jsonl":
            with open(output_file, 'w', encoding='utf-8') as f:
                for entry in entries:
                    f.write(entry + '\n')

        elif format_type == "csv":
            import csv
            with open(output_file, 'w', encoding='utf-8', newline='') as f:
                if entries:
                    first_entry = json.loads(entries[0])
                    writer = csv.DictWriter(f, fieldnames=first_entry.keys())
                    writer.writeheader()
                    for entry in entries:
                        writer.writerow(json.loads(entry))

        elif format_type == "json":
            data = [json.loads(e) for e in entries]
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        # تفريغ مجموعة التحسين بعد التصدير الناجح
        open(self.improvement_pool, 'w').close()

        self.logger.info(f"Exported training dataset: {output_file} ({count} entries)")
        self.log_user_action("dataset_exported", {"count": count, "format": format_type})

        return str(output_file)

    def get_recent_corrections(self, limit: int = 10, 
                               correction_type: str = None) -> List[Dict]:
        """
        الحصول على أحدث التصحيحات

        Args:
            limit: عدد النتائج
            correction_type: فلترة حسب النوع (اختياري)

        Returns:
            List[Dict]: قائمة التصحيحات
        """
        corrections = []

        if not self.corrections_file.exists():
            return corrections

        with open(self.corrections_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # قراءة من النهاية
        for line in reversed(lines):
            if len(corrections) >= limit:
                break
            try:
                entry = json.loads(line)
                if correction_type is None or entry.get("correction_type") == correction_type:
                    corrections.append(entry)
            except json.JSONDecodeError:
                continue

        return corrections

    def search_corrections(self, query: str, field: str = "original") -> List[Dict]:
        """
        البحث في التصحيحات

        Args:
            query: نص البحث
            field: الحقل للبحث (original, corrected, model_version)

        Returns:
            List[Dict]: نتائج البحث
        """
        results = []

        if not self.corrections_file.exists():
            return results

        with open(self.corrections_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if query.lower() in str(entry.get(field, "")).lower():
                        results.append(entry)
                except (json.JSONDecodeError, KeyError):
                    continue

        return results

    def generate_report(self, output_file: str = None) -> str:
        """
        إنشاء تقرير شامل

        Args:
            output_file: مسار ملف التقرير

        Returns:
            str: مسار ملف التقرير
        """
        stats = self.get_correction_stats()

        report = {
            "generated_at": datetime.now().isoformat(),
            "session_id": self.session_id,
            "summary": stats,
            "recent_corrections": self.get_recent_corrections(20),
            "performance": self.performance_monitor.get_metrics()
        }

        if not output_file:
            output_file = self.logs_dir / "feedback" / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            output_file = Path(output_file)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Report generated: {output_file}")
        return str(output_file)

    def cleanup_old_logs(self, days: int = 90):
        """
        تنظيف السجلات القديمة

        Args:
            days: حذف السجلات الأقدم من هذا العدد من الأيام
        """
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)

        cleaned = 0
        for log_dir in [self.logs_dir / "app", self.logs_dir / "user_actions", 
                        self.logs_dir / "errors"]:
            if log_dir.exists():
                for file in log_dir.glob("*.jsonl"):
                    try:
                        # استخراج التاريخ من اسم الملف
                        date_str = file.stem.split('_')[-1]
                        file_date = datetime.strptime(date_str, '%Y%m%d')
                        if file_date < cutoff:
                            file.unlink()
                            cleaned += 1
                    except (ValueError, OSError):
                        continue

        self.logger.info(f"Cleaned {cleaned} old log files")
        return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# دالة مساعدة للحصول على نسخة واحدة (Singleton)
# ─────────────────────────────────────────────────────────────────────────────
_feedback_collector = None
_feedback_lock = threading.Lock()

def get_feedback_collector(base_dir: str = None) -> FeedbackCollector:
    """
    الحصول على نسخة جامع التصحيحات (نمط Singleton)

    Args:
        base_dir: المجلد الأساسي (اختياري)

    Returns:
        FeedbackCollector: نسخة جامع التصحيحات
    """
    global _feedback_collector
    if _feedback_collector is None:
        with _feedback_lock:
            if _feedback_collector is None:
                _feedback_collector = FeedbackCollector(base_dir)
    return _feedback_collector


# ─────────────────────────────────────────────────────────────────────────────
# اختبار النظام
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("اختبار نظام التسجيل المتقدم - Omni Medical Suite")
    print("=" * 60)

    fb = get_feedback_collector()

    # تسجيل تصحيحات تجريبية
    test_corrections = [
        ("diabetis mellitus", "diabetes mellitus", "ocr", "tesseract_v5.3"),
        ("السكري النوع الأول", "السكري النوع 1", "translation", "mt_model_v2.1"),
        ("hypertention", "hypertension", "ocr", "tesseract_v5.3"),
        ("قلب", "القلب", "terminology", "dict_v1.0"),
        ("myocardial infarction", "احتشاء عضلة القلب", "translation", "mt_model_v2.1"),
    ]

    for orig, corr, ctype, model in test_corrections:
        fb.log_correction(
            original=orig,
            corrected=corr,
            correction_type=ctype,
            context={"page": 42, "language_pair": "en-ar"},
            model_version=model,
            confidence=0.75
        )
        print(f"✅ تم تسجيل: [{ctype}] '{orig}' -> '{corr}'")

    # تسجيل اقتراح
    fb.log_suggestion("أضف دعم اللغة التركية في الترجمة", category="feature")
    print("✅ تم تسجيل اقتراح")

    # تسجيل خطأ
    fb.log_error("ocr_failed", "فشل في معالجة الصفحة 15", context={"document": "doc_001.pdf"})
    print("✅ تم تسجيل خطأ")

    # عرض الإحصائيات
    print("\n" + "=" * 60)
    print("إحصائيات التصحيحات:")
    print("=" * 60)
    stats = fb.get_correction_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    # مقاييس الأداء
    print("\n" + "=" * 60)
    print("مقاييس الأداء:")
    print("=" * 60)
    print(json.dumps(fb.performance_monitor.get_metrics(), indent=2, ensure_ascii=False))

    # البحث
    print("\n" + "=" * 60)
    print("نتائج البحث عن 'diabetis':")
    print("=" * 60)
    results = fb.search_corrections("diabetis")
    for r in results:
        print(f"  - {r['original']} -> {r['corrected']}")

    # إنشاء تقرير
    print("\n" + "=" * 60)
    report_path = fb.generate_report()
    print(f"✅ تم إنشاء التقرير: {report_path}")

    print("\n" + "=" * 60)
    print("اكتمل الاختبار بنجاح!")
    print("=" * 60)
