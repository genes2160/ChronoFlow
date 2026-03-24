import requests
import time
from app.utils import log
from config import GROQ_API_KEY, MODEL_MAP


class GroqLLM:
    def generate(self, prompt: str):
        try:
            start = time.time()

            log("llm", "📡 Groq request started")
            log("llm", f"📏 Prompt size: {len(prompt)} chars")

            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MODEL_MAP["groq"],
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=60
            )

            duration = round(time.time() - start, 2)

            log("llm", f"📥 Status code: {response.status_code}")
            log("llm", f"⏱️ Response time: {duration}s")

            if response.status_code != 200:
                log("error", f"Groq error response → {response.text}")

            response.raise_for_status()

            data = response.json()

            log("success", "Groq response received")

            return data["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout:
            log("error", "Groq timeout")
            raise

        except requests.exceptions.RequestException as e:
            log("error", f"Groq request failed → {e}")
            raise

        except Exception as e:
            log("error", f"Groq parsing failed → {e}")
            raise