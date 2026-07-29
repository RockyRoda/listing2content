#!/usr/bin/env bash
# macOS entry point. Delegates to stop-unix.sh, shared with stop-linux.sh.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stop-unix.sh" "$@"
