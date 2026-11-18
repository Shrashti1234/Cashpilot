"""Explicit expense-forecast snapshot job; does not install a scheduler."""
import argparse
import json
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from business_clock import india_today
from forecast_journal import create_snapshot


def main():
    parser=argparse.ArgumentParser(description='Save a dated operating-expense forecast snapshot')
    parser.add_argument('--organization-id',required=True)
    parser.add_argument('--actor-id',default=os.getenv('CASH_PILOT_JOB_ACTOR'))
    parser.add_argument('--request-key',required=True,help='Stable replay key for the scheduled occurrence (maximum 80 characters)')
    args=parser.parse_args()
    if not args.actor_id:parser.error('Set CASH_PILOT_JOB_ACTOR or pass a current writable member ID')
    if not 1<=len(args.request_key)<=80:parser.error('Request key must contain 1–80 characters')
    url=os.getenv('SAAS_DATABASE_URL','')
    if not url:parser.error('SAAS_DATABASE_URL is required')
    engine=create_engine(url,pool_pre_ping=True,hide_parameters=True)
    try:
        with Session(engine) as db:
            row=create_snapshot(db,args.organization_id,args.actor_id,india_today(),args.request_key);db.commit()
            print(json.dumps({'snapshot_id':row.id,'as_of':str(row.as_of),'expense_method':row.payload['expense_method']}))
        return 0
    except Exception:
        print('Forecast job failed. Check configuration, membership and database health.',file=sys.stderr);return 1
    finally:engine.dispose()


if __name__=='__main__':raise SystemExit(main())
