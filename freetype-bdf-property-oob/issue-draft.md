# FreeType confidential issue draft

Submission target: <https://gitlab.freedesktop.org/freetype/freetype/-/issues>

Create the issue as **confidential**.  FreeType's `README` explicitly says that
its GitLab supports confidential reports.  Attach `poc.ttf` and `repro.c` from
this directory; `make_poc.py` is optional but makes the font reproducible.

## Suggested title

`[sfnt] Heap-buffer-over-read in embedded BDF property lookup`

## Issue body

### Summary

`tt_face_find_bdf_prop` can read beyond the end of an embedded `BDF ` string
table while checking whether a string/atom property value is NUL-terminated.
The function validates that the property value offset is within the string
table, but passes the size of the *entire* table to `ft_memchr` even though the
scan starts at that offset.

I reproduced this through the public memory-face and BDF APIs with a crafted
SFNT font.  AddressSanitizer reports a heap-buffer-overflow in
`tt_face_find_bdf_prop` at `src/sfnt/ttbdf.c:220`.

The issue is present in the default configuration, where
`TT_CONFIG_OPTION_BDF` is enabled.  Loading the font alone is not sufficient:
the application must select the matching pixel size and query a matching
embedded BDF property.

### Revisions tested

- Commit `5336c0d4da22a13dab3389eb153b12672fdf841c`
  (`VER-2-14-3-71-g5336c0d4d`)
- Release tag `VER-2-14-3`

Git history indicates that the faulty length expression has been present since
the embedded-BDF implementation was introduced in commit
`89a2a4b531cec490761ac971c7a222d2bcec441f` (2005-12-14).  I have not tested
every intervening release.

### Vulnerable code

Current source:
<https://gitlab.freedesktop.org/freetype/freetype/-/blob/5336c0d4da22a13dab3389eb153b12672fdf841c/src/sfnt/ttbdf.c#L218-220>

```c
if ( value < bdf->strings_size                               &&
     ft_memchr( bdf->strings + value, 0, bdf->strings_size ) )
```

After the `value < bdf->strings_size` check, the maximum safe scan length from
`bdf->strings + value` is:

```c
bdf->strings_size - value
```

Using `bdf->strings_size` instead makes the requested range extend `value`
bytes beyond the end of the string table if no NUL byte is found first.

### Trigger construction

The attached `poc.ttf` is a checksum-consistent SFNT containing a 44-byte
embedded `BDF ` table at the exact physical end of the file.  Its relevant
fields are:

- one strike at 16 ppem;
- one atom property named `CHARSET_REGISTRY`;
- a valid value offset of 17 into the 22-byte string table; and
- five nonzero bytes from that value offset to the end, with no terminating
  NUL.

The public trigger path is:

```text
FT_New_Memory_Face(...)
FT_Set_Pixel_Sizes(..., 16)
FT_Get_BDF_Property(..., "CHARSET_REGISTRY", ...)
```

The PoC font is synthetic and contains no third-party font data.  It can be
regenerated with FontTools:

```sh
python3 make_poc.py poc.ttf
```

`poc.ttf` SHA-256:

```text
1a2d93ee4796d28420654fa9215fe89910acb869aca91ddf4ad3089bc1084eee
```

### Reproduction

The following commands are the ASan shared-library build I tested.  In a
directory containing the attached `repro.c` and `poc.ttf`:

```sh
git clone https://gitlab.freedesktop.org/freetype/freetype.git
git -C freetype checkout 5336c0d4da22a13dab3389eb153b12672fdf841c

cmake -S freetype -B freetype-asan \
  -DCMAKE_BUILD_TYPE=Debug \
  -DBUILD_SHARED_LIBS=ON \
  -DCMAKE_C_FLAGS="-O1 -g -fsanitize=address -fno-omit-frame-pointer" \
  -DCMAKE_SHARED_LINKER_FLAGS="-fsanitize=address"
cmake --build freetype-asan --parallel

cc -O1 -g -fsanitize=address -fno-omit-frame-pointer \
  -Ifreetype/include repro.c \
  -Lfreetype-asan -Wl,-rpath,"$PWD/freetype-asan" -lfreetyped \
  -o repro

ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 ./repro poc.ttf
```

Stable portion of the result:

```text
y_ppem=16
ERROR: AddressSanitizer: heap-buffer-overflow
READ of size 6
    #0 __interceptor_memchr
    #1 tt_face_find_bdf_prop .../src/sfnt/ttbdf.c:220
    #2 FT_Get_BDF_Property .../src/base/ftbdf.c:82
    #3 main .../repro.c:41

0 bytes to the right of 936-byte region
allocated by thread T0 here:
    #0 __interceptor_malloc
    #1 main .../repro.c:27

SUMMARY: AddressSanitizer: heap-buffer-overflow in __interceptor_memchr
```

The full reproducer uses an allocation exactly the size of the input and opens
it with `FT_New_Memory_Face`, so the excessive scan crosses the memory-face
allocation boundary.

### Impact

A malformed SFNT can cause an out-of-bounds read (CWE-125) when an application
queries a matching embedded BDF string/atom property.  The demonstrated
outcome is an ASan-detected process abort.  This is a potential denial of
service, but behavior in an unsanitized build depends on adjacent memory and
the `memchr` implementation.  I have not separately demonstrated an
unsanitized crash, information disclosure, or code execution.

### Suggested correction

Limit the search to the bytes remaining after `value`:

```diff
diff --git a/src/sfnt/ttbdf.c b/src/sfnt/ttbdf.c
--- a/src/sfnt/ttbdf.c
+++ b/src/sfnt/ttbdf.c
@@
-                 ft_memchr( bdf->strings + value, 0, bdf->strings_size ) )
+                 ft_memchr( bdf->strings + value, 0,
+                            bdf->strings_size - value ) )
```

I tested this change locally with the attached PoC.  The ASan error disappears
and `FT_Get_BDF_Property` rejects the unterminated value with error 6
(`FT_Err_Invalid_Argument`).

A regression test could place an unterminated atom at the end of an embedded
`BDF ` table, query it at the matching ppem, and assert a clean error return.

### Disclosure status

I am reporting this confidentially first so the FreeType maintainers can assess
severity, affected versions, and coordinated disclosure.  I have not requested
a CVE and do not claim impact beyond the demonstrated out-of-bounds read and
the resulting potential denial of service.
