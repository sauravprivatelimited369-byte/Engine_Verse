#!/usr/bin/env bash
# EngineVerse OTP service — self-hosted setup + run, made for Git Bash.
#
# No third-party OTP/dashboard service is involved:
#   * this script runs on YOUR machine/server, in Git Bash (Windows) or any bash
#   * your SMTP password is typed here (hidden), written only to
#     services/otp/.env on this disk (chmod 600, git-ignored, verified below)
#   * user emails/phones and (hashed) codes live only in services/otp's local
#     SQLite file on this disk — nothing is sent to Render/Twilio/MSG91/analytics
#
# Usage (from Git Bash, anywhere):
#   bash services/otp/gitbash_setup_run.sh            # first run: setup, then start
#   bash services/otp/gitbash_setup_run.sh --setup-only
#   bash services/otp/gitbash_setup_run.sh --run-only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
MODE="${1:-run}"

# Git Bash on Windows may only have `python`; Linux/macOS usually `python3`.
PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || { echo "Python 3.11+ not found. Install it, then re-run."; exit 1; }
echo "Using $($PY --version 2>&1)"

setup() {
  if [ -f "$ENV_FILE" ]; then
    echo ".env already exists at $ENV_FILE — keeping it. Delete it to re-run setup."
    return
  fi
  echo
  echo "=== EngineVerse OTP setup (values stay on THIS machine) ==="
  read -r -p "Sender email address (e.g. your Gmail): " SENDER
  [ -n "$SENDER" ] || { echo "A sender address is required for email OTP."; exit 1; }
  read -r -p "SMTP host [smtp.gmail.com]: " SMTP_HOST
  SMTP_HOST="${SMTP_HOST:-smtp.gmail.com}"
  read -r -p "SMTP port [465]: " SMTP_PORT
  SMTP_PORT="${SMTP_PORT:-465}"
  echo "SMTP password / Gmail App Password (input hidden; stored ONLY in local .env):"
  read -r -s SMTP_PASS; echo
  [ -n "$SMTP_PASS" ] || { echo "Password was empty — aborting, nothing written."; exit 1; }
  read -r -p "Site origin allowed to call this service [https://authorsauravkushwaha.github.io]: " ORIGIN
  ORIGIN="${ORIGIN:-https://authorsauravkushwaha.github.io}"
  read -r -p "Port to listen on [8010]: " PORT
  PORT="${PORT:-8010}"

  # URL-encode credentials and mint the HMAC secret with Python itself,
  # so the password never appears in this script or in shell history files.
  SMTP_URL="$($PY - "$SENDER" "$SMTP_PASS" "$SMTP_HOST" "$SMTP_PORT" <<'PYEOF'
import sys, urllib.parse
user, pw, host, port = sys.argv[1:5]
q = lambda v: urllib.parse.quote(v, safe="")
print(f"smtps://{q(user)}:{q(pw)}@{host}:{port}/")
PYEOF
)"
  OTP_SECRET="$($PY -c "import secrets; print(secrets.token_hex(32))")"

  umask 077
  {
    echo "OTP_SECRET=$OTP_SECRET"
    echo "SMTP_URL=$SMTP_URL"
    echo "MAIL_FROM=\"EngineVerse <$SENDER>\""
    echo "OTP_ALLOWED_ORIGINS=$ORIGIN,http://localhost:8000,http://127.0.0.1:8000"
    echo "OTP_DB=$SCRIPT_DIR/otp.sqlite3"
    echo "PORT=$PORT"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
  unset SMTP_PASS

  # Prove the secrets file can never be committed by accident.
  if git -C "$SCRIPT_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    if git -C "$SCRIPT_DIR" check-ignore -q "services/otp/.env"; then
      echo "Verified: services/otp/.env is git-ignored (will never be committed)."
    else
      echo "WARNING: services/otp/.env is NOT git-ignored. Add it to .gitignore before committing anything."
    fi
  fi
  echo "Setup written to $ENV_FILE (permissions 600)."
}

case "$MODE" in
  --setup-only) setup; exit 0 ;;
  --run-only) ;;
  *) setup ;;
esac

[ -f "$ENV_FILE" ] || { echo "No .env found. Run with no arguments once to do setup."; exit 1; }

# Load .env without printing it.
set -a; . "$ENV_FILE"; set +a
PORT="${PORT:-8010}"
echo
echo "Starting EngineVerse OTP service on http://0.0.0.0:$PORT  (Ctrl+C to stop)"
echo "Health check (another terminal):  curl http://127.0.0.1:$PORT/health"
echo "Data file (yours only):           $OTP_DB"
exec "$PY" "$SCRIPT_DIR/app.py"
