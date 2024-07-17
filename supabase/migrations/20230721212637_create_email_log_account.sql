 -- Replace user_profile (user_id, full_name) with account.
DROP TABLE user_profile;

create table
  public.account (
    id uuid not null default gen_random_uuid (),
    onboarding_id bigint not null,
    user_id uuid null,
    full_name text null,
    created_at timestamp with time zone not null default now(),
    constraint account_pkey primary key (id),
    constraint account_onboarding_id_key unique (onboarding_id),
    constraint account_onboarding_id_fkey foreign key (onboarding_id) references onboarding (id),
    constraint account_user_id_fkey foreign key (user_id) references auth.users (id) on delete set null
  ) tablespace pg_default;
ALTER TABLE public.account ENABLE ROW LEVEL SECURITY;

create policy "User owns their account by user_id"
on "public"."account"
as permissive
for all
to public
using ((auth.uid() = user_id))
with check ((auth.uid() = user_id));

-- Replace FKs from user_id to account_id, this gives us more breathing space with Auth.
-- For email_log
ALTER TABLE public.email_log DROP CONSTRAINT email_log_user_id_idempotency_id_key;
ALTER TABLE public.email_log DROP CONSTRAINT email_log_user_id_fkey;
-- we keep account_id for better tracking
ALTER TABLE public.email_log RENAME COLUMN user_id TO account_id;
-- the real idempotency_key would be (recipient, idempotency_id)
ALTER TABLE public.email_log
ADD CONSTRAINT email_log_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.account (id);
ALTER TABLE public.email_log
ADD CONSTRAINT email_log_email_idempotency_id_key UNIQUE (recipient, idempotency_id);

-- For data_entry
ALTER TABLE public.data_entry DROP CONSTRAINT data_entries_user_id_fkey;
ALTER TABLE public.data_entry RENAME COLUMN user_id TO account_id;
ALTER TABLE public.data_entry
ADD CONSTRAINT data_entry_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.account (id);

-- As we already in the renaming business, rename the legacy data_entries constraints
ALTER TABLE public.data_entry DROP CONSTRAINT data_entries_pkey;
ALTER TABLE public.data_entry ADD CONSTRAINT data_entry_pkey PRIMARY KEY (id);

ALTER TABLE public.data_entry DROP CONSTRAINT data_entries_idempotency_id_key;
ALTER TABLE public.data_entry ADD CONSTRAINT data_entry_idempotency_id_key UNIQUE (idempotency_id);