-- FINIX AI — Supabase schema. Run once in: Supabase Dashboard -> SQL Editor.
-- The backend uses the SERVICE ROLE key, which bypasses RLS. RLS is enabled
-- with no policies so the public anon key can never read these tables.

create extension if not exists "pgcrypto";

create table if not exists users (
  id            uuid primary key default gen_random_uuid(),
  email         text not null unique,
  password_hash text not null,
  created_at    timestamptz not null default now()
);

create table if not exists chats (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references users(id) on delete cascade,
  title      text not null default 'New chat',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists chats_user_idx on chats(user_id, updated_at desc);

create table if not exists messages (
  id         uuid primary key default gen_random_uuid(),
  chat_id    uuid not null references chats(id) on delete cascade,
  user_id    uuid not null references users(id) on delete cascade,
  role       text not null check (role in ('user','assistant')),
  content    text not null,
  meta       jsonb not null default '{}'::jsonb,   -- chart tags, files, etc.
  created_at timestamptz not null default now()
);
create index if not exists messages_chat_idx on messages(chat_id, created_at);

-- One row per static chart image made by Mike. tag = '#Graph-04' (unique per chat).
create table if not exists charts (
  id         uuid primary key default gen_random_uuid(),
  chat_id    uuid not null references chats(id) on delete cascade,
  user_id    uuid not null references users(id) on delete cascade,
  seq        int  not null,
  tag        text not null,
  title      text not null,
  kind       text not null,
  url        text not null,
  meta       jsonb not null default '{}'::jsonb,   -- symbol, series key, etc. (used when user replies to a chart)
  created_at timestamptz not null default now(),
  unique (chat_id, seq)
);

-- Files the user attached in chat (parsed to text on upload).
create table if not exists uploads (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references users(id) on delete cascade,
  chat_id      uuid not null references chats(id) on delete cascade,
  filename     text not null,
  kind         text not null,                      -- txt | csv | pdf
  content_text text not null,
  created_at   timestamptz not null default now()
);

-- Declared holdings (manual on /portfolio, or reported in chat and picked up by Frank).
create table if not exists portfolio_holdings (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references users(id) on delete cascade,
  symbol     text not null,
  asset_type text not null default 'equity',
  quantity   double precision not null default 0,
  avg_price  double precision,
  currency   text not null default 'USD',
  source     text not null default 'manual',      -- manual | chat
  updated_at timestamptz not null default now(),
  unique (user_id, symbol)
);

-- Frank's long-term memory: condensed entries, retrieved selectively per prompt.
create table if not exists frank_memory (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references users(id) on delete cascade,
  chat_id    uuid references chats(id) on delete set null,
  kind       text not null default 'fact',        -- fact | decision | preference | holding_note
  topic      text not null,                       -- short headline used for retrieval
  summary    text not null,                       -- condensed content
  tags       text[] not null default '{}',
  created_at timestamptz not null default now()
);
create index if not exists frank_memory_user_idx on frank_memory(user_id, created_at desc);

alter table users              enable row level security;
alter table chats              enable row level security;
alter table messages           enable row level security;
alter table charts             enable row level security;
alter table uploads            enable row level security;
alter table portfolio_holdings enable row level security;
alter table frank_memory       enable row level security;

-- Storage buckets (run these too, or create them in Dashboard -> Storage as PUBLIC buckets).
insert into storage.buckets (id, name, public) values ('charts', 'charts', true)
  on conflict (id) do nothing;
insert into storage.buckets (id, name, public) values ('exports', 'exports', true)
  on conflict (id) do nothing;
