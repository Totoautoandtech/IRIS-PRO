"""
utils/user_settings.py
Sauvegarde persistante des paramètres par utilisateur (JSON local).
"""
import json
import os
import logging
from datetime import datetime, timezone

logger  = logging.getLogger("UserSettings")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")

DEFAULT_SETTINGS = {
    "watchlist":       ["^FCHI", "^GSPC", "BTC-USD", "AAPL"],
    "currency":        "EUR",
    "alerts_enabled":  True,
    "alert_threshold": 3.0,
    "portfolio":       [],
    "custom_alerts":   [],
    "created_at":      None,
}


class UserSettings:
    def __init__(self):
        self._data: dict = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(DB_PATH):
                with open(DB_PATH, "r", encoding="utf-8") as f:
                    raw        = json.load(f)
                    self._data = {int(k): v for k, v in raw.items()}
        except Exception as e:
            logger.error(f"Erreur chargement: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            with open(DB_PATH, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erreur sauvegarde: {e}")

    def get(self, user_id: int) -> dict:
        uid = int(user_id)
        if uid not in self._data:
            self._data[uid] = {
                **DEFAULT_SETTINGS,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save()
        return {**DEFAULT_SETTINGS, **self._data[uid]}

    def update(self, user_id: int, changes: dict):
        uid = int(user_id)
        self._data[uid] = {**self.get(uid), **changes}
        self._save()

    def add_to_watchlist(self, user_id: int, symbol: str):
        s = self.get(user_id)
        if symbol not in s["watchlist"]:
            s["watchlist"].append(symbol)
            self.update(user_id, {"watchlist": s["watchlist"]})

    def remove_from_watchlist(self, user_id: int, symbol: str):
        s = self.get(user_id)
        self.update(user_id, {"watchlist": [x for x in s["watchlist"] if x != symbol]})

    def add_position(self, user_id: int, symbol: str, qty: float, buy_price=None):
        s         = self.get(user_id)
        portfolio = [p for p in s["portfolio"] if p["symbol"] != symbol]
        portfolio.append({
            "symbol":    symbol,
            "qty":       qty,
            "buy_price": buy_price,
            "added_at":  datetime.now(timezone.utc).isoformat(),
        })
        self.update(user_id, {"portfolio": portfolio})

    def remove_position(self, user_id: int, symbol: str):
        s = self.get(user_id)
        self.update(user_id, {"portfolio": [p for p in s["portfolio"] if p["symbol"] != symbol]})

    def add_custom_alert(self, user_id: int, symbol: str, threshold: float):
        s      = self.get(user_id)
        alerts = [a for a in s["custom_alerts"] if a["symbol"] != symbol]
        alerts.append({"symbol": symbol, "threshold": threshold})
        self.update(user_id, {"custom_alerts": alerts})

    def reset(self, user_id: int):
        self._data[int(user_id)] = {
            **DEFAULT_SETTINGS,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def get_all(self):
        return list(self._data.items())
