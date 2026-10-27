-- ALTIER · Page 1 ("Today's Fit") — Supabase schema
-- ============================================================================
-- Run this once in the Supabase SQL editor. It is idempotent: every statement is
-- IF NOT EXISTS or CREATE OR REPLACE, so re-running it after an edit is safe.
--
-- THE HONESTY RULES ARE ENFORCED IN THE SCHEMA, NOT ONLY IN THE APP.
--   Columns holding an ESTIMATE are named and commented as estimates, and the ones holding a
--   MEASUREMENT say which standard produced them. A future query, a dashboard, or a different
--   client reading this database has no access to the Python docstrings — so the distinction
--   that matters most has to survive in the column comments, where psql \d+ will show it.
--
-- ROW-LEVEL SECURITY
--   profiles and feedback are YOURS: every policy is scoped to auth.uid(), so no authenticated
--   user can read another's row even with a valid token. rules and looks are shared reference
--   data — readable by any signed-in user, writable only by the service role (the FastAPI
--   backend), because a client that could edit the knowledge base could edit everyone's advice.
--
--   RLS is enabled on every table INCLUDING the shared ones. A table with RLS enabled and no
--   policy denies everything, which is the safe default; a table with RLS left off is readable
--   by anyone with the anon key, which is not.
-- ============================================================================

create extension if not exists vector;      -- pgvector, for the taste and look embeddings

-- ---------------------------------------------------------------------------
-- Embedding dimension. 768 = google/siglip2-base-patch16-224, which is what
-- page1/engines/taste_engine.py uses. If you change MODEL_ID there you must change it here too
-- and re-embed everything: vectors from two different models are not comparable, and cosine
-- distance between them returns a plausible number that means nothing. taste_engine.LookIndex
-- refuses to mix them; Postgres cannot, so this is the place to be careful.
-- ---------------------------------------------------------------------------


-- ============================================================================
-- profiles — one row per user: the colour read, the body read, the palette, the taste vector
-- ============================================================================
create table if not exists public.profiles (
  user_id        uuid primary key references auth.users(id) on delete cascade,

  -- MEASURED, standards-based. CIELAB hue angle (CIE 1976, D65) for undertone; ITA degrees
  -- (Chardon et al. 1991) for depth. Reproducible numbers, safe to state plainly to the user.
  undertone      text check (undertone in ('warm', 'cool', 'neutral')),
  depth          text check (depth in ('fair', 'medium', 'deep')),

  -- MEASURED L* spread, cut at an UNCALIBRATED threshold. The spread is a measurement; the
  -- word high/medium/low is craft convention. Both are stored so the app can show either.
  contrast       text check (contrast in ('high', 'medium', 'low')),
  contrast_spread_l  numeric,

  -- MEASURED, white-balanced from the sclera. '#rrggbb'.
  skin_hex       text,
  hair_hex       text,
  eye_hex        text,

  -- The full measured block: L*, a*, b*, hue angle, chroma, saturation, ITA, and how far each
  -- label sat from its cut point. Kept so a borderline read can be shown as borderline.
  measured       jsonb,
  color_confidence  numeric,

  -- How far this face sat from each label's cut point, per axis. Stored so the daily screen can
  -- qualify a borderline word rather than printing it flat. It is the only consumer of the
  -- margin that exists: nothing derives behaviour from the undertone or depth WORD -- the
  -- palette is generated from the continuous measurements above, and the rules key on body
  -- shape and contrast -- so the display is where this either counts or is decoration.
  label_margins  jsonb,

  -- CONVENTION, from MEASURED ratios. The ratios are reliable and scale-free; the five-shape
  -- classification of them uses thresholds that are ours and uncalibrated.
  -- CONVENTION over MEASURED ratios, same split as the body shape. The four face ratios are
  -- measured from the FaceLandmarker mesh and are scale-free; which of seven words they become
  -- is a cut with uncalibrated thresholds. hairstyle advice keys on this word, so a borderline
  -- face shape makes the hair advice borderline too.
  face_shape     text check (face_shape in
                   ('oval', 'round', 'square', 'heart', 'oblong', 'diamond', 'triangle')),
  face_ratios    jsonb,
  -- Seventeen measured features across eyes, brows, cheeks and lips, adopted from AstroStylist's
  -- styling.py. MEASURED and descriptive: material she is shown as self-knowledge, not a verdict,
  -- and no advice keys on them. Some are clamped against hand-chosen constants inside that
  -- module; the `saturated` list inside says which sat on a bound and are therefore uninformative.
  face_features  jsonb,
  face_confidence   numeric,

  body_shape     text check (body_shape in
                   ('pear', 'apple', 'hourglass', 'rectangle', 'inverted-triangle')),
  ratios         jsonb,
  body_confidence   numeric,

  -- A NOISY ESTIMATE. Never render this as an exact size. It carries its own confidence, a
  -- plausible range per measurement, and the reasons it is unreliable — read them before using
  -- it for anything. Deliberately not split into numeric columns: a bare `waist_cm numeric`
  -- would be quoted somewhere as a fact within a week.
  size_estimate  jsonb,

  -- SELF-SELECTED, never inferred. Kibbe image identity comes from a quiz the user takes.
  -- No engine writes this from a photo. Null is the normal state.
  kibbe_self_selected  text,

  -- GENERATED in CIELAB from the measured read: {best, care, params, provenance}. Every hex in
  -- it is computed and gamut-checked, over a region whose coefficients are uncalibrated.
  palette        jsonb,

  -- The mean of the SigLIP embeddings of the user's uploaded pins. Null until pins exist, and
  -- the recommender drops the taste term rather than scoring it zero when it is null.
  taste_vector   vector(768),
  taste_pins     integer default 0,
  taste_coherence   numeric,       -- mean pairwise cosine between pins; low = a split taste
  coherence_history jsonb default '[]'::jsonb,  -- coherence over time, for the convergence read
  pin_vectors    jsonb default '[]'::jsonb,     -- her pin embeddings, for re-proposing a vibe

  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

comment on column public.profiles.undertone is
  'MEASURED from CIELAB hue angle (lightness-independent). The word is a craft cut across a standards-based axis.';
comment on column public.profiles.depth is
  'MEASURED from ITA degrees, Chardon et al. 1991. The three bands are a craft cut. Read label_margins before quoting this word: a face 0.2 degrees from the cut prints the same as one 20 degrees inside it.';
comment on column public.profiles.label_margins is
  'Distance from each label''s cut point, and what lies the other side of it. A borderline flag here means the WORD could have gone either way; the measurement it was cut from did not change.';
comment on column public.profiles.contrast is
  'CRAFT CONVENTION applied to the MEASURED L* spread in contrast_spread_l. The cut points are uncalibrated.';
comment on column public.profiles.ratios is
  'MEASURED from the silhouette at MediaPipe landmark heights. Scale-free and the reliable half of the body read.';
comment on column public.profiles.size_estimate is
  'A NOISY ESTIMATE from photos, NOT a measurement. Never present as exact. See its own notes and confidence.';
comment on column public.profiles.face_shape is
  'CONVENTION over MEASURED mesh ratios. Capped at 0.75 confidence: a face is small in frame, the mesh sits on soft tissue, and head angle moves every width ratio.';
comment on column public.profiles.body_shape is
  'CRAFT CONVENTION over measured ratios. Thresholds are ours and uncalibrated; the five-shape system is sourced.';
comment on column public.profiles.kibbe_self_selected is
  'SELF-SELECT QUIZ ONLY. Never inferred from a photo by any engine.';
comment on column public.profiles.taste_vector is
  'Mean SigLIP embedding of the user''s own pins. Represents images she saved, not clothes she likes. Makes no correctness claim.';


-- ============================================================================
-- rules — the styling knowledge base. Shared, sourced, and read-only to clients.
-- ============================================================================
create table if not exists public.rules (
  id           text primary key,          -- stable slug; never renumber, feedback keys on it
  condition    jsonb not null,            -- e.g. {"body_shape": ["pear"]} — every key must match
  attribute    text not null check (attribute in
                 ('neckline', 'silhouette', 'waist', 'contrast')),
  recommends   text not null,
  avoid        text,

  -- The machine-readable form the recommender matches on. Our editorial rendering of the prose
  -- into the fixed vocabulary in rules_engine.VOCAB.
  recommends_values  jsonb not null default '[]'::jsonb,
  avoid_values       jsonb not null default '[]'::jsonb,

  reason       text not null,
  goal         text not null,             -- the assumption the rule optimises for, shown to the user
  source       text not null,             -- the publication its DIRECTION comes from
  source_url   text,

  -- The SEEDED PRIOR: how firmly the field agrees, NOT how true the rule is. Per-user
  -- confidence is this blended with that user's own feedback — see the view below.
  confidence   numeric not null check (confidence > 0 and confidence < 1),

  -- Global counts across all users. Kept because the brief asked for them, and useful for
  -- spotting a rule everybody rejects. NOT what the recommender uses — see the note below.
  likes        integer not null default 0,
  dislikes     integer not null default 0,

  created_at   timestamptz not null default now()
);

comment on table public.rules is
  'CRAFT CONVENTION, not measurement and not evidence. Every row cites the publication its direction comes from. No controlled study supports any of it.';
comment on column public.rules.confidence is
  'A seeded prior expressing how firmly styling practice agrees — NOT a probability that the rule is true.';
comment on column public.rules.likes is
  'GLOBAL counts across all users. The recommender does NOT use these: see the my_rule_confidence view for why.';
comment on column public.rules.goal is
  'The aesthetic assumption the rule optimises for (usually balancing toward an even shoulder-hip line). Shown to the user so it can be rejected.';


-- ============================================================================
-- looks — the candidate pool. Your own pins plus an open licensed dataset.
-- ============================================================================
create table if not exists public.looks (
  id           text primary key,
  image_url    text,
  source       text not null,             -- 'seed' | 'pin' | the dataset's name. NEVER a crawl.
  title        text,
  tags         jsonb not null default '{}'::jsonb,

  -- The tagged attributes the rules match against, in rules_engine.VOCAB's vocabulary.
  neckline     text,
  silhouette   text,
  waist        text,
  colors       jsonb not null default '[]'::jsonb,   -- ['#rrggbb', ...] for the look as a whole

  -- The outfit broken into garments: [{slot, name, colors, image_url}], slot being one of
  -- layer/top/dress/bottom/shoes. Page 1 shows each piece on its own, flat, rather than styled
  -- on a body, so this is what the card renders. A look has either a top and a bottom or a
  -- dress, never both, so nothing may assume a fixed number of entries.
  items        jsonb not null default '[]'::jsonb,
  contrast     text check (contrast in ('high', 'medium', 'low')),
  occasions    jsonb not null default '[]'::jsonb,
  moods        jsonb not null default '[]'::jsonb,

  -- SigLIP image embedding. Must come from the same model as profiles.taste_vector.
  embedding    vector(768),

  -- A pin belongs to the user who uploaded it and is private to her (see the RLS policy).
  -- Dataset and seed looks have a null owner and are visible to everyone.
  owner        uuid references auth.users(id) on delete cascade,

  created_at   timestamptz not null default now()
);

comment on column public.looks.source is
  'Where the look came from. Legitimate values only: the seed fixtures, the user''s own uploaded pins, or an open licensed dataset. Never a Pinterest crawl.';


-- ============================================================================
-- vibes — every version of her aesthetic phrase, newest last. Append-only.
-- ============================================================================
-- INTERPRETATION, never measured, and it overrides nothing. A vibe of 'cool minimalist' does not
-- change her undertone, depth or contrast; those are facts about her, this is a reading of what
-- she saves. Stored as HISTORY rather than one current value on purpose: how much she still
-- rewrites it is the clearest signal available that her sense of her own style is sharpening,
-- and overwriting would throw that away. See the my_rule_confidence view's neighbour,
-- page1/engines/convergence.py.
create table if not exists public.vibes (
  id              bigint generated always as identity primary key,
  user_id         uuid not null references auth.users(id) on delete cascade,
  phrase          text not null,              -- HERS once she edits it
  descriptors     jsonb not null default '[]'::jsonb,
  edited          boolean not null default false,   -- did she change the proposal?
  proposed_phrase text,                       -- what the engine suggested, for comparison
  confirmed       boolean not null default true,
  created_at      timestamptz not null default now()
);

create index if not exists vibes_user_idx on public.vibes (user_id, created_at);

comment on table public.vibes is
  'INTERPRETATION. Zero-shot similarity between her pins and a hand-written adjective list, then edited by her. Overrides no measured field. Kept as history because the shrinking of her edits is the success metric.';


-- ============================================================================
-- feedback — every reaction, one row each. The record the calibration is built from.
-- ============================================================================
create table if not exists public.feedback (
  id           bigint generated always as identity primary key,
  user_id      uuid not null references auth.users(id) on delete cascade,

  -- A reaction is to a LOOK, to a RULE, or to both (thumbs-down on a look also counts against
  -- the rules that put it there). At least one must be present.
  look_id      text references public.looks(id) on delete set null,
  rule_id      text references public.rules(id) on delete cascade,

  liked        boolean not null,
  occasion     text,
  mood         text,
  created_at   timestamptz not null default now(),

  constraint feedback_targets_something check (look_id is not null or rule_id is not null)
);

create index if not exists feedback_user_rule_idx on public.feedback (user_id, rule_id);
create index if not exists feedback_user_look_idx on public.feedback (user_id, look_id);


-- ============================================================================
-- my_rule_confidence — the per-user view the recommender actually reads.
-- ============================================================================
-- WHY THIS EXISTS, AND WHY rules.likes IS NOT USED FOR RANKING
--   The brief put likes and dislikes on the rules table, and they are there. But a single
--   global count means my thumbs-down moves YOUR advice, which is precisely backwards: the
--   whole value of the feedback loop is that it calibrates a shared, uncalibrated convention to
--   ONE person. Two users who disagree would fight over one number and both end up with advice
--   neither asked for.
--
--   So the counts live on the rule for reporting, and this view derives each user's own counts
--   from her own feedback rows. The blend is the Beta posterior mean from
--   rules_engine.effective_confidence, with the same prior strength of 6 — kept identical here
--   so a query against the database and a call into the Python agree.
create or replace view public.my_rule_confidence as
select
  r.id                as rule_id,
  f.user_id,
  r.confidence        as seed_confidence,
  -- The `f.id is null` arm is load-bearing. This is a LEFT JOIN, so a rule nobody has reacted
  -- to still produces one row with every f.* column null -- and `case when null then 0 else 1`
  -- takes the ELSE branch, so without the guard every untouched rule reported one phantom
  -- DISLIKE. The confidence itself was right, because it divides by count(f.id) which ignores
  -- nulls. It was the counts this view exposes that were wrong, and anything hydrating a
  -- RuleStore from them would have started every rule one dislike down.
  coalesce(sum(case when f.id is null then 0 when f.liked then 1 else 0 end), 0)::int as likes,
  coalesce(sum(case when f.id is null then 0 when f.liked then 0 else 1 end), 0)::int as dislikes,
  -- (seed * 6 + likes) / (6 + likes + dislikes)
  round(((r.confidence * 6.0) + coalesce(sum(case when f.id is null then 0
                                              when f.liked then 1 else 0 end), 0))
        / (6.0 + coalesce(count(f.id), 0)), 3)                    as effective_confidence
from public.rules r
left join public.feedback f
  on f.rule_id = r.id and f.user_id = auth.uid()
group by r.id, r.confidence, f.user_id;

comment on view public.my_rule_confidence is
  'Per-user rule confidence: the seeded convention blended with THIS user''s own feedback (Beta posterior, prior strength 6 — identical to rules_engine.effective_confidence). Your reactions never move anyone else''s advice.';


-- ============================================================================
-- Row-Level Security
-- ============================================================================
alter table public.profiles enable row level security;
alter table public.rules    enable row level security;
alter table public.looks    enable row level security;
alter table public.feedback enable row level security;
alter table public.vibes    enable row level security;

-- profiles: yours alone, for everything.
drop policy if exists "own profile" on public.profiles;
create policy "own profile" on public.profiles
  for all to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- feedback: yours alone. No update or delete policy — feedback is an append-only record, and
-- rewriting history would silently change a confidence that has already been shown.
drop policy if exists "own feedback read" on public.feedback;
create policy "own feedback read" on public.feedback
  for select to authenticated using (auth.uid() = user_id);

drop policy if exists "own feedback insert" on public.feedback;
create policy "own feedback insert" on public.feedback
  for insert to authenticated with check (auth.uid() = user_id);

-- vibes: hers alone, and append-only like feedback — rewriting the history would erase the
-- very thing the convergence read measures.
drop policy if exists "own vibes read" on public.vibes;
create policy "own vibes read" on public.vibes
  for select to authenticated using (auth.uid() = user_id);

drop policy if exists "own vibes insert" on public.vibes;
create policy "own vibes insert" on public.vibes
  for insert to authenticated with check (auth.uid() = user_id);

-- rules: any signed-in user may read the knowledge base. Nobody may write it from a client;
-- the service role bypasses RLS and is how the backend seeds and updates it.
drop policy if exists "rules are readable" on public.rules;
create policy "rules are readable" on public.rules
  for select to authenticated using (true);

-- looks: shared looks (seed and dataset, owner is null) are readable by everyone signed in;
-- an uploaded pin is readable only by the user who uploaded it.
drop policy if exists "looks readable" on public.looks;
create policy "looks readable" on public.looks
  for select to authenticated using (owner is null or owner = auth.uid());

drop policy if exists "own pins insert" on public.looks;
create policy "own pins insert" on public.looks
  for insert to authenticated with check (owner = auth.uid());

drop policy if exists "own pins delete" on public.looks;
create policy "own pins delete" on public.looks
  for delete to authenticated using (owner = auth.uid());


-- ============================================================================
-- Indexes
-- ============================================================================
-- HNSW on cosine distance. The embeddings are stored unit-normalised by taste_engine, so cosine
-- and inner product rank identically; cosine is used because it stays correct if an
-- un-normalised vector is ever written by hand.
--
-- Build this only once there are looks in the table. On an empty or tiny table Postgres will
-- sequential-scan anyway and the index is pure overhead.
create index if not exists looks_embedding_idx
  on public.looks using hnsw (embedding vector_cosine_ops);

create index if not exists looks_source_idx on public.looks (source);
create index if not exists looks_owner_idx  on public.looks (owner);


-- ============================================================================
-- updated_at
-- ============================================================================
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists profiles_touch on public.profiles;
create trigger profiles_touch before update on public.profiles
  for each row execute function public.touch_updated_at();


-- ============================================================================
-- Seeding the rules
-- ============================================================================
-- The 18 sourced rules live in page1/engines/rules_engine.py, which is their single source of
-- truth. Do not retype them here — they would drift. Seed with:
--
--     python -m page1.engines.rules_engine --seed-sql        -- prints them as JSON rows
--
-- or let the API do it, which is the normal path:
--
--     POST /admin/seed-rules      (service role key required)
