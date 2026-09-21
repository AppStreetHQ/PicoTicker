"""The mutable watchlist itself — seeded once from config.TICKERS on a
fresh device, then persisted here and edited from the web UI (add,
remove, and via scroll_selection.py, which symbols cycle in ticker
mode) from then on. config.TICKERS itself is never touched again."""

import json

TICKERS_FILE = "tickers.json"


def _normalize_seed(seed):
    """config.TICKERS as either a Python list of symbols (the original
    format) or one plain string of symbols separated by spaces and/or
    commas — much less fiddly to paste a long watchlist into than
    getting the quotes and commas of a 50-element list literal right.
    Also dedupes and uppercases, so either format tolerates a stray
    duplicate or lowercase entry."""
    if isinstance(seed, str):
        seed = seed.replace(",", " ").split()
    seen = []
    for symbol in seed:
        symbol = symbol.strip().upper()
        if symbol and symbol not in seen:
            seen.append(symbol)
    return seen


def load(default):
    try:
        with open(TICKERS_FILE) as f:
            return sorted(json.load(f))
    except Exception:
        tickers = sorted(_normalize_seed(default))
        save(tickers)
        return tickers


def save(tickers):
    with open(TICKERS_FILE, "w") as f:
        json.dump(tickers, f)
