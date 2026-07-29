#!/usr/bin/env bash
# Linux entry point. Delegates to stop-unix.sh, shared with stop-mac.sh.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stop-unix.sh" "$@"
