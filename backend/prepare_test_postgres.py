"""Explicitly initialize an isolated loopback test database, never a hosted one."""
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url


def main():
    if os.getenv('CASH_PILOT_ALLOW_TEST_SETUP')!='1':raise RuntimeError('Explicit isolated-test setup flag required')
    admin=make_url(os.environ['CASH_PILOT_PG_ADMIN_URL']);runtime=make_url(os.environ['CASH_PILOT_PG_RUNTIME_URL'])
    for url in [admin,runtime]:
        if url.host not in {'127.0.0.1','localhost'} or url.database!='cashpilot_checks':raise RuntimeError('Only the dedicated loopback test database is allowed')
    if (admin.host,admin.port,admin.database)!=(runtime.host,runtime.port,runtime.database) or runtime.username!='cashpilot_backend':
        raise RuntimeError('Test roles must use the same isolated database')
    engine=create_engine(admin,hide_parameters=True)
    try:
        with engine.begin() as connection:
            for name in ['anon','authenticated']:
                if not connection.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:name'),{'name':name}).scalar():
                    connection.exec_driver_sql(f'CREATE ROLE {name} NOLOGIN')
        old=os.environ.get('SAAS_DATABASE_URL');os.environ['SAAS_DATABASE_URL']=admin.render_as_string(hide_password=False)
        try:
            config=Config(str(Path(__file__).with_name('alembic.ini')))
            config.set_main_option('script_location',str(Path(__file__).with_name('migrations')))
            command.upgrade(config,'head')
        finally:
            if old is None:os.environ.pop('SAAS_DATABASE_URL',None)
            else:os.environ['SAAS_DATABASE_URL']=old
        with engine.begin() as connection:
            cursor=connection.connection.driver_connection.cursor()
            if runtime.password:
                cursor.execute(sql.SQL('ALTER ROLE cashpilot_backend LOGIN PASSWORD {}').format(sql.Literal(runtime.password)))
            else:cursor.execute('ALTER ROLE cashpilot_backend LOGIN')
            cursor.close()
            connection.execute(text('CREATE TABLE IF NOT EXISTS cashpilot_local_test_marker (marker text primary key)'))
            connection.execute(text("INSERT INTO cashpilot_local_test_marker VALUES ('cashpilot-local-postgres-isolated-20261026') ON CONFLICT DO NOTHING"))
        print('Isolated PostgreSQL test schema initialized. Credential values were not printed.')
    finally:engine.dispose()


if __name__=='__main__':main()
