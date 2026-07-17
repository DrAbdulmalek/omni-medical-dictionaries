# HF Space Deployment Guide

## خطوات الرفع إلى Hugging Face

### 1. إنشاء Space جديد
1. اذهب إلى https://huggingface.co/spaces
2. اضغط "Create new Space"
3. اختر:
   - **Space Name**: `omni-medical-suite` (أو أي اسم)
   - **License**: MIT
   - **Space SDK**: Gradio
   - **Hardware**: CPU (مجاني)

### 2. رفع الملفات

#### الطريقة A: Git (موصى بها)
```bash
# نفّذ على جهازك
git clone https://huggingface.co/spaces/YOUR_USERNAME/omni-medical-suite
cd omni-medical-suite

# انسخ ملفات HF Space
unzip /path/to/hf_space_omni_medical.zip -d .

# ارفع
git add .
git commit -m "Initial commit"
git push
```

#### الطريقة B: Drag & Drop
1. افتح صفحة الـ Space
2. اذهب إلى "Files" tab
3. ارفع الملفات مباشرة:
   - `app.py`
   - `requirements.txt`
   - `README.md`
   - `.gitignore`
   - `packages/` (المجلد كاملاً)
   - `scripts/` (المجلد كاملاً)

### 3. انتظر البناء
- يستغرق 2-5 دقائق
- شاهد الـ Logs إذا حدث خطأ

### 4. افتح التطبيق
- الرابط: `https://huggingface.co/spaces/YOUR_USERNAME/omni-medical-suite`

## ملاحظات هامة

### Tesseract على HF Spaces
- HF Spaces يستخدم Docker
- `tesseract-ocr` و `tesseract-ocr-ara` يجب تثبيتهم
- أضف `packages.txt` إذا لزم الأمر:
```
tesseract-ocr
tesseract-ocr-ara
tesseract-ocr-eng
```

### الحدود
- CPU فقط (مجاني)
- 16GB RAM
- الملفات تُحذف بعد إعادة التشغيل (استخدم Downloads)

### للاستخدام اليومي
- ارفع الصفحات في تبويب "Upload & OCR"
- ابحث في "Search Glossary"
- صدّر النتائج كـ ZIP
- حمّل ZIP إلى جهازك

## الدعم
- GitHub: DrAbdulmalek/omni-medical-suite
- Issues: افتح issue على GitHub
