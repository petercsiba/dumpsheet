ALTER TABLE public.data_entry
ADD COLUMN state text not null default 'upload_intent'::text