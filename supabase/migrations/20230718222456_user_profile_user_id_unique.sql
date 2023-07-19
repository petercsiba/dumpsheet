-- one-to-one
ALTER TABLE public.user_profile
ADD CONSTRAINT user_profile_user_id_key UNIQUE (user_id);