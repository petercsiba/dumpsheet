ALTER TABLE public.account ADD COLUMN state text not null default 'active'::text;
ALTER TABLE public.account ADD COLUMN merged_into_id uuid null;
ALTER TABLE public.account ADD constraint account_merged_into_id_fkey
    foreign key (merged_into_id) references account (id) on delete set null;