import time


def int_to_bits(val):
    if val < 2e8:
        return format(val, 'b').zfill(8)
    elif val < 2e16:
        return format(val, 'b').zfill(16)
    elif val < 2e32:
        return format(val, 'b').zfill(32)
    else:
        return ''


def debug_print(text, *args, **kwargs):
    print(f"{text}")
