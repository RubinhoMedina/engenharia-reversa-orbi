import { PGlite } from '@electric-sql/pglite';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const database = new PGlite();

try {
  // Test fixture only. Hosted Supabase supplies these roles and Auth objects.
  await database.exec(`
    create role anon nologin;
    create role authenticated nologin;
    create role service_role nologin bypassrls;
    create schema auth;
    create table auth.users (id uuid primary key);
    create function auth.uid() returns uuid
    language sql stable security invoker set search_path = ''
    as $$ select coalesce(
      nullif(current_setting('request.jwt.claim.sub', true), ''),
      nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
    )::uuid $$;
    grant usage on schema auth to anon, authenticated;
    grant execute on function auth.uid() to anon, authenticated;
  `);

  const files = (await readdir(path.join(root, 'migrations')))
    .filter(file => file.endsWith('.sql'))
    .sort();
  if (!files.length) throw new Error('No migration found.');
  for (const file of files) {
    await database.exec(await readFile(path.join(root, 'migrations', file), 'utf8'));
  }
  const results = await database.exec(await readFile(path.join(root, 'tests', 'tenant_isolation.sql'), 'utf8'));
  const leftovers = await database.query('select count(*)::integer as count from public.orbit_records');
  if (leftovers.rows[0].count !== 0) throw new Error('Test fixture rollback failed.');
  const version = await database.query('select version() as version');
  console.log(JSON.stringify({
    status: 'passed',
    engine: version.rows[0].version,
    migrations: files,
    assertion_result: results.at(-1).rows,
    test_rows_after_rollback: leftovers.rows[0].count,
    auth_fixture: 'Minimal local auth.uid function and synthetic roles. Supabase Auth/REST/JWT not exercised.'
  }, null, 2));
} finally {
  await database.close();
}
