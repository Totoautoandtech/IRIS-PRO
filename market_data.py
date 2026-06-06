"""
utils/market_data.py
Récupération des données boursières via Yahoo Finance.
Cache 20s, requêtes parallèles, headers anti-blocage.
"""
import asyncio
import aiohttp
import time
import logging

logger = logging.getLogger("MarketData")

YF_CHART   = "https://query1.finance.yahoo.com/v8/finance/chart"
YF_SUMMARY = "https://query1.finance.yahoo.com/v10/finance/quoteSummary"

YF_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

CACHE_TTL       = 20
PRELOAD_SYMBOLS = ["^FCHI", "^GSPC", "^IXIC", "BTC-USD", "ETH-USD", "AAPL", "MSFT", "NVDA", "TSLA", "^DJI"]


class MarketData:
    def __init__(self):
        self._cache:   dict = {}
        self._session: aiohttp.ClientSession | None = None
        self._running  = False

    def start(self):
        self._running = True
        asyncio.create_task(self._preload_loop())
        logger.info("📊 MarketData démarré (cache 20s, requêtes parallèles)")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector     = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(headers=YF_HEADERS, connector=connector)
        return self._session

    async def _preload_loop(self):
        """Précharge les symboles populaires en parallèle par batch de 5."""
        while self._running:
            for i in range(0, len(PRELOAD_SYMBOLS), 5):
                batch = PRELOAD_SYMBOLS[i:i + 5]
                await asyncio.gather(
                    *[self.get_quote(s, force=True) for s in batch],
                    return_exceptions=True
                )
                await asyncio.sleep(1)
            await asyncio.sleep(20)

    async def get_quote(self, symbol: str, force: bool = False) -> dict | None:
        key    = symbol.upper()
        cached = self._cache.get(key)
        if not force and cached and time.time() - cached["ts"] < CACHE_TTL:
            return cached["data"]
        try:
            session = await self._get_session()
            url     = f"{YF_CHART}/{key}?interval=1d&range=1d"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return cached["data"] if cached else None
                raw = await resp.json(content_type=None)

            result = (raw.get("chart") or {}).get("result") or []
            if not result:
                return None

            meta  = result[0]["meta"]
            prev  = (meta.get("previousClose")
                     or meta.get("chartPreviousClose")
                     or meta.get("regularMarketPrice"))
            price = meta.get("regularMarketPrice", 0)
            chg   = price - prev if prev else 0
            chgp  = (chg / prev * 100) if prev else 0

            data = {
                "symbol":        meta.get("symbol", key),
                "name":          meta.get("longName") or meta.get("shortName") or key,
                "price":         price,
                "previousClose": prev,
                "change":        chg,
                "changePercent": chgp,
                "volume":        meta.get("regularMarketVolume", 0),
                "currency":      meta.get("currency", ""),
                "marketState":   meta.get("marketState", "UNKNOWN"),
                "open":          meta.get("regularMarketOpen"),
                "dayHigh":       meta.get("regularMarketDayHigh"),
                "dayLow":        meta.get("regularMarketDayLow"),
            }
            self._cache[key] = {"data": data, "ts": time.time()}
            return data

        except Exception as e:
            logger.error(f"get_quote {symbol}: {e}")
            return cached["data"] if cached else None

    async def get_detailed_quote(self, symbol: str) -> dict | None:
        base = await self.get_quote(symbol)
        if not base:
            return None
        try:
            session = await self._get_session()
            url     = f"{YF_SUMMARY}/{symbol}?modules=summaryDetail,price"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return base
                raw = await resp.json(content_type=None)

            result_list = ((raw.get("quoteSummary") or {}).get("result")) or []
            if not result_list:
                return base

            detail  = result_list[0]
            price   = detail.get("price", {})
            summary = detail.get("summaryDetail", {})
            return {
                **base,
                "marketCap": (price.get("marketCap") or {}).get("raw"),
                "high52w":   (summary.get("fiftyTwoWeekHigh") or {}).get("raw"),
                "low52w":    (summary.get("fiftyTwoWeekLow") or {}).get("raw"),
                "pe":        (summary.get("trailingPE") or {}).get("raw"),
            }
        except Exception:
            return base

    async def get_multiple(self, symbols: list) -> list:
        if not symbols:
            return []
        results = await asyncio.gather(
            *[self.get_quote(s) for s in symbols],
            return_exceptions=True
        )
        return [r for r in results if r and not isinstance(r, Exception)]

    async def is_valid(self, symbol: str) -> bool:
        q = await self.get_quote(symbol, force=True)
        return q is not None and q.get("price", 0) > 0


# ── Fonctions de formatage ────────────────────────────────
def format_price(price) -> str:
    if price is None:
        return "N/A"
    return f"{price:,.2f}".replace(",", " ").replace(".", ",")

def format_change(value) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}"

def get_emoji(change_pct) -> str:
    if change_pct is None: return "⚪"
    if change_pct >= 3:    return "🚀"
    if change_pct >= 1:    return "📈"
    if change_pct > 0:     return "🟢"
    if change_pct == 0:    return "⚪"
    if change_pct > -1:    return "🔴"
    if change_pct > -3:    return "📉"
    return "💥"

def market_state_label(state: str) -> str:
    return {
        "REGULAR": "🟢 Ouvert",
        "PRE":     "🟡 Pré-marché",
        "POST":    "🟠 Post-marché",
        "CLOSED":  "🔴 Fermé",
    }.get(state, "⚪ Inconnu")

def format_quote_line(q: dict) -> str:
    emoji = get_emoji(q.get("changePercent", 0))
    price = format_price(q.get("price"))
    chg   = format_change(q.get("changePercent", 0))
    sign  = "+" if q.get("changePercent", 0) >= 0 else ""
    name  = q.get("name", q["symbol"])
    if len(name) > 22:
        name = q["symbol"]
    cur   = q.get("currency", "")
    vol   = q.get("volume", 0)
    vol_s = (f"{vol/1_000_000:.1f}M" if vol >= 1_000_000
             else f"{vol/1_000:.0f}K" if vol >= 1000
             else str(vol))
    return (
        f"{emoji} **{q['symbol']}** · `{price} {cur}` · `{sign}{chg}%`\n"
        f"┗ Vol: `{vol_s}` · _{name}_"
    )
