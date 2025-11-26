#!/usr/bin/env python3
# label_batch_generator.py

from typing import List
import os
import io
import textwrap
import shutil

import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from barcode.codex import Code128   # ✅ correct import for Code128
from barcode.writer import ImageWriter


# root folder for labels
LABEL_ROOT = "labels"
CURRENT_RUN_DIR = os.path.join(LABEL_ROOT, "current_run")


def prepare_label_folder() -> str:
    """
    Delete previous labels and create a fresh folder for the current run.
    Returns the folder path.
    """
    if os.path.exists(CURRENT_RUN_DIR):
        shutil.rmtree(CURRENT_RUN_DIR)
    os.makedirs(CURRENT_RUN_DIR, exist_ok=True)
    return CURRENT_RUN_DIR


def _generate_barcode_image(data: str, dpi: int = 300) -> Image.Image:
    """
    Create a Code128 barcode image for the given data (e.g. SKU).
    Returns a PIL Image.
    """
    code = Code128(data, writer=ImageWriter())
    buffer = io.BytesIO()
    code.write(buffer, options={"dpi": dpi})
    buffer.seek(0)
    img = Image.open(buffer).convert("RGB")
    return img


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """
    Try to load a TTF font; fall back to a known Pillow-bundled font
    before using the tiny default bitmap font.

    This makes it work both locally (Arial available) and on Streamlit Cloud
    (DejaVuSans available).
    """
    # Try common Arial names (local dev on Windows/macOS)
    for name in ["Arial.ttf", "arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue

    # Try DejaVuSans, which is usually bundled with Pillow (works on cloud)
    for name in ["DejaVuSans.ttf", "DejaVuSans-Regular.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue

    # Last resort – small bitmap font
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    """
    Helper for Pillow >= 10 where textsize is removed.
    Uses textbbox to compute width and height.
    """
    if not text:
        return 0, 0
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    return w, h


def _get_font_bold(size: int) -> ImageFont.FreeTypeFont:
    """
    Try to load a bold TTF font; fall back to regular if not available.
    Works both locally and on Streamlit Cloud.
    """
    # Try common Arial bold names
    for name in ["Arial Bold.ttf", "Arial-Bold.ttf", "arialbd.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue

    # Try DejaVuSans Bold variants (bundled with Pillow)
    for name in ["DejaVuSans-Bold.ttf", "DejaVuSans-BoldOblique.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue

    # Fallback to regular font
    return _get_font(size)


def create_label_image(
    row: pd.Series,
    idx: str,
    label_inches: float = 4.0,
    dpi: int = 300,
    out_dir: str = CURRENT_RUN_DIR,
) -> str:
    """
    Create a 4x4 inch label image:

    - Top: Product name (smaller than flavour, wrapped, centered)
    - Middle: Flavour (BOLD, biggest)
    - Under flavour: Strength (BOLD, big)
    - Under strength: Case size (e.g. 'Case: 60')
    - Bottom: Narrow rectangular barcode of SKU
    """
    # dimensions in pixels (4x4 inches by default)
    width_px = int(label_inches * dpi)
    height_px = int(label_inches * dpi)

    img = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(img)

    padding = int(0.05 * height_px)  # 5% padding

    # --- Text values ---
    sku = str(row.get("Sku", "") or "")
    product = str(row.get("Product", "") or "")
    flavour = str(row.get("Flavour", "") or "")
    strength = str(row.get("Strength", "") or "")

    # Case size as nice string
    case_raw = row.get("Case_Size", "")
    case_text = ""
    if pd.notna(case_raw) and str(case_raw).strip() != "":
        try:
            case_int = int(float(case_raw))
            case_text = f"Case Size: {case_int}"
        except Exception:
            case_text = f"Case size: {case_raw}"

    # --- Fonts ---
    font_product = _get_font(50)          # product – medium
    font_flavour = _get_font_bold(80)     # flavour – BIG & bold
    font_strength = _get_font_bold(50)    # strength – slightly smaller but still big & bold
    font_case = _get_font_bold(50)        # case size – a bit smaller than strength

    # --- Layout zones ---
    top_area_height = int(height_px * 0.30)      # top 30% for product
    middle_area_height = int(height_px * 0.30)   # next 30% for flavour + strength + case
    # bottom area is for barcode

    # --- 1) Product (top, centered, wrapped) ---
    max_text_width = width_px - 2 * padding
    wrapper = textwrap.TextWrapper(width=32)
    product_lines = wrapper.wrap(product) if product else []
    y = padding

    for line in product_lines:
        w, h = _text_size(draw, line, font_product)
        if w > max_text_width:
            # fallback shrink a bit if extremely long
            f = _get_font(30)
            w, h = _text_size(draw, line, f)
        else:
            f = font_product
        x = (width_px - w) // 2
        draw.text((x, y), line, font=f, fill="black")
        y += h + 4
        if y > top_area_height - h:
            break  # don't overflow product area

    # --- 2) Flavour (center, bold, biggest) ---
    centre_mid = top_area_height + middle_area_height // 2
    used_flavour_height = 0
    flavour_y = centre_mid

    if flavour:
        w_f, h_f = _text_size(draw, flavour, font_flavour)
        x_f = (width_px - w_f) // 2
        flavour_y = centre_mid - int(h_f * 0.8)  # a bit above centre
        draw.text((x_f, flavour_y), flavour, font=font_flavour, fill="black")
        used_flavour_height = h_f
    else:
        used_flavour_height = 0

    # --- 3) Strength (just under flavour, bold) ---
    strength_drawn = False
    strength_bottom_y = None

    if strength:
        w_s, h_s = _text_size(draw, strength, font_strength)
        x_s = (width_px - w_s) // 2
        if flavour:
            y_s = flavour_y + used_flavour_height + 30  # extra spacing between flavour and mg
        else:
            y_s = centre_mid - h_s // 2
        draw.text((x_s, y_s), strength, font=font_strength, fill="black")
        strength_drawn = True
        strength_bottom_y = y_s + h_s

    # --- 4) Case size (under strength, or under flavour if no strength) ---
    if case_text:
        w_c, h_c = _text_size(draw, case_text, font_case)
        x_c = (width_px - w_c) // 2

        if strength_drawn and strength_bottom_y is not None:
            y_c = strength_bottom_y + 20  # space under strength
        elif flavour:
            y_c = flavour_y + used_flavour_height + 20
        else:
            # fallback: center in middle area
            y_c = centre_mid - h_c // 2

        draw.text((x_c, y_c), case_text, font=font_case, fill="black")

    # --- 5) Barcode (bottom, narrower) ---
    if sku:
        barcode_img = _generate_barcode_image(sku, dpi=dpi)

        # Use ~55–60% of label width, and reduce height
        target_width = int(width_px * 0.55)
        w_b, h_b = barcode_img.size
        scale = target_width / float(w_b)
        new_w = int(w_b * scale)
        new_h = int(h_b * scale * 0.6)  # make it shorter

        barcode_resized = barcode_img.resize((new_w, new_h), Image.LANCZOS)

        # Position at bottom centre
        x_barcode = (width_px - new_w) // 2
        y_barcode = height_px - new_h - padding
        img.paste(barcode_resized, (x_barcode, y_barcode))

    # --- Save image ---
    os.makedirs(out_dir, exist_ok=True)
    # filename as simple sequential number: 1.png, 2.png, ...
    filename = f"{idx}.png"
    out_path = os.path.join(out_dir, filename)
    img.save(out_path)

    return out_path


def generate_labels_from_table(final_df: pd.DataFrame, label_dir: str = CURRENT_RUN_DIR) -> List[str]:
    """
    For each row in final_df, generate Final_Labels images using create_label_image.
    Expects final_df to have:
      - Sku, Product, Flavour, Strength, Case_Size, Final_Labels

    label_dir: folder where PNGs will be stored.

    Returns list of file paths.
    """
    paths: List[str] = []
    counter = 1  # for filenames 1.png, 2.png, ...

    for _, row in final_df.iterrows():
        n = int(row.get("Final_Labels", 0) or 0)
        if n <= 0:
            continue

        for _ in range(n):
            idx = str(counter)  # filename index
            path = create_label_image(
                row=row,
                idx=idx,
                label_inches=4.0,  # 4x4 inch label
                dpi=300,
                out_dir=label_dir,
            )
            paths.append(path)
            counter += 1

    return paths