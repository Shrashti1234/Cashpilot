"""Imported statement evidence and reversible one-to-one ledger reconciliation."""
import csv
from io import StringIO
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
import re

from sqlalchemy import BigInteger,Boolean,CheckConstraint,Date,DateTime,ForeignKey,ForeignKeyConstraint,Index,String,UniqueConstraint,text
from sqlalchemy.orm import Mapped,mapped_column
from saas_domain import SaaSBase,new_id


class BankAccount(SaaSBase):
    __tablename__='saas_bank_accounts'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36),ForeignKey('saas_organizations.id'))
    label:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(UniqueConstraint('organization_id','id'),UniqueConstraint('organization_id','label'))


class BankTransaction(SaaSBase):
    __tablename__='saas_bank_transactions'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36))
    account_id:Mapped[str]=mapped_column(String(36))
    booked_date:Mapped[date]=mapped_column(Date)
    reference:Mapped[str]=mapped_column(String(160))
    description:Mapped[str]=mapped_column(String(500))
    amount_paise:Mapped[int]=mapped_column(BigInteger)
    imported_by:Mapped[str]=mapped_column(String(200))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(ForeignKeyConstraint(['organization_id','account_id'],['saas_bank_accounts.organization_id','saas_bank_accounts.id']),
        UniqueConstraint('organization_id','id'),UniqueConstraint('account_id','reference'),
        CheckConstraint('amount_paise != 0 AND amount_paise BETWEEN -1000000000000 AND 1000000000000'),
        Index('ix_bank_transactions_org_account_date','organization_id','account_id','booked_date'))


class BankMatch(SaaSBase):
    __tablename__='saas_bank_matches'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36))
    transaction_id:Mapped[str]=mapped_column(String(36))
    payment_id:Mapped[str|None]=mapped_column(String(36),nullable=True)
    refund_id:Mapped[str|None]=mapped_column(String(36),nullable=True)
    cash_entry_id:Mapped[str|None]=mapped_column(String(36),nullable=True)
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    note:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[str]=mapped_column(String(200))
    reversal_reason:Mapped[str|None]=mapped_column(String(1000),nullable=True)
    reversed_by:Mapped[str|None]=mapped_column(String(200),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(
        ForeignKeyConstraint(['organization_id','transaction_id'],['saas_bank_transactions.organization_id','saas_bank_transactions.id']),
        ForeignKeyConstraint(['organization_id','payment_id'],['saas_payments.organization_id','saas_payments.id']),
        ForeignKeyConstraint(['organization_id','refund_id'],['saas_invoice_refunds.organization_id','saas_invoice_refunds.id']),
        ForeignKeyConstraint(['organization_id','cash_entry_id'],['saas_cash_entries.organization_id','saas_cash_entries.id']),
        CheckConstraint('(CASE WHEN payment_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN refund_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN cash_entry_id IS NOT NULL THEN 1 ELSE 0 END) = 1'),
        *[Index('uq_bank_match_active_'+column,'organization_id',column,unique=True,
                postgresql_where=text('active = true'),sqlite_where=text('active = 1'))
          for column in ['transaction_id','payment_id','refund_id','cash_entry_id']],
    )


HEADERS=['booked_date','reference','description','amount_inr','currency']


def parse_statement(content,today):
    if len(content.encode('utf-8'))>1_000_000:raise ValueError('Statement must be at most 1 MB')
    reader=csv.DictReader(StringIO(content.lstrip('\ufeff'),newline=''),strict=True)
    try:headers=reader.fieldnames
    except csv.Error:raise ValueError('Malformed CSV header. Check quotes and line endings.')
    if headers!=HEADERS:raise ValueError('Use exactly these CSV headers: '+','.join(HEADERS))
    rows=[];seen=set()
    try:
        for number,row in enumerate(reader,start=2):
            if len(rows)>=1000:raise ValueError('Import at most 1,000 statement rows per file')
            if None in row or any(v is None for v in row.values()):raise ValueError(f'Row {number}: invalid CSV column count')
            row={k:v.strip() for k,v in row.items()}
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',row['booked_date']):raise ValueError(f'Row {number}: date must be YYYY-MM-DD')
            try:booked=date.fromisoformat(row['booked_date'])
            except ValueError:raise ValueError(f'Row {number}: invalid booking date')
            if not date(2000,1,1)<=booked<=today:raise ValueError(f'Row {number}: use a booking date from 2000 through today')
            if row['currency']!='INR':raise ValueError(f'Row {number}: only INR statements are supported')
            if not row['reference'] or len(row['reference'])>160:raise ValueError(f'Row {number}: a stable bank transaction reference of up to 160 characters is required')
            if row['reference'] in seen:raise ValueError(f'Row {number}: duplicate bank reference within this file')
            if len(row['description'])>500:raise ValueError(f'Row {number}: description exceeds 500 characters')
            if not re.fullmatch(r'-?\d+(?:\.\d{1,2})?',row['amount_inr']):raise ValueError(f'Row {number}: amount must be signed INR with at most two decimals, without commas')
            try:amount=int(Decimal(row['amount_inr'])*100)
            except (InvalidOperation,ValueError):raise ValueError(f'Row {number}: invalid amount')
            if amount==0 or abs(amount)>1_000_000_000_000:raise ValueError(f'Row {number}: nonzero amount must not exceed INR 1,000 crore')
            rows.append({'booked_date':booked,'reference':row['reference'],'description':row['description'],'amount_paise':amount});seen.add(row['reference'])
    except csv.Error:raise ValueError('Malformed CSV. Check quotes and line endings.')
    if not rows:raise ValueError('Statement contains no rows')
    return rows
