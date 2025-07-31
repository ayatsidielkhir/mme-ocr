FROM python:3.11-slim

# Installer Tesseract + toutes les langues + utilitaires nécessaires
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-ara \
    poppler-utils \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Créer dossier app
WORKDIR /app

# Copier les fichiers du projet
COPY . /app

# Installer dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Exposer le port pour FastAPI
EXPOSE 8000

# Lancer l'application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
