-- Design discussion: https://chat.openai.com/share/d4f58715-3c20-48a8-b1d6-42967e24b1d6

ALTER TABLE public.organization ADD COLUMN owner_account_id uuid null;
ALTER TABLE public.organization ADD constraint organization_owner_account_id_fkey foreign key (owner_account_id) references account (id) on delete restrict;

create table
  public.destination (
    id bigint generated by default as identity not null,
    created_at timestamp with time zone null default now(),
    name text not null,
    install_url text null,
    setup_info_url text null,
    constraint destination_pkey primary key (id)
  ) tablespace pg_default;

ALTER TABLE public.destination ENABLE ROW LEVEL SECURITY;

INSERT INTO public.destination (
    id, name, install_url
) VALUES (
    1, 'hubspot', 'https://app.hubspot.com/oauth/authorize?client_id=501ffe58-5d49-47ff-b41f-627fccc28715&scope=oauth%20crm.objects.contacts.read%20crm.objects.contacts.write%20crm.objects.owners.read&redirect_uri=https%3A%2F%2Fapi.voxana.ai%2Fhubspot%2Foauth%2Fredirect&state=accountId%3Anull'
);

create table
  public.oauth_data (
    id uuid not null default gen_random_uuid (),
    token_type text not null,
    access_token text null,
    refresh_token text null,
    refreshed_at timestamp with time zone null,
    expires_at timestamp with time zone null,
    created_at timestamp with time zone not null default now(),
    constraint oauth_data_pkey primary key (id)
  ) tablespace pg_default;
ALTER TABLE public.oauth_data ENABLE ROW LEVEL SECURITY;

-- in the ETL world usually encompasses all of Pipeline, Workflow (Transformation), Connector (or Adapter).
create table
  public.pipeline (
    id bigint generated by default as identity not null,
    organization_id uuid not null,
    destination_id bigint not null,
    oauth_data_id uuid null,
    state text not null default 'initiated'::text,
    created_at timestamp with time zone null default now(),
    constraint pipeline_pkey primary key (id),
    constraint pipeline_organization_id_fkey foreign key (organization_id) references organization (id) on delete cascade,
    constraint pipeline_destination_id_fkey foreign key (destination_id) references destination (id) on delete restrict,
    constraint pipeline_oauth_data_id_fkey foreign key (oauth_data_id) references oauth_data (id) on delete set null,
    UNIQUE(organization_id, destination_id)
  ) tablespace pg_default;
ALTER TABLE public.pipeline ENABLE ROW LEVEL SECURITY;

-- DATA MIGRATION
-- Supabase AI is experimental and may produce incorrect answers
-- Always verify the output before executing

-- First, Insert into the oauth_data table
--do $$
--DECLARE
--  org_record public.organization%ROWTYPE;
--  new_oauth_id UUID;
--BEGIN
--  FOR org_record IN SELECT * FROM public.organization WHERE hubspot_refresh_token IS NOT NULL LOOP
--
--    -- Create a new oauth_data record based on the organization
--    INSERT INTO public.oauth_data (token_type, access_token, refresh_token, refreshed_at, expires_at)
--    VALUES ('oauth', org_record.hubspot_access_token, org_record.hubspot_refresh_token, NULL, org_record.hubspot_expires_at)
--    ON CONFLICT DO NOTHING
--    RETURNING id INTO new_oauth_id;
--
--    -- Create a new pipeline record linking to the new oauth_data record
--    INSERT INTO public.pipeline (organization_id, destination_id, oauth_data_id, state)
--    VALUES (org_record.id, 1, new_oauth_id, 'initiated');
--
--  END LOOP;
--END $$;