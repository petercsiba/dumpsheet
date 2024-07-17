# Tried using psycopg 3 and just failed hard with
#   psycopg.OperationalError: connection failed: :1), port 54322 failed:
#   could not receive data from server: Connection refused
# While I connected to it totally fine using psql
#   An error related to the database’s operation.
#   These errors are not necessarily under the control of the programmer, e.g. an unexpected disconnect occurs,
#   the data source name is not found, a transaction could not be processed,
#   a memory allocation error occurred during processing, etc.
#   https://www.psycopg.org/psycopg3/docs/api/errors.html#psycopg.OperationalError
# with psycopg.connect(POSTGRES_LOGIN_URL_FROM_ENV) as conn:
# with psycopg.connect("host=localhost dbname=postgres user=postgres password=postgres port=54322") as conn:

"""
def connect_postgres(postgres_login_url: str = POSTGRES_LOGIN_URL_FROM_ENV) -> "psycopg.Connection[Any]":
    # Parse the database URL
    # https://stackoverflow.com/a/71138999/1040122
    conn_dict = psycopg.conninfo.conninfo_to_dict(postgres_login_url)
    print(conn_dict)
    return psycopg.connect(postgres_login_url)
    # return psycopg.connect(**conn_dict)
# postgres = connect_postgres(POSTGRES_LOGIN_URL_FROM_ENV)
"""
