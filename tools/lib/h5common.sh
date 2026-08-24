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

# Encode a byte-oriented path for the JSON report contract.  Bash cannot hold a
# NUL (and Unix paths cannot contain one), but every other byte is handled: valid
# UTF-8 remains readable, while literal percent signs, controls, DEL, and bytes
# outside well-formed UTF-8 become uppercase %HH escapes.  Keep this in sync
# with h5policy_path_encode in h5policy/pickles/h5_findings.pk.
encode_report_path() {
    local value=$1
    local LC_ALL=C
    local encoded="" piece char0
    local i=0 length=${#value}
    local b0=0 b1=0 b2=0 b3=0 sequence_length=0

    while ((i < length)); do
        char0=${value:i:1}
        printf -v b0 '%d' "'$char0"
        sequence_length=0

        if ((b0 == 0x25 || b0 < 0x20 || b0 == 0x7f)); then
            printf -v piece '%%%02X' "$b0"
            encoded+=$piece
            i=$((i + 1))
        elif ((b0 < 0x80)); then
            encoded+=$char0
            i=$((i + 1))
        else
            if ((b0 >= 0xc2 && b0 <= 0xdf && i + 1 < length)); then
                printf -v b1 '%d' "'${value:i+1:1}"
                if ((b1 >= 0x80 && b1 <= 0xbf)); then
                    sequence_length=2
                fi
            elif ((b0 >= 0xe0 && b0 <= 0xef && i + 2 < length)); then
                printf -v b1 '%d' "'${value:i+1:1}"
                printf -v b2 '%d' "'${value:i+2:1}"
                if ((b2 >= 0x80 && b2 <= 0xbf)) \
                   && { ((b0 == 0xe0 && b1 >= 0xa0 && b1 <= 0xbf)) \
                        || ((b0 == 0xed && b1 >= 0x80 && b1 <= 0x9f)) \
                        || ((b0 != 0xe0 && b0 != 0xed \
                             && b1 >= 0x80 && b1 <= 0xbf)); }; then
                    sequence_length=3
                fi
            elif ((b0 >= 0xf0 && b0 <= 0xf4 && i + 3 < length)); then
                printf -v b1 '%d' "'${value:i+1:1}"
                printf -v b2 '%d' "'${value:i+2:1}"
                printf -v b3 '%d' "'${value:i+3:1}"
                if ((b2 >= 0x80 && b2 <= 0xbf \
                      && b3 >= 0x80 && b3 <= 0xbf)) \
                   && { ((b0 == 0xf0 && b1 >= 0x90 && b1 <= 0xbf)) \
                        || ((b0 == 0xf4 && b1 >= 0x80 && b1 <= 0x8f)) \
                        || ((b0 != 0xf0 && b0 != 0xf4 \
                             && b1 >= 0x80 && b1 <= 0xbf)); }; then
                    sequence_length=4
                fi
            fi

            if ((sequence_length == 0)); then
                printf -v piece '%%%02X' "$b0"
                encoded+=$piece
                i=$((i + 1))
            else
                encoded+=${value:i:sequence_length}
                i=$((i + sequence_length))
            fi
        fi
    done

    printf '%s' "$encoded"
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
