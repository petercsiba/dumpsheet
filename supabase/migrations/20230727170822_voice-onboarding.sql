ALTER TABLE public.onboarding ADD COLUMN phone text null;
ALTER TABLE public.onboarding ADD COLUMN phone_carrier_info text null;
ALTER TABLE public.onboarding ADD constraint onboarding_phone_key unique (phone);