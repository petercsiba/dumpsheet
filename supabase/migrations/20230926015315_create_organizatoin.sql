create table
  public.organization (
    id uuid not null default gen_random_uuid (),
    name text not null,
    hubspot_code text null,
    hubspot_linked_at timestamp with time zone null,
    created_at timestamp with time zone not null default now(),
    constraint organization_pkey primary key (id)
  ) tablespace pg_default;

-- ACCOUNT TABLE UPDATES
  alter table public.account add column organization_id uuid null;
  alter table public.account add column organization_role text null;
  alter table public.account add constraint account_organization_id_fkey foreign key (organization_id) references organization (id) on delete set null;