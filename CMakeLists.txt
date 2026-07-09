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

cmake_minimum_required(VERSION 3.19)

project(h5markers LANGUAGES CXX)


add_executable(h5markers
    src/h5markers.cpp
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

target_compile_options(h5markers PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-Wall -Wextra -Wpedantic>
    $<$<CXX_COMPILER_ID:MSVC>:/W4>
)

find_package(Threads REQUIRED)
target_link_libraries(h5markers PRIVATE Threads::Threads)

find_package(Python3 COMPONENTS Interpreter REQUIRED)

set(PKDOC_SPECS
    drv_info
    earray
    farray
    fheap
    ohdr_msgs
    stab
    superblock
    v1_btree
    v2_btree
)

set(PKDOC_GENERATED_FILES)
set(PKDOC_SOURCE_FILES "${CMAKE_CURRENT_SOURCE_DIR}/tools/pkdoc.py")
set(PKDOC_CHECK_COMMANDS)

foreach(PKDOC_SPEC IN LISTS PKDOC_SPECS)
    set(PKDOC_SIDECAR "${CMAKE_CURRENT_SOURCE_DIR}/docs/spec/${PKDOC_SPEC}.yml")
    set(PKDOC_PICKLE "${CMAKE_CURRENT_SOURCE_DIR}/pickles/${PKDOC_SPEC}.pk")
    set(PKDOC_OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/docs/generated/${PKDOC_SPEC}.md")

    list(APPEND PKDOC_GENERATED_FILES "${PKDOC_OUTPUT}")
    list(APPEND PKDOC_SOURCE_FILES "${PKDOC_SIDECAR}" "${PKDOC_PICKLE}")
    list(APPEND PKDOC_CHECK_COMMANDS
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/pkdoc.py"
                --doc "${PKDOC_SIDECAR}"
                --check
    )

    add_custom_command(
        OUTPUT "${PKDOC_OUTPUT}"
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/pkdoc.py"
                --doc "${PKDOC_SIDECAR}"
                --out "${PKDOC_OUTPUT}"
        DEPENDS
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/pkdoc.py"
            "${PKDOC_SIDECAR}"
            "${PKDOC_PICKLE}"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        COMMENT "Generating docs/generated/${PKDOC_SPEC}.md"
        VERBATIM
    )
endforeach()

add_custom_target(docs
    DEPENDS ${PKDOC_GENERATED_FILES}
)

add_custom_target(docs-check
    ${PKDOC_CHECK_COMMANDS}
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    COMMENT "Checking generated documentation sidecars"
    VERBATIM
    USES_TERMINAL
)

# ---- h5policy regression suite (CTest) -------------------------------------
# Runs h5policy/tests/run.sh: datatype unit checks, the corpus, and the
# differential harness.  Requires GNU poke and python3 with h5py; if either is
# missing the test is skipped rather than reported as a failure (h5dump/h5debug
# are optional and the harness degrades gracefully without them).
enable_testing()

find_program(POKE_EXECUTABLE poke)
execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c "import h5py"
    RESULT_VARIABLE H5POLICY_H5PY_RC
    OUTPUT_QUIET ERROR_QUIET
)

if(POKE_EXECUTABLE AND H5POLICY_H5PY_RC EQUAL 0)
    add_test(
        NAME h5policy_regression
        COMMAND "${CMAKE_CURRENT_SOURCE_DIR}/h5policy/tests/run.sh"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(h5policy_regression PROPERTIES TIMEOUT 300)
    add_test(
        NAME h5patch_regression
        COMMAND "${CMAKE_CURRENT_SOURCE_DIR}/h5patch/tests/run.sh"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(h5patch_regression PROPERTIES TIMEOUT 120)
    message(STATUS "h5policy regression test enabled (poke: ${POKE_EXECUTABLE})")
else()
    message(STATUS "h5policy/h5patch regression tests skipped (needs poke and python3 h5py)")
endif()

# ---- emacs-check target ------------------------------------------------------

set(EMACS_EXECUTABLE "emacs" CACHE STRING "Emacs executable used by emacs-check")
set(EMACS_SOURCES
    "${CMAKE_CURRENT_SOURCE_DIR}/emacs/hdf5-poke-core.el"
    "${CMAKE_CURRENT_SOURCE_DIR}/emacs/hdf5-poke-ui.el"
    "${CMAKE_CURRENT_SOURCE_DIR}/emacs/hdf5-poke.el"
)
set(EMACS_BYTE_COMPILE_DIR "${CMAKE_CURRENT_BINARY_DIR}/emacs-byte-compile")
set(EMACS_BYTE_COMPILE_DEST_EXPR
    "(setq byte-compile-dest-file-function (lambda (file) (expand-file-name (concat (file-name-nondirectory file) \"c\") \"${EMACS_BYTE_COMPILE_DIR}\")))"
)
set(EMACS_FIXTURE_DIR "${CMAKE_CURRENT_BINARY_DIR}/emacs/tests/fixtures")

add_custom_target(emacs-check
    COMMAND "${CMAKE_COMMAND}" -E make_directory
            "${EMACS_BYTE_COMPILE_DIR}"
            "${EMACS_FIXTURE_DIR}"
    COMMAND "${EMACS_EXECUTABLE}" -Q --batch -L "${CMAKE_CURRENT_SOURCE_DIR}/emacs"
            --eval "${EMACS_BYTE_COMPILE_DEST_EXPR}"
            -f batch-byte-compile ${EMACS_SOURCES}
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/emacs/tests/fixtures/make_hdf5_fixtures.py"
            "${EMACS_FIXTURE_DIR}"
    COMMAND "${EMACS_EXECUTABLE}" -Q --batch
            -l "${CMAKE_CURRENT_SOURCE_DIR}/emacs/tests/hdf5-poke-test.el"
            -f ert-run-tests-batch-and-exit
    COMMAND "${CMAKE_COMMAND}" -E env
            "HDF5_POKE_TEST_FIXTURES=${EMACS_FIXTURE_DIR}"
            "${EMACS_EXECUTABLE}" -Q --batch
            -l "${CMAKE_CURRENT_SOURCE_DIR}/emacs/tests/hdf5-poke-process-test.el"
            -f ert-run-tests-batch-and-exit
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    COMMENT "Running Emacs byte compilation and ERT tests"
    VERBATIM
    USES_TERMINAL
)
