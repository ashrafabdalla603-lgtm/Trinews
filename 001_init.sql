-- Run in Supabase: SQL Editor. First replace YOU@EXAMPLE.COM (twice) with your admin email.
create extension if not exists pgcrypto;

create table if not exists sources (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  url text not null unique,
  type text not null default 'rss',          -- rss | watch
  category text,
  trust_level int not null default 3,        -- 1 low .. 5 official
  active boolean not null default true,
  state jsonb not null default '{}'
);

create table if not exists items (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references sources(id) on delete set null,
  source_name text,
  source_url text not null unique,
  original_title text,
  original_text text,
  fetched_at timestamptz not null default now(),
  topic text,
  claim_status text not null default 'unverified' check (claim_status in ('confirmed','unverified','speculation')),
  risk text not null default 'medium' check (risk in ('low','medium','high')),
  priority_score int not null default 0,
  deadline timestamptz,
  headline text,
  rewritten_text text,
  caption text,
  hashtags text[] not null default '{}',
  slides jsonb not null default '[]',
  suggested_format text not null default 'feed' check (suggested_format in ('feed','carousel','reel','story')),
  media_suggestion text,
  media_url text,
  channels text[] not null default '{instagram,whatsapp}',
  status text not null default 'pending' check (status in ('pending','approved','publishing','published','rejected','failed')),
  edited_by_admin boolean not null default false,
  approved_at timestamptz,
  published_at timestamptz,
  ig_media_id text,
  note text
);
create index if not exists items_queue on items (status, priority_score desc);

create table if not exists audit_log (
  id bigserial primary key,
  item_id uuid references items(id) on delete cascade,
  action text,
  at timestamptz not null default now()
);

-- Only your signed-in admin email can read or change items. The worker uses the service key.
alter table sources enable row level security;   -- no policy: service key only
alter table items enable row level security;
alter table audit_log enable row level security;

drop policy if exists admin_items on items;
create policy admin_items on items for all to authenticated
  using ((auth.jwt() ->> 'email') = 'YOU@EXAMPLE.COM')
  with check ((auth.jwt() ->> 'email') = 'YOU@EXAMPLE.COM');

drop policy if exists admin_audit on audit_log;
create policy admin_audit on audit_log for all to authenticated
  using ((auth.jwt() ->> 'email') = 'YOU@EXAMPLE.COM')
  with check ((auth.jwt() ->> 'email') = 'YOU@EXAMPLE.COM');

-- Live updates in the admin page
alter publication supabase_realtime add table items;

-- Public bucket: Instagram must be able to fetch the images
insert into storage.buckets (id, name, public) values ('media', 'media', true)
on conflict (id) do nothing;
