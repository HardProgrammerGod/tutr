-- Run in the Supabase SQL editor if you want persistent leads.
-- The service_role key must NEVER be sent to Telegram users or committed to GitHub.
CREATE TABLE IF NOT EXISTS public.leads (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    telegram_id bigint NOT NULL,
    telegram_username text,
    display_name text,
    subject text NOT NULL CHECK (subject IN ('en','math','nmt','de','history','code')),
    goal text NOT NULL,
    schedule text NOT NULL,
    source text NOT NULL DEFAULT 'organic',
    status text NOT NULL DEFAULT 'new',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS leads_telegram_id_idx ON public.leads(telegram_id);
CREATE INDEX IF NOT EXISTS leads_created_at_idx ON public.leads(created_at DESC);
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
-- Deliberately no public RLS policies: access is server-side via the service_role key.
-- Suggested manual cleanup when no longer needed:
-- DELETE FROM public.leads WHERE created_at < now() - interval '90 days';
