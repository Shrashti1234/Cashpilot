"""Explicit job entrypoint. No scheduler is installed by importing this module."""
import argparse
import json
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from intelligence_api import today
from recurring import generate_due


def main():
    parser=argparse.ArgumentParser(description='Generate reviewable recurring invoice drafts')
    parser.add_argument('--organization-id',required=True)
    parser.add_argument('--actor-id',default=os.getenv('CASH_PILOT_JOB_ACTOR'))
    args=parser.parse_args()
    if not args.actor_id:parser.error('Set CASH_PILOT_JOB_ACTOR or pass a current organization member ID')
    url=os.getenv('SAAS_DATABASE_URL','')
    if not url:parser.error('SAAS_DATABASE_URL is required')
    engine=create_engine(url,pool_pre_ping=True)
    try:
        with Session(engine) as db:
            result=generate_due(db,args.organization_id,args.actor_id,today());db.commit()
        print(json.dumps({'created':len(result['created']),'failed_series':len(result['errors']),'remaining_due':result['remaining_due']}))
        return 1 if result['errors'] else 0
    except Exception:
        # Connection errors can contain credentials/parameters; do not log them.
        print('Job failed. Check configuration, membership and database health.',file=__import__('sys').stderr)
        return 1
    finally:engine.dispose()


if __name__=='__main__':raise SystemExit(main())
