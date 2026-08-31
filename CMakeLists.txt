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
    dspace_enc
    dtype_enc
    earray
    farray
    fheap
    fsm
    gheap
    lheap
    mdci
    ohdr_msgs
    ref_enc
    sohm
    stab
    superblock
    v1_btree
    v2_btree
    vds
)

set(PKDOC_GENERATED_FILES)
set(PKDOC_SOURCE_FILES "${CMAKE_CURRENT_SOURCE_DIR}/tools/pkdoc.py")
set(PKDOC_CHECK_COMMANDS)
set(PKDOC_INDEX "${CMAKE_CURRENT_SOURCE_DIR}/docs/spec/index.yml")
set(PKDOC_INDEX_OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/docs/generated/README.md")

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
                --check-generated "${PKDOC_OUTPUT}"
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

list(APPEND PKDOC_GENERATED_FILES "${PKDOC_INDEX_OUTPUT}")
list(APPEND PKDOC_SOURCE_FILES "${PKDOC_INDEX}")
list(APPEND PKDOC_CHECK_COMMANDS
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/pkdoc.py"
            --index "${PKDOC_INDEX}"
            --check
            --check-generated "${PKDOC_INDEX_OUTPUT}"
)

add_custom_command(
    OUTPUT "${PKDOC_INDEX_OUTPUT}"
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/pkdoc.py"
            --index "${PKDOC_INDEX}"
            --out "${PKDOC_INDEX_OUTPUT}"
    DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/pkdoc.py"
        "${PKDOC_INDEX}"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    COMMENT "Generating docs/generated/README.md"
    VERBATIM
)

add_custom_target(docs
    DEPENDS ${PKDOC_GENERATED_FILES}
)

add_custom_target(docs-check
    ${PKDOC_CHECK_COMMANDS}
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_tutorial.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_quickstart.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/test_check_hygiene.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_advisory_draft.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/h5policy/tests/check_cache_image_docs.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/h5policy/tests/check_workflow_docs.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/h5policy/tests/check_profile_docs.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/h5patch/tests/check_docs.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/h5explain/tests/check_docs.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/h5policy/tests/check_lazy_docs.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_tool_overview.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_cli_docs.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_marker_docs.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_objectstore_example.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_markdown_links.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_hygiene.py"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/.devcontainer/check.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    COMMENT "Checking generated docs, commands, profiles, markers, summaries, links, tool map, hygiene, and devcontainer"
    VERBATIM
    USES_TERMINAL
)

# ---- regression suites (CTest) ----------------------------------------------
# Runs h5policy/tests/run.sh: synthetic unit checks, the corpus, and the
# differential harness.  Requires GNU poke and python3 with h5py; if either is
# missing the test is skipped rather than reported as a failure (h5dump/h5debug
# are optional and the harness degrades gracefully without them).
enable_testing()

find_program(POKE_EXECUTABLE poke)

add_test(
    NAME h5patch_docs_regression
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/h5patch/tests/check_docs.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
set_tests_properties(h5patch_docs_regression PROPERTIES TIMEOUT 30)

add_test(
    NAME h5explain_docs_regression
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/h5explain/tests/check_docs.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
set_tests_properties(h5explain_docs_regression PROPERTIES TIMEOUT 30)

add_test(
    NAME lazy_validation_docs_regression
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/h5policy/tests/check_lazy_docs.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
set_tests_properties(lazy_validation_docs_regression PROPERTIES TIMEOUT 90)

add_test(
    NAME h5policy_workflow_docs_regression
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/h5policy/tests/check_workflow_docs.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
set_tests_properties(h5policy_workflow_docs_regression PROPERTIES TIMEOUT 30)

add_test(
    NAME h5policy_profile_docs_regression
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/h5policy/tests/check_profile_docs.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
set_tests_properties(h5policy_profile_docs_regression PROPERTIES TIMEOUT 30)

add_test(
    NAME cli_docs_regression
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_cli_docs.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
set_tests_properties(cli_docs_regression PROPERTIES TIMEOUT 30)

add_test(
    NAME marker_docs_regression
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_marker_docs.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
set_tests_properties(marker_docs_regression PROPERTIES TIMEOUT 30)

add_test(
    NAME tool_overview_docs_regression
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_tool_overview.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
set_tests_properties(tool_overview_docs_regression PROPERTIES TIMEOUT 30)

add_test(
    NAME devcontainer_config_regression
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/.devcontainer/check.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
set_tests_properties(devcontainer_config_regression PROPERTIES TIMEOUT 30)

add_test(
    NAME devcontainer_policy_verdict_regression
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/.devcontainer/check.py"
            --policy-report
            "${CMAKE_CURRENT_SOURCE_DIR}/.devcontainer/testdata/h5policy-accept-with-warnings.json"
            --policy-exit 1
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
set_tests_properties(devcontainer_policy_verdict_regression PROPERTIES
    TIMEOUT 30
)

# The shared format pickles have synthetic byte-level unit tests that require
# GNU poke but do not require libhdf5 or h5py.
if(POKE_EXECUTABLE)
    add_test(
        NAME tutorial_docs_regression
        COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_tutorial.py"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(tutorial_docs_regression PROPERTIES TIMEOUT 30)

    add_test(
        NAME cache_image_docs_regression
        COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/h5policy/tests/check_cache_image_docs.py"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(cache_image_docs_regression PROPERTIES TIMEOUT 60)

    add_test(
        NAME pickle_ohdr_msgs_regression
        COMMAND "${POKE_EXECUTABLE}" --quiet -L
                "${CMAKE_CURRENT_SOURCE_DIR}/pickles/tests/unit_ohdr_msgs.pk"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(pickle_ohdr_msgs_regression PROPERTIES
        TIMEOUT 30
        ENVIRONMENT "POKE_LOAD_PATH=${CMAKE_CURRENT_SOURCE_DIR}/pickles"
    )
    add_test(
        NAME pickle_fheap_regression
        COMMAND "${POKE_EXECUTABLE}" --quiet -L
                "${CMAKE_CURRENT_SOURCE_DIR}/pickles/tests/unit_fheap.pk"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(pickle_fheap_regression PROPERTIES
        TIMEOUT 30
        ENVIRONMENT "POKE_LOAD_PATH=${CMAKE_CURRENT_SOURCE_DIR}/pickles"
    )
    add_test(
        NAME pickle_mdci_regression
        COMMAND "${POKE_EXECUTABLE}" --quiet -L
                "${CMAKE_CURRENT_SOURCE_DIR}/pickles/tests/unit_mdci.pk"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(pickle_mdci_regression PROPERTIES
        TIMEOUT 30
        ENVIRONMENT "POKE_LOAD_PATH=${CMAKE_CURRENT_SOURCE_DIR}/pickles"
    )
    add_test(
        NAME pickle_checksum_regression
        COMMAND "${POKE_EXECUTABLE}" --quiet -L
                "${CMAKE_CURRENT_SOURCE_DIR}/pickles/tests/unit_checksums.pk"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(pickle_checksum_regression PROPERTIES
        TIMEOUT 30
        ENVIRONMENT "POKE_LOAD_PATH=${CMAKE_CURRENT_SOURCE_DIR}/pickles"
    )
    add_test(
        NAME pickle_range_reference_regression
        COMMAND "${POKE_EXECUTABLE}" --quiet -L
                "${CMAKE_CURRENT_SOURCE_DIR}/pickles/tests/unit_ranges_refs.pk"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(pickle_range_reference_regression PROPERTIES
        TIMEOUT 30
        ENVIRONMENT "POKE_LOAD_PATH=${CMAKE_CURRENT_SOURCE_DIR}/pickles"
    )
    add_test(
        NAME pickle_ref_enc_regression
        COMMAND "${POKE_EXECUTABLE}" --quiet -L
                "${CMAKE_CURRENT_SOURCE_DIR}/pickles/tests/unit_ref_enc.pk"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(pickle_ref_enc_regression PROPERTIES
        TIMEOUT 30
        ENVIRONMENT "POKE_LOAD_PATH=${CMAKE_CURRENT_SOURCE_DIR}/pickles"
    )
    # The global-heap walk cases assert TERMINATION, so the timeout is part of
    # the assertion rather than a safety net: before the progress guard in
    # gheap.pk these inputs spun forever and this test would hang here instead
    # of reporting a failed expectation.
    add_test(
        NAME pickle_gheap_regression
        COMMAND "${POKE_EXECUTABLE}" --quiet -L
                "${CMAKE_CURRENT_SOURCE_DIR}/pickles/tests/unit_gheap.pk"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(pickle_gheap_regression PROPERTIES
        TIMEOUT 30
        ENVIRONMENT "POKE_LOAD_PATH=${CMAKE_CURRENT_SOURCE_DIR}/pickles"
    )
    add_test(
        NAME pickle_fsm_regression
        COMMAND "${POKE_EXECUTABLE}" --quiet -L
                "${CMAKE_CURRENT_SOURCE_DIR}/pickles/tests/unit_fsm.pk"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(pickle_fsm_regression PROPERTIES
        TIMEOUT 30
        ENVIRONMENT "POKE_LOAD_PATH=${CMAKE_CURRENT_SOURCE_DIR}/pickles"
    )
    message(STATUS "shared pickle regression tests enabled (poke: ${POKE_EXECUTABLE})")
else()
    message(STATUS "shared pickle regression tests skipped (needs poke)")
endif()

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
    # The suite runs the full corpus, the h5cve exact-build matrix, a 315-file
    # differential, the external CVE specimen corpus, truncation sweeps, and the
    # mutation family.  MEASURED 2026-08-26 on an unloaded host: 946s end to end,
    # of which the differential is 523s and the corpus cases 219s -- the two
    # phases that scale with fixture count, and the corpus has roughly doubled
    # (188 -> 350 expected fixtures) since this ceiling was first set.  It
    # exceeds the measurement again under parallel CTest load, so keep the
    # ceiling generous rather than tight; raise it with the corpus, and prefer
    # splitting the differential into its own test over trimming coverage to fit.
    set_tests_properties(h5policy_regression PROPERTIES TIMEOUT 1800)
    # cache_image_docs_regression reads h5policy/tests/valid/cache_image.h5,
    # which only exists once h5policy_regression's run.sh has (re)generated the
    # corpus; on a clean checkout, running it in registration order (before
    # h5policy_regression) hits a missing file. Anchor it after the corpus
    # exists instead.
    set_tests_properties(cache_image_docs_regression PROPERTIES
        DEPENDS h5policy_regression)
    add_test(
        NAME h5patch_regression
        COMMAND "${CMAKE_CURRENT_SOURCE_DIR}/h5patch/tests/run.sh"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(h5patch_regression PROPERTIES TIMEOUT 120)
    add_test(
        NAME h5explain_regression
        COMMAND "${CMAKE_CURRENT_SOURCE_DIR}/h5explain/tests/run.sh"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(h5explain_regression PROPERTIES TIMEOUT 180)
    message(STATUS "h5policy/h5patch/h5explain regression tests enabled (poke: ${POKE_EXECUTABLE})")
else()
    message(STATUS "h5policy/h5patch/h5explain regression tests skipped (needs poke and python3 h5py)")
endif()

# ---- emacs-check target ------------------------------------------------------

find_program(EMACS_EXECUTABLE emacs)
if(EMACS_EXECUTABLE AND H5POLICY_H5PY_RC EQUAL 0 AND POKE_EXECUTABLE)
    set(EMACS_TEST_COMMAND
        "${CMAKE_COMMAND}" -E env
        "EMACS=${EMACS_EXECUTABLE}"
        "PYTHON=${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/emacs/tests/run.sh"
        "${CMAKE_CURRENT_BINARY_DIR}/emacs/tests"
    )
    add_custom_target(emacs-check
        COMMAND ${EMACS_TEST_COMMAND}
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        COMMENT "Running Emacs byte compilation and ERT tests"
        VERBATIM
        USES_TERMINAL
    )
    add_test(
        NAME emacs_regression
        COMMAND ${EMACS_TEST_COMMAND}
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    set_tests_properties(emacs_regression PROPERTIES TIMEOUT 120)
else()
    message(STATUS "Emacs regression test skipped (needs emacs, poke, and python3 h5py)")
endif()
