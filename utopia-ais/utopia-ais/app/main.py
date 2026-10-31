import uuid
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import Session, select

from .db import get_session, init_db
from .models import (Invoice, LedgerEntry, Owner, Payment, Property, Vendor,
                      VendorInvoice, VendorPayment)

app = FastAPI(title="uTopia AIS prototype....by: Alex Osterneck, CLA, MSCS, MSIT")


@app.on_event("startup")
def on_startup():
    init_db()


def post(session, debit_acct, credit_acct, amount, ref_type, ref_id, memo=""):
    """Record a balanced double-entry transaction."""
    txn = str(uuid.uuid4())
    session.add(LedgerEntry(txn_id=txn, account=debit_acct, debit=amount,
                             ref_type=ref_type, ref_id=ref_id, memo=memo))
    session.add(LedgerEntry(txn_id=txn, account=credit_acct, credit=amount,
                             ref_type=ref_type, ref_id=ref_id, memo=memo))


def next_month_due(period: str, day: int = 10) -> date:
    y, m = map(int, period.split("-"))
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return date(y, m, day)


# ---- master data -----------------------------------------------------

@app.post("/owners")
def create_owner(owner: Owner, session: Session = Depends(get_session)):
    session.add(owner); session.commit(); session.refresh(owner)
    return owner


@app.get("/owners")
def list_owners(session: Session = Depends(get_session)):
    return session.exec(select(Owner)).all()


@app.post("/properties")
def create_property(prop: Property, session: Session = Depends(get_session)):
    if not (150 <= prop.rate <= 200):
        raise HTTPException(400, "rate must be between 150 and 200")
    session.add(prop); session.commit(); session.refresh(prop)
    return prop


@app.get("/properties")
def list_properties(session: Session = Depends(get_session)):
    return session.exec(select(Property)).all()


# ---- billing -----------------------------------------------------------

@app.post("/billing/run")
def run_billing(period: str, session: Session = Depends(get_session)):
    """Generate one invoice per active property for the period. Reruns are idempotent."""
    created = []
    for prop in session.exec(select(Property).where(Property.active == True)).all():  # noqa: E712
        if session.exec(select(Invoice).where(Invoice.property_id == prop.id,
                                               Invoice.period == period)).first():
            continue
        prior = session.exec(select(Invoice).where(Invoice.property_id == prop.id)
                              .order_by(Invoice.id.desc())).first()
        balance_prior = prior.balance_due if prior else 0.0
        inv = Invoice(property_id=prop.id, period=period, balance_prior=balance_prior,
                       charge=prop.rate, balance_due=balance_prior + prop.rate,
                       due_date=next_month_due(period))
        session.add(inv); session.commit(); session.refresh(inv)
        post(session, "AR:Homeowners", "Revenue:Assessments", prop.rate,
             "invoice", inv.id, f"{prop.address} {period}")
        session.commit()
        created.append(inv)
    return created


@app.post("/billing/late-fees")
def apply_late_fees(period: str, as_of: Optional[date] = None,
                     session: Session = Depends(get_session)):
    """Apply the 20% late fee once, to qualifying unpaid invoices past their due date."""
    as_of = as_of or date.today()
    flagged = []
    invs = session.exec(select(Invoice).where(Invoice.period == period,
                                               Invoice.status != "paid",
                                               Invoice.late_fee == 0)).all()
    for inv in invs:
        if inv.due_date >= as_of:
            continue
        fee = round(inv.balance_due * 0.20, 2)
        inv.late_fee = fee
        inv.balance_due += fee
        session.add(inv); session.commit()
        post(session, "AR:Homeowners", "Revenue:LateFees", fee, "late_fee", inv.id,
             f"invoice {inv.id}")
        session.commit()
        flagged.append(inv)
    return flagged


@app.get("/invoices")
def list_invoices(property_id: Optional[int] = None, status: Optional[str] = None,
                   session: Session = Depends(get_session)):
    q = select(Invoice)
    if property_id:
        q = q.where(Invoice.property_id == property_id)
    if status:
        q = q.where(Invoice.status == status)
    return session.exec(q).all()


@app.get("/reports/aging")
def aging(session: Session = Depends(get_session)):
    out: dict = {}
    for inv in session.exec(select(Invoice).where(Invoice.status != "paid")).all():
        out[inv.property_id] = out.get(inv.property_id, 0.0) + inv.balance_due
    return out


# ---- collections ---------------------------------------------------------

@app.post("/payments")
def receive_payment(property_id: int, amount: float, method: str = "electronic",
                     session: Session = Depends(get_session)):
    pay = Payment(property_id=property_id, amount=amount, method=method)
    session.add(pay); session.commit(); session.refresh(pay)
    remaining = amount
    opens = session.exec(select(Invoice).where(Invoice.property_id == property_id,
                                                Invoice.status != "paid")
                          .order_by(Invoice.id)).all()
    for inv in opens:
        if remaining <= 0:
            break
        applied = min(remaining, inv.balance_due)
        inv.balance_due -= applied
        inv.status = "paid" if inv.balance_due <= 0 else "partial"
        remaining -= applied
        session.add(inv); session.commit()
        post(session, "Cash", "AR:Homeowners", applied, "payment", pay.id, f"invoice {inv.id}")
        session.commit()
    if remaining > 0:
        post(session, "Cash", "Liability:UnappliedCash", remaining, "payment", pay.id,
             "unmatched / no open invoice")
        session.commit()
    return pay


# ---- electronic payments / disbursements ---------------------------------

@app.post("/vendors")
def create_vendor(vendor: Vendor, session: Session = Depends(get_session)):
    session.add(vendor); session.commit(); session.refresh(vendor)
    return vendor


@app.get("/vendors")
def list_vendors(session: Session = Depends(get_session)):
    return session.exec(select(Vendor)).all()


@app.get("/vendor-invoices")
def list_vendor_invoices(session: Session = Depends(get_session)):
    return session.exec(select(VendorInvoice)).all()


@app.post("/vendor-invoices")
def create_vendor_invoice(vi: VendorInvoice, session: Session = Depends(get_session)):
    dup = session.exec(select(VendorInvoice).where(VendorInvoice.vendor_id == vi.vendor_id,
                                                     VendorInvoice.number == vi.number)).first()
    if dup:
        raise HTTPException(409, f"duplicate invoice {vi.number} for this vendor, held as id {dup.id}")
    session.add(vi); session.commit(); session.refresh(vi)
    post(session, "Expense:Vendor", "AP:Vendors", vi.amount, "vendor_invoice", vi.id, vi.number)
    session.commit()
    return vi


@app.post("/vendor-payments")
def pay_vendor_invoice(vendor_invoice_id: int, session: Session = Depends(get_session)):
    vi = session.get(VendorInvoice, vendor_invoice_id)
    if not vi or vi.status == "paid":
        raise HTTPException(400, "invoice not found or already paid")
    vp = VendorPayment(vendor_invoice_id=vi.id, amount=vi.amount)
    vi.status = "paid"
    session.add(vp); session.add(vi); session.commit(); session.refresh(vp)
    post(session, "AP:Vendors", "Cash", vi.amount, "vendor_payment", vp.id,
         f"vendor invoice {vi.id}")
    session.commit()
    return vp


# ---- ledger ----------------------------------------------------------------

@app.get("/ledger/trial-balance")
def trial_balance(session: Session = Depends(get_session)):
    out: dict = {}
    for r in session.exec(select(LedgerEntry)).all():
        acc = out.setdefault(r.account, {"debit": 0.0, "credit": 0.0})
        acc["debit"] += r.debit
        acc["credit"] += r.credit
    return out


@app.get("/health")
def health():
    return {"status": "ok"}


# ---- UI (static) -----------------------------------------------------------
# Mounted last so it never shadows an API route above.
from pathlib import Path
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "static", html=True), name="ui")
