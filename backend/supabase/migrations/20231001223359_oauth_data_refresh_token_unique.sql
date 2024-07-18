ALTER TABLE public.oauth_data
ADD CONSTRAINT unique_refresh_token UNIQUE (refresh_token);
