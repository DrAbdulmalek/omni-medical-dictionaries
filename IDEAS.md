# IDEAS.md — OmniFile Processor / omni-medical-suite
# مستودع الأفكار والتطوير المستقبلي
# Last Updated: 2026-07-18

## ============================================================
## الأفكار المستخلصة من الملفات المرفوعة
## ============================================================

### 1. Archive.org Book Downloader (Tampermonkey v3.6)
**المصدر**: Archive-Borrowed-Book-Downloader-main

**أفكار مفيدة:**
- [ ] **SimplePDF class** — مُولّد PDF بدون مكتبات خارجية (JPEG → PDF 1.4 binary)
  - يبني PDF يدوياً باستخدام Uint8Array + DataView + chunk-based assembly
  - يحلل JPEG SOF markers لاكتشاف Color Space (Gray/RGB/CMYK)
  - مفيد لدمج صفحات الكتاب المحمّلة في PDF واحد بدون img2pdf
- [ ] **IIIF URL Pattern** — `https://archive.org/iiif/{book_id}/page/{n}/full/pct:100/0/default.jpg`
  - أنظف وأسرع من scraping DOM
  - يعمل بدون تسجيل دخول (للكتب المفتوحة)
- [ ] **IIIF info.json** — `GET /iiif/{book_id}/info.json` يعيد عدد الصفحات والأبعاد
- [ ] **PiP Trick** — Canvas → MediaStream → Video → Picture-in-Picture يبقي التبويب نشطاً
  - مفيد لعمليات التحميل الطويلة في المتصفح
- [ ] **CSS Selectors لـ Archive.org**:
  ```js
  image: 'img.BRpageimage'
  nextBtn: ['.book_flip_next', '.flip-btn.next', 'button[title="Next page"]']
  pageDisplay: '.BRcurrentpage'
  ```
- [ ] **Deduplication** — `processedURLs = new Set()` لمنع إعادة التحميل

### 2. Archive Book Extractor (Hitti Script)
**المصدر**: archive_hitti_extractor.zip

**أفكار مفيدة:**
- [x] **IIIF Page Download** — مستخدم بالفعل (نفس النمط أعلاه)
- [x] **3 أنماط Regex لاستخراج المسارد**:
  - En→Ar: `([A-Za-z][A-Za-z\s\-]{2,50})[,;]\s*([\u0600-\u06FF\s]{2,100})`
  - Ar→En: عكس النمط أعلاه
  - Bold Dict: `^([A-Z][A-Z\s\-]{1,40})\s*[—\-]\s*(.+)$`
- [x] **Skip-if-exists** — قابلية استئناف التحميل
- [x] **Multi-format Export** — JSON + CSV (UTF-8 BOM) + TXT
- [x] **Context Window** — `text[max(0, match.start()-50):match.end()+50]`
- [x] **SQLite Schema** مع `verified` flag لسير المراجعة البشرية
- [x] **img2pdf** لتجميع الصفحات في PDF
- [ ] **تحسين**: استبدال Tesseract فقط بـ multi-engine OCR

### 3. Medical Glossary Collector (15 Collector)
**المصدر**: medical-glossary-collector(1).zip

**أفكار مفيدة:**
- [x] **BaseCollector Pattern** — فئة أساسية مع:
  - Auto-retry HTTP (5 retries, exponential backoff)
  - SHA256-based deduplication
  - JSON per-source storage
  - Progress tracking (state.json)
  - Per-source logging
- [x] **TermEntry Dataclass** — نموذج موحد:
  ```python
  @dataclass
  class TermEntry:
      term: str
      definition: str
      source: str
      language: str  # "ar", "en", "mixed"
      confidence: float = 1.0
      tags: List[str] = None
      raw_text: str = ""
      date_added: str = None
  ```
- [x] **Confidence-based Merge** — عند التكرار، نحفظ الأعلى ثقة
- [x] **MeSH SPARQL** — مصطلحات طبية من NLM (LIMIT 5000)
- [x] **Wikidata SPARQL** — أمراض مع تسميات عربية (`bd:serviceParam wikibase:language "en,ar"`)
- [x] **ICD-11 OAuth2** — WHO ICD-API v2 مع token caching
- [x] **Multi-index** — `by_language` + `by_source` للبحث السريع
- [ ] **Dashboard Streamlit** — 4 مقاييس + بحث نصي كامل
- [ ] **CI/CD** — جمع يومي (02:00 و 14:00 UTC) + تقرير أسبوعي

### 4. OmniFile AI Processor (50MB, 5197 ملف)
**المصدر**: Archive_code_export.txt

**أفكار مفيدة:**
- [x] **OCREngine (5 محركات)** — Surya, TrOCR, EasyOCR, Tesseract, PaddleOCR
  - Lazy Loading (يُحمّل عند أول استخدام)
  - Graceful Degradation (يسقط لمحرك بديل عند الفشل)
  - Confidence Thresholds (accept < 0.5, retry < 0.7)
  - Batch Processing + PDF Support
- [x] **Medical OCR Pipeline** — CLAHE → Otsu → Projection Profile → EasyOCR → Dictionary Correction
- [x] **Medical Dictionary Correction** — Regex-based JSON mergeable
- [x] **PDF Processor** — PyMuPDF (fast) + pdfplumber (fallback)
- [x] **NLP Pipeline** — Arabic RTL, spell checker, language detector, entity extractor
- [x] **AI Gateway** — Multi-provider routing (DeepSeek, Kimi, Ollama, etc.)
- [x] **PatternDB** — يتعلم من تصحيحات المستخدم
- [ ] **Parallel Processor** — Batch processing with progress callback
- [ ] **HTML Review Page** — صفحة مراجعة تفاعلية للنص المُستخرج
- [ ] **Model Manager** — Lazy loading + registry + version management

### 5. Glossary Parser (4 استراتيجيات)
**المصدر**: medical-glossary-collector tests

**أفكار مفيدة:**
- [x] **_pattern_colon** — `([^\n:]{2,80})[:：]\s*([^\n]{5,500})` (confidence: 0.8)
- [x] **_pattern_numbered** — `\d+[.)]\s*([^\n-]{2,80})\s*[-–]\s*([^\n]{5,500})` (0.75)
- [x] **_pattern_table** — Line split by `\s*[|\t]\s*` (0.7)
- [x] **_pattern_parentheses** — `([^\n(]{2,50})\s*\(\s*([^\)]{5,200})\s*\)` (0.6)
- [x] **Language Detection** — ratio of Arabic chars > 0.3 → "ar"

### 6. Text Extractor (Multi-format)
**المصدر**: medical-glossary-collector processors/text_extractor.py

**أفكار مفيدة:**
- [x] **Cascading Fallback** — txt → pdf (PyPDF2→pdfplumber) → docx → rtf → html → raw binary
- [x] **Multi-Encoding Fallback** — utf-8 → utf-16 → cp1256 (Arabic) → latin-1
- [x] **Arabic-aware regex** — يحافظ على U+0600-U+06FF و U+0750-U+077F و ؛،

## ============================================================
## خطة التكامل (Integration Roadmap)
## ============================================================

### Phase 1: Archive.org Integration (فوري)
1. إضافة `archive_book_downloader.py` — IIIF page download + OCR + glossary extraction
2. دمج 7 أنماط regex (3 من Hitti + 4 من glossary_parser)
3. SQLite schema مع verified flag

### Phase 2: Multi-Engine OCR (قريب)
1. إضافة OCREngine مع 5 محركات (lazy loading + fallback)
2. Medical dictionary correction pattern
3. Projection profile line segmentation

### Phase 3: Medical Glossary Collectors (متوسط المدى)
1. BaseCollector pattern مع retry + dedup + progress
2. MeSH + Wikidata collectors (SPARQL)
3. Merge pipeline مع confidence-based dedup

### Phase 4: AI Enhancement (طويل المدى)
1. AI Gateway integration
2. PatternDB learning from corrections
3. Streamlit dashboard

## ============================================================
## ملاحظات تقنية
## ============================================================

- **IIIF هو الطريقة الأنسب** لاستخراج صفحات Archive.org (أسرع وأكثر استقراراً من Selenium)
- **cp1256 encoding** ضروري لملفات نصية عربية قديمة
- **Tesseract psm 6** أفضل للقواميس (كتلة نصية منفردة)
- **Projection Profile** أفضل من Tesseract لتقسيم الأسطر في الخط اليدوي
- **SimplePDF** مفيد كـ fallback عندما لا يتوفر img2pdf/ReportLab