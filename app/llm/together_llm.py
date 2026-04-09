import requests
import time
from app.utils import log
from config import TOGETHER_API_KEY, MODEL_MAP


class TogetherLLM:
    def model_name(self):
        return MODEL_MAP["together"]

    def generate(self, prompt: str):
        try:
            start = time.time()

            log("llm", "📡 Together request started")
            log("llm", f"📏 Prompt size: {len(prompt)} chars")

            response = requests.post(
                "https://api.together.xyz/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {TOGETHER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL_MAP["together"],
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                },
                timeout=60,
            )

            duration = round(time.time() - start, 2)

            log("llm", f"📥 Status code: {response.status_code}")
            log("llm", f"⏱️ Response time: {duration}s")

            if response.status_code != 200:
                log("error", f"Together error response → {response.text}")

            response.raise_for_status()

            data = response.json()

            log("success", "Together response received")

            return data["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout:
            log("error", "Together timeout")
            raise

        except requests.exceptions.RequestException as e:
            log("error", f"Together request failed → {e}")
            raise

        except Exception as e:
            log("error", f"Together parsing failed → {e}")
            raise