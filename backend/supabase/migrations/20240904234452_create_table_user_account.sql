-- Create the user_account table
CREATE TABLE public.user_account (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id UUID NOT NULL DEFAULT auth.uid(),  -- assuming this function exists
    account_id UUID NOT NULL,
    CONSTRAINT user_account_pkey PRIMARY KEY (id),  -- Primary key on id
    CONSTRAINT user_account_unique UNIQUE (user_id, account_id)  -- Unique constraint on (user_id, account_id)
) TABLESPACE pg_default;

ALTER TABLE public.prompt_log ENABLE ROW LEVEL SECURITY;