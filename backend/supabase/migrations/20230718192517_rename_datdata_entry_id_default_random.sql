ALTER TABLE public.data_entry
ALTER COLUMN id SET DEFAULT uuid_generate_v4();