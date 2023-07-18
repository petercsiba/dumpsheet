-- PostgreSQL assumes that the new table name will be in the same schema as the old one.
ALTER TABLE public.data_entries
RENAME TO data_entry;