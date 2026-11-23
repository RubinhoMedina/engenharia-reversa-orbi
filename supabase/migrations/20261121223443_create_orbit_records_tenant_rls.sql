-- Foundation only. The current SQLite API has not switched providers.
create table public.orbit_records (
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  kind text not null,
  id text not null,
  body jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint orbit_records_pkey primary key (user_id, kind, id),
  constraint orbit_records_kind_check check (kind in ('orders','scripts','creators','analyses','notifications')),
  constraint orbit_records_id_check check (length(id) between 1 and 1000),
  constraint orbit_records_body_check check (
    jsonb_typeof(body) = 'object'
    and body ? 'id'
    and jsonb_typeof(body->'id') = 'string'
    and body->>'id' = id
  )
);

comment on table public.orbit_records is 'Tenant-scoped successor to SQLite records(kind,id,body). All payloads remain JSON objects.';
comment on column public.orbit_records.user_id is 'Verified Supabase Auth subject. Never derived from a user-editable payload.';
comment on column public.orbit_records.body is 'Existing ORBIT record, including its legacy string id and all module-specific fields. Excludes credentials and push subscription secrets.';

create index orbit_records_user_kind_updated_idx
  on public.orbit_records (user_id, kind, updated_at desc);

create schema if not exists orbit_private;
revoke all on schema orbit_private from public, anon, authenticated;

create function orbit_private.touch_orbit_record()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at := pg_catalog.statement_timestamp();
  return new;
end;
$$;
revoke all on function orbit_private.touch_orbit_record() from public, anon, authenticated;

create trigger orbit_records_touch_updated_at
before update on public.orbit_records
for each row execute function orbit_private.touch_orbit_record();

alter table public.orbit_records enable row level security;
alter table public.orbit_records force row level security;

-- Remove inherited Supabase table grants before granting the needed surface.
revoke all on table public.orbit_records from public, anon, authenticated, service_role;
grant usage on schema public to authenticated;
grant select, delete on table public.orbit_records to authenticated;
grant insert (user_id,kind,id,body) on public.orbit_records to authenticated;
grant update (body) on public.orbit_records to authenticated;

create policy orbit_records_select_own
on public.orbit_records for select to authenticated
using ((select auth.uid()) = user_id);

create policy orbit_records_insert_own
on public.orbit_records for insert to authenticated
with check ((select auth.uid()) = user_id);

create policy orbit_records_update_own
on public.orbit_records for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy orbit_records_delete_own
on public.orbit_records for delete to authenticated
using ((select auth.uid()) = user_id);
