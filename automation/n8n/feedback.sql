-- Tables for the EngineVerse n8n automation templates.
--
-- Run this in the database the automation uses, with an owner role. Do not run
-- it with the EngineVerse runtime role: the web process must not be able to
-- create tables (see docs/SECURITY.md). Nothing here is a copy of a learner
-- account, and no column stores a chat transcript.
--
--   psql "$AUTOMATION_DB_URL" -v ON_ERROR_STOP=1 -f automation/n8n/feedback.sql

CREATE TABLE IF NOT EXISTS engineverse_feedback (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    helpful     BOOLEAN     NOT NULL,
    code        TEXT        NOT NULL,
    contact     TEXT,
    message     TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The aggregate report reads these two columns; index the category and time.
CREATE INDEX IF NOT EXISTS engineverse_feedback_received_at
    ON engineverse_feedback (received_at DESC);
CREATE INDEX IF NOT EXISTS engineverse_feedback_code
    ON engineverse_feedback (code);

-- One row per opt-in. The unique address is what makes onboarding idempotent:
-- a repeated subscription conflicts and sends no second welcome message.
CREATE TABLE IF NOT EXISTS engineverse_subscribers (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email       TEXT        NOT NULL UNIQUE,
    topics      JSONB       NOT NULL DEFAULT '[]'::jsonb,
    token       TEXT        NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS engineverse_subscribers_active
    ON engineverse_subscribers (created_at DESC) WHERE revoked_at IS NULL;

-- Weekly aggregate. This counts what was measured; it makes no estimate of
-- people who did not submit feedback.
CREATE OR REPLACE VIEW engineverse_feedback_weekly AS
SELECT date_trunc('week', received_at) AS week,
       count(*) FILTER (WHERE helpful)     AS helpful,
       count(*) FILTER (WHERE NOT helpful) AS not_helpful,
       count(*)                            AS total,
       mode() WITHIN GROUP (ORDER BY code) AS most_common_reason
  FROM engineverse_feedback
 WHERE received_at > now() - interval '90 days'
 GROUP BY 1
 ORDER BY 1 DESC;
