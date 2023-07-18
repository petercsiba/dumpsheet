from contextlib import contextmanager
from urllib.parse import urlparse

from peewee import OperationalError, PostgresqlDatabase

from common.config import POSTGRES_LOGIN_URL


def get_postgres_kwargs(postgres_login_url: str = POSTGRES_LOGIN_URL):
    parsed_url = urlparse(postgres_login_url)

    res = {
        "database": parsed_url.path[1:],
        "user": parsed_url.username,
        "password": parsed_url.password,
        "host": parsed_url.hostname,
        "port": parsed_url.port,
    }
    # never dump credentials in prod
    print(postgres_login_url, parsed_url, res)
    return res


database = PostgresqlDatabase(**get_postgres_kwargs())


@contextmanager
def connect_to_postgres():
    try:
        database.connect()
        database.execute_sql("SELECT 1")
        yield database
    except OperationalError:
        print("Couldn't connect to the database, running in offline mode.")
        yield None
    finally:
        print("closing connection to postgres database")
        database.close()
