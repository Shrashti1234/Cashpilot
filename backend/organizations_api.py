"""Authenticated organization onboarding and membership listing.

This router must be mounted with the verified OIDC identity dependency.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth_identity import get_verified_identity
from saas_api import get_saas_session
from saas_domain import Membership, Organization

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])
Identity = Annotated[str, Depends(get_verified_identity)]
Db = Annotated[Session, Depends(get_saas_session)]


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    mode: str


def organization_out(org: Organization, role: str) -> dict:
    return {"id": org.id, "name": org.name, "mode": org.mode, "role": role}


@router.post("", status_code=201)
def create_organization(payload: OrganizationCreate, identity: Identity, db: Db):
    if payload.mode not in ("micro", "b2b") or not payload.name.strip():
        raise HTTPException(status_code=422, detail="Valid business name and mode required")
    org = Organization(name=payload.name.strip(), mode=payload.mode)
    try:
        db.add(org)
        db.flush()
        db.add(Membership(organization_id=org.id, user_id=identity, role="owner"))
        db.commit()
        db.refresh(org)
    except Exception:
        db.rollback()
        raise
    return organization_out(org, "owner")


@router.get("")
def my_organizations(identity: Identity, db: Db):
    rows = db.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == identity)
        .order_by(Organization.name)
    ).all()
    return {"organizations": [organization_out(org, role) for org, role in rows]}
