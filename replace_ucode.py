#!/bin/python
"""
Description:
    Hack to replace Intel microcode in UEFI firmare.
    Assumes that microcode is located in UEFI FFS 'files' with GUID 197DB236-F856-4924-90F8-CDF12FB875F3.

Usage:
    replace_ucode.py INPUT_ROM INPUT_UCODE OUTPUT_ROM

    INPUT_ROM    Path to firmware image file
    INPUT_UCODE  Path to raw binary Intel microcode file
    OUTPUT_ROM   Path to output firmware image

License:
    MIT License

    Copyright (c) 2024 Andreas Rosvall

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
"""

import sys
import uuid
from ctypes import c_uint8 as u8
from ctypes import c_uint16 as u16
from ctypes import c_uint32 as u32
from ctypes import sizeof, Array, LittleEndianStructure

UCODE_FFS_GUID = uuid.UUID('197DB236-F856-4924-90F8-CDF12FB875F3')

class ChksumError(Exception):
    pass

class PrettyStructPrinter:
    def __str__(self):
        lines = [self.__class__.__name__]
        for field in self._fields_:
            name = field[0]
            val = getattr(self, name)
            if isinstance(val, Array):
                val = int.from_bytes(val, 'big')
            lines.append(f'\t{name:20} = {hex(val)}')
        return '\n'.join(lines)

class IntelUcodeHeader(LittleEndianStructure, PrettyStructPrinter):
    """
    Borrowed from MCExtractor
    https://github.com/platomav/MCExtractor/
    """
    _pack_ = True
    _fields_ = (
        ('HeaderType',          u32),
        ('UpdateRevision',      u32),
        ('Year',                u16),
        ('Day',                 u8),
        ('Month',               u8),
        ('ProcessorSignature',  u32),
        ('Checksum',            u32),
        ('LoaderRevision',      u32),
        ('PlatformIDs',         u32),
        ('DataSize',            u32),
        ('TotalSize',           u32),
        ('MetadataSize',        u32),
        ('UpdateRevisionMin',   u32),
        ('Reserved',            u32),
    )

class EfiFFSHeader(LittleEndianStructure, PrettyStructPrinter):
    _pack_ = True
    _fields_ = (
        ('GUID',        u8 * 16),
        ('ChkHdr',      u8),
        ('ChkData',     u8),
        ('Type',        u8),
        ('Attributes',  u8),
        ('Size',        u32, 24),
        ('State',       u32, 8),
    )


def array_sum(data: bytes, typ):
    A = typ * (len(data) // sizeof(typ))
    a = A.from_buffer_copy(data, 0)
    return sum(a) & typ(-1).value


class FFS:
    def __init__(self, data: bytes):
        self.hdr = EfiFFSHeader.from_buffer_copy(data, 0)

        chk = array_sum(data[0:sizeof(self.hdr)], u8)
        chk -= self.hdr.ChkData
        chk -= self.hdr.State
        chk &= 0xff
        if chk != 0:
            raise ChksumError('Invalid FFS header')

        self.body = data[sizeof(self.hdr):self.hdr.Size]

    def __str__(self):
        return str(self.hdr)

class IntelUCode:
    def __init__(self, data: bytes):
        self.hdr = IntelUcodeHeader.from_buffer_copy(data, 0)
        self.data = data[:self.hdr.TotalSize]
        chk = array_sum(self.data, u32)
        if chk != 0:
            raise ChksumError('Invalid ucode')

    def __str__(self):
        return str(self.hdr)


def find_all(haystack: bytes, needle: bytes):
    pos = 0
    while True:
        pos = haystack.find(needle, pos)
        if pos < 0:
            return
        yield pos
        pos += len(needle)

def print_concatenated_ucode(data: bytes):
    offset = 0
    while True:
        try:
            ucode = IntelUCode(data[offset:])
            print('At', hex(offset))
            print(ucode)
            offset += len(ucode.data)
        except (ChksumError, ValueError):
            break

    if offset == 0:
        print('WARNING: No ucode found here!')
    else:
        trailing = len(data) - offset
        if trailing:
            print(f'Note: Found {hex(trailing)} trailing bytes after ucode')


if __name__ == '__main__':
    try:
        _, infile, ucodefile, outfile = sys.argv
    except:
        print(__doc__)
        raise

    orig_rom = open(infile, 'rb').read()
    rom = memoryview(bytearray(orig_rom))

    print('Input ROM:', infile, 'size:', len(rom))

    new_ucode = open(ucodefile, 'rb').read()
    print('Input ucode file:', ucodefile)

    # Raise ChksumError if ucode file is invalid
    IntelUCode(new_ucode)

    print_concatenated_ucode(new_ucode)

    print('-' * 79)

    print(f'Searching for all occurences of {UCODE_FFS_GUID} in {infile}...')
    for offset in find_all(rom.obj, UCODE_FFS_GUID.bytes_le):
        print(f'Found {UCODE_FFS_GUID} at {hex(offset)}')

        try:
            ffs = FFS(rom[offset:])
            print(ffs)

            print_concatenated_ucode(ffs.body)

            print('Erasing entire FFS body...')
            ffs.body[:] = bytes([0xff] * len(ffs.body))

            print('Copying new ucode to FFS body...')
            ffs.body[:len(new_ucode)] = new_ucode

        except ChksumError:
            print('Invalid FFS header checksum, skipping...')

        print('-' * 79)

    assert len(rom) == len(orig_rom)
    assert rom != orig_rom, 'Result is identical to original rom. Not saving.'

    print(f'Writing {len(rom)} bytes to {outfile}...')
    open(outfile, 'wb').write(rom)

    print('DONE')
