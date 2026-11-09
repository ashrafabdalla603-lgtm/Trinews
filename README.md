# Tri News newsroom

Tri News is a TriBridge Services company. Mostly entertaining, with edutainment above all: every post should leave the reader knowing one useful thing.

Sources -> score -> Claude rewrite -> Supabase (status `pending`) -> Telegram alert -> you review in the admin page -> publish job posts to Instagram.

Nothing posts unless `status = 'approved'`. Only your signed-in admin email can set that (row-level security), and the publisher reads nothing else.

## How stories are ranked
Deadline alerts (KCSE, KUCCPS, HELB, KNEC, KRA, portals) score 70 to 90 and sit at the top of the queue, because a missed deadline hurts people. Entertainment (celebrity, music, viral, screen, comedy) scores about 50 to 58. Anything with a learning angle (explained, how to, why, facts) gets +12. Change the weights in `worker/scorer.py`.

## Brand files
`brand/out/` holds the mark, lockups, Instagram avatar (1080), app icons and `brand-sheet.png`. `python brand/make_brand.py` rebuilds all of them, plus the watermark used on post images (`worker/assets/`). The TriBridge logo lives in `brand/source/`; every post carries "A TriBridge Services company".

## Setup (about an hour)
1. **Supabase**: new project. SQL editor: replace `YOU@EXAMPLE.COM` in `supabase/migrations/001_init.sql`, run it, then run `002_slides.sql`. Authentication > Users: add your email and a password (auto-confirm on).
2. **Telegram**: message @BotFather, `/newbot`, keep the token. Send your bot a message, open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the chat id.
3. **Instagram**: Business or Creator account. Easiest route, no Facebook Page: Meta developer app > Instagram API with Instagram login > add your account as a tester, accept the invite inside Instagram, generate a token in the dashboard. Set the repo variable `GRAPH_HOST` to `https://graph.instagram.com`. Facebook Login route: link a Facebook Page, use permissions `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, and leave `GRAPH_HOST` unset. Your own account works in development mode without App Review. Tokens last about 60 days: refresh before then.
4. **Admin page**: put your Supabase URL and the **anon** key at the top of `admin/app.js` (never the service key). Host `admin/` on GitHub Pages, Netlify or Vercel. Open it on your phone and use Add to Home Screen.
5. **GitHub**: push this repo (public = free Actions minutes). Settings > Secrets and variables > Actions.
   Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GEMINI_API_KEY` (free, from Google AI Studio; `GROQ_API_KEY`, `OPENROUTER_API_KEY` or `ANTHROPIC_API_KEY` also work), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `IG_USER_ID`, `IG_ACCESS_TOKEN`, `ADMIN_URL`.
   Variables: `BRAND_NAME` (Tri News), `BRAND_HANDLE` (your real handle), `BRAND_TAG` (TriNews), `GRAPH_HOST`.
6. Actions > **fetch** > Run workflow. The first run seeds the sources. Official pages only learn their current links, so they raise items from the second run on.
7. Check the RSS URLs in the `sources` table (they are guesses). Fix or disable dead ones.
8. Instagram profile: upload `brand/out/avatar-1080.png` as the profile picture.
9. Approve one item in the admin page, then run Actions > **publish** (or wait up to 15 minutes). Test on a throwaway account first.

## Notes
- **Actions minutes**: a public repo runs free. A private repo has a monthly cap that the 15-minute publish job would use up.
- **Reels** are an 8-second silent video made from the card image. Replace `make_reel` for real video.
- **WhatsApp**: Channels have no posting API, so Telegram sends you a ready-to-paste message after each post.
- **Previews** in the admin page are drafts; the final image is drawn again from your edited text at publish time.
- Local test: copy `.env.example` to `.env`, export it, run `python worker/run_fetch.py`.
- **AI provider**: free by default. Set `GEMINI_API_KEY` and you are done; add `GROQ_API_KEY` as a backup and the system switches to it when Gemini's daily quota runs out. Model names change, so if a provider answers 404, set `AI_MODEL` (Gemini), `GROQ_MODEL` or `OPENROUTER_MODEL` to a current name. Lower the repo variable `MAX_AI_PER_RUN` to fit your quota.
