create table
  public.user_profile (
    id uuid not null default gen_random_uuid (),
    user_id uuid not null,
    full_name text null,
    constraint user_profile_pkey primary key (id),
    constraint user_profile_user_id_fkey foreign key (user_id) references auth.users (id)
  ) tablespace pg_default;
ALTER TABLE public.user_profile ENABLE ROW LEVEL SECURITY;

create policy "User owns their user_profile by user_id"
on "public"."user_profile"
as permissive
for all
to public
using ((auth.uid() = user_id))
with check ((auth.uid() = user_id))
