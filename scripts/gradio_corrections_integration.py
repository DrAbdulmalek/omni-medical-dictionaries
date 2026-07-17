"""
تكامل واجهة Gradio لجمع التصحيحات من المستخدمين
Gradio Corrections Integration Module

يقوم بإضافة تبويب "تصحيح النتائج" في واجهة Gradio
لتمكين المستخدمين من:
- تصحيح نتائج OCR
- تصحيح الترجمات الطبية
- تقديم اقتراحات التحسين
- عرض إحصائيات التصحيحات
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

import gradio as gr

# استيراد نظام التسجيل
import sys
sys.path.insert(0, str(Path(__file__).parent))
from advanced_logger import get_feedback_collector, CorrectionType


class GradioCorrectionsUI:
    """
    واجهة Gradio لجمع التصحيحات والتغذية الراجعة
    """

    def __init__(self, base_dir: str = None):
        self.fb = get_feedback_collector(base_dir)
        self.base_dir = Path(base_dir) if base_dir else Path.home() / "omni-medical-suite"

    def submit_correction(self, original_text: str, corrected_text: str, 
                         correction_type: str, model_version: str,
                         page_number: str, document_id: str,
                         language_pair: str, severity: str,
                         notes: str) -> str:
        """
        إرسال تصحيح جديد

        Returns:
            str: رسالة تأكيد
        """
        if not original_text.strip() or not corrected_text.strip():
            return "❌ يرجى إدخال النص الأصلي والمصحح"

        try:
            page = int(page_number) if page_number.strip() else None
        except ValueError:
            page = None

        self.fb.log_correction(
            original=original_text,
            corrected=corrected_text,
            correction_type=correction_type,
            model_version=model_version,
            page_number=page,
            document_id=document_id if document_id.strip() else None,
            language_pair=language_pair if language_pair.strip() else None,
            severity=severity,
            notes=notes
        )

        return f"✅ تم تسجيل التصحيح بنجاح!\n\nالنوع: {correction_type}\nالنص الأصلي: {original_text[:50]}...\nالنص المصحح: {corrected_text[:50]}..."

    def submit_suggestion(self, suggestion: str, category: str) -> str:
        """إرسال اقتراح"""
        if not suggestion.strip():
            return "❌ يرجى إدخال الاقتراح"

        self.fb.log_suggestion(suggestion, category)
        return f"✅ تم تسجيل الاقتراح بنجاح!\n\nالفئة: {category}\nالاقتراح: {suggestion[:100]}..."

    def get_stats(self) -> str:
        """الحصول على الإحصائيات"""
        stats = self.fb.get_correction_stats()

        if stats["total_corrections"] == 0:
            return "📊 لا توجد تصحيحات مسجلة بعد."

        report = f"""
📊 **إحصائيات التصحيحات**

**الإجمالي:** {stats["total_corrections"]} تصحيح

**حسب النوع:**
"""
        for ctype, count in stats["by_type"].items():
            report += f"  • {ctype}: {count}\n"

        report += f"\n**حسب النموذج:**\n"
        for model, count in stats["by_model"].items():
            report += f"  • {model}: {count}\n"

        report += f"\n**حسب الأهمية:**\n"
        for sev, count in stats["by_severity"].items():
            report += f"  • {sev}: {count}\n"

        report += f"\n**مستندات فريدة:** {stats["unique_documents"]}\n"
        report += f"**مستخدمين فريدين:** {stats["unique_users"]}\n"
        report += f"**متوسط الثقة:** {stats["average_confidence"]}\n"

        return report

    def get_recent_corrections(self, limit: int = 10) -> str:
        """الحصول على أحدث التصحيحات"""
        corrections = self.fb.get_recent_corrections(limit)

        if not corrections:
            return "📋 لا توجد تصحيحات حديثة."

        report = "📋 **أحدث التصحيحات**\n\n"
        for i, corr in enumerate(corrections, 1):
            report += f"**{i}.** [{corr['correction_type']}] {corr['timestamp'][:16]}\n"
            report += f"   النص الأصلي: {corr['original'][:40]}...\n"
            report += f"   النص المصحح: {corr['corrected'][:40]}...\n"
            if corr.get('model_version'):
                report += f"   النموذج: {corr['model_version']}\n"
            report += "\n"

        return report

    def export_dataset(self, min_corrections: int) -> str:
        """تصدير مجموعة التدريب"""
        result = self.fb.export_training_dataset(min_corrections=min_corrections)

        if result:
            return f"✅ تم تصدير مجموعة التدريب!\n\nالمسار: {result}"
        else:
            return f"⚠️ لا توجد بيانات كافية للتصدير.\nالمطلوب: {min_corrections} تصحيح على الأقل."

    def create_correction_tab(self) -> gr.Tab:
        """إنشاء تبويب التصحيحات"""
        with gr.Tab("✏️ تصحيح النتائج") as tab:
            gr.Markdown("## تصحيح نتائج OCR والترجمة")
            gr.Markdown("ساعد في تحسين النماذج بتصحيح الأخطاء التي تجدها.")

            with gr.Row():
                with gr.Column(scale=1):
                    original_text = gr.Textbox(
                        label="النص الأصلي (الخاطئ)",
                        placeholder="أدخل النص الخاطئ هنا...",
                        lines=3
                    )
                    corrected_text = gr.Textbox(
                        label="النص المصحح",
                        placeholder="أدخل النص الصحيح هنا...",
                        lines=3
                    )

                with gr.Column(scale=1):
                    correction_type = gr.Dropdown(
                        label="نوع التصحيح",
                        choices=["ocr", "translation", "terminology", "formatting", "classification", "extraction", "other"],
                        value="ocr"
                    )
                    model_version = gr.Textbox(
                        label="إصدار النموذج",
                        placeholder="مثال: tesseract_v5.3"
                    )
                    page_number = gr.Number(
                        label="رقم الصفحة",
                        value=None,
                        precision=0
                    )
                    document_id = gr.Textbox(
                        label="معرف المستند",
                        placeholder="مثال: doc_001.pdf"
                    )
                    language_pair = gr.Textbox(
                        label="زوج اللغات",
                        placeholder="مثال: en-ar"
                    )
                    severity = gr.Dropdown(
                        label="درجة الأهمية",
                        choices=["low", "normal", "high", "critical"],
                        value="normal"
                    )
                    notes = gr.Textbox(
                        label="ملاحظات",
                        placeholder="ملاحظات إضافية...",
                        lines=2
                    )

            submit_btn = gr.Button("إرسال التصحيح", variant="primary")
            result_msg = gr.Textbox(label="النتيجة", interactive=False)

            submit_btn.click(
                fn=self.submit_correction,
                inputs=[original_text, corrected_text, correction_type, model_version,
                       page_number, document_id, language_pair, severity, notes],
                outputs=result_msg
            )

        return tab

    def create_suggestions_tab(self) -> gr.Tab:
        """إنشاء تبويب الاقتراحات"""
        with gr.Tab("💡 اقتراحات التحسين") as tab:
            gr.Markdown("## اقتراحات التحسين والميزات الجديدة")

            suggestion_text = gr.Textbox(
                label="الاقتراح",
                placeholder="صف اقتراحك هنا...",
                lines=4
            )
            category = gr.Dropdown(
                label="الفئة",
                choices=["feature", "bug", "improvement", "general"],
                value="improvement"
            )
            submit_suggestion_btn = gr.Button("إرسال الاقتراح", variant="primary")
            suggestion_result = gr.Textbox(label="النتيجة", interactive=False)

            submit_suggestion_btn.click(
                fn=self.submit_suggestion,
                inputs=[suggestion_text, category],
                outputs=suggestion_result
            )

        return tab

    def create_stats_tab(self) -> gr.Tab:
        """إنشاء تبويب الإحصائيات"""
        with gr.Tab("📊 الإحصائيات") as tab:
            gr.Markdown("## إحصائيات التصحيحات والاستخدام")

            refresh_btn = gr.Button("تحديث الإحصائيات", variant="secondary")
            stats_output = gr.Textbox(label="الإحصائيات", interactive=False, lines=20)

            refresh_btn.click(
                fn=self.get_stats,
                outputs=stats_output
            )

            # عرض أحدث التصحيحات
            gr.Markdown("### أحدث التصحيحات")
            recent_output = gr.Textbox(label="أحدث التصحيحات", interactive=False, lines=15)

            refresh_btn.click(
                fn=self.get_recent_corrections,
                outputs=recent_output
            )

            # تصدير البيانات
            gr.Markdown("### تصدير بيانات التدريب")
            min_corrections = gr.Number(
                label="الحد الأدنى للتصحيحات",
                value=50,
                precision=0
            )
            export_btn = gr.Button("تصدير مجموعة التدريب", variant="primary")
            export_result = gr.Textbox(label="نتيجة التصدير", interactive=False)

            export_btn.click(
                fn=self.export_dataset,
                inputs=min_corrections,
                outputs=export_result
            )

        return tab

    def integrate_with_app(self, app: gr.Blocks):
        """
        تكامل مع تطبيق Gradio موجود

        Args:
            app: كائن Gradio Blocks
        """
        self.create_correction_tab()
        self.create_suggestions_tab()
        self.create_stats_tab()


# ─────────────────────────────────────────────────────────────────────────────
# دالة مساعدة للتكامل السريع
# ─────────────────────────────────────────────────────────────────────────────
def add_corrections_to_app(app: gr.Blocks, base_dir: str = None):
    """
    إضافة تبويبات التصحيحات لتطبيق Gradio موجود

    Usage:
        import gradio as gr
        from gradio_corrections_integration import add_corrections_to_app

        with gr.Blocks() as app:
            # ... تبويباتك الأخرى ...
            add_corrections_to_app(app)

        app.launch()
    """
    ui = GradioCorrectionsUI(base_dir)
    ui.integrate_with_app(app)


# ─────────────────────────────────────────────────────────────────────────────
# مثال تشغيل مستقل
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("تشغيل واجهة Gradio لجمع التصحيحات")
    print("=" * 60)

    with gr.Blocks(title="Omni Medical - نظام التصحيحات") as demo:
        gr.Markdown("# 🏥 Omni Medical Suite - نظام جمع التصحيحات")
        gr.Markdown("ساعد في تحسين النماذج بتصحيح الأخطاء وتقديم الاقتراحات.")

        ui = GradioCorrectionsUI()
        ui.create_correction_tab()
        ui.create_suggestions_tab()
        ui.create_stats_tab()

    demo.launch(
        server_name="0.0.0.0",
        server_port=7861,
        share=False,
        show_error=True
    )
