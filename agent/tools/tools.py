# tools.py
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from langchain.tools import tool
from data.db import SessionLocal
from api.portfolio_actions import list_positions as _list, buy_stock as _buy, sell_stock as _sell

def _position_to_dict(p) -> Dict[str, Any]:
    return {} if p is None else {
        "ticker": getattr(p, "ticker", None),
        "qty": getattr(p, "qty", None),
        "exec_price": getattr(p, "exec_price", None),
        "current_price": getattr(p, "current_price", None),
    }

@tool("show_portfolio")
def show_portfolio_tool() -> List[Dict[str, Any]]:
    """Return current portfolio as a JSON array."""
    db = SessionLocal()
    try:
        return [_position_to_dict(p) for p in _list(db)]
    finally:
        db.close()

class BuyArgs(BaseModel):
    ticker: str = Field(..., description="Stock ticker, e.g., AAPL")
    qty: float = Field(..., gt=0, description="Number of shares to buy (>0)")
    exec_price: Optional[float] = Field(None, description="Executed price")
    current_price: Optional[float] = Field(None, description="Current market price")

@tool("buy_stock", args_schema=BuyArgs)
def buy_stock_tool(ticker: str, qty: float,
                   exec_price: Optional[float] = None,
                   current_price: Optional[float] = None) -> Dict[str, Any]:
    """Buy shares of a ticker and return updated position."""
    db = SessionLocal()
    try:
        pos = _buy(db, ticker=ticker, qty=qty, exec_price=exec_price, current_price=current_price)
        return _position_to_dict(pos)
    finally:
        db.close()

class SellArgs(BaseModel):
    ticker: str = Field(..., description="Stock ticker, e.g., AAPL")
    qty: float = Field(..., gt=0, description="Number of shares to sell (>0)")

@tool("sell_stock", args_schema=SellArgs)
def sell_stock_tool(ticker: str, qty: float) -> Dict[str, Any]:
    """Sell shares and return updated position (or empty if closed)."""
    db = SessionLocal()
    try:
        pos = _sell(db, ticker=ticker, qty=qty)
        return _position_to_dict(pos) if pos else {}
    finally:
        db.close()




@tool("web_search", return_direct=False)
def web_search_tool(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """Search the web (DuckDuckGo HTML) and return up to num_results results with title, url, snippet."""
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse, parse_qs, unquote

    if not query or not query.strip():
        return []

    url = "https://duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        resp = requests.post(url, data={"q": query}, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results: List[Dict[str, str]] = []
    max_results = max(1, min(10, int(num_results)))

    for result in soup.select("div.result"):
        a = result.select_one("a.result__a")
        if not a:
            continue
        href = a.get("href", "")
        title = a.get_text(" ", strip=True)
        snippet_el = result.select_one("a.result__snippet") or result.select_one("div.result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""

        parsed = urlparse(href)
        real_url = href
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
            qs = parse_qs(parsed.query)
            if "uddg" in qs and qs["uddg"]:
                real_url = unquote(qs["uddg"][0])

        results.append({"title": title, "url": real_url, "snippet": snippet})
        if len(results) >= max_results:
            break

    return results

