import logging
import multiprocessing as mp
import warnings

import orjson
import numpy as np
from core.utils.files import file_exists


def _default(obj):
    """
    Custom serializer for orjson.
    Handles numpy arrays and scalars.
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.generic,)):  # e.g. np.int32, np.float64
        return obj.item()
    raise TypeError


def jsonEncode(obj):
    opts = orjson.OPT_NON_STR_KEYS
    return orjson.dumps(obj, option=opts, default=_default, )


def readJSON(file) -> dict | None:
    if not file_exists(file):
        warnings.warn(f"File {file} does not exist", UserWarning)
        return None
    with open(file, "rb") as f:  # must read bytes
        return orjson.loads(f.read())


def writeJSON(file, data, pretty: bool = True):
    opts = (orjson.OPT_INDENT_2 if pretty else 0) | orjson.OPT_NON_STR_KEYS
    with open(file, "wb") as f:  # must write bytes
        f.write(orjson.dumps(data, option=opts, default=_default))


def _writeJSON_worker(file, data, pretty, convert_dataclass):
    """Subprocess target for writeJSON_mp."""
    if convert_dataclass:
        import dataclasses
        data = dataclasses.asdict(data)
    writeJSON(file, data, pretty)


def writeJSON_mp(file, data, pretty: bool = True, timeout: float = 60.0,
                 convert_dataclass: bool = False) -> bool:
    """Write JSON in a subprocess so the GIL is not blocked.

    Args:
        file: Output file path.
        data: Dict or dataclass to serialize.
        pretty: Use indented formatting.
        timeout: Max seconds to wait for the subprocess.
        convert_dataclass: If True, call dataclasses.asdict(data) inside the
            subprocess before writing. Use this when data is a dataclass and
            the asdict conversion itself is expensive.

    Returns True on success, False on timeout or error.
    """
    logger = logging.getLogger(__name__)
    proc = mp.Process(
        target=_writeJSON_worker,
        args=(file, data, pretty, convert_dataclass),
        daemon=True,
    )
    proc.start()
    proc.join(timeout=timeout)
    if proc.is_alive():
        logger.error(f"writeJSON_mp timed out ({timeout}s), killing subprocess")
        proc.kill()
        return False
    if proc.exitcode != 0:
        logger.error(f"writeJSON_mp failed (exit code {proc.exitcode})")
        return False
    return True
