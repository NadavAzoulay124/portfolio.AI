# portfolio_repo.py
from typing import Iterable, Optional
import pandas as pd
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from data.models import Position

# ---------- Query helpers ----------

def list_positions(db: Session) -> list[Position]:
    return list(db.scalars(select(Position).order_by(Position.ticker)))

def get_position(db: Session, ticker: str) -> Optional[Position]:
    return db.scalar(select(Position).where(Position.ticker == ticker.upper()))

# ---------- Mutations ----------

def insert_position(db: Session, *, ticker: str, qty_delta: float,
                    exec_price: float | None = None,
                    current_price: float | None = None) -> Position | None:
    t = ticker.upper()
    pos = get_position(db, t)
    if pos is None:
        # create when buying or importing (must be positive qty)
        pos = Position(
            ticker=t,
            qty=max(qty_delta, 0.0),
            exec_price=exec_price if exec_price is not None else current_price,
            current_price=current_price if current_price is not None else exec_price,
        )
        db.add(pos)
    else:
        pos.qty = (pos.qty or 0.0) + qty_delta
        if exec_price is not None:
            pos.exec_price = exec_price
        if current_price is not None:
            pos.current_price = current_price
        if pos.qty <= 0:
            db.delete(pos)
            pos = None
    db.commit()
    if pos:
        db.refresh(pos)
    return pos

def buy_stock(db: Session, *, ticker: str, qty: float,
              exec_price: float | None = None,
              current_price: float | None = None) -> Position:
    if qty <= 0:
        raise ValueError("Quantity must be positive.")
    pos = insert_position(db, ticker=ticker, qty_delta=qty,
                          exec_price=exec_price, current_price=current_price)
    assert pos is not None
    return pos

def sell_stock(db: Session, *, ticker: str, qty: float) -> Position | None:
    if qty <= 0:
        raise ValueError("Quantity must be positive.")
    pos = get_position(db, ticker)
    if pos is None or (pos.qty or 0.0) < qty:
        raise ValueError("Not enough shares to sell.")
    return insert_position(db, ticker=ticker, qty_delta=-qty)

# ---------- Excel ingestion ----------

RENAME = {
    "Ticker (RIC)": "ticker",
    "Company Name": "company",      # optional column for later
    "quantity": "qty",
}

def df_from_excel_bytes(content: bytes) -> pd.DataFrame:
    import io
    df = pd.read_excel(io.BytesIO(content))
    # normalize columns to snake_case used here
    df = df.rename(columns={k: v for (k, v) in RENAME.items() if k in df.columns})
    # require ticker & qty minimally
    required = {"ticker", "qty"}
    if not required.issubset(set(c.lower() for c in df.columns)):
        raise ValueError("Excel must include columns: ticker, qty")
    # enforce schema
    df.columns = [c.lower() for c in df.columns]
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)
    return df

def load_df_into_db(db: Session, df: pd.DataFrame) -> None:
    """Idempotent import: replaces existing tickers with provided rows, inserts new ones."""
    # simple policy: clear table and re-load (for first version)
    for p in list_positions(db):
        db.delete(p)
    db.commit()

    rows = []
    for _, row in df.iterrows():
        t = str(row["ticker"]).upper()
        q = float(row["qty"])
        exec_price = float(row["exec_price"]) if "exec_price" in df.columns and pd.notna(row.get("exec_price")) else None
        curr_price = float(row["current_price"]) if "current_price" in df.columns and pd.notna(row.get("current_price")) else None
        rows.append(Position(ticker=t, qty=q, exec_price=exec_price, current_price=curr_price))
    db.add_all(rows)
    db.commit()
