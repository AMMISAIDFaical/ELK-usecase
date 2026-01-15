#This uses VADER, which is a rule-based sentiment model (no training) provided in NLTK.

from fastapi import FastAPI
from pydantic import BaseModel
from nltk.sentiment.vader import SentimentIntensityAnalyzer

app = FastAPI()
analyzer = SentimentIntensityAnalyzer()

class Req(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/predict")
def predict(req: Req):
    text = (req.text or "").strip()
    scores = analyzer.polarity_scores(text)
    c = scores["compound"]
    label = "positive" if c >= 0.05 else "negative" if c <= -0.05 else "neutral"
    return {"label": label, "compound": c, "scores": scores}
