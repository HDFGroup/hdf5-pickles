/* Create dense link storage whose records are fractal-heap HUGE objects.
 *
 * A link message larger than the dense link heap's maximum managed object size
 * (H5G_FHEAP_MAX_MAN_SIZE, 4096 bytes -- src/H5Gdense.c) is not stored in a
 * managed direct block.  libhdf5 writes it as a standalone file extent and
 * records it in the heap's huge-object v2 B-tree, so the name index's heap ID
 * holds a B-tree key instead of a doubling-table offset.  h5policy used to
 * decline that whole layout as a coverage gap.
 *
 * Usage: make_dense_huge_links OUTPUT.h5 (mixed|huge_only)
 *
 *   mixed      one short soft link (a MANAGED heap object) and one long one (a
 *              HUGE object), so both ID forms appear in one name index and the
 *              doubling-table root is defined.
 *   huge_only  only the long link, so the heap has NO managed blocks at all and
 *              its doubling-table root address is undefined.  That is a legal
 *              heap, and reading an undefined root as "empty heap" is what used
 *              to make this regime invisible -- it is a separate fixture for
 *              exactly that reason.
 *
 * h5py (the corpus writer) does not expose H5Pset_link_phase_change, and
 * without it a group needs nine links before it converts to dense storage,
 * which makes both fixtures an order of magnitude larger and slower to walk.
 * Forcing max_compact to zero from C keeps each file around 6 KB.
 */
#include <hdf5.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Comfortably above H5G_FHEAP_MAX_MAN_SIZE (4096) once the link message's
   version, flags, name and length fields are added; comfortably below the
   65535-byte limit of the soft-link value's own length field, so the file this
   writes is well formed. */
#define HUGE_TARGET_LEN 4200
#define MANAGED_TARGET_LEN 24

/* The malformed sibling (gencorpus _make_dense_link_heap_object_slack) shrinks
   the huge soft link's stored value length by exactly this much.  A group with
   the shortened path is created here so that the patched link still RESOLVES:
   the point of that fixture is that libhdf5 accepts it and silently follows a
   DIFFERENT object, which is what the real H5Lcreate_soft truncation does.  A
   dangling shortened target would make libhdf5 fail the lookup instead, and the
   guard would then prove nothing about silent substitution.  Keep this in step
   with _SLACK_BYTES in tools/h5policy-gencorpus. */
#define SLACK_BYTES 100

/* "/" + (n-1) repeats of 'd': a path of exactly n bytes. */
static char *
long_path(size_t n)
{
    char *target = malloc(n + 1);

    if (NULL == target)
        return NULL;
    target[0] = '/';
    memset(target + 1, 'd', n - 1);
    target[n] = '\0';
    return target;
}

static herr_t
add_soft(hid_t group, const char *name, const char *target)
{
    return H5Lcreate_soft(target, group, name, H5P_DEFAULT, H5P_DEFAULT);
}

int
main(int argc, char **argv)
{
    hid_t fapl = H5I_INVALID_HID, gcpl = H5I_INVALID_HID;
    hid_t file = H5I_INVALID_HID, group = H5I_INVALID_HID;
    hid_t target = H5I_INVALID_HID;
    char *huge_target = NULL, *managed_target = NULL;
    int   huge_only;

    if (argc != 3)
        return 2;
    huge_only = (0 == strcmp(argv[2], "huge_only"));
    if (!huge_only && 0 != strcmp(argv[2], "mixed"))
        return 2;

    if ((fapl = H5Pcreate(H5P_FILE_ACCESS)) < 0 ||
        H5Pset_libver_bounds(fapl, H5F_LIBVER_LATEST, H5F_LIBVER_LATEST) < 0)
        return 3;
    if ((file = H5Fcreate(argv[1], H5F_ACC_TRUNC, H5P_DEFAULT, fapl)) < 0)
        return 4;

    /* max_compact = 0: the group uses dense storage from its very first link,
       so neither fixture has to carry filler members. */
    if ((gcpl = H5Pcreate(H5P_GROUP_CREATE)) < 0 ||
        H5Pset_link_phase_change(gcpl, 0, 0) < 0)
        return 5;
    if ((group = H5Gcreate2(file, "group", H5P_DEFAULT, gcpl, H5P_DEFAULT)) < 0)
        return 6;

    /* BOTH soft links RESOLVE.  A dangling target would be perfectly legal
       HDF5, but the dense_index exercise walks the group with H5Lvisit2 and
       then opens what each link names, so a dangling fixture comes back
       `rejected_in_traversal` and cannot serve as a clean canary.  The long
       target is a real group created at the root; its own link stays a compact
       message in the root's object header, so only "group" goes dense. */
    if (NULL == (huge_target = long_path(HUGE_TARGET_LEN)) ||
        NULL == (managed_target = long_path(MANAGED_TARGET_LEN)))
        return 7;
    if ((target = H5Gcreate2(file, huge_target, H5P_DEFAULT, H5P_DEFAULT,
                             H5P_DEFAULT)) < 0 ||
        H5Gclose(target) < 0)
        return 8;
    if ((target = H5Gcreate2(file, managed_target, H5P_DEFAULT, H5P_DEFAULT,
                             H5P_DEFAULT)) < 0 ||
        H5Gclose(target) < 0)
        return 9;
    huge_target[HUGE_TARGET_LEN - SLACK_BYTES] = '\0';     /* the decoy */
    if ((target = H5Gcreate2(file, huge_target, H5P_DEFAULT, H5P_DEFAULT,
                             H5P_DEFAULT)) < 0 ||
        H5Gclose(target) < 0)
        return 9;
    huge_target[HUGE_TARGET_LEN - SLACK_BYTES] = 'd';

    if (!huge_only && add_soft(group, "managed", managed_target) < 0)
        return 10;
    if (add_soft(group, "huge", huge_target) < 0)
        return 11;

    free(huge_target);
    free(managed_target);
    if (H5Gclose(group) < 0 || H5Pclose(gcpl) < 0 || H5Pclose(fapl) < 0 ||
        H5Fclose(file) < 0)
        return 12;
    return 0;
}
