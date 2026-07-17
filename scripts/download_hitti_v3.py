#!/usr/bin/env python3
"""
De-obfuscate Archive.org book pages and convert to PDF.
Uses the same AES-128-CTR algorithm as the BookReader JavaScript.
"""
import hashlib
import base64
import json
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ===== CONFIG =====
IDENTIFIER = "hittisnewmedical0000hitt"
ZIP_PATH = "/30/items/hittisnewmedical0000hitt/hittisnewmedical0000hitt_jp2.zip"
JP2_DIR = f"{IDENTIFIER}_jp2"
SERVER = "ia800109.us.archive.org"
SCALE = 4
TOTAL_PAGES = 696

OUTPUT_DIR = Path("/home/z/my-project/download/hitti_medical_dictionary")
PAGES_DIR = OUTPUT_DIR / "pages"
PAGES_DIR.mkdir(parents=True, exist_ok=True)

# ===== COOKIES =====
COOKIES = {
    "logged-in-sig": "1815865045%201784329045%20WWp5WT%2FjOjlNS2xgq340elvzJEg90cE8kIw3R3RJHqxE6rYnfzrshUhdLLSUuq387zOG6GbOsCwc2fvSxZZHbi1CpPWZjqM9E8PDfcjINtHw46SYIpl40vrsnKxOlcgzhhKSAt4OeoyoKvPykoMnKWWI7kiNarLfFR41n87y9NMQ1PHRabXa51kPeprTj%2Fr8dV4cq4dLDElILb8LbJW1PsPlONUrQT2Cdgwi9JaMSJvXKdW0WjjfO3JRhhNZCA7cy7flscpVX0CwojWjrwGm0fjQ7cKRJQTDGSR5G%2FdTsP3tNHJr5kNZfPnTvIGhnX7hGzh2Hd2uJzZfM89HTUXWdw%3D%3D",
    "logged-in-user": "xor984%40gmail.com",
    "loan-hittisnewmedical0000hitt": "1784329655-ccd4c55d0a9199342fce27270317ce5b",
}

session = requests.Session()
session.cookies.update(COOKIES)
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": f"https://archive.org/details/{IDENTIFIER}",
})


def deobfuscate(encrypted_data, url_path, obfuscate_header):
    """
    De-obfuscate the first 1024 bytes using AES-128-CTR.
    Mirrors the BookReader JavaScript algorithm.
    """
    version, b64_counter = obfuscate_header.split("|")
    assert version == "1", f"Unsupported obfuscation version: {version}"

    # SHA-1 of the URL path, take first 16 bytes as AES key
    sha1 = hashlib.sha1(url_path.encode('utf-8')).digest()
    aes_key = sha1[:16]

    # Counter/IV from base64
    counter = base64.b64decode(b64_counter)

    # AES-128-CTR decrypt first 1024 bytes
    cipher = Cipher(algorithms.AES(aes_key), modes.CTR(counter))
    decryptor = cipher.decryptor()
    decrypted_first = decryptor.update(encrypted_data[:1024]) + decryptor.finalize()

    # Replace first 1024 bytes with decrypted version
    result = bytearray(encrypted_data)
    result[:1024] = decrypted_first
    return bytes(result)


def download_and_deobfuscate(page_num):
    """Download a single page, de-obfuscate, and save as JPEG."""
    jp2_name = f"{IDENTIFIER}_{page_num:04d}.jp2"
    jp2_file = f"{JP2_DIR}/{jp2_name}"
    output_file = PAGES_DIR / f"page_{page_num:04d}.jpg"

    # Skip if already valid
    if output_file.exists() and output_file.stat().st_size > 10000:
        with open(output_file, 'rb') as f:
            header = f.read(3)
        if header[:2] == b'\xff\xd8':  # JPEG magic bytes
            return page_num, "skipped", output_file.stat().st_size

    url = f"https://{SERVER}/BookReader/BookReaderImages.php"
    params = {
        "zip": ZIP_PATH,
        "file": jp2_file,
        "id": IDENTIFIER,
        "scale": SCALE,
        "rotate": 0,
    }

    try:
        resp = session.get(url, params=params, timeout=60)

        if resp.status_code != 200:
            return page_num, f"http_{resp.status_code}", 0

        obfuscate_header = resp.headers.get("X-Obfuscate")
        data = resp.content

        if obfuscate_header:
            # Build URL path: remove protocol+domain, use URL-encoded path as-is
            import re
            url_path = re.sub(r'https?://[^/]+', '', resp.url)
            data = deobfuscate(data, url_path, obfuscate_header)

        # Verify it's a valid image
        if len(data) < 1000:
            return page_num, "too_small", len(data)

        with open(output_file, 'wb') as f:
            f.write(data)

        return page_num, "ok", len(data)

    except Exception as e:
        return page_num, f"error_{str(e)[:40]}", 0


def convert_to_pdf():
    """Convert JPEG pages to PDF using Pillow (more robust than img2pdf)."""
    from PIL import Image

    pages = sorted(PAGES_DIR.glob("page_*.jpg"))
    if not pages:
        print("  No pages found!")
        return False

    print(f"  Converting {len(pages)} pages to PDF...")

    # Convert all images to RGB and get sizes
    imgs = []
    for i, p in enumerate(pages):
        try:
            img = Image.open(p)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            imgs.append(img)
            if (i + 1) % 100 == 0:
                print(f"    Loaded {i+1}/{len(pages)} images...")
        except Exception as e:
            print(f"    Error loading {p.name}: {e}")

    if not imgs:
        print("  No valid images!")
        return False

    pdf_path = OUTPUT_DIR / "hitti_medical_dictionary.pdf"
    first = imgs[0]
    rest = imgs[1:]

    print(f"  Saving PDF ({len(imgs)} pages)...")
    first.save(str(pdf_path), "PDF", save_all=True, append_images=rest, resolution=300)

    size = pdf_path.stat().st_size
    print(f"  PDF created: {pdf_path} ({size/(1024*1024):.1f} MB)")
    return True


def main():
    print("=" * 60)
    print("Hitti's Medical Dictionary - De-obfuscated Downloader")
    print(f"Pages: {TOTAL_PAGES}, Scale: {SCALE}")
    print(f"Output: {PAGES_DIR}")
    print("=" * 60)

    # Clean up old (corrupted) files
    old_count = 0
    for f in PAGES_DIR.glob("page_*.jpg"):
        with open(f, 'rb') as fh:
            if fh.read(2) != b'\xff\xd8':
                f.unlink()
                old_count += 1
    if old_count:
        print(f"Cleaned {old_count} corrupted files")

    # Check valid files
    valid = sum(1 for f in PAGES_DIR.glob("page_*.jpg")
                if f.stat().st_size > 10000)
    print(f"Valid pages already downloaded: {valid}/{TOTAL_PAGES}")

    if valid < TOTAL_PAGES:
        start_time = time.time()
        downloaded = 0
        errors = 0
        workers = 8

        print(f"\nDownloading with {workers} workers...")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for page in range(1, TOTAL_PAGES + 1):
                f = PAGES_DIR / f"page_{page:04d}.jpg"
                if f.exists() and f.stat().st_size > 10000:
                    with open(f, 'rb') as fh:
                        if fh.read(2) == b'\xff\xd8':
                            continue
                future = executor.submit(download_and_deobfuscate, page)
                futures[future] = page

            for future in as_completed(futures):
                page_num, status, size = future.result()
                if status == "ok":
                    downloaded += 1
                elif status != "skipped":
                    errors += 1

                total_done = downloaded + errors + valid
                if total_done % 20 == 0:
                    elapsed = time.time() - start_time
                    rate = (downloaded + errors) / elapsed if elapsed > 0 else 0
                    eta = (TOTAL_PAGES - total_done - valid) / rate if rate > 0 else 0
                    print(f"  Page {page_num}: {status:15s} | "
                          f"Done: {total_done + valid}/{TOTAL_PAGES} | "
                          f"New OK: {downloaded} Err: {errors} | "
                          f"ETA: {eta/60:.0f}m")

        elapsed = time.time() - start_time
        print(f"\nDownload: {downloaded} new, {errors} errors, {elapsed/60:.1f} min")

    # Final count
    final_pages = sorted(PAGES_DIR.glob("page_*.jpg"))
    valid_final = 0
    total_size = 0
    for p in final_pages:
        sz = p.stat().st_size
        total_size += sz
        if sz > 10000:
            valid_final += 1

    print(f"\nFinal: {valid_final} valid pages, {total_size/(1024*1024):.1f} MB")

    # Convert to PDF
    if valid_final > 10:
        print("\n" + "=" * 60)
        print("CONVERTING TO PDF...")
        print("=" * 60)
        convert_to_pdf()


if __name__ == "__main__":
    main()