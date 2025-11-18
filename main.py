import os
from datetime import datetime
from typing import List, Optional, Literal, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import create_document, get_documents, db

app = FastAPI(title="AI Money Manager API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Utilities
# -----------------------------
class ParseTextRequest(BaseModel):
    text: str = Field(..., description="Raw text pasted from a screen or receipt")


def serialize_document(doc: dict) -> dict:
    """Convert MongoDB document to JSON-serializable dict"""
    from bson import ObjectId
    out = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# -----------------------------
# Schemas (request models)
# -----------------------------
class AccountCreate(BaseModel):
    name: str
    type: Literal["cash", "card", "bank", "other"] = "other"
    currency: str = "USD"
    note: Optional[str] = None


class CategoryCreate(BaseModel):
    name: str
    color: str = "#64748b"
    icon: Optional[str] = None


class TransactionCreate(BaseModel):
    date: datetime
    amount: float
    direction: Literal["expense", "income"] = "expense"
    description: str
    category_id: Optional[str] = None
    account_id: Optional[str] = None
    merchant: Optional[str] = None
    notes: Optional[str] = None


# -----------------------------
# Root & health
# -----------------------------
@app.get("/")
def read_root():
    return {"message": "AI Money Manager Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response


# -----------------------------
# Accounts
# -----------------------------
@app.post("/api/accounts")
def create_account(payload: AccountCreate):
    try:
        inserted_id = create_document("account", payload.model_dump())
        return {"id": inserted_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/accounts")
def list_accounts(limit: int = 100):
    try:
        docs = get_documents("account", limit=limit)
        return [serialize_document(d) for d in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------
# Categories
# -----------------------------
@app.post("/api/categories")
def create_category(payload: CategoryCreate):
    try:
        inserted_id = create_document("category", payload.model_dump())
        return {"id": inserted_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/categories")
def list_categories(limit: int = 200):
    try:
        docs = get_documents("category", limit=limit)
        return [serialize_document(d) for d in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/setup/defaults")
def setup_defaults():
    """Seed common categories and a default Cash account if empty"""
    try:
        # Seed categories if none
        if db["category"].count_documents({}) == 0:
            defaults = [
                {"name": "Groceries", "color": "#22c55e", "icon": "shopping-basket"},
                {"name": "Restaurants", "color": "#f97316", "icon": "utensils"},
                {"name": "Transport", "color": "#06b6d4", "icon": "car"},
                {"name": "Rent", "color": "#6366f1", "icon": "home"},
                {"name": "Utilities", "color": "#14b8a6", "icon": "zap"},
                {"name": "Salary", "color": "#84cc16", "icon": "banknote"},
                {"name": "Other", "color": "#64748b", "icon": "dots"},
            ]
            for c in defaults:
                create_document("category", c)
        # Seed Cash account if none
        if db["account"].count_documents({}) == 0:
            create_document("account", {"name": "Cash", "type": "cash", "currency": "USD"})
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------
# Transactions
# -----------------------------
@app.post("/api/transactions")
def create_transaction(payload: TransactionCreate):
    try:
        data = payload.model_dump()
        # Ensure amount is positive; store sign via direction
        data["amount"] = abs(float(data["amount"]))
        inserted_id = create_document("transaction", data)
        return {"id": inserted_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/transactions")
def list_transactions(limit: int = 50):
    try:
        docs = db["transaction"].find({}).sort("date", -1).limit(limit)
        return [serialize_document(d) for d in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------
# Parse text to structured transaction
# -----------------------------
@app.post("/api/parse")
def parse_text(req: ParseTextRequest):
    import re
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    # Amount detection
    amount = None
    # Common patterns: $12.34, 12.34 USD, -$5.60, 1,234.56
    amount_patterns = [
        r"[-+]?\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+(?:\.[0-9]{2}))",
        r"[-+]?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+(?:\.[0-9]{2}))\s*(?:USD|usd|US\$)?",
    ]
    sign = 1
    if re.search(r"(^|\s)-", text):
        sign = -1
    for pat in amount_patterns:
        m = re.search(pat, text)
        if m:
            amt_str = m.group(1).replace(",", "")
            try:
                amount = abs(float(amt_str))
                break
            except Exception:
                pass

    # Date detection
    # Patterns: 2025-01-31, 31/01/2025, Jan 31 2025, 01/31/2025
    date_found: Optional[datetime] = None
    date_patterns = [
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{2}/\d{2}/\d{4})",
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})",
    ]
    for dp in date_patterns:
        m = re.search(dp, text, flags=re.IGNORECASE)
        if m:
            raw = m.group(1)
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%b %d %Y", "%B %d %Y", "%b %d, %Y", "%B %d, %Y"):
                try:
                    date_found = datetime.strptime(raw.replace(",", ""), fmt)
                    break
                except ValueError:
                    continue
            if date_found:
                break
    if not date_found:
        date_found = datetime.now()

    # Merchant/description heuristic: take a line with letters around amount
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    description = None
    merchant = None
    if lines:
        # Prefer a line that is not just amount or date words
        candidates = []
        for ln in lines:
            if not re.search(r"\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}", ln):
                if not re.search(r"\$|USD|Total|Amount|Balance", ln, re.IGNORECASE):
                    candidates.append(ln)
        description = candidates[0] if candidates else lines[0]
        merchant = description.split(" - ")[0][:80]

    direction: Literal["expense", "income"] = "expense"
    if sign < 0 or re.search(r"refund|credit|reversal|deposit|salary|income", text, re.IGNORECASE):
        direction = "income"

    result = {
        "date": date_found.isoformat(),
        "amount": amount if amount is not None else 0.0,
        "direction": direction,
        "description": description or "",
        "merchant": merchant or None,
    }
    return result


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
