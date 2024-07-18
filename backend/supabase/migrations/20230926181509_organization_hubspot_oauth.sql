alter table public.organization drop column hubspot_code;

alter table public.organization add column hubspot_access_token text null;
alter table public.organization add column hubspot_refresh_token text null;
alter table public.organization add column hubspot_expires_at timestamp with time zone null;