-- also drops the constraint
alter table public.task drop column pipeline_id;

ALTER TABLE public.task ADD COLUMN workflow_name text null;