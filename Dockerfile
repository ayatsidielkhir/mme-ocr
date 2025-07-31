# ---- Image de base Python ----
FROM python:3.11-slim

# ---- Installer dépendances système ----
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ---- Dossier de travail ----
WORKDIR /app

# ---- Copier et installer les dépendances Python ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Copier le code du projet ----
COPY . .

# ---- Exposer le port ----
EXPOSE 8000

# ---- Lancer FastAPI ----
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
