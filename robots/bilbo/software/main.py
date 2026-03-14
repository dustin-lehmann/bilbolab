import os
import time
import warnings

# Suppress RPi.GPIO "No channels have been set up yet" cleanup warning
warnings.filterwarnings("ignore", message=".*No channels have been set up yet.*")

# Suppress ALSA underrun warnings (C-level, not catchable by Python warnings)
import ctypes
try:
    _ALSA_ERR_HANDLER = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int,
                                          ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
    _alsa_noop = _ALSA_ERR_HANDLER(lambda *args: None)
    asound = ctypes.cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(_alsa_noop)
except Exception:
    pass

from robot.bilbo import BILBO


def main():
    bilbo = BILBO()
    bilbo.init()
    bilbo.start()

    while True:
        time.sleep(100)




if __name__ == '__main__':
    main()

