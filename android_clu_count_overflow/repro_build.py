#!/usr/bin/env python3

import sys

SECTOR_SIZE = 512
BOOT_SECTOR_COUNT = 11
CHECKSUM_SECTOR = 11

# Bytes excluded from checksum calculation in sector 0.
EXCLUDED_OFFSETS = {106, 107, 112}


def update_checksum(checksum, value):
    """
    Rotate checksum right by 1 bit, then add one byte.
    The result is kept as a 32-bit unsigned integer.
    """
    checksum = (
        (0x80000000 if (checksum & 1) else 0)
        + (checksum >> 1)
        + value
    )

    return checksum & 0xFFFFFFFF


def calculate_boot_checksum(f):
    checksum = 0

    for sector_index in range(BOOT_SECTOR_COUNT):
        offset = sector_index * SECTOR_SIZE

        f.seek(offset)
        sector = f.read(SECTOR_SIZE)

        if len(sector) != SECTOR_SIZE:
            raise RuntimeError(
                f"Failed to read sector {sector_index}: "
                f"expected {SECTOR_SIZE} bytes, got {len(sector)} bytes"
            )

        for index in range(SECTOR_SIZE):

            # Sector 0 has three bytes excluded from checksum calculation.
            if sector_index == 0 and index in EXCLUDED_OFFSETS:
                continue

            checksum = update_checksum(checksum, sector[index])

    return checksum


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <file/device>")
        print(f"Example: {sys.argv[0]} disk.img")
        sys.exit(1)

    target = sys.argv[1]

    with open(target, "r+b") as f:

        # ------------------------------------------------------------
        # Step 1:
        # Modify sector 0 offsets [0x48, 0x50) to 0xFF.
        #
        # Offsets:
        #   0x48
        #   0x49
        #   0x4A
        #   0x4B
        #   0x4C
        #   0x4D
        #   0x4E
        #   0x4F
        # ------------------------------------------------------------
        f.seek(0x48)
        f.write(b"\xFF" * 8)
        f.flush()

        print("Sector 0 offsets [0x48, 0x50) have been set to 0xFF.")

        # ------------------------------------------------------------
        # Step 2:
        # Calculate checksum over sectors 0 through 10.
        #
        # Sector 0 skips offsets:
        #   106 (0x6A)
        #   107 (0x6B)
        #   112 (0x70)
        #
        # Sectors 1 through 10 include all bytes.
        # ------------------------------------------------------------
        checksum = calculate_boot_checksum(f)

        print(f"Calculated checksum: 0x{checksum:08X}")

        # ------------------------------------------------------------
        # Step 3:
        # Convert checksum to little-endian 4-byte format.
        # ------------------------------------------------------------
        checksum_bytes = checksum.to_bytes(4, byteorder="little")

        print(
            "Checksum little-endian bytes: "
            f"{checksum_bytes.hex(' ').upper()}"
        )

        # ------------------------------------------------------------
        # Step 4:
        # Fill the entire checksum sector (LBA 11).
        #
        # 512 / 4 = 128 copies.
        # ------------------------------------------------------------
        checksum_sector_data = checksum_bytes * (SECTOR_SIZE // 4)

        checksum_sector_offset = CHECKSUM_SECTOR * SECTOR_SIZE

        f.seek(checksum_sector_offset)
        f.write(checksum_sector_data)
        f.flush()

        print(
            f"Checksum written to LBA {CHECKSUM_SECTOR} "
            f"at offset 0x{checksum_sector_offset:X}."
        )

        print("Checksum repeated 128 times to fill the 512-byte sector.")

    print("All modifications completed successfully.")


if __name__ == "__main__":
    main()
