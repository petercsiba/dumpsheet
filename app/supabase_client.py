from contextlib import contextmanager
from urllib.parse import urlparse

import psycopg2

from gotrue import Session
from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_KEY, POSTGRES_LOGIN_URL
from aws_utils import is_running_in_aws


supabase: Client = create_client(
    supabase_url=SUPABASE_URL,
    supabase_key=SUPABASE_KEY,
)


@contextmanager
def get_postgres_connection(postgres_login_url: str = POSTGRES_LOGIN_URL):
    parsed_url = urlparse(postgres_login_url)
    dbname = parsed_url.path[1:]
    user = parsed_url.username
    password = parsed_url.password
    host = parsed_url.hostname
    port = parsed_url.port
    conn = psycopg2.connect(
        dbname=dbname,
        user=user,
        password=password,
        host=host,
        port=port
    )
    try:
        yield conn
    except Exception as e:
        raise e
    finally:
        conn.close()


def user_exists(conn, email: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM auth.users WHERE email = %s LIMIT 1;", (email,))
        return cur.fetchone() is not None


def get_user_id_for_email(conn, email: str):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM auth.users WHERE email = %s LIMIT 1;", (email,))
        result = cur.fetchone()
        return result[0] if result else None


def insert_into_todos(conn, todos):
    with conn.cursor() as cur:
        insert_query = "INSERT INTO todos (user_id, task, is_complete) VALUES (%s, %s, %s);"
        for todo in todos:
            res = cur.execute(insert_query, (todo['user_id'], todo['task'], todo['is_complete']))
            print(f"insert into todos: {res}")
    conn.commit()


# TODO: There is something about Confirm email
# https://supabase.com/docs/reference/python/auth-signup
# TODO: There must be regulation around "by clicking you accept the terms of service"
# TODO: Is the return type true? Seems sign_in returns session, which should be the same as the sign_up
def get_or_create_user_rest(conn, email: str, password) -> Session:
    # user = supabase.auth.get_user('email', email)
    if not user_exists(conn, email):
        # User does not exist, so sign them up
        print(f"sign_up {email} with {password}")
        sign_up_res = supabase.auth.sign_up({
          "email": email,
          "password": password,
        })
        print(f"sign_up user_id {sign_up_res.user.id}")
        return sign_up_res.session

    # User already exists, log them in
    # TODO(P0, ux): Users will need to change their initial password (or the lack of existence of it).
    return supabase.auth.sign_in(email, password)


# TODO(P0, ux): Users will need to set password / connect their SSO - figure this out there must be Next.js code.
def get_magic_link_and_create_user_if_does_not_exists(email: str) -> Session:
    # If the user doesn't exist, sign_in_with_otp() will signup the user instead.
    response = supabase.auth.sign_in_with_otp({
        "email": email,
        "options": {
            "email_redirect_to": 'https://app.voxana.ai/' if is_running_in_aws() else "http://localhost:3000/"
        }
    })
    print(f"sign_in_with_otp for {email} yielded {response}")
    return response


# Supabase caters to frontend peeps without much backend knowledge, so their core functionality is catered toward
# a logged in user instead of say batch jobs like the voice transcript stuff is.
def create_todos_rest(session: Session):
    # https://github.com/supabase-community/supabase-py/issues/185
    # After you sign a user in, the user's access token is not being used by the library for any of the API calls,
    # and therefore RLS does not work right now. See related issue and discussion
    # OH NO
    postgrest_client = supabase.postgrest
    postgrest_client.auth(session.access_token)

    todos = []
    for i in range(3):
        todos.append({
            "user_id": session.user.id,
            "task": f"Test REST {i}",
            "is_complete": False,
        })

    insert_response, count = supabase.table('todos').insert(todos).execute()
    # TODO: This response seems off
    print(f"inserted {count} rows with response {insert_response}")


if __name__ == "__main__":
    with get_postgres_connection() as postgres_conn:
        test_email = f"peter+otp@voxana.ai"

        # Through REST API
        # test_email = "peter+test1@voxana.ai"
        # test_password = 'admin123'
        # session = get_or_create_user(conn, test_email, test_password)
        # create_todos_rest(session=session)
        # user_id = session.user.id

        # Through good old psycopg2 (not even psycopg3)
        # TODO: Figure out if this is any good - e.g. having a link?
        response = get_magic_link_and_create_user_if_does_not_exists(email=test_email)
        user_id = get_user_id_for_email(postgres_conn, test_email)

        todos = []
        for i in range(3):
            todos.append({
                "user_id": user_id,
                "task": f"Test Psycopg2 {i}",
                "is_complete": False,
            })
        insert_into_todos(postgres_conn, todos)

        # Just try querying:
        response = supabase.table('todos').select("*").execute()
        print(f"all todos for user {user_id}: {response}")

        supabase.auth.sign_out()
