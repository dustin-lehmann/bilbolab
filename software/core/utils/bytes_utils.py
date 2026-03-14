from typing import Literal


def bytes_(val: int):
    assert (val < 2e8)
    return bytes([val])


def byteArrayToInt(b: (list, bytearray, bytes), byteorder: Literal["little", "big"] = "big"):
    if isinstance(b, list):
        b = bytes(b)
    assert (isinstance(b, (list, bytes, bytearray)))
    return int.from_bytes(b, byteorder=byteorder)


def intToByte(i: int, num_bytes, byteorder: Literal["little", "big"] = "big"):
    return i.to_bytes(length=num_bytes, byteorder=byteorder)


def intToByteList(i: int, num_bytes, byteorder: Literal["little", "big"] = "big"):
    return list(intToByte(i, num_bytes, byteorder=byteorder))


def setBit(number, bit):
    assert (number < 2e8)
    number = number | 1 << bit
    return number


def clearBit(number, bit):
    assert (number < 2e8)
    number = number & ~(1 << bit)
    return number


def toggleBit(number, bit):
    assert (number < 2e8)
    number = number ^ 1 << bit
    return number


def checkBit(number, bit):
    assert (number < 2e8)
    bit = (number >> bit) & 1
    return bit


def changeBit(number, bit, val):
    assert (number < 2e8)
    number = number ^ (-val ^ number) & (1 << bit)
    return number


def bytearray_to_string(data, pos=False):
    """

    :param data:
    :param pos:
    :return:
    """
    if isinstance(data, int):
        data = bytes([data])

    if pos:
        data = " ".join("0x{:02X}({:d})".format(b, i) for (i, b) in enumerate(data))
    else:
        data = " ".join("0x{:02X}".format(b) for b in data)

    return data


def int_to_bit_string(value: int) -> str:
    """
    Converts an integer to its bit representation as a string.
    Uses 8 bits for values under 256 and scales up for larger values.

    Args:
        value (int): The integer to convert.

    Returns:
        str: The bit representation of the integer.
    """
    if value < 0:
        raise ValueError("Only non-negative integers are supported.")

    # Determine the number of bits needed to represent the value
    bit_length = max(8, value.bit_length())  # At least 8 bits for values < 256
    num_bits = (bit_length + 7) // 8 * 8  # Round up to the nearest byte

    # Convert the integer to a binary string, zero-padded to the correct length
    bit_string = format(value, f'0{num_bits}b')
    return bit_string
