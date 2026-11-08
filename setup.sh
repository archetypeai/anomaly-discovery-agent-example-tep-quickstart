#!/usr/bin/env bash
# One-step setup: Git LFS data, a Python virtual environment, requirements, and .env.
#
#     ./setup.sh
#
# Safe to rerun. The API key comes from your environment (ATAI_API_KEY) or, when run
# in a terminal, from a hidden prompt; it is written to .env and never printed. The
# endpoint is found by asking production and the free trial which accepts the key
# (ATAI_API_ENDPOINT, when set, is tried first).
#
# Exit status: 0 ready, 2 set up but the API key is missing (Stages 0-3 still work),
# 3 the key was rejected by every deployment.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '%s\n' "$*"; }

# 1. Git LFS: the prepared data and role files are LFS objects.
if ! command -v git-lfs >/dev/null 2>&1; then
    say "Git LFS is not installed. Install it (macOS: brew install git-lfs), then rerun ./setup.sh."
    exit 1
fi
if head -c 40 data/roles/library/tep_library.csv | grep -q "git-lfs.github.com"; then
    say "fetching the LFS data files (~75 MB)"
    git lfs install --local >/dev/null
    git lfs pull
fi
say "data: LFS files present"

# 2. Python virtual environment and requirements. Prefer the newest Python 3.10+ on PATH:
#    macOS's stock python3 (3.9, with an old pip) is too old.
if [ ! -x .venv/bin/python ]; then
    py=""
    for c in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
            py="$c"; break
        fi
    done
    if [ -z "$py" ]; then
        say "Python 3.10 or newer is needed (macOS: brew install python), then rerun ./setup.sh."
        exit 1
    fi
    say "creating .venv with $py"
    "$py" -m venv .venv
fi
.venv/bin/python -m pip install -q --disable-pip-version-check --upgrade pip
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
say "python: .venv ready ($(.venv/bin/python --version))"

# 3. .env: copy the example once, then fill the key and endpoint without echoing them.
[ -f .env ] || cp .env.example .env

key="${ATAI_API_KEY:-}"
endpoint="${ATAI_API_ENDPOINT:-}"
current_key="$(sed -n 's/^ATAI_API_KEY=//p' .env | head -1)"
if [ -z "$key" ] && { [ -z "$current_key" ] || [ "$current_key" = "sk_your_key_here" ]; } && [ -t 0 ]; then
    read -r -s -p "ATAI_API_KEY (input hidden, Enter to skip): " key; echo
fi

# Write the key and endpoint, then find the deployment the key belongs to: a key is
# accepted (200) only by its own deployment and gets 401 from the others, so a
# free-trial key works without anyone setting the free trial's endpoint by hand.
set +e
ATAI_SETUP_KEY="$key" ATAI_SETUP_ENDPOINT="$endpoint" .venv/bin/python - <<'EOF'
import os, re, sys, urllib.error, urllib.request

DEPLOYMENTS = {"production": "https://platform.u1.archetypeai.app",
               "free trial": "https://try.archetypeai.app/api"}
env = open(".env").read()


def get(name):
    m = re.search(rf"^{name}=(.*)$", env, flags=re.M)
    return m.group(1).strip() if m else ""


def put(name, value):
    global env
    line = f"{name}={value}"
    env = re.sub(rf"^{name}=.*$", lambda _: line, env, count=1, flags=re.M) \
        if re.search(rf"^{name}=", env, flags=re.M) else env.rstrip("\n") + f"\n{line}\n"


for name, given in (("ATAI_API_KEY", os.environ["ATAI_SETUP_KEY"]),
                    ("ATAI_API_ENDPOINT", os.environ["ATAI_SETUP_ENDPOINT"])):
    if given:
        put(name, given)
open(".env", "w").write(env)

key, endpoint = get("ATAI_API_KEY"), get("ATAI_API_ENDPOINT").rstrip("/")
if not key or key == "sk_your_key_here":
    sys.exit(2)


def accepts(base):
    """True/False for the key on this endpoint; None when it can't be reached."""
    api = re.sub(r"/api$", "", base) + "/api"
    req = urllib.request.Request(f"{api}/agents/blueprints/ad", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=20):
            return True
    except urllib.error.HTTPError as e:
        return False if e.code in (401, 403) else None
    except Exception:
        return None


candidates = [endpoint] + [u for u in DEPLOYMENTS.values() if u.rstrip("/") != endpoint]
results = {u: accepts(u) for u in candidates}
good = next((u for u in candidates if results[u]), None)
if good is None:
    if any(r is None for r in results.values()):
        print(f"env: could not reach the API to check the key; keeping ATAI_API_ENDPOINT={endpoint}")
        sys.exit(0)
    print("The API key was rejected by production and by the free trial: check it and rerun ./setup.sh.")
    sys.exit(3)
if good != endpoint:
    put("ATAI_API_ENDPOINT", good)
    open(".env", "w").write(env)
name = next((n for n, u in DEPLOYMENTS.items() if u == good), good)
print(f"env: the key works on {name}; .env has ATAI_API_KEY (hidden) and ATAI_API_ENDPOINT={good}")
EOF
status=$?
set -e

if [ "$status" = 2 ]; then
    say ""
    say "Almost done: no API key yet (needed from Step 2 / Stage 4 on). In your own terminal, run"
    say "  cd \"$PWD\" && ./setup.sh"
    say "and type the key at the hidden prompt (production or free trial: the endpoint is found for you)."
    exit 2
fi
[ "$status" = 0 ] || exit "$status"
say "ready: source .venv/bin/activate"
