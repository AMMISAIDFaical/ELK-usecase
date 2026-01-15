FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download VADER lexicon needed by NLTK/VADER
RUN python -c "import nltk; nltk.download('vader_lexicon')"

COPY app.py .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host=0.0.0.0", "--port=8000"]
