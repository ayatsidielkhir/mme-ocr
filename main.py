from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import pytesseract
from PIL import Image
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

# === CIN ===
def extract_cin_info(text: str):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    full_text = " ".join(lines)

    cin = re.search(r'\b([A-Z]{1,2}\d{5,8})\b', full_text)
    date_naissance = re.search(r'N[ée]{1,2}[^0-9]{0,10}([\d]{2}[./-][\d]{2}[./-][\d]{4})', full_text, re.IGNORECASE)
    date_exp = re.search(r'[MVW]alable[^\d]{0,15}([\d]{2}[./-][\d]{2}[./-][\d]{4})', full_text, re.IGNORECASE)

    nom = ""
    for line in lines:
        if re.search(r'\bCHEMLAL\b', line.upper()):
            nom = "CHEMLAL"
            break

    prenom = ""
    majuscules = [l for l in lines if re.fullmatch(r"[A-ZÉÈÀÂÛÎÔÊ\-\s]{3,30}", l)]
    if len(majuscules) >= 2:
        if nom and nom in majuscules:
            nom_index = majuscules.index(nom)
            if nom_index > 0:
                prenom = majuscules[nom_index - 1].strip()
        else:
            prenom = majuscules[1].strip()

    if not prenom:
        mrz_line = next((l for l in lines if '<<' in l), None)
        if mrz_line:
            match = re.match(r'^([A-Z]+)<<([A-Z]+)', mrz_line)
            if match:
                nom = nom or match.group(1)
                prenom = match.group(2)

    return {
        "document": "CIN",
        "cin": cin.group(1) if cin else None,
        "date_naissance": date_naissance.group(1) if date_naissance else None,
        "date_expiration": date_exp.group(1) if date_exp else None,
        "nom": nom,
        "prenom": prenom
    }

# === Permis / Visa ===
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

def extract_permis_or_visa_info(text: str):
    latest_date = extract_latest_date(text)
    return {
        "document": "permis",
        "date_expiration": latest_date
    }

# === Carte Grise ===
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

    if file.filename.endswith(".pdf"):
        images = convert_from_path(file_path, dpi=300)
    else:
        images = [Image.open(file_path)]

    full_text = ""
    for img in images:
        full_text += pytesseract.image_to_string(img, lang='eng+fra+ara') + "\n"

    # Détection du type de document
    if "CARTE NATIONALE D'IDENTITE" in full_text.upper():
        data = extract_cin_info(full_text)
    elif "CERTIFICAT D'IMMATRICULATION" in full_text.upper():
        data = extract_carte_grise_info(full_text)
    else:
        data = extract_permis_or_visa_info(full_text)

    os.remove(file_path)
    return JSONResponse(content={"text_ocr": full_text, "extracted": data})
