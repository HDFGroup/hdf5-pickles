/* main.cpp - File format marker scanner.  */

/* Copyright (C) 2026 The HDF Group.  */

/* This program is free software: you can redistribute it and/or modify
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
 */

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fcntl.h>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>

namespace {

struct Marker {
    std::string name;
    std::string description;
    std::string group;
    std::vector<std::uint8_t> bytes;
};

struct Match {
    std::uint64_t offset;
    std::string marker_name;
};

struct Options {
    std::optional<std::string> file_path;
    std::optional<std::size_t> thread_count;
    std::optional<std::string> group_filter;
    bool list_markers = false;
    bool help = false;
};

// Each block is read in one pread call to bound per-thread memory usage.
// 8 MiB is a reasonable unit for sequential I/O on modern hardware.
constexpr std::size_t kScanBlockSize = 8ULL * 1024ULL * 1024ULL;

// Chunks smaller than this don't benefit meaningfully from additional threads.
constexpr std::size_t kMinChunkSize = 1ULL * 1024ULL * 1024ULL;

// Thrown for command-line mistakes so the caller can print usage alongside the
// error message.  Other std::runtime_errors are I/O or logic errors where the
// usage text adds no value.
class UsageError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

class FileDescriptor {
  public:
    explicit FileDescriptor(int fd)
        : fd_(fd) {
    }

    ~FileDescriptor() {
        if (fd_ >= 0) {
            ::close(fd_);
        }
    }

    FileDescriptor(const FileDescriptor &) = delete;
    FileDescriptor &operator=(const FileDescriptor &) = delete;

    int get() const {
        return fd_;
    }

  private:
    int fd_;
};

std::vector<Marker> build_markers() {
    return {
        {"HDF5_SIGNATURE", "HDF5 file signature", "HDF5",
         {0x89, 0x48, 0x44, 0x46, 0x0d, 0x0a, 0x1a, 0x0a}},
        {"TREE", "Version 1 B-tree node", "HDF5", {'T', 'R', 'E', 'E'}},
        {"BTHD", "Version 2 B-tree header", "HDF5", {'B', 'T', 'H', 'D'}},
        {"BTIN", "Version 2 B-tree internal node", "HDF5", {'B', 'T', 'I', 'N'}},
        {"BTLF", "Version 2 B-tree leaf node", "HDF5", {'B', 'T', 'L', 'F'}},
        {"SNOD", "Symbol table node", "HDF5", {'S', 'N', 'O', 'D'}},
        {"HEAP", "Local heap", "HDF5", {'H', 'E', 'A', 'P'}},
        {"GCOL", "Global heap collection", "HDF5", {'G', 'C', 'O', 'L'}},
        {"FRHP", "Fractal heap header", "HDF5", {'F', 'R', 'H', 'P'}},
        {"FHDB", "Fractal heap direct block", "HDF5", {'F', 'H', 'D', 'B'}},
        {"FHIB", "Fractal heap indirect block", "HDF5", {'F', 'H', 'I', 'B'}},
        {"FSHD", "Free-space manager header", "HDF5", {'F', 'S', 'H', 'D'}},
        {"FSSE", "Free-space section information", "HDF5", {'F', 'S', 'S', 'E'}},
        {"SMTB", "Shared Object Header Message table", "HDF5", {'S', 'M', 'T', 'B'}},
        {"SMLI", "Shared message record list", "HDF5", {'S', 'M', 'L', 'I'}},
        {"OHDR", "Version 2 object header", "HDF5", {'O', 'H', 'D', 'R'}},
        {"OCHK", "Version 2 object header continuation block", "HDF5",
         {'O', 'C', 'H', 'K'}},
        {"FAHD", "Fixed Array header", "HDF5", {'F', 'A', 'H', 'D'}},
        {"FADB", "Fixed Array data block", "HDF5", {'F', 'A', 'D', 'B'}},
        {"EAHD", "Extensible Array header", "HDF5", {'E', 'A', 'H', 'D'}},
        {"EAIB", "Extensible Array index block", "HDF5", {'E', 'A', 'I', 'B'}},
        {"EASB", "Extensible Array secondary block", "HDF5", {'E', 'A', 'S', 'B'}},
        {"EADB", "Extensible Array data block", "HDF5", {'E', 'A', 'D', 'B'}},
        {"OHDH", "Onion History Data Header", "Onion", {'O', 'H', 'D', 'H'}},
        {"OWHR", "Onion Whole-History Record", "Onion", {'O', 'W', 'H', 'R'}},
        {"ORRS", "Onion Revision Record Signature", "Onion", {'O', 'R', 'R', 'S'}},
    };
}

const std::vector<Marker> &markers() {
    static const std::vector<Marker> all_markers = build_markers();
    return all_markers;
}

std::array<std::vector<std::size_t>, 256> build_buckets() {
    std::array<std::vector<std::size_t>, 256> buckets;

    for (std::size_t i = 0; i < markers().size(); ++i) {
        const auto first_byte = static_cast<unsigned char>(markers()[i].bytes.front());
        buckets[first_byte].push_back(i);
    }

    return buckets;
}

const std::array<std::vector<std::size_t>, 256> &marker_buckets() {
    static const auto buckets = build_buckets();
    return buckets;
}

std::size_t max_marker_length() {
    static const std::size_t max_len = []() {
        std::size_t len = 0;
        for (const auto &marker : markers()) {
            len = std::max(len, marker.bytes.size());
        }
        return len;
    }();
    return max_len;
}

std::size_t max_marker_name_width() {
    static const std::size_t width = []() {
        std::size_t w = 0;
        for (const auto &marker : markers()) {
            w = std::max(w, marker.name.size());
        }
        return w;
    }();
    return width;
}

std::vector<std::string> known_groups() {
    std::vector<std::string> groups;
    for (const auto &marker : markers()) {
        if (std::find(groups.begin(), groups.end(), marker.group) == groups.end()) {
            groups.push_back(marker.group);
        }
    }
    return groups;
}

void print_usage(std::ostream &out, const char *argv0) {
    out << "Usage:\n"
        << "  " << argv0 << " [--list-markers/-l] [FILE]\n"
        << "  " << argv0 << " [--threads/-j N] [--group GROUP] FILE\n"
        << "  " << argv0 << " --help\n"
        << "\n"
        << "Groups: ";
    const auto groups = known_groups();
    for (std::size_t i = 0; i < groups.size(); ++i) {
        if (i != 0) {
            out << ", ";
        }
        out << groups[i];
    }
    out << '\n';
}

std::string format_errno(const std::string &context) {
    std::ostringstream oss;
    oss << context << ": " << std::strerror(errno);
    return oss.str();
}

Options parse_options(int argc, char **argv) {
    Options options;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];

        if (arg == "--help" || arg == "-h") {
            options.help = true;
            continue;
        }

        if (arg == "--list-markers" || arg == "-l") {
            options.list_markers = true;
            continue;
        }

        if (arg == "--threads" || arg == "-j") {
            if (i + 1 >= argc) {
                throw UsageError("missing value for --threads");
            }

            const std::string value = argv[++i];
            std::size_t parsed = 0;

            try {
                parsed = std::stoull(value);
            }
            catch (const std::exception &) {
                throw UsageError("invalid thread count: " + value);
            }

            if (parsed == 0) {
                throw UsageError("thread count must be greater than zero");
            }

            options.thread_count = parsed;
            continue;
        }

        if (arg == "--group") {
            if (i + 1 >= argc) {
                throw UsageError("missing value for --group");
            }
            options.group_filter = argv[++i];
            continue;
        }

        if (options.file_path.has_value()) {
            throw UsageError("multiple input files were provided");
        }

        options.file_path = arg;
    }

    if (!options.help && !options.list_markers && !options.file_path.has_value()) {
        throw UsageError("an input file is required unless --list-markers/-l is used");
    }

    return options;
}

std::string bytes_to_hex(const std::vector<std::uint8_t> &bytes) {
    std::ostringstream oss;
    oss << std::hex << std::uppercase << std::setfill('0');

    for (std::size_t i = 0; i < bytes.size(); ++i) {
        if (i != 0) {
            oss << ' ';
        }
        oss << std::setw(2) << static_cast<unsigned int>(bytes[i]);
    }

    return oss.str();
}

void list_markers(std::ostream &out, const std::optional<std::string> &group_filter) {
    out << "Markers defined in the HDF5 and Onion formats:\n\n";

    std::string current_group;
    const std::size_t col_width = max_marker_name_width();
    for (const auto &marker : markers()) {
        if (group_filter.has_value() && marker.group != *group_filter) {
            continue;
        }

        if (marker.group != current_group) {
            current_group = marker.group;
            out << current_group << ":\n";
        }

        out << "  " << std::left << std::setfill(' ')
            << std::setw(static_cast<int>(col_width)) << marker.name
            << "  " << marker.description;

        const bool has_non_ascii = std::any_of(marker.bytes.begin(), marker.bytes.end(),
            [](std::uint8_t b) { return b < 0x20 || b > 0x7e; });
        if (has_non_ascii) {
            out << " = " << bytes_to_hex(marker.bytes);
        }

        out << '\n';
    }
}

void pread_all(int fd, std::uint8_t *buffer, std::size_t size, std::uint64_t offset) {
    std::size_t total_read = 0;

    while (total_read < size) {
        const auto file_offset = static_cast<off_t>(offset + total_read);
        const ssize_t bytes_read = ::pread(fd, buffer + total_read, size - total_read, file_offset);

        if (bytes_read < 0) {
            if (errno == EINTR) {
                continue;
            }
            throw std::runtime_error(format_errno("pread failed"));
        }

        if (bytes_read == 0) {
            throw std::runtime_error("unexpected end of file while scanning");
        }

        total_read += static_cast<std::size_t>(bytes_read);
    }
}

std::size_t choose_thread_count(std::uint64_t file_size, std::optional<std::size_t> requested) {
    std::size_t thread_count = requested.value_or(std::max<std::size_t>(1, std::thread::hardware_concurrency()));

    if (file_size == 0) {
        return 1;
    }

    const std::size_t max_useful_threads =
        std::max<std::size_t>(1, (file_size + kMinChunkSize - 1) / kMinChunkSize);

    return std::max<std::size_t>(1, std::min(thread_count, max_useful_threads));
}

std::vector<Match> scan_range(int fd, std::uint64_t file_size, std::uint64_t start, std::uint64_t end,
                               const std::optional<std::string> &group_filter,
                               std::atomic<std::uint64_t> &bytes_scanned) {
    std::vector<Match> matches;

    if (start >= end) {
        return matches;
    }

    const std::size_t overlap = max_marker_length() - 1;
    std::vector<std::uint8_t> buffer;

    for (std::uint64_t block_start = start; block_start < end; block_start += kScanBlockSize) {
        const std::uint64_t block_end = std::min<std::uint64_t>(end, block_start + kScanBlockSize);
        const std::uint64_t read_end = std::min<std::uint64_t>(file_size, block_end + overlap);
        const std::size_t bytes_to_read = static_cast<std::size_t>(read_end - block_start);
        const std::size_t owned_bytes = static_cast<std::size_t>(block_end - block_start);

        buffer.resize(bytes_to_read);
        pread_all(fd, buffer.data(), buffer.size(), block_start);

        for (std::size_t i = 0; i < owned_bytes; ++i) {
            const auto &candidate_markers = marker_buckets()[buffer[i]];

            for (const std::size_t marker_index : candidate_markers) {
                const auto &marker = markers()[marker_index];

                if (group_filter.has_value() && marker.group != *group_filter) {
                    continue;
                }

                if (i + marker.bytes.size() > buffer.size()) {
                    continue;
                }

                if (std::memcmp(buffer.data() + i, marker.bytes.data(), marker.bytes.size()) == 0) {
                    matches.push_back(Match{block_start + i, marker.name});
                }
            }
        }

        bytes_scanned.fetch_add(owned_bytes, std::memory_order_relaxed);
    }

    return matches;
}

void print_matches(const std::vector<Match> &matches, std::ostream &out) {
    const std::size_t col_width = max_marker_name_width();
    for (const auto &match : matches) {
        out << std::left << std::setfill(' ') << std::setw(static_cast<int>(col_width))
            << match.marker_name
            << "  0x" << std::right << std::setfill('0') << std::setw(16)
            << std::hex << std::uppercase << match.offset << std::dec << std::setfill(' ')
            << " (" << match.offset << ")\n";
    }
}

} // namespace

int main(int argc, char **argv) {
    try {
        Options options;
        try {
            options = parse_options(argc, argv);
        }
        catch (const UsageError &error) {
            std::cerr << "error: " << error.what() << '\n';
            print_usage(std::cerr, argv[0]);
            return 1;
        }

        if (options.help) {
            print_usage(std::cout, argv[0]);
            return 0;
        }

        if (options.group_filter.has_value()) {
            const auto groups = known_groups();
            if (std::find(groups.begin(), groups.end(), *options.group_filter) == groups.end()) {
                std::cerr << "error: unknown group '" << *options.group_filter << "'\n";
                print_usage(std::cerr, argv[0]);
                return 1;
            }
        }

        if (options.list_markers) {
            list_markers(std::cout, options.group_filter);
            if (!options.file_path.has_value()) {
                return 0;
            }
            std::cout << '\n';
        }

        const std::filesystem::path input_path = *options.file_path;
        const std::uint64_t file_size = std::filesystem::file_size(input_path);
        const std::size_t thread_count = choose_thread_count(file_size, options.thread_count);

        const int raw_fd = ::open(input_path.c_str(), O_RDONLY);
        if (raw_fd < 0) {
            throw std::runtime_error(format_errno("failed to open " + input_path.string()));
        }
        FileDescriptor fd(raw_fd);

        std::vector<std::thread> threads;
        std::vector<std::vector<Match>> thread_matches(thread_count);
        std::exception_ptr worker_error;
        std::mutex worker_error_mutex;

        std::atomic<std::uint64_t> bytes_scanned{0};
        std::atomic<bool> scan_done{false};

        const std::uint64_t chunk_size = (file_size + thread_count - 1) / thread_count;

        for (std::size_t i = 0; i < thread_count; ++i) {
            const std::uint64_t start = chunk_size * i;
            const std::uint64_t end = std::min<std::uint64_t>(file_size, start + chunk_size);

            threads.emplace_back([&, i, start, end]() {
                try {
                    thread_matches[i] = scan_range(fd.get(), file_size, start, end,
                                                   options.group_filter, bytes_scanned);
                }
                catch (...) {
                    std::lock_guard<std::mutex> lock(worker_error_mutex);
                    if (!worker_error) {
                        worker_error = std::current_exception();
                    }
                }
            });
        }

        // Show progress on stderr when scanning large files in a terminal.
        std::thread progress_thread;
        const bool show_progress = file_size > 0 && ::isatty(STDERR_FILENO);
        if (show_progress) {
            progress_thread = std::thread([&]() {
                while (!scan_done.load(std::memory_order_relaxed)) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(500));
                    if (scan_done.load(std::memory_order_relaxed)) {
                        break;
                    }
                    const std::uint64_t scanned = bytes_scanned.load(std::memory_order_relaxed);
                    const int pct = static_cast<int>(scanned * 100 / file_size);
                    std::cerr << '\r' << scanned << " / " << file_size
                              << " bytes (" << pct << "%)   " << std::flush;
                }
                // Clear the progress line.
                std::cerr << '\r' << std::string(60, ' ') << '\r' << std::flush;
            });
        }

        for (auto &thread : threads) {
            thread.join();
        }

        scan_done.store(true, std::memory_order_relaxed);
        if (progress_thread.joinable()) {
            progress_thread.join();
        }

        if (worker_error) {
            std::rethrow_exception(worker_error);
        }

        std::vector<Match> matches;
        for (auto &partial : thread_matches) {
            matches.insert(matches.end(), partial.begin(), partial.end());
        }

        std::sort(matches.begin(), matches.end(), [](const Match &left, const Match &right) {
            if (left.offset != right.offset) {
                return left.offset < right.offset;
            }
            return left.marker_name < right.marker_name;
        });

        print_matches(matches, std::cout);
    }
    catch (const std::exception &error) {
        std::cerr << "error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
