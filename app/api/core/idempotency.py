# app/core/idempotency.py
import hashlib

def contact_input_hash(contact, provider: str) -> str:
    # use your normalized fields (already in Contact)
    parts = [
        provider,
        (contact.name_norm or "").strip(),
        (contact.address_norm or "").strip(),
        (contact.city_norm or "").strip(),
        (contact.state_norm or "").strip(),
    ]
    raw = "|".join(parts).lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()