# 📚 دليل استخدام Omni Medical Suite

## نظام معالجة المستندات الطبية مع جمع التصحيحات والتغذية الراجعة

---

## 📋 جدول المحتويات

1. [مقدمة](#مقدمة)
2. [متطلبات النظام](#متطلبات-النظام)
3. [التثبيت على Manjaro](#التثبيت-على-manjaro)
4. [هيكل المجلدات](#هيكل-المجلدات)
5. [التشغيل والاستخدام](#التشغيل-والاستخدام)
6. [نظام التسجيل المتقدم](#نظام-التسجيل-المتقدم)
7. [جمع التصحيحات](#جمع-التصحيحات)
8. [تصدير بيانات التدريب](#تصدير-بيانات-التدريب)
9. [التحديث التلقائي](#التحديث-التلقائي)
10. [خدمات systemd](#خدمات-systemd)
11. [استكشاف الأخطاء](#استكشاف-الأخطاء)
12. [الأسئلة الشائعة](#الأسئلة-الشائعة)

---

## مقدمة

**Omni Medical Suite** هو نظام متكامل لمعالجة المستندات الطبية يتضمن:
- 📝 **OCR** لاستخراج النصوص من المستندات الطبية
- 🔄 **ترجمة** المصطلحات الطبية بين اللغات
- 📊 **تصنيف** المستندات الطبية
- ✏️ **جمع تصحيحات** المستخدمين لتحسين النماذج
- 📈 **تسجيل مفصل** لجميع الإجراءات والأخطاء

### المميزات الرئيسية

| الميزة | الوصف |
|--------|-------|
| OCR متعدد اللغات | دعم العربية، الإنجليزية، الفرنسية |
| جمع التصحيحات | تسجيل التصحيحات لإعادة تدريب النماذج |
| مراقبة الأداء | تتبع CPU، الذاكرة، GPU |
| تحديث تلقائي | تحديث المستودعات يومياً |
| تسجيل مفصل | JSONL لجميع الإجراءات والأخطاء |

---

## متطلبات النظام

### الحد الأدنى
- **النظام**: Manjaro Linux / Arch Linux
- **الذاكرة**: 4 GB RAM
- **المساحة**: 10 GB مساحة حرة
- **الإنترنت**: اتصال مستقر
- **Python**: 3.8 أو أحدث

### الموصى به
- **الذاكرة**: 8 GB RAM أو أكثر
- **المساحة**: 20 GB SSD
- **GPU**: NVIDIA مع CUDA (للتسريع)
- **المعالج**: 4 أنوية أو أكثر

---

## التثبيت على Manjaro

### الطريقة 1: التثبيت السريع (موصى به)

```bash
# 1. تحميل السكربت
wget https://github.com/your-repo/omni-medical-suite/raw/main/scripts/setup_manjaro_complete.sh

# 2. منح صلاحيات التنفيذ
chmod +x setup_manjaro_complete.sh

# 3. تشغيل السكربت
./setup_manjaro_complete.sh
```

### الطريقة 2: التثبيت اليدوي

```bash
# 1. تحديث النظام
sudo pacman -Syu

# 2. تثبيت الاعتماديات
sudo pacman -S git python python-pip python-virtualenv     tesseract tesseract-data-ara tesseract-data-eng     libtiff libjpeg zlib freetype2 ffmpeg poppler imagemagick

# 3. إنشاء البيئة الافتراضية
python -m venv ~/omni-medical-suite/venv
source ~/omni-medical-suite/venv/bin/activate

# 4. تثبيت حزم Python
pip install gradio pytesseract pillow opencv-python numpy     pandas matplotlib scikit-learn torch transformers     datasets accelerate psutil GPUtil requests tqdm rich     loguru pydantic fastapi uvicorn

# 5. استنساخ المستودعات
cd ~/omni-medical-suite/repos
git clone https://github.com/Archive-Borrowed-Book-Downloader
git clone https://github.com/archive-hitti-extractor
git clone https://github.com/omni-medical-suite
git clone https://github.com/medical-glossary-collector
```

### التحقق من التثبيت

```bash
# تفعيل البيئة الافتراضية
source ~/omni-medical-suite/venv/bin/activate

# التحقق من Tesseract
tesseract --version

# التحقق من Python
python --version

# تشغيل الاختبار
python ~/omni-medical-suite/scripts/advanced_logger.py
```

---

## هيكل المجلدات

بعد التثبيت، يكون الهيكل كالتالي:

```
~/omni-medical-suite/
├── repos/                          # المستودعات المستنسخة
│   ├── Archive-Borrowed-Book-Downloader/
│   ├── archive-hitti-extractor/
│   ├── omni-medical-suite/
│   └── medical-glossary-collector/
├── data/                           # البيانات والقواعد
│   ├── models/                     # النماذج المدربة
│   ├── dictionaries/               # القواميس الطبية
│   └── temp/                       # ملفات مؤقتة
├── logs/                           # السجلات
│   ├── app/                        # سجلات التطبيق
│   ├── user_actions/              # إجراءات المستخدم
│   ├── errors/                    # الأخطاء
│   ├── performance/               # مقاييس الأداء
│   └── feedback/                  # التغذية الراجعة
├── feedback/                       # تصحيحات المستخدم
│   ├── corrections/               # التصحيحات
│   ├── training_data/             # بيانات التدريب
│   │   └── improvement_pool.jsonl # مجموعة التحسين
│   └── suggestions/               # الاقتراحات
├── scripts/                        # السكربتات
│   ├── advanced_logger.py         # نظام التسجيل
│   ├── gradio_corrections_integration.py  # تكامل Gradio
│   └── auto_update.sh             # التحديث التلقائي
├── configs/                        # الإعدادات
│   └── config.json                # ملف الإعدادات الرئيسي
├── systemd/                        # خدمات النظام
│   ├── omni-medical.service       # خدمة التطبيق
│   ├── omni-medical-logger.service # خدمة التسجيل
│   └── omni-medical-logger.timer  # مؤقت التسجيل
├── venv/                           # بيئة Python الافتراضية
└── omni-medical                    # سكربت التشغيل
```

---

## التشغيل والاستخدام

### تشغيل التطبيق

```bash
# الطريقة 1: باستخدام السكربت
omni-medical

# الطريقة 2: يدوياً
source ~/omni-medical-suite/venv/bin/activate
cd ~/omni-medical-suite/repos/omni-medical-suite
python -m main

# الطريقة 3: عبر سطح المكتب
# انقر على أيقونة Omni Medical Suite في قائمة التطبيقات
```

### استخدام واجهة Gradio

```bash
# تشغيل واجهة التصحيحات فقط
source ~/omni-medical-suite/venv/bin/activate
python ~/omni-medical-suite/scripts/gradio_corrections_integration.py
```

سيتم فتح المتصفح تلقائياً على `http://localhost:7861`

---

## نظام التسجيل المتقدم

### المفهوم

نظام التسجيل يجمع البيانات التالية:

| نوع السجل | الوصف | الموقع |
|-----------|-------|--------|
| إجراءات المستخدم | كل نقرة وإجراء | `logs/user_actions/` |
| تصحيحات OCR | النص الخاطئ والصحيح | `feedback/corrections/` |
| أخطاء التطبيق | الأخطاء والتتبع | `logs/errors/` |
| مقاييس الأداء | CPU، RAM، GPU | `logs/performance/` |
| اقتراحات المستخدمين | اقتراحات التحسين | `feedback/suggestions/` |

### الاستخدام في الكود

```python
from scripts.advanced_logger import get_feedback_collector

# الحصول على نسخة جامع التصحيحات
fb = get_feedback_collector()

# 1. تسجيل إجراء المستخدم
fb.log_user_action(
    action="document_uploaded",
    details={"filename": "report.pdf", "pages": 15},
    duration_ms=2500
)

# 2. تسجيل تصحيح
fb.log_correction(
    original="diabetis mellitus",
    corrected="diabetes mellitus",
    correction_type="ocr",
    context={"page": 42, "language_pair": "en-ar"},
    model_version="tesseract_v5.3",
    confidence=0.65,
    severity="high"
)

# 3. تسجيل خطأ
fb.log_error(
    error_type="ocr_failed",
    error_message="فشل في معالجة الصفحة 15",
    traceback="Traceback (most recent call last):...",
    context={"document": "doc_001.pdf", "page": 15}
)

# 4. تسجيل اقتراح
fb.log_suggestion(
    suggestion="أضف دعم اللغة التركية",
    category="feature"
)

# 5. عرض الإحصائيات
stats = fb.get_correction_stats()
print(f"إجمالي التصحيحات: {stats['total_corrections']}")

# 6. تصدير بيانات التدريب
dataset_path = fb.export_training_dataset(min_corrections=50)
if dataset_path:
    print(f"تم تصدير البيانات: {dataset_path}")

# 7. إنشاء تقرير
report_path = fb.generate_report()
print(f"تم إنشاء التقرير: {report_path}")
```

### تنسيق ملفات JSONL

كل سطر يمثل إدخال JSON واحد:

```jsonl
{"timestamp": "2026-07-17T10:30:00", "session_id": "a1b2c3d4", "action": "document_uploaded", "details": {"filename": "report.pdf"}}
{"timestamp": "2026-07-17T10:31:00", "session_id": "a1b2c3d4", "original": "diabetis", "corrected": "diabetes", "correction_type": "ocr"}
```

---

## جمع التصحيحات

### آلية العمل

```
المستخدم يستخدم التطبيق
        ↓
النظام يسجل الإجراء + النتيجة
        ↓
المستخدم يلاحظ خطأ في النتيجة
        ↓
يفتح تبويب "تصحيح النتائج"
        ↓
يدخل النص الخاطئ والمصحح
        ↓
يُحفظ في feedback/corrections/corrections_202601.jsonl
        ↓
يُضاف تلقائياً لـ training_data/improvement_pool.jsonl
        ↓
عند الوصول للحد الأدنى (50 تصحيح)
        ↓
يتم تصدير مجموعة تدريب
        ↓
إرسالها للمطورين لتحسين النماذج
```

### أنواع التصحيحات

| النوع | الوصف | مثال |
|-------|-------|------|
| ocr | أخطاء التعرف الضوئي | "hypertention" → "hypertension" |
| translation | أخطاء الترجمة | "القلب" → "قلب" |
| terminology | مصطلحات طبية خاطئة | "myocardial infarction" → "احتشاء عضلة القلب" |
| formatting | تنسيق خاطئ | فواصل أسطر مفقودة |
| classification | تصنيف خاطئ | "تقرير أشعة" بدلاً من "تقرير دم" |
| extraction | استخراج خاطئ | استخراج تاريخ خاطئ |

### عبر واجهة Gradio

1. افتح المتصفح على `http://localhost:7861`
2. اختر تبويب **"✏️ تصحيح النتائج"**
3. أدخل النص الخاطئ في "النص الأصلي"
4. أدخل النص الصحيح في "النص المصحح"
5. اختر نوع التصحيح
6. أدخل إصدار النموذج (إذا معروف)
7. اضغط **"إرسال التصحيح"**

---

## تصدير بيانات التدريب

### الطرق

**1. عبر واجهة Gradio:**
- افتح تبويب **"📊 الإحصائيات"**
- اضبط "الحد الأدنى للتصحيحات"
- اضغط **"تصدير مجموعة التدريب"**

**2. عبر Python:**
```python
from scripts.advanced_logger import get_feedback_collector

fb = get_feedback_collector()

# تصدير بصيغة JSONL (افتراضي)
dataset = fb.export_training_dataset(min_corrections=50)

# تصدير بصيغة CSV
dataset = fb.export_training_dataset(
    min_corrections=50,
    format_type="csv"
)

# تصدير بصيغة JSON
dataset = fb.export_training_dataset(
    min_corrections=50,
    format_type="json"
)
```

### تنسيق بيانات التدريب

```jsonl
{"input": "diabetis mellitus", "output": "diabetes mellitus", "type": "ocr", "model_version": "tesseract_v5.3", "timestamp": "2026-07-17T10:30:00"}
{"input": "hypertention", "output": "hypertension", "type": "ocr", "model_version": "tesseract_v5.3", "timestamp": "2026-07-17T10:35:00"}
```

### إرسال البيانات للمطورين

```bash
# ضغط البيانات
cd ~/omni-medical-suite/feedback/training_data
tar -czvf training_data_$(date +%Y%m%d).tar.gz dataset_*.jsonl

# رفع إلى GitHub (إذا كان لديك صلاحيات)
gh release upload v1.0.0 training_data_*.tar.gz

# أو إرسال بالبريد
# أو نسخ إلى USB
```

---

## التحديث التلقائي

### الإعداد

```bash
# جعل السكربت قابلاً للتنفيذ
chmod +x ~/omni-medical-suite/scripts/auto_update.sh

# إضافة إلى crontab (يومياً الساعة 3 صباحاً)
crontab -e
# أضف:
0 3 * * * /home/$USER/omni-medical-suite/scripts/auto_update.sh >> /home/$USER/omni-medical-suite/logs/auto_update.log 2>&1

# أو استخدم systemd timer
systemctl --user enable omni-medical-logger.timer
systemctl --user start omni-medical-logger.timer
```

### الخيارات

```bash
# تحديث كامل
~/omni-medical-suite/scripts/auto_update.sh

# تحديث المستودعات فقط
~/omni-medical-suite/scripts/auto_update.sh --repos

# تحديث حزم Python فقط
~/omni-medical-suite/scripts/auto_update.sh --packages

# تحديث النظام فقط
~/omni-medical-suite/scripts/auto_update.sh --system

# تنظيف السجلات
~/omni-medical-suite/scripts/auto_update.sh --cleanup
```

---

## خدمات systemd

### الخدمات المتاحة

| الخدمة | الوصف | الأمر |
|--------|-------|-------|
| omni-medical | التطبيق الرئيسي | `systemctl --user start omni-medical` |
| omni-medical-logger | تسجيل دوري | `systemctl --user start omni-medical-logger` |
| omni-medical-logger.timer | مؤقت كل 15 دقيقة | `systemctl --user enable omni-medical-logger.timer` |

### الأوامر

```bash
# تشغيل التطبيق كخدمة
systemctl --user start omni-medical

# إيقاف التطبيق
systemctl --user stop omni-medical

# إعادة تشغيل
systemctl --user restart omni-medical

# عرض الحالة
systemctl --user status omni-medical

# تفعيل التشغيل التلقائي
systemctl --user enable omni-medical

# عرض السجلات
journalctl --user -u omni-medical -f

# تفعيل مؤقت التسجيل
systemctl --user enable omni-medical-logger.timer
systemctl --user start omni-medical-logger.timer

# عرض المؤقتات
systemctl --user list-timers
```

---

## استكشاف الأخطاء

### المشكلة: Tesseract غير موجود

```bash
# التحقق
which tesseract

# الحل
sudo pacman -S tesseract tesseract-data-ara tesseract-data-eng

# التحقق من اللغات
ls /usr/share/tessdata/
```

### المشكلة: البيئة الافتراضية لا تعمل

```bash
# إعادة إنشاء
rm -rf ~/omni-medical-suite/venv
python -m venv ~/omni-medical-suite/venv
source ~/omni-medical-suite/venv/bin/activate
pip install -r ~/omni-medical-suite/requirements.txt
```

### المشكلة: عدم الوصول للمستودعات

```bash
# التحقق من الإنترنت
ping github.com

# التحقق من SSH
ssh -T git@github.com

# إعادة استنساخ
cd ~/omni-medical-suite/repos
rm -rf repo-name
git clone https://github.com/user/repo-name
```

### المشكلة: صلاحيات الكتابة

```bash
# إصلاح الصلاحيات
chmod -R u+rw ~/omni-medical-suite/logs
chmod -R u+rw ~/omni-medical-suite/feedback
```

### المشكلة: الخدمة لا تبدأ

```bash
# عرض الأخطاء
journalctl --user -u omni-medical --no-pager

# التحقق من المسارات
cat ~/.config/systemd/user/omni-medical.service

# إعادة تحميل
systemctl --user daemon-reload
```

---

## الأسئلة الشائعة

### س: كيف أعرف عدد التصحيحات المسجلة؟

```bash
# عبر Python
python -c "from scripts.advanced_logger import get_feedback_collector; fb=get_feedback_collector(); print(fb.get_correction_stats())"

# عبر سطر الأوامر
wc -l ~/omni-medical-suite/feedback/corrections/*.jsonl
```

### س: كيف أصدر البيانات يدوياً؟

```bash
# نسخ ملفات التصحيحات
cp ~/omni-medical-suite/feedback/corrections/*.jsonl ./backup/

# أو عبر Python
python -c "from scripts.advanced_logger import get_feedback_collector; fb=get_feedback_collector(); fb.export_training_dataset(min_corrections=1)"
```

### س: هل يمكن تشغيل التطبيق بدون GPU؟

**نعم**، التطبيق يعمل على CPU. GPU يُستخدم فقط للتسريع.

### س: كيف أحذف جميع السجلات؟

```bash
# حذف السجلات (كن حذراً!)
rm -rf ~/omni-medical-suite/logs/*
rm -rf ~/omni-medical-suite/feedback/corrections/*
```

### س: كيف أغير إعدادات التسجيل؟

```bash
# تعديل ملف الإعدادات
nano ~/omni-medical-suite/configs/config.json
```

---

## 🔗 روابط مفيدة

- [مستودع Omni Medical Suite](https://github.com/omni-medical-suite)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- [Gradio Documentation](https://gradio.app/docs)
- [Manjaro Wiki](https://wiki.manjaro.org)

---

## 📞 الدعم

للإبلاغ عن مشاكل أو اقتراحات:

1. استخدم تبويب **"💡 اقتراحات التحسين"** في التطبيق
2. أو افتح issue على GitHub
3. أو أرسل بيانات التصحيحات عبر `feedback/training_data/`

---

**تم إنشاء هذا الدليل بتاريخ: 2026-07-17**
**إصدار: 1.0.0**
