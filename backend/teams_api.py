from datetime import datetime,timedelta,timezone
import hashlib
import secrets
from typing import Annotated

from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,func
from sqlalchemy.orm import Session

from audit import record_event
from auth_identity import get_verified_identity
from operations_api import authorize,mutation
from organizations_api import organization_out
from request_limits import allow_action
from saas_api import get_saas_session
from saas_domain import Membership,Organization
from teams import TeamInvitation

router=APIRouter(prefix='/api/v1',tags=['team-access'])
Identity=Annotated[str,Depends(get_verified_identity)]
Db=Annotated[Session,Depends(get_saas_session)]


class InvitationInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    target_user_id:str=Field(min_length=1,max_length=200)
    role:str=Field(pattern=r'^(admin|accountant|viewer)$')


class AcceptInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    token:str=Field(min_length=40,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')


class MemberInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    user_id:str=Field(min_length=1,max_length=200)
    role:str=Field(pattern=r'^(owner|admin|accountant|viewer)$')
    active:bool=Field(strict=True)


def utc(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def member_out(m):return {'user_id':m.user_id,'role':m.role,'active':m.active}


def invite_out(i):
    return {'id':i.id,'target_user_id':i.target_user_id,'role':i.role,'expires_at':utc(i.expires_at),
            'used':i.used,'revoked':i.revoked,'created_by':i.created_by}


def locked_admin(db,identity,org):
    authorize(db,identity,org,admin=True)
    db.scalar(select(Organization).where(Organization.id==org).with_for_update())
    db.execute(select(Membership).where(Membership.organization_id==org,Membership.user_id==identity).execution_options(populate_existing=True)).scalar_one()
    return authorize(db,identity,org,admin=True)


def may_manage(actor,target_role,desired_role):
    if actor.role!='owner' and (target_role in {'owner','admin'} or desired_role in {'owner','admin'}):
        raise HTTPException(403,'Only an owner can manage owners or administrators')


@router.get('/me')
def me(identity:Identity):return {'user_id':identity}


@router.get('/organizations/{organization_id}/team')
def team(organization_id:str,identity:Identity,db:Db):
    actor=authorize(db,identity,organization_id,admin=True)
    members=db.scalars(select(Membership).where(Membership.organization_id==organization_id).order_by(Membership.role,Membership.user_id))
    invites=db.scalars(select(TeamInvitation).where(TeamInvitation.organization_id==organization_id).order_by(TeamInvitation.created_at.desc()).limit(100))
    return {'actor_id':identity,'actor_role':actor.role,'members':[member_out(m) for m in members],
            'invitations':[invite_out(i) for i in invites]}


@router.post('/organizations/{organization_id}/team/invitations',status_code=201)
def invite(organization_id:str,payload:InvitationInput,identity:Identity,db:Db):
    allow_action(identity,'team-invite','invitations')
    with mutation(db):
        actor=locked_admin(db,identity,organization_id)
        target=db.get(Membership,(organization_id,payload.target_user_id))
        may_manage(actor,target.role if target else '',payload.role)
        if target and target.active:raise ValueError('This account is already an active member')
        if target and target.role=='owner':raise ValueError('An owner must be reactivated directly by another owner')
        now=datetime.now(timezone.utc)
        pending=db.scalar(select(TeamInvitation.id).where(TeamInvitation.organization_id==organization_id,
            TeamInvitation.target_user_id==payload.target_user_id,TeamInvitation.used.is_(False),
            TeamInvitation.revoked.is_(False),TeamInvitation.expires_at>now).limit(1))
        if pending:raise ValueError('A pending invitation already exists. Revoke it before creating a replacement.')
        token=secrets.token_urlsafe(32)
        invitation=TeamInvitation(organization_id=organization_id,target_user_id=payload.target_user_id,
            role=payload.role,token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=now+timedelta(days=7),created_by=identity,used=False,revoked=False)
        db.add(invitation);db.flush();record_event(db,organization_id,identity,'team.invited',invitation.id)
    return {**invite_out(invitation),'token':token,'note':'Private, account-bound invitation code. Shown only once; share directly with its intended recipient.'}


@router.post('/organizations/{organization_id}/team/invitations/{invitation_id}/revoke')
def revoke_invite(organization_id:str,invitation_id:str,identity:Identity,db:Db):
    with mutation(db):
        actor=locked_admin(db,identity,organization_id)
        invitation=db.scalar(select(TeamInvitation).where(TeamInvitation.organization_id==organization_id,
            TeamInvitation.id==invitation_id).with_for_update())
        if invitation is None:raise HTTPException(404,'Invitation not found')
        may_manage(actor,invitation.role,invitation.role)
        invitation.revoked=True;record_event(db,organization_id,identity,'team.invitation_revoked',invitation.id)
    return invite_out(invitation)


@router.post('/invitations/accept')
def accept(payload:AcceptInput,identity:Identity,db:Db):
    allow_action(identity,'invite-accept','invitation attempts')
    with mutation(db):
        digest=hashlib.sha256(payload.token.encode()).hexdigest()
        # Discover only the organization before taking locks in the same order as
        # revocation/member updates: organization first, invitation second.
        org_id=db.scalar(select(TeamInvitation.organization_id).where(TeamInvitation.token_hash==digest))
        if org_id is None:raise HTTPException(404,'Invitation is invalid or expired')
        org=db.scalar(select(Organization).where(Organization.id==org_id).with_for_update())
        invitation=db.scalar(select(TeamInvitation).where(TeamInvitation.token_hash==digest).with_for_update())
        if invitation.revoked or utc(invitation.expires_at)<=datetime.now(timezone.utc):raise HTTPException(404,'Invitation is invalid or expired')
        if invitation.target_user_id!=identity:raise HTTPException(403,'This invitation belongs to a different account')
        member=db.get(Membership,(org_id,identity))
        if invitation.used:
            if not member or not member.active:raise HTTPException(403,'This invitation was already used; ask an administrator for access')
            return {'organization':organization_out(org,member.role)}
        inviter=db.get(Membership,(org_id,invitation.created_by))
        if not inviter or not inviter.active or inviter.role not in {'owner','admin'} or (invitation.role=='admin' and inviter.role!='owner'):
            raise HTTPException(403,'Inviter permissions changed. Ask an owner for a new invitation.')
        if member and member.active:
            # Another admin may have granted access since creation; never let an
            # old invitation overwrite that newer decision.
            invitation.used=True
        else:
            if member and member.role in {'owner','admin'} and inviter.role!='owner':raise HTTPException(403,'An owner must restore this membership')
            if member:member.role=invitation.role;member.active=True
            else:
                member=Membership(organization_id=org_id,user_id=identity,role=invitation.role,active=True);db.add(member)
            invitation.used=True
        record_event(db,org_id,identity,'team.invitation_accepted',invitation.id)
    return {'organization':organization_out(org,member.role)}


@router.post('/organizations/{organization_id}/team/member')
def change_member(organization_id:str,payload:MemberInput,identity:Identity,db:Db):
    with mutation(db):
        actor=locked_admin(db,identity,organization_id)
        target=db.get(Membership,(organization_id,payload.user_id))
        if target is None:raise HTTPException(404,'Member not found. Create an invitation for new accounts.')
        may_manage(actor,target.role,payload.role)
        if target.active and target.role=='owner' and (not payload.active or payload.role!='owner'):
            owners=db.scalar(select(func.count()).select_from(Membership).where(Membership.organization_id==organization_id,
                Membership.active.is_(True),Membership.role=='owner'))
            if owners<=1:raise ValueError('The last active owner cannot be demoted or deactivated. Assign another owner first.')
        target.role=payload.role;target.active=payload.active
        record_event(db,organization_id,identity,'team.member_updated',target.user_id)
    return member_out(target)
