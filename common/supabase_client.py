# TODO(P0, reliability): How they do backups / recoveries? What about read-replicas?
from common.config import SUPABASE_KEY, SUPABASE_URL
from supabase import Client, create_client

# TODO(P2, devx): One day we can extend this wrapper with some stats and monitoring
supabase_client = None


def get_supabase_client() -> Client:
    global supabase_client
    if supabase_client is None:
        supabase_client = create_client(
            supabase_url=SUPABASE_URL,
            supabase_key=SUPABASE_KEY,
        )
    return supabase_client
