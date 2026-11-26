# Feedback in an online database (Supabase, free)

All feedback (the Feedback tab and the Rate this buttons, from every computer and the iPhone app)
can land in one small online database, so the team reads it in one place and it is not wiped like
Render's free disk. Nothing else leaves a computer: budgets and payments stay local.

The app writes with the project's **public key**, which can only **add** rows: row level security
allows `insert` for `anon` and nothing else, so nobody can read feedback through the API. The team
reads it in the Supabase dashboard (Table Editor), signed in.

## Set it up (about 5 minutes)

1. Create a free account and a project on <https://supabase.com> (any region; Singapore is close to Hong Kong).
2. Open **SQL Editor**, paste this and press **Run**:

```sql
create table public.feedback (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  rating smallint check (rating between 1 and 5),
  message text not null default '' check (char_length(message) <= 500),
  screen text not null check (screen in ('today', 'map', 'week', 'day', 'settings', 'add', 'home',
                                         'groceries', 'receipt', 'insight', 'budget', 'feedback', 'other')),
  context_id text check (context_id ~ '^[A-Za-z0-9_.:/-]{1,64}$'),
  device_id text check (device_id ~ '^[0-9a-f]{32}$'),
  app_version text check (app_version ~ '^[0-9A-Za-z.+-]{1,20}$'),
  check (rating is not null or char_length(message) > 0)
);

-- The public key may add feedback, and do nothing else (no read, no change, no delete).
alter table public.feedback enable row level security;
create policy "anyone can add feedback" on public.feedback for insert to anon with check (true);
```

3. Open **Project Settings > API Keys** (or **API**) and copy the **Project URL**
   (`https://<something>.supabase.co`) and the **publishable** key (`sb_publishable_...`; older
   projects call it the `anon` `public` key). Never use the `secret` / `service_role` key here.
4. Put both in `backend/ssust/data/feedback_hub.json`:

```json
{"url": "https://<something>.supabase.co", "key": "sb_publishable_..."}
```

That is all: `python run.py` (or `run.bat`) now sends feedback there, and the hosted server
(`serve.py`, which the iPhone app uses) forwards its feedback there too once deployed. The file may
be committed: the key can only add feedback rows that pass the checks above. To keep it out of git
instead, set `SSUST_FEEDBACK_URL` and `SSUST_FEEDBACK_KEY` in the environment.

## Read it

Supabase dashboard > **Table Editor** > `feedback`: one row per entry, newest at the bottom (sort by
`created_at`), with the rating, the message, the screen, the context (for example
`recipe:tomato_egg_rice`) and the app version. **Export > CSV** downloads it.

## Check it works

Start the app, open the Feedback tab, send a rating with a few words: the row appears in the table
within a second. Offline, the app keeps it in `data/feedback.db` and sends it at the next send or
the next start. If the key or the table is wrong (401, 403, 404), nothing is lost: it waits in the
same place until the setup is fixed.
