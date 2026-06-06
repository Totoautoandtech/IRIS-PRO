"""
utils/shared.py
Fonctions partagées entre tous les bots : formatage, safe_send, Pollinations IA.
"""
import asyncio
import aiohttp

# ── Headers navigateur (évite les 403) ───────────────────
BROWSER_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
    "Cache-Control":   "max-age=0",
}

# ── Envoi de longs messages ───────────────────────────────
async def safe_send(destination, text: str):
    if not text:
        return
    for i in range(0, len(text), 1900):
        await destination.send(text[i:i + 1900])

# ── Pollinations.ai — IA gratuite sans clé ───────────────
async def pollinations_chat(system: str, user: str, seed: int = 42) -> str:
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "model":   "openai",
        "seed":    seed,
        "private": True,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://text.pollinations.ai/openai",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=35),
            headers={"Content-Type": "application/json"},
        ) as resp:
            if resp.status != 200:
                raise Exception(f"Pollinations HTTP {resp.status}")
            data = await resp.json(content_type=None)
    return data["choices"][0]["message"]["content"]
