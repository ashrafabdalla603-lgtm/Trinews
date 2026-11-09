-- Safe to run on any install: adds the carousel slides column if it is missing.
alter table items add column if not exists slides jsonb not null default '[]';
