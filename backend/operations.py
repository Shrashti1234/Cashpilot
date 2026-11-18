"""Financial document snapshots and append-only stock accounting.

Amounts are integer paise; quantities are integer thousandths of a unit.
Tax rates are user-reviewed basis points, not a tax-classification service.
"""
from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint,
    Index, JSON, String, Text, UniqueConstraint, select, func,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from saas_domain import SaaSBase, new_id


class BusinessProfile(SaaSBase):
    __tablename__ = 'saas_business_profiles'
    organization_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(1000))
    gstin: Mapped[str] = mapped_column(String(15), default='')
    state_code: Mapped[str] = mapped_column(String(2))
    require_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (ForeignKeyConstraint(['organization_id'], ['saas_organizations.id']),)


class Product(SaaSBase):
    __tablename__ = 'saas_products'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36))
    sku: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(160))
    unit: Mapped[str] = mapped_column(String(16))
    hsn_sac: Mapped[str] = mapped_column(String(8), default='')
    unit_price_paise: Mapped[int] = mapped_column(BigInteger)
    tax_rate_bps: Mapped[int] = mapped_column(BigInteger)
    track_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    reorder_milliunits: Mapped[int] = mapped_column(BigInteger, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['saas_organizations.id']),
        UniqueConstraint('organization_id', 'id'),
        UniqueConstraint('organization_id', 'sku'),
        CheckConstraint('unit_price_paise >= 0 AND unit_price_paise <= 1000000000'),
        CheckConstraint('tax_rate_bps >= 0 AND tax_rate_bps <= 10000'),
        CheckConstraint('reorder_milliunits >= 0'),
    )


class StockMovement(SaaSBase):
    __tablename__ = 'saas_stock_movements'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36))
    product_id: Mapped[str] = mapped_column(String(36))
    quantity_milliunits: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str] = mapped_column(String(160))
    request_key: Mapped[str] = mapped_column(String(100))
    actor_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        ForeignKeyConstraint(['organization_id', 'product_id'], ['saas_products.organization_id', 'saas_products.id']),
        UniqueConstraint('organization_id', 'request_key'),
        CheckConstraint('quantity_milliunits != 0'),
        CheckConstraint("reason IN ('opening', 'adjustment', 'purchase_receipt', 'invoice_issue')"),
        Index('ix_stock_org_product', 'organization_id', 'product_id'),
    )


class TradeDocument(SaaSBase):
    __tablename__ = 'saas_trade_documents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20))
    number: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default='draft')
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    invoice_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    party: Mapped[dict] = mapped_column(JSON)
    supplier: Mapped[dict] = mapped_column(JSON)
    lines: Mapped[list] = mapped_column(JSON)
    totals: Mapped[dict] = mapped_column(JSON)
    received: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default='')
    created_by: Mapped[str] = mapped_column(String(200))
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['saas_organizations.id']),
        ForeignKeyConstraint(['organization_id', 'customer_id'], ['saas_customers.organization_id', 'saas_customers.id']),
        ForeignKeyConstraint(['organization_id', 'invoice_id'], ['saas_invoices.organization_id', 'saas_invoices.id']),
        UniqueConstraint('organization_id', 'kind', 'number'),
        CheckConstraint("kind IN ('estimate', 'purchase_order', 'invoice')"),
        CheckConstraint("status IN ('draft', 'approved', 'issued', 'cancelled')"),
        Index('ix_documents_org_created', 'organization_id', 'created_at'),
    )


def stock_balance(db: Session, organization_id: str, product_id: str) -> int:
    return db.scalar(select(func.coalesce(func.sum(StockMovement.quantity_milliunits), 0)).where(
        StockMovement.organization_id == organization_id,
        StockMovement.product_id == product_id))


def post_stock(db: Session, *, organization_id: str, product_id: str,
               quantity: int, reason: str, reference: str, request_key: str, actor_id: str):
    # Lock the product before inspecting both balance and idempotency. All stock
    # writes take this lock, preventing concurrent overselling in PostgreSQL.
    product = db.scalar(select(Product).where(Product.organization_id == organization_id,
                                              Product.id == product_id).with_for_update())
    if product is None or not product.track_stock:
        raise ValueError('Choose a stock-tracked product in this business')
    prior = db.scalar(select(StockMovement).where(StockMovement.organization_id == organization_id,
                                                 StockMovement.request_key == request_key))
    if prior:
        if (prior.product_id, prior.quantity_milliunits, prior.reason, prior.reference) != (product_id, quantity, reason, reference):
            raise ValueError('Request key was already used for a different stock movement')
        return prior
    if stock_balance(db, organization_id, product_id) + quantity < 0:
        raise ValueError(f'Insufficient stock for {product.sku}')
    movement = StockMovement(organization_id=organization_id, product_id=product_id,
        quantity_milliunits=quantity, reason=reason, reference=reference,
        request_key=request_key, actor_id=actor_id)
    db.add(movement)
    db.flush()
    return movement


def calculate_lines(lines: list[dict], supplier_state: str, place_of_supply: str) -> tuple[list, dict]:
    """Round each tax component to the nearest paise, half up, per line."""
    result = []
    totals = {k: 0 for k in ['subtotal_paise', 'discount_paise', 'taxable_paise',
                            'cgst_paise', 'state_tax_paise', 'igst_paise', 'cess_paise', 'total_paise']}
    interstate = supplier_state != place_of_supply
    for source in lines:
        item = dict(source)
        gross = (item['quantity_milliunits'] * item['unit_price_paise'] + 500) // 1000
        discount = item['discount_paise']
        if discount > gross:
            raise ValueError('A line discount cannot exceed its value')
        taxable = gross - discount
        rate = item['tax_rate_bps']
        central = 0 if interstate else (taxable * rate + 10000) // 20000
        local = central
        integrated = (taxable * rate + 5000) // 10000 if interstate else 0
        cess = (taxable * item['cess_rate_bps'] + 5000) // 10000
        item.update(subtotal_paise=gross, taxable_paise=taxable, cgst_paise=central,
                    state_tax_paise=local, igst_paise=integrated, cess_paise=cess,
                    total_paise=taxable + central + local + integrated + cess)
        for key in totals:
            totals[key] += item[key]
        result.append(item)
    if totals['total_paise'] <= 0 or totals['total_paise'] > 2_000_000_000:
        raise ValueError('Document total must be positive and at most INR 2 crore')
    totals['tax_regime'] = 'interstate' if interstate else 'intrastate'
    totals['state_tax_label'] = 'UTGST' if supplier_state in {'04', '26', '31', '35', '38'} else 'SGST'
    return result, totals
