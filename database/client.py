import os
from contextlib import contextmanager

from dotenv import load_dotenv
from peewee import DatabaseProxy, OperationalError, PostgresqlDatabase

# The DatabaseProxy simply defers the configuration of the database until a later time,
# but all interaction with the database (like connecting) should be done via the actual Database instance.
database_proxy = DatabaseProxy()

load_dotenv()
# NOTE: We try to keep the dependencies low here as we deploy these to AWS Lambda
# Also available in AWS Secrets Manager under prod/database/postgres-login-url
POSTGRES_LOGIN_URL_FROM_ENV = os.environ.get("POSTGRES_LOGIN_URL_FROM_ENV")


def remove_postgres_scheme(postgres_login_url):
    url = None
    if postgres_login_url.startswith("postgresql://"):
        url = postgres_login_url[13:]  # remove scheme
    elif postgres_login_url.startswith("postgres://"):
        url = postgres_login_url[11:]  # remove scheme

    if url is None:
        raise ValueError(
            "Invalid postgres login url, must start with postgres:// or postgresql://"
        )

    return url


def get_postgres_kwargs(postgres_login_url):
    if postgres_login_url is None:
        raise ValueError("postgres_login_url is required, None given")

    # AWS Lambda only supports archaic package versions, also some passwords might contain wildcards like ? or &
    # parsed_url = urlparse(postgres_login_url)
    #
    # res = {
    #     "database": parsed_url.path[1:],
    #     "user": parsed_url.username,
    #     "password": parsed_url.password,
    #     "host": parsed_url.hostname,
    #     "port": parsed_url.port,
    # }
    url = remove_postgres_scheme(postgres_login_url)
    user, rest = url.split("@")[0], url.split("@")[1]
    login, password = user.split(":")[0], user.split(":")[1]

    host_port, database_name = rest.split("/")[0], rest.split("/")[1]
    host, port = host_port.split(":")[0], host_port.split(":")[1]

    res = {
        "database": database_name,
        "user": login,
        "password": password,
        "host": host,
        "port": int(port),  # convert string to int
    }
    return res


@contextmanager
def connect_to_postgres(postgres_login_url: str):
    kwargs = get_postgres_kwargs(postgres_login_url)
    print(
        f"postgres login url parsed into {kwargs['host']} port {kwargs['port']} for db {kwargs['database']}"
    )

    postgres = PostgresqlDatabase(**kwargs)
    database_proxy.initialize(postgres)
    try:
        print("connecting to postgres")
        postgres.connect()
        postgres.execute_sql("SELECT 1")
        yield postgres
    except OperationalError:
        print("Couldn't connect to the database, running in offline mode.")
        yield None
    finally:
        print("closing connection to postgres database")
        postgres.close()
