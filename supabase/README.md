# Persistência por usuário

Base SQL preparada para uma integração futura com Supabase Auth. A API existente continua usando SQLite. A migration foi criada pelo comando oficial `npx --yes supabase@3.2.0 migration new create_orbit_records_tenant_rls` e foi verificada somente em banco local descartável.

## Contrato dos registros

| Coluna | Tipo PostgreSQL | Origem e regra |
| --- | --- | --- |
| `user_id` | `uuid` | Identidade autenticada retornada por `auth.uid()`, com referência a `auth.users(id)` e remoção em cascata. |
| `kind` | `text` | `orders`, `scripts`, `creators`, `analyses` ou `notifications`, conforme os nomes usados pelo backend atual. |
| `id` | `text` | Identificador legado de 1 a 1000 caracteres. Pedidos conservam o identificador composto existente. |
| `body` | `jsonb` | Objeto completo do registro existente, incluindo `id` string igual à coluna `id`. Os campos opcionais de cada módulo são preservados. |
| `created_at` | `timestamptz` | Horário do envelope no banco, atribuído pelo servidor. Datas originais do conteúdo permanecem em `body`. |
| `updated_at` | `timestamptz` | Horário atribuído pelo servidor e atualizado por trigger sem privilégios elevados. |

A chave primária é `(user_id, kind, id)`. Duas pessoas podem ter o mesmo identificador de pedido, roteiro ou análise. O índice `(user_id, kind, updated_at desc)` atende consultas de histórico por usuário e módulo.

O adaptador futuro deve gravar `{kind, id, body}` usando o JWT verificado do usuário. `user_id` assume `auth.uid()` por padrão. O conteúdo completo atual fica em `body`, incluindo produto, valores, estados, transcrição, sugestões, método, provedor e uso quando presentes. A tabela exige um objeto com ID coerente. As validações específicas de pedidos, dinheiro e análises continuam pertencendo ao serviço da aplicação.

RLS está habilitado e forçado. Cada operação possui sua política por `auth.uid()`. O usuário autenticado recebe SELECT e DELETE de seus registros, INSERT nas colunas de conteúdo e propriedade, e UPDATE apenas de `body`. INSERT de outro proprietário é rejeitado. UPDATE não permite trocar proprietário, tipo, identificador ou datas do envelope. `anon` não recebe acesso. Não há grant operacional para `service_role` nesta base.

Credenciais OAuth, senhas, cookies, chaves VAPID e subscriptions de push ficam fora de `orbit_records`. A autenticação de proprietário único existente não equivale a Supabase Auth. Migrar registros do banco local exige associar explicitamente seu proprietário a uma identidade real, com revisão e backup.

## Reproduzir a verificação local

No diretório raiz do projeto, com Node.js instalado, execute no PowerShell ou em outro shell:

```text
npm ci --prefix supabase/test-runtime
npm test --prefix supabase/test-runtime
```

O runtime tem uma única dependência fixada no lockfile, `@electric-sql/pglite@0.5.17`. O teste aplica a migration a PostgreSQL 18.7 compilado para WASM, em memória. Cria roles sem login e uma fixture mínima `auth.users`/`auth.uid()` exclusivamente no banco descartável. Executa `tests/tenant_isolation.sql` e encerra o banco. Os registros sintéticos são revertidos por ROLLBACK, confirmado pelo runner.

O SQL verifica duas identidades, CRUD permitido no próprio usuário, invisibilidade e rejeição entre usuários, IDs iguais em tenants distintos, tentativa de transferência de propriedade, UID ausente, grants mínimos, payload inválido e `anon` sem acesso. A saída esperada contém `status: passed` e `test_rows_after_rollback: 0`.

## Resultado e cobertura

Verificação realizada com sucesso usando o runner acima. Docker, psql e uma instalação local completa de Supabase não estavam disponíveis no PATH desta máquina. O teste executa RLS real do PostgreSQL, com identidade SQL simulada. Supabase Auth, assinatura/expiração de JWT, REST/PostgREST e configuração da Data API permanecem sem teste de integração. Também não foram executados advisors de um projeto Supabase.

Antes de uma aplicação futura, revisar os grants e a migration em um projeto de desenvolvimento autorizado, executar esse SQL no PostgreSQL de destino isolado e testar o caminho com duas sessões reais de Auth. Roles administrativas com `BYPASSRLS` exigem cuidado independente das políticas. Nenhuma base remota foi alterada nesta entrega.

## Fontes consultadas

- [Changelog do Supabase](https://supabase.com/changelog.md)
- [Mudanças da CLI v3](https://supabase.com/changelog/supabase-cli-v3)
- [RLS e grants](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Testes de banco](https://supabase.com/docs/guides/database/testing)
- [PGlite](https://pglite.dev/docs/)
