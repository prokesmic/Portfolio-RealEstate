-- Supabase schema for Island Deal Observatory

create table if not exists listings (
  id bigserial primary key,
  external_id text not null unique,
  url text not null,
  title text not null,
  locality text,
  locality_slug text,
  area_group text,
  category_type text,
  estate_type text,
  property_kind text,
  disposition text,
  usable_area numeric,
  land_area numeric,
  price_czk integer not null,
  currency text not null default 'EUR',
  price_per_m2 numeric,
  lat numeric,
  lon numeric,
  image_url text,
  features jsonb,
  quality_score numeric,
  quality_tier text,
  quality_reasons jsonb,
  price_min integer,
  price_max integer,
  price_drop_pct numeric,
  first_seen timestamptz not null,
  last_seen timestamptz not null,
  is_active boolean not null default true,
  alerted_at timestamptz,
  source_payload jsonb
);

create table if not exists price_history (
  id bigserial primary key,
  external_id text not null references listings(external_id) on delete cascade,
  observed_at timestamptz not null,
  price_czk integer not null,
  price_per_m2 numeric
);

create table if not exists sync_runs (
  id bigserial primary key,
  started_at timestamptz not null,
  finished_at timestamptz,
  status text not null,
  fetched_count integer not null default 0,
  stored_count integer not null default 0,
  error_text text
);

create index if not exists idx_listings_active on listings(is_active);
create index if not exists idx_listings_area_group on listings(area_group);
create index if not exists idx_listings_estate_type on listings(estate_type);
create index if not exists idx_listings_quality on listings(quality_score);
create index if not exists idx_listings_last_seen on listings(last_seen);
create index if not exists idx_listings_first_seen on listings(first_seen);

-- Views for the dashboard
create or replace view listing_stats as
select
  count(*) filter (
    where is_active = true and estate_type in ('flat', 'house')
  ) as total_listings,
  count(*) filter (
    where is_active = true and estate_type in ('flat', 'house') and area_group = 'lefkada'
  ) as lefkada_total,
  count(*) filter (
    where is_active = true and estate_type in ('flat', 'house') and area_group = 'crete'
  ) as crete_total,
  avg(price_czk) filter (
    where is_active = true and estate_type in ('flat', 'house')
  ) as avg_price,
  avg(price_per_m2) filter (
    where is_active = true and estate_type in ('flat', 'house')
  ) as avg_ppm2,
  avg(quality_score) filter (
    where is_active = true and estate_type in ('flat', 'house')
  ) as avg_quality,
  max(last_seen) filter (
    where is_active = true and estate_type in ('flat', 'house')
  ) as latest_seen
from listings;

create or replace view tier_counts as
select
  quality_tier,
  count(*) as count
from listings
where is_active = true
  and estate_type in ('flat', 'house')
group by quality_tier;

create or replace view top_picks as
select
  external_id,
  title,
  locality,
  price_czk,
  price_per_m2,
  quality_score,
  quality_tier,
  estate_type,
  area_group,
  url,
  image_url
from listings
where is_active = true
  and estate_type in ('flat', 'house')
order by quality_score desc nulls last, last_seen desc
limit 8;

-- Public read access
alter table listings enable row level security;
alter table sync_runs enable row level security;
alter table price_history enable row level security;

drop policy if exists "Public read listings" on listings;
create policy "Public read listings"
  on listings for select
  using (true);

drop policy if exists "Public read sync_runs" on sync_runs;
create policy "Public read sync_runs"
  on sync_runs for select
  using (true);

drop policy if exists "Public read price_history" on price_history;
create policy "Public read price_history"
  on price_history for select
  using (true);
