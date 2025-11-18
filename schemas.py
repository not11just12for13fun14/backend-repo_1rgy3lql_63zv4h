"""
Database Schemas for AI Money Manager

Each Pydantic model represents a MongoDB collection. The collection name is the
lowercased class name (e.g., Transaction -> "transaction").
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field
from datetime import date

class Account(BaseModel):
    name: str = Field(..., description="Account name, e.g., Cash, Wallet, Card")
    type: Literal["cash", "card", "bank", "other"] = Field("other", description="Account type")
    currency: str = Field("USD", description="ISO currency code")
    note: Optional[str] = Field(None, description="Optional account note")

class Category(BaseModel):
    name: str = Field(..., description="Category name, e.g., Groceries")
    color: str = Field("#64748b", description="Hex color used in UI")
    icon: Optional[str] = Field(None, description="Optional icon name for UI")

class Transaction(BaseModel):
    date: date = Field(..., description="Transaction date")
    amount: float = Field(..., description="Positive values only; use direction for sign")
    direction: Literal["expense", "income"] = Field("expense", description="Expense or income")
    description: str = Field(..., description="What this transaction is for")
    category_id: Optional[str] = Field(None, description="Reference to Category _id as string")
    account_id: Optional[str] = Field(None, description="Reference to Account _id as string")
    merchant: Optional[str] = Field(None, description="Merchant or source")
    notes: Optional[str] = Field(None, description="Optional notes")

class Budget(BaseModel):
    category_id: str = Field(..., description="Category this budget applies to")
    amount: float = Field(..., description="Budget amount in account currency")
    period: Literal["monthly", "weekly", "yearly", "custom"] = Field("monthly", description="Budget period")
    start_date: Optional[date] = Field(None, description="Start date for custom periods")
    end_date: Optional[date] = Field(None, description="End date for custom periods")
