#!/usr/bin/env bash
# macOS entry point. The Docker commands are identical on macOS and Linux, so
# both delegate to start-unix.sh rather than keeping two copies in sync.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/start-unix.sh" "$@"
