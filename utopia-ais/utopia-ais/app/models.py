from datetime import date, datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Owner(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: Optional[str] = None


class Property(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="owner.id")
    association: str
    address: str
    unit_type: str = "single_family"
    zone: str = "A"
    rate: float  # monthly assessment, 150-200
    active: bool = True


class Invoice(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("property_id", "period"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")
    period: str  # "2026-11"
    balance_prior: float = 0
    charge: float = 0
    late_fee: float = 0
    balance_due: float = 0
    status: str = "open"  # open, partial, paid
    due_date: date
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")
    amount: float
    method: str = "electronic"
    received_at: datetime = Field(default_factory=datetime.utcnow)


class Vendor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    bank_ref: str


class VendorInvoice(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("vendor_id", "number"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    vendor_id: int = Field(foreign_key="vendor.id")
    number: str
    amount: float
    status: str = "open"  # open, paid
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VendorPayment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    vendor_invoice_id: int = Field(foreign_key="vendorinvoice.id")
    amount: float
    paid_at: datetime = Field(default_factory=datetime.utcnow)


class LedgerEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    txn_id: str
    account: str
    debit: float = 0
    credit: float = 0
    ref_type: str
    ref_id: int
    memo: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
