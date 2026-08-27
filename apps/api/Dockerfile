FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# tesseract-ocr backs the default prescription OCR provider (see
# apps.prescriptions.services.ocr.tesseract, PRESCRIPTION_OCR_PROVIDER) - self-hosted, so no
# external account is needed for OCR intake to work at all. French/Arabic language data cover
# the scripts real Lebanese prescriptions are written in (English-only data silently produced
# garbage on those). poppler-utils backs pdf2image for PDF prescription uploads (every provider
# that renders PDF pages goes through it).
#
# EasyOCR is deliberately NOT in this image. It needs torch + torchvision + opencv, which add
# several GB to an image that pulls on every task start, for a provider that is off unless
# PRESCRIPTION_OCR_PROVIDER=easyocr. To build a variant that includes it, add
# `libgl1 libglib2.0-0` below and, after the pip install:
#   RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
#   RUN pip install --no-cache-dir -r requirements-easyocr.txt
# Both torch lines matter: see requirements-easyocr.txt for why they must run together.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No DB connection is made here - collectstatic only touches STATIC_ROOT. USE_S3 defaults
# to false at build time so this always writes to local disk regardless of runtime config.
RUN DJANGO_SECRET_KEY=build-time-only python manage.py collectstatic --noinput

EXPOSE 8080

RUN chmod +x docker-entrypoint.sh
ENTRYPOINT ["./docker-entrypoint.sh"]
