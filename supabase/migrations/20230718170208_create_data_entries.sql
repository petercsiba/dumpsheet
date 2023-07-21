create table
  public.data_entries (
    id uuid not null,
    user_id uuid null,
    idempotency_id text not null,
    display_name text not null,
    input_type text not null,
    input_uri text null,
    output_transcript text null,
    created_at timestamp with time zone not null default now(),
    processed_at timestamp with time zone null,
    constraint data_entries_pkey primary key (id),
    constraint data_entries_idempotency_id_key unique (idempotency_id),
    constraint data_entries_user_id_fkey foreign key (user_id) references auth.users (id)
  ) tablespace pg_default;

ALTER TABLE public.data_entries ENABLE ROW LEVEL SECURITY;
