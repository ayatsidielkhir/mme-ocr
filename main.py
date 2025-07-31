from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import shutil
import os
from pdf2image import convert_from_path
import re
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# === Utility functions ===
def preprocess_image(img: Image.Image) -> Image.Image:
    """Convert to grayscale and enhance for better OCR speed/accuracy."""
    img = img.convert("L")  # grayscale
    img = ImageEnhance.Contrast(img).enhance(1.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img

def extract_latest_date(text: str):
    matches = re.findall(r'(\d{2}[./-]\d{2}[./-]\d{2,4})', text)
    parsed_dates = []
    for date_str in matches:
        for sep in ['/', '.', '-']:
            if sep in date_str:
                try:
                    parts = date_str.split(sep)
                    if len(parts[2]) == 2:
                        year = int(parts[2])
                        parts[2] = str(2000 + year) if year < 50 else str(1900 + year)
                    normalized = f"{parts[0]}.{parts[1]}.{parts[2]}"
                    date_obj = datetime.strptime(normalized, "%d.%m.%Y")
                    if 2000 <= date_obj.year <= 2100:
                        parsed_dates.append(date_obj)
                except:
                    continue
    if parsed_dates:
        return max(parsed_dates).strftime("%d.%m.%Y")
    return None

# === CIN extraction ===
def extract_cin_info(text: str):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    full_text = " ".join(lines)

    cin = re.search(r'\b([A-Z]{1,2}\s?\d{5,8})\b', full_text)
    cin_value = cin.group(1).replace(" ", "") if cin else None

    date_naissance = re.search(r'N[ée]{1,2}[^0-9]{0,10}(\d{2}[./-]\d{2}[./-]\d{4})', full_text, re.IGNORECASE)
    date_exp = re.search(r'Valable[^\d]{0,15}(\d{2}[./-]\d{2}[./-]\d{4})', full_text, re.IGNORECASE)

    # Nom et prénom depuis MRZ ou majuscules
    nom, prenom = "", ""
    mrz_line = next((l for l in lines if '<<' in l), None)
    if mrz_line:
        match = re.match(r'^([A-Z]+)<<([A-Z]+)', mrz_line)
        if match:
            nom, prenom = match.group(1), match.group(2)

    if not nom or not prenom:
        majuscules = [l for l in lines if re.fullmatch(r"[A-ZÉÈÀÂÛÎÔÊ\-\s]{3,30}", l)]
        if len(majuscules) >= 2:
            nom = majuscules[-1]
            prenom = majuscules[0]

    return {
        "document": "CIN",
        "cin": cin_value,
        "date_naissance": date_naissance.group(1) if date_naissance else None,
        "date_expiration": date_exp.group(1) if date_exp else None,
        "nom": nom,
        "prenom": prenom
    }

# === Permis / Visa extraction ===
def extract_permis_or_visa_info(text: str):
    latest_date = extract_latest_date(text)
    return {
        "document": "permis",
        "date_expiration": latest_date
    }

# === Carte Grise extraction ===
def extract_carte_grise_info(text: str):
    date_exp = re.search(r'Fin de validité\s*:?[\s\n]*(\d{2}[./-]\d{2}[./-]\d{4})', text, re.IGNORECASE)
    return {
        "document": "carte_grise",
        "date_expiration": date_exp.group(1) if date_exp else extract_latest_date(text)
    }

# === Endpoint OCR ===
@app.post("/api/ocr")
async def ocr_endpoint(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # Convert PDF → image (only first page)
        if file.filename.lower().endswith(".pdf"):
            images = convert_from_path(file_path, dpi=200, first_page=1, last_page=1)
        else:
            images = [Image.open(file_path)]

        full_text = ""
        for img in images:
            img = preprocess_image(img)
            full_text += pytesseract.image_to_string(img, lang="fra+ara") + "\n"

        # Detect document type
        text_upper = full_text.upper()
        if "CARTE NATIONALE D'IDENTITE" in text_upper:
            data = extract_cin_info(full_text)
        elif "CERTIFICAT D'IMMATRICULATION" in text_upper:
            data = extract_carte_grise_info(full_text)
        else:
            data = extract_permis_or_visa_info(full_text)

        return JSONResponse(content={"text_ocr": full_text, "extracted": data})

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
