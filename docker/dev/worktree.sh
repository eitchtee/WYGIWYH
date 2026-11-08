#!/bin/sh
# Prepares or tears down the dev environment of an extra git worktree.
#   sh docker/dev/worktree.sh            copy .env from the main checkout with free host ports, install host node_modules
#   sh docker/dev/worktree.sh teardown   stop this worktree's containers and delete its volumes
# Plain POSIX sh: no GNU-only flags, so it runs on Linux, macOS and Git for Windows.
set -eu

if [ "${1:-setup}" = "teardown" ]; then
    # Without .env compose can't find its config, and nothing was ever started here
    [ -f .env ] || exit 0
    exec docker compose down -v --remove-orphans
fi

main=$(git worktree list --porcelain | head -n 1 | cut -d ' ' -f 2-)
if [ "$main" = "$(git rev-parse --show-toplevel)" ]; then
    echo "This is the main checkout, nothing to do." >&2
    exit 0
fi

if [ ! -f .env ]; then
    if [ ! -f "$main/.env" ]; then
        echo "No .env in the main checkout ($main). Create it from .env.example first." >&2
        exit 1
    fi
    # Same folder name -> same offset, so re-creating a worktree keeps its ports
    off=$(( $(basename "$PWD" | cksum | cut -d ' ' -f 1) % 100 + 1 ))
    grep -v -E '^(OUTBOUND_PORT|WEBPACK_OUTBOUND_PORT|SQL_OUTBOUND_PORT)=' "$main/.env" > .env || true
    {
        echo ""
        echo "# Host ports for this worktree, set by docker/dev/worktree.sh"
        echo "OUTBOUND_PORT=$((18000 + off))"
        echo "WEBPACK_OUTBOUND_PORT=$((15100 + off))"
        echo "SQL_OUTBOUND_PORT=$((15400 + off))"
    } >> .env
    echo "Created .env: app on http://localhost:$((18000 + off))"
fi

# For tools run on the host (the vite container keeps its own copy in a volume)
if command -v npm > /dev/null 2>&1; then
    npm ci --prefix frontend --no-audit --no-fund
else
    echo "npm not found, skipping frontend/node_modules." >&2
fi
