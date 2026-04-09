import requests
import time
from app.utils import log
from config import GOOGLE_API_KEY, MODEL_MAP


class GoogleLLM:
    def model_name(self):
        return MODEL_MAP["google"]

    def generate(self, prompt: str):
        try:
            start = time.time()

            log("llm", "📡 Google request started")
            log("llm", f"📏 Prompt size: {len(prompt)} chars")

            model = MODEL_MAP["google"]

            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": GOOGLE_API_KEY,
                },
                json={
                    "contents": [
                        {
                            "parts": [{"text": prompt}]
                        }
                    ]
                },
                timeout=60,
            )

            duration = round(time.time() - start, 2)

            log("llm", f"📥 Status code: {response.status_code}")
            log("llm", f"⏱️ Response time: {duration}s")

            if response.status_code != 200:
                log("error", f"Google error response → {response.text}")

            response.raise_for_status()

            data = response.json()

            log("success", "Google response received")

            return data["candidates"][0]["content"]["parts"][0]["text"]

        except requests.exceptions.Timeout:
            log("error", "Google timeout")
            raise

        except requests.exceptions.RequestException as e:
            log("error", f"Google request failed → {e}")
            raise

        except Exception as e:
            log("error", f"Google parsing failed → {e}")
            raise