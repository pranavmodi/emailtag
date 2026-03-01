FROM python:3.11-slim

WORKDIR /app/

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies needed for:
# - gcc: compiling Python C extensions
# - tesseract-ocr: OCR processing (pytesseract)
# - poppler-utils: PDF to image conversion (pdf2image)
# - libzbar0: barcode/QR code reading (pyzbar)
# - libgl1-mesa-glue, libglib2.0-0: OpenCV runtime deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc \
       tesseract-ocr \
       poppler-utils \
       libzbar0 \
       libgl1 \
       libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install system curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create non-root user for security
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8444

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8444/health || exit 1

# Run the application (port 8444 matches existing deployment)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8444"]
