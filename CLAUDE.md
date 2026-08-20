# Working in this repo

## `apps/api/test.sqlite3` is NOT disposable

Despite the name, this file is the live shared dev database, not throwaway test
scaffolding. `apps/api/.env` sets `DJANGO_TEST_SQLITE=1`, which repurposes this exact
path as `DATABASES.NAME` in `config/settings.py` — it's what `runserver`, `seed_poc`,
and every manual `manage.py` command actually read and write to.

**Never run `rm`, `truncate`, or any "clean slate" reset against this file.** It has
already caused repeated data loss across concurrent sessions working in this repo at
the same time.

If you need a clean database for something, create your own copy first
(`cp test.sqlite3 test.sqlite3.myscratch`) or point `DATABASE_URL`/`--database` at an
isolated file — don't touch the shared one.

Note this doesn't matter for `manage.py test` itself: Django's sqlite backend always
uses an in-memory database for test runs when `DATABASES.TEST.NAME` is unset (which it
is here), regardless of what `NAME` points to. So there is never a reason to reset this
file before running tests — it was never involved in the first place.

## Don't run multiple `next dev` processes against `apps/web`

Every `next dev` (or `next build`/`next start`) invocation writes to the same
`apps/web/.next` build cache. If more than one process compiles concurrently against
it — which happens easily when multiple sessions each start their own dev server here —
the shared cache gets corrupted: you'll see errors like `Cannot find module
'./NNNN.js'` referencing `.next/server/webpack-runtime.js`. This already happened and
broke the app for whoever was viewing it.

If you need your own isolated dev server (e.g. to visually verify a change without
touching what another session might be running), copy the source to a scratch
directory instead of running a second `next dev` in place:

```bash
rsync -a --exclude node_modules --exclude .next apps/web/ /path/to/scratch/
ln -s "$(pwd)/apps/web/node_modules" /path/to/scratch/node_modules
cd /path/to/scratch && NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api npm run dev -- -p <unused-port>
```

This gets its own `.next` cache and can't collide with anyone else's. If you do end up
with a corrupted shared `.next`, it's always safe to delete
(`rm -rf apps/web/.next`) and let it rebuild — just check first whether other sessions
have a dev server pointed at the shared directory, since deleting it out from under an
active compile can cause a transient error for them too.

## Multiple sessions may be active in this repo at once

This repo is sometimes worked on by more than one Claude session simultaneously,
sharing the same working tree, database file, and dev server ports. Before running
anything destructive or broad (resets, `git clean`, killing processes, migrations),
consider that another session may have in-progress state depending on it.
