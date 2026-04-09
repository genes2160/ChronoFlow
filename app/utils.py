from datetime import datetime

LOG_EMOJIS = {
    "scan": "🔍",
    "found": "📂",
    "skip": "⏭️",
    "move": "📦",
    "process": "⚙️",
    "success": "✅",
    "error": "❌",
    "warn": "⚠️",
    "llm": "🧠",
    "save": "💾"
}


def log(event, message):
    emoji = LOG_EMOJIS.get(event, "•")
    time = datetime.now().strftime("%H:%M:%S")
    print(f"{time} {emoji} {message}")
    
STATUS = {
    "success": "success",
    "completed": "completed",
    "failed": "failed"
}