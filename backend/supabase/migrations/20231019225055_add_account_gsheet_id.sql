ALTER TABLE account ADD COLUMN gsheet_id text null;
ALTER TABLE account ADD constraint account_gsheet_id_key unique (gsheet_id);