import requests
import time
from app.utils import log
from config import JINA_API_KEY, MODEL_MAP


class JinaLLM:
    def generate(self, prompt: str):
        try:
            start = time.time()

            log("llm", "📡 Jina request started")
            log("llm", f"📏 Prompt size: {len(prompt)} chars")

            response = requests.post(
                "https://api.jina.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {JINA_API_KEY}"
                },
                json={
                    "model": MODEL_MAP["jina"],
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )

            duration = round(time.time() - start, 2)

            log("llm", f"📥 Status code: {response.status_code}")
            log("llm", f"⏱️ Response time: {duration}s")

            response.raise_for_status()

            data = response.json()

            log("success", "Jina response received")

            return data["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout:
            log("error", "Jina timeout")
            raise

        except requests.exceptions.RequestException as e:
            log("error", f"Jina request failed → {e}")
            raise

        except Exception as e:
            log("error", f"Jina parsing failed → {e}")
            raise