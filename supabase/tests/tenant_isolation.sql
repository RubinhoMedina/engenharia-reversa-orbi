-- Execute only in an isolated test database, after the migration.
-- All synthetic users and rows are rolled back.
begin;

insert into auth.users (id) values
  ('10000000-0000-4000-8000-000000000001'),
  ('20000000-0000-4000-8000-000000000002');

do $$
begin
  if not (select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.orbit_records'::regclass) then
    raise exception 'RLS must be enabled and forced';
  end if;
  if (select rolbypassrls or rolsuper from pg_roles where rolname = 'authenticated') then
    raise exception 'authenticated must not bypass RLS';
  end if;
  if has_table_privilege('anon', 'public.orbit_records', 'select,insert,update,delete,truncate,references,trigger') then
    raise exception 'anon has unexpected table privileges';
  end if;
  if has_table_privilege('authenticated', 'public.orbit_records', 'truncate,references,trigger') then
    raise exception 'authenticated has excessive table privileges';
  end if;
  if (select count(*) from pg_policies where schemaname='public' and tablename='orbit_records') <> 4 then
    raise exception 'Expected one policy per CRUD operation';
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='orbit_records' and cmd='UPDATE' and qual is not null and with_check is not null) then
    raise exception 'UPDATE requires USING and WITH CHECK';
  end if;
end;
$$;

set local role authenticated;
select set_config('request.jwt.claim.sub', '10000000-0000-4000-8000-000000000001', true);
select set_config('request.jwt.claims', '{"sub":"10000000-0000-4000-8000-000000000001","role":"authenticated"}', true);

insert into public.orbit_records (kind, id, body)
select kind, 'same-id', jsonb_build_object('id','same-id','marker','tenant-a')
from unnest(array['orders','scripts','creators','analyses']) as kind;

do $$
declare changed integer;
begin
  if (select count(*) from public.orbit_records) <> 4 then
    raise exception 'Tenant A cannot read own rows';
  end if;
  begin
    insert into public.orbit_records (user_id,kind,id,body)
    values ('20000000-0000-4000-8000-000000000002','orders','foreign','{"id":"foreign"}');
    raise exception 'Cross-tenant insert unexpectedly succeeded';
  exception when insufficient_privilege then null;
  end;
  begin
    update public.orbit_records set user_id='20000000-0000-4000-8000-000000000002' where kind='orders';
    raise exception 'Tenant reassignment unexpectedly succeeded';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.orbit_records (kind,id,body) values ('orders','bad-payload','{"id":"different"}');
    raise exception 'Mismatched payload ID unexpectedly succeeded';
  exception when check_violation then null;
  end;
  begin
    insert into public.orbit_records (kind,id,body) values ('unknown','bad-kind','{"id":"bad-kind"}');
    raise exception 'Unknown kind unexpectedly succeeded';
  exception when check_violation then null;
  end;
  update public.orbit_records set body=body || '{"edited":true}' where kind='scripts';
  get diagnostics changed = row_count;
  if changed <> 1 then raise exception 'Own update failed'; end if;
end;
$$;

select set_config('request.jwt.claim.sub', '20000000-0000-4000-8000-000000000002', true);
select set_config('request.jwt.claims', '{"sub":"20000000-0000-4000-8000-000000000002","role":"authenticated"}', true);

do $$
declare changed integer;
begin
  if (select count(*) from public.orbit_records) <> 0 then
    raise exception 'Tenant B can read tenant A rows';
  end if;
  update public.orbit_records set body=body || '{"stolen":true}' where user_id='10000000-0000-4000-8000-000000000001';
  get diagnostics changed = row_count;
  if changed <> 0 then raise exception 'Cross-tenant update unexpectedly changed rows'; end if;
  delete from public.orbit_records where user_id='10000000-0000-4000-8000-000000000001';
  get diagnostics changed = row_count;
  if changed <> 0 then raise exception 'Cross-tenant delete unexpectedly changed rows'; end if;
end;
$$;

-- Identical legacy IDs coexist because the tenant participates in the key.
insert into public.orbit_records (kind,id,body)
select kind, 'same-id', jsonb_build_object('id','same-id','marker','tenant-b')
from unnest(array['orders','scripts','creators','analyses']) as kind;

do $$
declare changed integer;
begin
  if (select count(*) from public.orbit_records) <> 4 then
    raise exception 'Tenant B cannot read exactly its four rows';
  end if;
  if exists(select 1 from public.orbit_records where body->>'marker' <> 'tenant-b') then
    raise exception 'Tenant B sees another tenant payload';
  end if;
  delete from public.orbit_records where kind='creators';
  get diagnostics changed = row_count;
  if changed <> 1 then raise exception 'Own delete failed'; end if;
end;
$$;

-- Missing identity never matches ownership even with authenticated SQL role.
select set_config('request.jwt.claim.sub', '', true);
select set_config('request.jwt.claims', '{"role":"authenticated"}', true);
do $$
begin
  if (select count(*) from public.orbit_records) <> 0 then
    raise exception 'Missing UID can read private rows';
  end if;
  begin
    insert into public.orbit_records (user_id,kind,id,body)
    values ('10000000-0000-4000-8000-000000000001','orders','no-identity','{"id":"no-identity"}');
    raise exception 'Missing UID can insert private rows';
  exception when insufficient_privilege then null;
  end;
end;
$$;

set local role anon;
do $$
begin
  begin
    perform count(*) from public.orbit_records;
    raise exception 'anon can select';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.orbit_records (kind,id,body) values ('orders','anon','{"id":"anon"}');
    raise exception 'anon can insert';
  exception when insufficient_privilege then null;
  end;
  begin
    update public.orbit_records set body=body;
    raise exception 'anon can update';
  exception when insufficient_privilege then null;
  end;
  begin
    delete from public.orbit_records;
    raise exception 'anon can delete';
  exception when insufficient_privilege then null;
  end;
end;
$$;

reset role;
do $$
begin
  if (select count(*) from public.orbit_records where user_id='10000000-0000-4000-8000-000000000001') <> 4 then
    raise exception 'Tenant A rows were corrupted';
  end if;
  if (select count(*) from public.orbit_records where user_id='20000000-0000-4000-8000-000000000002') <> 3 then
    raise exception 'Tenant B state is incorrect';
  end if;
end;
$$;

rollback;
select 'tenant isolation assertions passed' as result;
