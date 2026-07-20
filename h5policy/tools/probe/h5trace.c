/* Copyright (C) 2026 The HDF Group.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 * h5trace -- an LD_PRELOAD activation interposer.
 *
 * The h5policy corpus expectations forbid a handful of OS-observable activation
 * events on a hostile file: external/VDS/EFL file opens, filter-plugin dlopen,
 * writes, and (implicitly) network.  This library records those events from the
 * outside, WITHOUT instrumenting libhdf5, so a probe run against any exact build
 * can prove them absent.  Internal event counters (cache insertion order, ID
 * registration, materialization ordering) need a patched libhdf5 and are a
 * separate, cross-repo effort; this is the OS-level second layer.
 *
 * It interposes the file-open, dlopen, and network entry points and appends one
 * tab-separated event line per occurrence to the file descriptor named by
 * $H5TRACE_FD.  Per-event, unbuffered writes mean the trace survives even if
 * libhdf5 crashes the process.  Path classification (input vs foreign vs system
 * noise) is deliberately left to the wrapper, which is easier to maintain than C
 * string prefix logic; this library reports raw facts only.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <dlfcn.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

static int trace_fd = -1;

__attribute__((constructor))
static void h5trace_init(void)
{
    const char *fd = getenv("H5TRACE_FD");
    trace_fd = fd ? atoi(fd) : -1;
}

/* One event line, written with the real write(2) so we never re-enter our own
 * open interposer.  Best-effort: a short write on the trace pipe is ignored. */
static void emit(const char *kind, const char *a, const char *b)
{
    if (trace_fd < 0) return;
    char line[4352];
    int n;
    if (b)
        n = snprintf(line, sizeof line, "%s\t%s\t%s\n", kind, a ? a : "", b);
    else
        n = snprintf(line, sizeof line, "%s\t%s\n", kind, a ? a : "");
    if (n > 0) {
        ssize_t (*real_write)(int, const void *, size_t) =
            (ssize_t (*)(int, const void *, size_t))dlsym(RTLD_NEXT, "write");
        if (real_write) real_write(trace_fd, line, (size_t)((size_t)n < sizeof line ? n : sizeof line));
    }
}

/* A file opened with any write intent is a mutation/creation attempt; anything
 * else is a read.  HDF5 opening the input read-only is a read, and the wrapper
 * filters that path out; a write-open of any path is always reported. */
static const char *open_mode(int flags)
{
    if ((flags & O_ACCMODE) == O_WRONLY || (flags & O_ACCMODE) == O_RDWR ||
        (flags & (O_CREAT | O_TRUNC)))
        return "W";
    return "R";
}

#define REAL(name, ret, ...)                                                   \
    static ret (*real_##name)(__VA_ARGS__);                                    \
    if (!real_##name)                                                          \
        real_##name = (ret (*)(__VA_ARGS__))dlsym(RTLD_NEXT, #name);

int open(const char *path, int flags, ...)
{
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list ap; va_start(ap, flags); mode = (mode_t)va_arg(ap, int); va_end(ap);
    }
    REAL(open, int, const char *, int, ...);
    emit("OPEN", open_mode(flags), path);
    return real_open(path, flags, mode);
}

int open64(const char *path, int flags, ...)
{
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list ap; va_start(ap, flags); mode = (mode_t)va_arg(ap, int); va_end(ap);
    }
    REAL(open64, int, const char *, int, ...);
    emit("OPEN", open_mode(flags), path);
    return real_open64(path, flags, mode);
}

int openat(int dirfd, const char *path, int flags, ...)
{
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list ap; va_start(ap, flags); mode = (mode_t)va_arg(ap, int); va_end(ap);
    }
    REAL(openat, int, int, const char *, int, ...);
    emit("OPEN", open_mode(flags), path);
    return real_openat(dirfd, path, flags, mode);
}

FILE *fopen(const char *path, const char *mode)
{
    REAL(fopen, FILE *, const char *, const char *);
    emit("OPEN", (mode && (strchr(mode, 'w') || strchr(mode, 'a') ||
                           strchr(mode, '+'))) ? "W" : "R", path);
    return real_fopen(path, mode);
}

void *dlopen(const char *file, int flags)
{
    REAL(dlopen, void *, const char *, int);
    emit("DLOPEN", file ? file : "(null)", NULL);
    return real_dlopen(file, flags);
}

int socket(int domain, int type, int protocol)
{
    REAL(socket, int, int, int, int);
    if (domain == AF_INET || domain == AF_INET6)
        emit("NET", "socket", "inet");
    return real_socket(domain, type, protocol);
}

int connect(int fd, const struct sockaddr *addr, socklen_t len)
{
    REAL(connect, int, int, const struct sockaddr *, socklen_t);
    if (addr && (addr->sa_family == AF_INET || addr->sa_family == AF_INET6))
        emit("NET", "connect", "inet");
    return real_connect(fd, addr, len);
}
