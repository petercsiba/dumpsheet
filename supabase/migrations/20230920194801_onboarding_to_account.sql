-- changes the direction of onboarding -> account to be account -> onboarding
-- so we can better track how an user might have had multiple journeys through our demos / sales channels
ALTER TABLE onboarding ADD COLUMN account_id uuid null;
ALTER TABLE onboarding ADD COLUMN created_at timestamp with time zone not null default now();
ALTER TABLE onboarding ADD constraint onboarding_account_id_fkey foreign key (account_id) references account (id) on delete cascade;

UPDATE onboarding SET account_id = account.id FROM account WHERE onboarding.id = account.onboarding_id;

ALTER TABLE account DROP CONSTRAINT account_onboarding_id_key;
ALTER TABLE account ALTER COLUMN onboarding_id DROP NOT NULL;

-- adjust uniqueness constraints to allow for multiple ip_addresses tied to the same
ALTER TABLE onboarding DROP CONSTRAINT email_key;
ALTER TABLE onboarding DROP CONSTRAINT onboarding_phone_key;
ALTER TABLE onboarding ADD CONSTRAINT unique_email_ip_address UNIQUE(ip_address, email);
ALTER TABLE onboarding ADD CONSTRAINT unique_phone UNIQUE(phone);
-- therefore also UNIQUE(email, phone) and UNIQUE(ip_address, phone) BUT the NULL stuff