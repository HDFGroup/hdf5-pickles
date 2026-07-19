# h5common.sh - Shared shell helpers for the h5explain/h5policy/h5patch launchers.
#
# Copyright (C) 2026 The HDF Group.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Sourced, not executed.  Each launcher still resolves its own script path
# (that bootstrap has to run before this file can be located) and then sources
# this library for the escaping and load-path helpers below, so the tools share
# one canonical copy of the injection-sensitive quoting routines.

# Escape a value for interpolation into a double-quoted poke string literal.
escape_poke_string() {
    local value=$1
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    printf '%s' "$value"
}

# Escape a value for a poke dot-command file argument (e.g. `.file PATH`), where
# whitespace, `#`, and backslashes are the significant characters.
escape_poke_file_arg() {
    local value=$1
    local tab=$'\t'
    value=${value//\\/\\\\}
    value=${value//#/\\#}
    value=${value// /\\ }
    value=${value//"$tab"/\\"$tab"}
    printf '%s' "$value"
}

# Escape a value for a JSON string body (control characters that JSON forbids
# bare, plus quotes and backslashes).
escape_json_string() {
    local value=$1
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//$'\t'/\\t}
    value=${value//$'\r'/\\r}
    printf '%s' "$value"
}

# Resolve an absolute path, preferring readlink -f and falling back to a plain
# join when readlink is unavailable.
abs_path() {
    if command -v readlink >/dev/null 2>&1; then
        readlink -f -- "$1"
    else
        case "$1" in
            /*) printf '%s\n' "$1" ;;
            *) printf '%s/%s\n' "$PWD" "$1" ;;
        esac
    fi
}

# Export POKE_LOAD_PATH with the given directories (in order) prepended to any
# path already inherited from the environment.
h5_export_load_path() {
    local joined
    local IFS=:
    joined="$*"
    if [[ -n "${POKE_LOAD_PATH:-}" ]]; then
        export POKE_LOAD_PATH="$joined:$POKE_LOAD_PATH"
    else
        export POKE_LOAD_PATH="$joined"
    fi
}
