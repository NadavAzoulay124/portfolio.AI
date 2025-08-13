# api/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os, shutil
import pandas as pd
from fastapi.staticfiles import StaticFiles


load_dotenv()
app = FastAPI(title="Finsight API", version="0.1.0")
# mount the "frontend/static" directory at /app
app.mount("/app", StaticFiles(directory="frontend/static", html=True), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev convenience
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

# -------- SIMPLE DATAFRAME STORAGE --------
PORTFOLIO_DF: pd.DataFrame | None = None

# map your Excel headers to simple snake_case columns we’ll reuse later
COL_RENAME = {
    "Ticker (RIC)": "ticker",
    "Company Name": "company",
    "qunatity": "qty",             # handle the typo
    "quantity": "qty",             # also accept the correct spelling
    "Sector": "sector",
    "Execution Price": "exec_price",
    "Current Price": "current_price",
    "Daily Change (%)": "daily_change_pct",
    "Change Since Traded (%)": "since_traded_pct",
}

NUMERIC_COLS = ["qty", "exec_price", "current_price", "daily_change_pct", "since_traded_pct"]

def _load_excel_to_df(path: str) -> pd.DataFrame:
    # read Excel by sheet 0; if you use CSV sometimes, swap to read_csv
    df = pd.read_excel(path)
    # rename columns we know; keep unknown columns as-is
    # we’ll match case-insensitively so "Quantity"/"quantity" both work
    lower_map = {c.lower(): c for c in df.columns}
    rename_map = {}
    for k,v in COL_RENAME.items():
        if k.lower() in lower_map:
            rename_map[ lower_map[k.lower()] ] = v
    df = df.rename(columns=rename_map)

    # minimum required columns
    required = {"ticker", "qty", "exec_price", "current_price"}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found: {list(df.columns)}")

    # light cleanup
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    for c in NUMERIC_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # optional: drop rows with no ticker or qty
    df = df.dropna(subset=["ticker", "qty"]).reset_index(drop=True)

    # OPTIONAL derived fields (comment out if you don’t want them now)
    # Market Value and P&L%
    df["market_value"] = df["qty"] * df["current_price"]
    # simple P&L% based on execution vs current
    df["pnl_pct"] = (df["current_price"] - df["exec_price"]) / df["exec_price"] * 100.0

    return df

@app.post("/portfolio/upload")
async def upload_portfolio(file: UploadFile = File(...)):
    global PORTFOLIO_DF
    try:
        # save to a temp path
        tmp_dir = os.path.join(os.getcwd(), "data", "portfolio_samples")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_path = os.path.join(tmp_dir, file.filename)
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # parse into a single DataFrame
        PORTFOLIO_DF = _load_excel_to_df(tmp_path)
        return {"rows_loaded": int(len(PORTFOLIO_DF))}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Upload/parse error: {e}")

@app.get("/portfolio")
def get_portfolio():
    if PORTFOLIO_DF is None or PORTFOLIO_DF.empty:
        return {"positions": []}
    # return as records (list of dicts) for easy frontend use
    return {"positions": PORTFOLIO_DF.to_dict(orient="records")}
