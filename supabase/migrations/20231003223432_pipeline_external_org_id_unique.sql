ALTER TABLE public.pipeline
ADD CONSTRAINT pipeline_external_org_id_destination_id_unique UNIQUE (external_org_id, destination_id);
