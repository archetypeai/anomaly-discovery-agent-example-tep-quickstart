#!/usr/bin/env bash
# One-step setup: Git LFS data, a Python virtual environment, requirements, and .env.
#
#     ./setup.sh
#
# Safe to rerun. The API key and endpoint come from your environment
# (ATAI_API_KEY, ATAI_API_ENDPOINT) or, when run in a terminal, from a hidden
# prompt. Values are written to .env and never printed.
#
# Exit status: 0 ready, 2 set up but the API key is missing (Stages 0-3 still work).
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '%s\n' "$*"; }

# 1. Git LFS: the prepared data and role files are LFS objects.
if ! command -v git-lfs >/dev/null 2>&1; then
    say "Git LFS is not installed. Install it (macOS: brew install git-lfs), then rerun ./setup.sh."
    exit 1
fi
if head -c 40 data/roles/library/tep_ref_normal_sim001.csv | grep -q "git-lfs.github.com"; then
    say "fetching the LFS data files (~140 MB)"
    git lfs install --local >/dev/null
    git lfs pull
fi
say "data: LFS files present"

# 2. Python virtual environment and requirements. Prefer the newest Python 3.10+ on PATH:
#    macOS's stock python3 (3.9, with an old pip) can't install pyreadr's prebuilt wheel.
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
    if [ -n "$key" ] && [ -z "$endpoint" ]; then
        read -r -p "ATAI_API_ENDPOINT (Enter for the .env default; free trial: https://try.archetypeai.app/api): " endpoint
    fi
fi

ATAI_SETUP_KEY="$key" ATAI_SETUP_ENDPOINT="$endpoint" .venv/bin/python - <<'EOF'
import os, re
path, env = ".env", open(".env").read()
for name, value in (("ATAI_API_KEY", os.environ["ATAI_SETUP_KEY"]),
                    ("ATAI_API_ENDPOINT", os.environ["ATAI_SETUP_ENDPOINT"])):
    if value:
        line = f"{name}={value}"
        env = re.sub(rf"^{name}=.*$", lambda _: line, env, count=1, flags=re.M) \
            if re.search(rf"^{name}=", env, flags=re.M) else env.rstrip("\n") + f"\n{line}\n"
open(path, "w").write(env)
EOF

final_key="$(sed -n 's/^ATAI_API_KEY=//p' .env | head -1)"
final_endpoint="$(sed -n 's/^ATAI_API_ENDPOINT=//p' .env | head -1)"
if [ -z "$final_key" ] || [ "$final_key" = "sk_your_key_here" ]; then
    say ""
    say "Almost done: no API key yet (needed from Stage 4 on). In your own terminal, either"
    say "  export ATAI_API_KEY=...   (and ATAI_API_ENDPOINT=https://try.archetypeai.app/api on the free trial)"
    say "  ./setup.sh"
    say "or just run ./setup.sh there and type the key at the hidden prompt."
    exit 2
fi
say "env: .env has ATAI_API_KEY (hidden) and ATAI_API_ENDPOINT=$final_endpoint"
say "ready: source .venv/bin/activate"
