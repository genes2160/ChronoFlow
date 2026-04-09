import requests
import time
from app.utils import log
from config import ANTHROPIC_API_KEY, MODEL_MAP


class AnthropicLLM:
    def model_name(self):
        return MODEL_MAP["anthropic"]
    
    def generate(self, prompt: str):
        try:
            start = time.time()

            log("llm", "📡 Anthropic request started")
            log("llm", f"📏 Prompt size: {len(prompt)} chars")

            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": MODEL_MAP["anthropic"],
                    "max_tokens": 2000,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=60
            )

            duration = round(time.time() - start, 2)

            log("llm", f"📥 Status code: {response.status_code}")
            log("llm", f"⏱️ Response time: {duration}s")

            response.raise_for_status()

            data = response.json()

            log("success", "Anthropic response received")

            return data["content"][0]["text"]

        except requests.exceptions.Timeout:
            log("error", "Anthropic timeout")
            raise

        except requests.exceptions.RequestException as e:
            log("error", f"Anthropic request failed → {e}")
            raise

        except Exception as e:
            log("error", f"Anthropic parsing failed → {e}")
            raise