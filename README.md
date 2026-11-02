# Neta Tutor — Telegram MVP

A Ukrainian-language Telegram lead bot for individual online lessons: English, maths, NMT, German, Ukrainian history, programming. Built with **Python 3.11 + aiogram 3 + aiohttp**. It can start with *only* a BotFather token and administrator ID.

> Status: source code and static tests prepared. Live Telegram API/runtime integration was **not tested** in this environment (aiogram was not available for installation here). Test using a newly created bot before publishing.

## What it does

- Ukrainian home screen, subject choice, purpose/level, convenient time, explicit confirmation. A free-text message like «Шукаю репетитора з математики для 8 класу» is also understood as a starting request.
- One lead sent to the private administrator Telegram chat (no phone number required).
- Administrator can reply to that lead using the inline **«Відповісти учню»** button or by replying to the bot's lead message.
- Student can send a separate question via **«Написати викладачу»**.
- `/start en`, `/start math`, `/start nmt`, `/start de`, `/start history`, `/start code` preselect a subject; `tiktok`, `channel`, `threads`, `instagram`, `website`, `buki` are attribution labels.
- In-memory spam cooldown; `/health` endpoint for external HTTP monitoring.
- Optional durable lead storage in Supabase via server-side REST; `/stats` when enabled.
- `/privacy` and `/delete` (DB deletion + admin notification to manually delete Telegram chat copies).

### Setup in BotFather (all texts in Ukrainian)

1. Open [@BotFather](https://t.me/BotFather), choose `/newbot`.
2. Display name (search-oriented): **Репетитор онлайн | НМТ • Neta**.
3. Preferred username: `NetaTutorBot` if BotFather confirms it is available. Backups: `NetaRepetytorBot`, `RepetytorNMTBot`, `TutorNetaBot`.
4. Keep the token secret. Never paste it into public chat, source code or GitHub.
5. `/setabouttext`:

   `Репетитор онлайн: англійська, математика, НМТ, німецька, історія України, програмування. Neta Tutor.`

6. `/setdescription`:

   `Шукаєте репетитора онлайн? Neta Tutor приймає заявки на індивідуальні заняття з англійської та німецької мов, математики, історії України, програмування і підготовки до НМТ. Оберіть предмет, напишіть мету та зручний час — викладач відповість вам у Telegram. Умови, ціна та графік узгоджуються перед початком занять.`

7. Optionally upload Neta-branded profile picture using `/setuserpic`.
8. Set your bot privacy policy in BotFather if required. This implementation includes `/privacy` and the README's privacy notes; assess whether separate policy hosting is needed for your use case.

## Deploy on Render (free trial/MVP)

1. Create a **new private GitHub repository** and upload all files in this folder; do **not** upload an actual `.env`.
2. Render Dashboard → **New → Web Service** → connect that repository.
3. Runtime: Python, branch: `main`, build command: `pip install -r requirements.txt`, start command: `python main.py`, instance type **Free**.
4. Under **Environment**, define:
   - `BOT_TOKEN`: token from BotFather (secret)
   - `ADMIN_ID`: your numeric Telegram user ID (not your username). To find it use Telegram's own APIs or a trusted ID tool; the bot's `/myid` returns this value after it is running with any valid numeric ADMIN_ID.
   - `PYTHON_VERSION`: `3.11.11` (or another supported Python 3.11 release)
5. Deploy. The log should say `Health server running on port ...`, followed by Telegram polling logs. Telegram bot must have **only one polling process**.
6. Open `https://YOUR-SERVICE.onrender.com/health`; expect `{"status":"ok","service":"neta-tutor"}`.
7. Open UptimeRobot → Add New Monitor → **HTTP(s)** → URL `https://YOUR-SERVICE.onrender.com/health` → monitoring interval **5 minutes** on the Free plan.
8. In Telegram, open your bot and use `/start` to submit a test request. Check that ADMIN_ID receives it and that a response works through the reply button.

**Hosting limits:** Render Free web services normally sleep after ~15 minutes without incoming requests, have an ephemeral filesystem, and have no strong availability guarantee. Frequent health checks can keep a service active under normal circumstances, but do not prevent all crashes/redeploys/suspensions. See https://render.com/docs/free and https://help.uptimerobot.com/en/articles/11360876-what-is-a-monitoring-interval-in-uptimerobot . Render Free's 750 instance-hours per workspace per month are shared among its services.

## Optional persistent leads: Supabase

1. Create a separate Supabase project or use an existing suitable one.
2. Open its **SQL Editor** and execute `schema.sql`.
3. Set Render env vars `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from Supabase's project settings, and redeploy.
4. Never put the service-role key in client code, a public repo, screenshots or Telegram messages.
5. All lead records are received by the admin even without Supabase; however `/stats` and durable structured storage require Supabase.
6. Set your operational data-retention procedure (e.g. periodically remove old resolved leads). Telegram admin-chat copies also need manual cleanup when a deletion request is received. The bot deliberately does **not** attempt to scrape Telegram users or collect private telephone numbers.

Supabase Free projects may pause after sustained inactivity: https://supabase.com/docs/guides/platform/free-project-pausing .

## Tracking channels

Build links after BotFather gives a confirmed username:

- `https://t.me/YOUR_BOT_USERNAME?start=tiktok`
- `https://t.me/YOUR_BOT_USERNAME?start=channel`
- `https://t.me/YOUR_BOT_USERNAME?start=threads`
- `https://t.me/YOUR_BOT_USERNAME?start=en`
- `https://t.me/YOUR_BOT_USERNAME?start=nmt`

The source field is stored in the lead and included in the admin notification. Direct Telegram search starts are generally marked `organic`.

## Test checklist

1. `/start` → choose each subject → complete request → administrator receives it.
2. Send two requests rapidly; cooldown should prevent back-to-back submissions.
3. Administrator clicks reply button, types a response, and user receives it.
4. Administrator replies directly to the bot's lead notification, and user receives it.
5. Test `/start tiktok` and ensure source appears in notification.
6. Test `/privacy`, `/delete`, `/cancel` and `/myid`.
7. If using Supabase, verify a row was created, then `/stats` and `/delete`.
8. Verify a 200 OK response from `/health` after deployment and that UptimeRobot tracks it.

## Operational notes

- This bot is a **request channel for Neta tutoring**, not a verified directory of multiple tutors. The copy does not promise automatic matching with many independent teachers.
- The form uses aiogram's in-memory FSM. A deployment restart can interrupt an **in-progress** form; submitted lead cards remain in Telegram admin chat. Add Redis-backed FSM if interrupted forms become frequent.
- A bot cannot initiate an arbitrary private conversation with a Telegram user. In this design it replies only after the student has opened the bot.
- As the project grows, consider adding automated follow-up, availability management, structured statuses and a proper privacy-policy page; don't build those before validating demand.
