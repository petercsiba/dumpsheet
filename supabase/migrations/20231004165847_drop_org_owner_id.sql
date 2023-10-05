ALTER TABLE public.organization DROP COLUMN owner_account_id;
ALTER TABLE public.organization DROP CONSTRAINT organization_owner_account_id_fkey;