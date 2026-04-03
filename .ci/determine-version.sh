#!/bin/sh
# Get version file from server, bump it, then push it back
set -eu

REMOTE_VERSION="$REMOTE_BASE/mkosi.version"

# fetch current version from server, or start fresh
scp -P "$SSH_PORT" "$SSH_HOST:$REMOTE_VERSION" mkosi.version || true

mkosi bump

# write back immediately to claim this version
scp -P "$SSH_PORT" mkosi.version "$SSH_HOST:$REMOTE_VERSION"
