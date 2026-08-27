FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# tesseract-ocr backs the default prescription OCR provider (see
# apps.prescriptions.services.ocr.tesseract, PRESCRIPTION_OCR_PROVIDER) - self-hosted, so no
# external account is needed for OCR intake to work at all. French/Arabic language data cover
# the scripts real Lebanese prescriptions are written in (English-only data silently produced
# garbage on those). poppler-utils backs pdf2image for PDF prescription uploads (both the
# Tesseract and EasyOCR providers render PDF pages through it). libgl1/libglib2.0-0 satisfy
# opencv (an EasyOCR dependency), which this slim base image otherwise lacks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara poppler-utils libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# torch and torchvision (EasyOCR dependencies, PRESCRIPTION_OCR_PROVIDER=easyocr) install from
# PyPI by default with a bundled CUDA toolkit meant for GPU inference - several GB nobody asked
# for, since apps.prescriptions.services.ocr.easyocr_provider always runs with gpu=False.
# Installing both together from PyTorch's own CPU index first means the later `pip install -r
# requirements.txt` finds them already satisfied and never reaches for the CUDA variant.
# Installing torch alone here and letting easyocr pull in torchvision separately (from PyPI's
# default index) was tried and breaks: PyPI's torchvision build doesn't match this exact torch
# build, and easyocr fails to import with "operator torchvision::nms does not exist" - a
# classic torch/torchvision ABI mismatch. Both must come from the same index together.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No DB connection is made here - collectstatic only touches STATIC_ROOT. USE_S3 defaults
# to false at build time so this always writes to local disk regardless of runtime config.
RUN DJANGO_SECRET_KEY=build-time-only python manage.py collectstatic --noinput

EXPOSE 8080

RUN chmod +x docker-entrypoint.sh
ENTRYPOINT ["./docker-entrypoint.sh"]
