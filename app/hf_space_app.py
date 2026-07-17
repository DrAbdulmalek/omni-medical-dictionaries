#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni Medical Suite v3.0 - HF Space
=====================================
Scanner Fixer + Hitti Glossary + Multi-Model Fine-tuning + Model Comparison
Models: TrOCR | Qwen2-VL LoRA | Donut | Pix2Struct
Author: DrAbdulmalek / Z.ai
"""

import os
import sys
import sqlite3
import logging
import zipfile
import shutil
import json
import re
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, asdict, field
from collections import defaultdict

import gradio as gr
from PIL import Image
import cv2
import numpy as np

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR / "packages" / "preprocessors"))
sys.path.insert(0, str(BASE_DIR / "scripts"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = BASE_DIR / "hitti_glossary.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS en_ar_glossary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            english_term TEXT NOT NULL,
            arabic_term TEXT,
            page_num INTEGER,
            context TEXT,
            confidence REAL DEFAULT 0.0,
            verified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ar_en_glossary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arabic_term TEXT NOT NULL,
            english_term TEXT,
            page_num INTEGER,
            context TEXT,
            confidence REAL DEFAULT 0.0,
            verified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS model_comparison (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT,
            image_path TEXT,
            ground_truth TEXT,
            prediction TEXT,
            cer REAL,
            wer REAL,
            inference_time REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_en ON en_ar_glossary(english_term)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ar ON ar_en_glossary(arabic_term)")
    conn.commit()
    conn.close()

init_db()

# ============== SCANNER FIXER ==============

class ScannerFixer:
    def auto_detect_skew(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        edges = cv2.Canny(gray, 50, 150)
        lines_h = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=100, maxLineGap=10)
        angles = []
        if lines_h is not None:
            for line in lines_h:
                x1, y1, x2, y2 = line[0]
                if x2 != x1:
                    angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                    if abs(angle) < 45:
                        angles.append(angle)
        return np.median(angles) if angles else 0.0
    
    def auto_rotate(self, image):
        try:
            import pytesseract
            osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
            osd_angle = float(osd.get("rotate", 0))
        except:
            osd_angle = 0
        hough_angle = self.auto_detect_skew(image)
        final_angle = osd_angle * 0.6 + hough_angle * 0.4 if osd_angle != 0 else hough_angle
        if abs(final_angle) < 0.5:
            return image, 0.0
        h, w = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, final_angle, 1.0)
        rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        return rotated, float(final_angle)
    
    def remove_borders(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        coords = cv2.findNonZero(binary)
        if coords is None:
            return image
        x, y, w, h = cv2.boundingRect(coords)
        pad = 5
        x = max(0, x - pad)
        y = max(0, y - pad)
        w = min(image.shape[1] - x, w + 2*pad)
        h = min(image.shape[0] - y, h + 2*pad)
        return image[y:y+h, x:x+w]
    
    def denoise(self, image):
        if len(image.shape) == 3:
            return cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
        return cv2.fastNlMeansDenoising(image, None, 10, 7, 21)
    
    def enhance(self, image):
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    
    def fix_image(self, image):
        img_array = np.array(image)
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        rotated, angle = self.auto_rotate(img_bgr)
        cropped = self.remove_borders(rotated)
        denoised = self.denoise(cropped)
        enhanced = self.enhance(denoised)
        result_rgb = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)
        return Image.fromarray(result_rgb), f"Fixed! Angle: {angle:.1f} degrees"

# ============== GLOSSARY BUILDER ==============

class GlossaryBuilder:
    def __init__(self):
        self.db_path = DB_PATH
    
    def process_uploaded_images(self, files):
        if not files:
            return "No files uploaded"
        try:
            import pytesseract
            total_entries = 0
            for i, file_path in enumerate(files):
                img = cv2.imread(file_path)
                if img is None:
                    continue
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                text = pytesseract.image_to_string(binary, lang='eng+ara', config='--psm 6 --oem 3')
                entries = self._extract_entries(text, i + 1)
                if entries:
                    self._save_entries(entries)
                    total_entries += len(entries)
            return f"Processed {len(files)} images. Found {total_entries} glossary entries."
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _extract_entries(self, text, page_num):
        entries = []
        p1 = re.compile(r"([A-Za-z][A-Za-z\s\-/]{2,50})[,;:]\s*([\u0600-\u06FF\s]{2,100})", re.MULTILINE)
        for m in p1.finditer(text):
            en = re.sub(r"\s+", " ", m.group(1).strip())
            ar = re.sub(r"\s+", " ", m.group(2).strip())
            if len(en) > 2 and len(ar) > 2:
                entries.append(("en_ar", en, ar, page_num, 0.7))
        p2 = re.compile(r"([\u0600-\u06FF][\u0600-\u06FF\s]{2,50})[,;:]\s*([A-Za-z][A-Za-z\s\-/]{2,50})", re.MULTILINE)
        for m in p2.finditer(text):
            ar = re.sub(r"\s+", " ", m.group(1).strip())
            en = re.sub(r"\s+", " ", m.group(2).strip())
            if len(ar) > 2 and len(en) > 2:
                entries.append(("ar_en", ar, en, page_num, 0.7))
        return entries
    
    def _save_entries(self, entries):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for e in entries:
            if e[0] == "en_ar":
                cursor.execute("INSERT OR IGNORE INTO en_ar_glossary (english_term, arabic_term, page_num, confidence) VALUES (?, ?, ?, ?)", (e[1], e[2], e[3], e[4]))
            else:
                cursor.execute("INSERT OR IGNORE INTO ar_en_glossary (arabic_term, english_term, page_num, confidence) VALUES (?, ?, ?, ?)", (e[1], e[2], e[3], e[4]))
        conn.commit()
        conn.close()
    
    def search(self, query, direction):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if direction == "en->ar":
            cursor.execute("SELECT english_term, arabic_term, page_num, confidence FROM en_ar_glossary WHERE english_term LIKE ? ORDER BY english_term LIMIT 50", (f"%{query}%",))
        else:
            cursor.execute("SELECT arabic_term, english_term, page_num, confidence FROM ar_en_glossary WHERE arabic_term LIKE ? ORDER BY arabic_term LIMIT 50", (f"%{query}%",))
        results = cursor.fetchall()
        conn.close()
        if not results:
            return "No results found."
        lines = []
        for row in results:
            conf = f"[{row[3]:.1f}]" if row[3] else ""
            lines.append(f"{row[0]} -> {row[1]} | Page {row[2]} {conf}")
        return "\n".join(lines)
    
    def get_stats(self):
        conn = sqlite3.connect(self.db_path)
        en_ar = conn.execute("SELECT COUNT(*) FROM en_ar_glossary").fetchone()[0]
        ar_en = conn.execute("SELECT COUNT(*) FROM ar_en_glossary").fetchone()[0]
        conn.close()
        return f"EN->AR: {en_ar} entries\nAR->EN: {ar_en} entries\nTotal: {en_ar + ar_en}"
    
    def export_zip(self):
        try:
            zip_path = BASE_DIR / "glossary_export.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                import csv
                conn = sqlite3.connect(self.db_path)
                cursor = conn.execute("SELECT * FROM en_ar_glossary ORDER BY english_term")
                en_ar = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
                cursor = conn.execute("SELECT * FROM ar_en_glossary ORDER BY arabic_term")
                ar_en = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
                conn.close()
                json_path = BASE_DIR / "hitti_glossary.json"
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump({"en_ar": en_ar, "ar_en": ar_en, "metadata": {"total_en_ar": len(en_ar), "total_ar_en": len(ar_en)}}, f, ensure_ascii=False, indent=2)
                zf.write(json_path, "hitti_glossary.json")
                csv_path = BASE_DIR / "hitti_en_ar.csv"
                with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["English", "Arabic", "Page", "Confidence"])
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.execute("SELECT english_term, arabic_term, page_num, confidence FROM en_ar_glossary ORDER BY english_term")
                    writer.writerows(cursor.fetchall())
                    conn.close()
                zf.write(csv_path, "hitti_en_ar.csv")
                if DB_PATH.exists():
                    zf.write(DB_PATH, "hitti_glossary.db")
            return str(zip_path)
        except Exception as e:
            return f"Error: {str(e)}"

# ============== MULTI-MODEL OCR ENGINE ==============

@dataclass
class OCRResult:
    model_name: str
    text: str
    confidence: float = 0.0
    inference_time: float = 0.0
    error: str = ""

class MultiModelOCR:
    """Unified interface for multiple OCR models"""
    
    AVAILABLE_MODELS = {
        "tesseract": "Tesseract OCR (rule-based)",
        "trocr": "TrOCR (Microsoft - handwritten)",
        "qwen2vl": "Qwen2-VL (multilingual vision)",
        "donut": "Donut (document understanding)",
        "pix2struct": "Pix2Struct (screenshot understanding)"
    }
    
    def __init__(self):
        self.models = {}
        self.processors = {}
    
    def load_model(self, model_name: str, device: str = "cpu") -> str:
        """Load a specific model"""
        try:
            if model_name == "trocr":
                from transformers import TrOCRProcessor, VisionEncoderDecoderModel
                self.processors["trocr"] = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
                self.models["trocr"] = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten").to(device)
                return "TrOCR loaded successfully"
            
            elif model_name == "qwen2vl":
                from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
                self.processors["qwen2vl"] = AutoProcessor.from_pretrained("Qwen/Qwen2-VL-2B-Instruct")
                self.models["qwen2vl"] = Qwen2VLForConditionalGeneration.from_pretrained(
                    "Qwen/Qwen2-VL-2B-Instruct", torch_dtype="auto", device_map="auto")
                return "Qwen2-VL loaded successfully"
            
            elif model_name == "donut":
                from transformers import DonutProcessor, VisionEncoderDecoderModel
                self.processors["donut"] = DonutProcessor.from_pretrained("naver-clova-ix/donut-base-finetuned-cord-v2")
                self.models["donut"] = VisionEncoderDecoderModel.from_pretrained("naver-clova-ix/donut-base-finetuned-cord-v2").to(device)
                return "Donut loaded successfully"
            
            elif model_name == "pix2struct":
                from transformers import Pix2StructProcessor, Pix2StructForConditionalGeneration
                self.processors["pix2struct"] = Pix2StructProcessor.from_pretrained("google/pix2struct-base").to(device)
                self.models["pix2struct"] = Pix2StructForConditionalGeneration.from_pretrained("google/pix2struct-base").to(device)
                return "Pix2Struct loaded successfully"
            
            elif model_name == "tesseract":
                import pytesseract
                return "Tesseract ready (no loading needed)"
            
            else:
                return f"Unknown model: {model_name}"
        except Exception as e:
            return f"Error loading {model_name}: {str(e)}"
    
    def predict(self, image: Image.Image, model_name: str) -> OCRResult:
        """Run inference with specified model"""
        start_time = time.time()
        try:
            if model_name == "tesseract":
                import pytesseract
                img_array = np.array(image)
                if len(img_array.shape) == 3:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
                else:
                    gray = img_array
                _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                text = pytesseract.image_to_string(binary, lang="eng+ara", config="--psm 6 --oem 3")
                return OCRResult("tesseract", text, 0.8, time.time() - start_time)
            
            elif model_name == "trocr":
                if "trocr" not in self.models:
                    self.load_model("trocr")
                processor = self.processors["trocr"]
                model = self.models["trocr"]
                pixel_values = processor(images=image, return_tensors="pt").pixel_values
                generated_ids = model.generate(pixel_values)
                text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
                return OCRResult("trocr", text, 0.85, time.time() - start_time)
            
            elif model_name == "qwen2vl":
                if "qwen2vl" not in self.models:
                    self.load_model("qwen2vl")
                processor = self.processors["qwen2vl"]
                model = self.models["qwen2vl"]
                messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": "Read all text in this image:"}]}]
                text_input = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = processor(text=[text_input], images=[image], return_tensors="pt", padding=True)
                inputs = {k: v.to(model.device) for k, v in inputs.items()}
                generated_ids = model.generate(**inputs, max_new_tokens=256)
                output_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
                return OCRResult("qwen2vl", output_text, 0.9, time.time() - start_time)
            
            elif model_name == "donut":
                if "donut" not in self.models:
                    self.load_model("donut")
                processor = self.processors["donut"]
                model = self.models["donut"]
                pixel_values = processor(images=image, return_tensors="pt").pixel_values
                task_prompt = "<s_cord-v2>"
                decoder_input_ids = processor.tokenizer(task_prompt, add_special_tokens=False, return_tensors="pt")["input_ids"]
                generated_ids = model.generate(pixel_values, decoder_input_ids=decoder_input_ids, max_length=768)
                text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
                return OCRResult("donut", text, 0.82, time.time() - start_time)
            
            elif model_name == "pix2struct":
                if "pix2struct" not in self.models:
                    self.load_model("pix2struct")
                processor = self.processors["pix2struct"]
                model = self.models["pix2struct"]
                inputs = processor(images=image, text="Read text:", return_tensors="pt")
                inputs = {k: v.to(model.device) for k, v in inputs.items()}
                generated_ids = model.generate(**inputs, max_new_tokens=256)
                text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
                return OCRResult("pix2struct", text, 0.83, time.time() - start_time)
            
            else:
                return OCRResult(model_name, "", 0.0, 0.0, f"Unknown model: {model_name}")
        except Exception as e:
            return OCRResult(model_name, "", 0.0, time.time() - start_time, str(e))
    
    def compare_all(self, image: Image.Image, ground_truth: str = "") -> Dict[str, Any]:
        """Run all models and compare results"""
        results = {}
        for model_name in ["tesseract", "trocr", "qwen2vl", "donut", "pix2struct"]:
            result = self.predict(image, model_name)
            results[model_name] = {
                "text": result.text,
                "confidence": result.confidence,
                "time": result.inference_time,
                "error": result.error
            }
            if ground_truth:
                results[model_name]["cer"] = self._calculate_cer(ground_truth, result.text)
                results[model_name]["wer"] = self._calculate_wer(ground_truth, result.text)
        return results
    
    def _calculate_cer(self, reference: str, hypothesis: str) -> float:
        """Character Error Rate"""
        import Levenshtein
        if not reference:
            return 0.0
        distance = Levenshtein.distance(reference, hypothesis)
        return distance / max(len(reference), 1)
    
    def _calculate_wer(self, reference: str, hypothesis: str) -> float:
        """Word Error Rate"""
        ref_words = reference.split()
        hyp_words = hypothesis.split()
        if not ref_words:
            return 0.0
        import Levenshtein
        distance = Levenshtein.distance(" ".join(ref_words), " ".join(hyp_words))
        return distance / max(len(ref_words), 1)

# ============== FINE-TUNER (ALL MODELS) ==============

class FineTuner:
    def __init__(self):
        self.model = None
        self.processor = None
        self.training_log = []
    
    def check_dependencies(self):
        missing = []
        for pkg in ["transformers", "torch", "peft", "datasets", "accelerate", "Levenshtein"]:
            try:
                __import__(pkg.lower() if pkg != "Levenshtein" else "Levenshtein")
            except ImportError:
                missing.append(pkg)
        return missing if missing else []
    
    def install_dependencies(self):
        import subprocess
        import sys
        packages = ["transformers", "torch", "peft", "datasets", "accelerate", "python-Levenshtein"]
        for pkg in packages:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])
            except Exception as e:
                return f"Failed to install {pkg}: {e}"
        return "All dependencies installed!"
    
    def prepare_dataset_from_db(self, output_dir="./training_data"):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.execute("SELECT english_term, arabic_term FROM en_ar_glossary WHERE verified = 1 LIMIT 1000")
            pairs = cursor.fetchall()
            conn.close()
            if not pairs:
                return None, "No verified entries. Verify some entries first."
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            dataset = [{"text": f"{en} -> {ar}", "label": ar} for en, ar in pairs]
            dataset_path = Path(output_dir) / "glossary_dataset.json"
            with open(dataset_path, "w", encoding="utf-8") as f:
                json.dump(dataset, f, ensure_ascii=False, indent=2)
            return str(dataset_path), f"Dataset: {len(dataset)} verified pairs"
        except Exception as e:
            return None, f"Error: {e}"
    
    def prepare_dataset_from_upload(self, files, labels, output_dir="./training_data"):
        try:
            if not files or not labels:
                return None, "No files or labels"
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            (Path(output_dir) / "images").mkdir(exist_ok=True)
            dataset = []
            label_list = labels.split("\n")
            for i, (file_path, label) in enumerate(zip(files, label_list)):
                if not label.strip():
                    continue
                dest = Path(output_dir) / "images" / f"img_{i:04d}.jpg"
                shutil.copy(file_path, dest)
                dataset.append({"image": str(dest), "text": label.strip()})
            dataset_path = Path(output_dir) / "image_dataset.json"
            with open(dataset_path, "w", encoding="utf-8") as f:
                json.dump(dataset, f, ensure_ascii=False, indent=2)
            return str(dataset_path), f"Dataset: {len(dataset)} image-label pairs"
        except Exception as e:
            return None, f"Error: {e}"
    
    def train_model(self, model_type, dataset_path, epochs=3, batch_size=4, lr=5e-5, output_dir="./model_finetuned"):
        try:
            if model_type == "trocr":
                return self._train_trocr(dataset_path, epochs, batch_size, lr, output_dir)
            elif model_type == "qwen2vl":
                return self._train_qwen_lora(dataset_path, epochs, batch_size, lr, output_dir)
            elif model_type == "donut":
                return self._train_donut(dataset_path, epochs, batch_size, lr, output_dir)
            elif model_type == "pix2struct":
                return self._train_pix2struct(dataset_path, epochs, batch_size, lr, output_dir)
            else:
                return f"Unknown model type: {model_type}"
        except Exception as e:
            return f"Training error: {e}"
    
    def _train_trocr(self, dataset_path, epochs, batch_size, lr, output_dir):
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel, TrainingArguments, Trainer
        import torch
        with open(dataset_path, "r") as f:
            data = json.load(f)
        processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
        model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")
        class DS(torch.utils.data.Dataset):
            def __init__(self, data, processor):
                self.data = data; self.processor = processor
            def __len__(self): return len(self.data)
            def __getitem__(self, idx):
                item = self.data[idx]
                if "image" in item:
                    img = Image.open(item["image"]).convert("RGB")
                else:
                    img = Image.new("RGB", (224, 224), "white")
                pv = self.processor(images=img, return_tensors="pt").pixel_values.squeeze()
                lbl = self.processor.tokenizer(item.get("text", ""), return_tensors="pt").input_ids.squeeze()
                return {"pixel_values": pv, "labels": lbl}
        ds = DS(data, processor)
        args = TrainingArguments(output_dir=output_dir, num_train_epochs=epochs, per_device_train_batch_size=batch_size, learning_rate=lr, save_steps=200, logging_steps=50, push_to_hub=False)
        trainer = Trainer(model=model, args=args, train_dataset=ds)
        trainer.train()
        model.save_pretrained(output_dir)
        processor.save_pretrained(output_dir)
        return f"TrOCR trained! Saved to {output_dir}"
    
    def _train_qwen_lora(self, dataset_path, epochs, batch_size, lr, output_dir):
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor, TrainingArguments, Trainer
        from peft import LoraConfig, get_peft_model
        import torch
        with open(dataset_path, "r") as f:
            data = json.load(f)
        model = Qwen2VLForConditionalGeneration.from_pretrained("Qwen/Qwen2-VL-2B-Instruct", torch_dtype=torch.float32, device_map="auto")
        processor = AutoProcessor.from_pretrained("Qwen/Qwen2-VL-2B-Instruct")
        lora = LoraConfig(r=16, lora_alpha=32, target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], lora_dropout=0.05, bias="none", task_type="CAUSAL_LM")
        model = get_peft_model(model, lora)
        class DS(torch.utils.data.Dataset):
            def __init__(self, data, processor):
                self.data = data; self.processor = processor
            def __len__(self): return len(self.data)
            def __getitem__(self, idx):
                item = self.data[idx]
                if "image" in item:
                    img = Image.open(item["image"]).convert("RGB")
                else:
                    img = Image.new("RGB", (224, 224), "white")
                msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": "Read:"}]}]
                ti = self.processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
                inputs = self.processor(text=[ti], images=[img], return_tensors="pt", padding=True)
                lbl = self.processor.tokenizer(item.get("text", ""), return_tensors="pt").input_ids.squeeze()
                return {k: v.squeeze(0) for k, v in inputs.items()} | {"labels": lbl}
        ds = DS(data, processor)
        args = TrainingArguments(output_dir=output_dir, num_train_epochs=epochs, per_device_train_batch_size=batch_size, learning_rate=lr, save_steps=100, logging_steps=25, push_to_hub=False, remove_unused_columns=False)
        trainer = Trainer(model=model, args=args, train_dataset=ds)
        trainer.train()
        model.save_pretrained(output_dir)
        processor.save_pretrained(output_dir)
        return f"Qwen2-VL LoRA trained! Saved to {output_dir}"
    
    def _train_donut(self, dataset_path, epochs, batch_size, lr, output_dir):
        from transformers import DonutProcessor, VisionEncoderDecoderModel, TrainingArguments, Trainer
        import torch
        with open(dataset_path, "r") as f:
            data = json.load(f)
        processor = DonutProcessor.from_pretrained("naver-clova-ix/donut-base")
        model = VisionEncoderDecoderModel.from_pretrained("naver-clova-ix/donut-base")
        class DS(torch.utils.data.Dataset):
            def __init__(self, data, processor):
                self.data = data; self.processor = processor
            def __len__(self): return len(self.data)
            def __getitem__(self, idx):
                item = self.data[idx]
                if "image" in item:
                    img = Image.open(item["image"]).convert("RGB")
                else:
                    img = Image.new("RGB", (224, 224), "white")
                pixel_values = self.processor(images=img, return_tensors="pt").pixel_values.squeeze()
                decoder_input_ids = self.processor.tokenizer(item.get("text", ""), add_special_tokens=False, return_tensors="pt").input_ids.squeeze()
                return {"pixel_values": pixel_values, "labels": decoder_input_ids}
        ds = DS(data, processor)
        args = TrainingArguments(output_dir=output_dir, num_train_epochs=epochs, per_device_train_batch_size=batch_size, learning_rate=lr, save_steps=200, logging_steps=50, push_to_hub=False)
        trainer = Trainer(model=model, args=args, train_dataset=ds)
        trainer.train()
        model.save_pretrained(output_dir)
        processor.save_pretrained(output_dir)
        return f"Donut trained! Saved to {output_dir}"
    
    def _train_pix2struct(self, dataset_path, epochs, batch_size, lr, output_dir):
        from transformers import Pix2StructProcessor, Pix2StructForConditionalGeneration, TrainingArguments, Trainer
        import torch
        with open(dataset_path, "r") as f:
            data = json.load(f)
        processor = Pix2StructProcessor.from_pretrained("google/pix2struct-base")
        model = Pix2StructForConditionalGeneration.from_pretrained("google/pix2struct-base")
        class DS(torch.utils.data.Dataset):
            def __init__(self, data, processor):
                self.data = data; self.processor = processor
            def __len__(self): return len(self.data)
            def __getitem__(self, idx):
                item = self.data[idx]
                if "image" in item:
                    img = Image.open(item["image"]).convert("RGB")
                else:
                    img = Image.new("RGB", (224, 224), "white")
                inputs = self.processor(images=img, text="Read text:", return_tensors="pt")
                lbl = self.processor.tokenizer(item.get("text", ""), return_tensors="pt").input_ids.squeeze()
                return {k: v.squeeze(0) for k, v in inputs.items()} | {"labels": lbl}
        ds = DS(data, processor)
        args = TrainingArguments(output_dir=output_dir, num_train_epochs=epochs, per_device_train_batch_size=batch_size, learning_rate=lr, save_steps=200, logging_steps=50, push_to_hub=False, remove_unused_columns=False)
        trainer = Trainer(model=model, args=args, train_dataset=ds)
        trainer.train()
        model.save_pretrained(output_dir)
        processor.save_pretrained(output_dir)
        return f"Pix2Struct trained! Saved to {output_dir}"

# ============== GRADIO INTERFACE ==============

def create_interface():
    scanner = ScannerFixer()
    glossary = GlossaryBuilder()
    trainer = FineTuner()
    ocr_engine = MultiModelOCR()
    
    with gr.Blocks(title="Omni Medical Suite v3.0", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🏥 Omni Medical Suite v3.0")
        gr.Markdown("Scanner + Glossary + Multi-Model OCR + Fine-tuning | by DrAbdulmalek")
        
        with gr.Tabs():
            
            # TAB 1: Scanner Fixer
            with gr.TabItem("🖼️ Scanner Fixer"):
                gr.Markdown("### Fix scanned medical documents")
                with gr.Row():
                    with gr.Column():
                        input_img = gr.Image(label="Upload Scanned Image", type="pil")
                        fix_btn = gr.Button("Fix Image", variant="primary")
                    with gr.Column():
                        output_img = gr.Image(label="Fixed Image", type="pil")
                        fix_status = gr.Textbox(label="Status")
                fix_btn.click(scanner.fix_image, input_img, [output_img, fix_status])
            
            # TAB 2: Glossary Upload
            with gr.TabItem("📁 Upload & OCR"):
                gr.Markdown("### Upload scanned dictionary pages")
                upload_files = gr.File(label="Upload Images", file_count="multiple", file_types=["image"])
                process_btn = gr.Button("Process Images", variant="primary")
                upload_status = gr.Textbox(label="Status", lines=3)
                process_btn.click(glossary.process_uploaded_images, upload_files, upload_status)
            
            # TAB 3: Search
            with gr.TabItem("🔍 Search Glossary"):
                gr.Markdown("### Search extracted glossary")
                with gr.Row():
                    query = gr.Textbox(label="Search Term")
                    direction = gr.Dropdown(["en->ar", "ar->en"], value="en->ar", label="Direction")
                search_btn = gr.Button("Search", variant="primary")
                search_results = gr.Textbox(label="Results", lines=20)
                search_btn.click(glossary.search, [query, direction], search_results)
            
            # TAB 4: Stats & Export
            with gr.TabItem("📊 Statistics & Export"):
                stats_btn = gr.Button("Refresh Stats", variant="primary")
                stats_output = gr.Textbox(label="Statistics", lines=5)
                stats_btn.click(glossary.get_stats, [], stats_output)
                
                gr.Markdown("### Export")
                export_btn = gr.Button("📦 Export as ZIP", variant="secondary")
                export_file = gr.File(label="Download ZIP")
                export_btn.click(glossary.export_zip, [], export_file)
            
            # TAB 5: Model Comparison (NEW)
            with gr.TabItem("⚖️ Model Comparison"):
                gr.Markdown("### Compare OCR models on the same image")
                
                with gr.Row():
                    with gr.Column():
                        compare_img = gr.Image(label="Upload Image", type="pil")
                        ground_truth = gr.Textbox(label="Ground Truth (optional, for CER/WER)", lines=2)
                        compare_btn = gr.Button("Run All Models", variant="primary")
                    with gr.Column():
                        compare_results = gr.JSON(label="Comparison Results")
                        compare_time = gr.Textbox(label="Timing Summary")
                
                def run_comparison(image, gt):
                    if image is None:
                        return {}, "No image"
                    results = ocr_engine.compare_all(image, gt)
                    timing = "\n".join([f"{k}: {v['time']:.2f}s" for k, v in results.items()])
                    return results, timing
                compare_btn.click(run_comparison, [compare_img, ground_truth], [compare_results, compare_time])
                
                gr.Markdown("### Individual Model Test")
                with gr.Row():
                    single_img = gr.Image(label="Image", type="pil")
                    model_select = gr.Dropdown(["tesseract", "trocr", "qwen2vl", "donut", "pix2struct"], value="tesseract", label="Model")
                    single_btn = gr.Button("Run Single Model", variant="secondary")
                single_result = gr.Textbox(label="Result", lines=5)
                single_conf = gr.Number(label="Confidence")
                single_time = gr.Number(label="Inference Time (s)")
                
                def run_single(image, model):
                    if image is None:
                        return "No image", 0, 0
                    result = ocr_engine.predict(image, model)
                    return result.text, result.confidence, result.inference_time
                single_btn.click(run_single, [single_img, model_select], [single_result, single_conf, single_time])
            
            # TAB 6: Fine-tuning
            with gr.TabItem("🧠 Fine-tuning"):
                gr.Markdown("### Fine-tune OCR models on your glossary data")
                
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("#### Step 1: Dependencies")
                        check_btn = gr.Button("Check Dependencies", variant="primary")
                        check_status = gr.Textbox(label="Missing Packages")
                        check_btn.click(trainer.check_dependencies, [], check_status)
                        install_btn = gr.Button("Install Dependencies", variant="secondary")
                        install_status = gr.Textbox(label="Install Status")
                        install_btn.click(trainer.install_dependencies, [], install_status)
                
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("#### Step 2: Prepare Dataset")
                        db_btn = gr.Button("From Database (Verified)", variant="primary")
                        db_status = gr.Textbox(label="Dataset Status")
                        db_btn.click(trainer.prepare_dataset_from_db, [], [gr.State(), db_status])
                        
                        train_images = gr.File(label="Training Images", file_count="multiple", file_types=["image"])
                        train_labels = gr.Textbox(label="Labels (one per line)", lines=5)
                        upload_ds_btn = gr.Button("From Upload", variant="secondary")
                        upload_ds_status = gr.Textbox(label="Dataset Status")
                        upload_ds_btn.click(trainer.prepare_dataset_from_upload, [train_images, train_labels], [gr.State(), upload_ds_status])
                
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("#### Step 3: Train")
                        model_choice = gr.Dropdown(["trocr", "qwen2vl", "donut", "pix2struct"], value="trocr", label="Model")
                        epochs = gr.Slider(1, 10, value=3, step=1, label="Epochs")
                        batch_size = gr.Slider(1, 8, value=4, step=1, label="Batch Size")
                        lr = gr.Number(value=5e-5, label="Learning Rate")
                        dataset_path_state = gr.State()
                        
                        train_btn = gr.Button("🚀 Start Training", variant="primary")
                        train_status = gr.Textbox(label="Training Status", lines=5)
                        
                        def run_training(model, epochs_val, bs, lr_val, dataset_path):
                            if not dataset_path:
                                return "Please prepare dataset first!"
                            return trainer.train_model(model, dataset_path, epochs_val, bs, lr_val)
                        train_btn.click(run_training, [model_choice, epochs, batch_size, lr, dataset_path_state], train_status)
    
    return demo


if __name__ == "__main__":
    demo = create_interface()
    demo.launch()