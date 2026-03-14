import copy
import enum
import re
import time
from collections.abc import Mapping, MutableSequence, MutableSet
from typing import Any, Dict, List, Optional, Union

import numpy as np


# ======================================================================================================================
# Functions from dict_utils.py (original)
# ======================================================================================================================

def copy_dict(dict_from, dict_to, structure_cache=None):
    """
    Copies elementary values from dict_from to dict_to for matching key paths.

    Only copies the value if the entire key path exists in dict_from.
    The source dict (dict_from) is expected to be a subset of dict_to.
    Elementary values are those that are not dicts (e.g., int, float, enum.IntEnum).

    Parameters:
        dict_to (dict): The target dictionary to update.
        dict_from (dict): The source dictionary from which to copy values.
        structure_cache (list, optional): A list of key paths that lead to elementary values in dict_to.
            If None, the cache will be built recursively.

    Returns:
        list: The structure_cache built or reused for copying.
    """
    # Build a cache of key paths from dict_to if not provided.
    if structure_cache is None:
        structure_cache = []

        def build_cache(current_dict, current_path):
            for key, value in current_dict.items():
                new_path = current_path + [key]
                if isinstance(value, dict):
                    build_cache(value, new_path)
                else:
                    structure_cache.append(new_path)

        build_cache(dict_to, [])

    # Use the cached paths to update values in dict_to from dict_from.
    for path in structure_cache:
        target_a = dict_to
        target_b = dict_from
        # Traverse the path up to the final key.
        for key in path[:-1]:
            if key in target_b:
                target_a = target_a[key]
                target_b = target_b[key]
            else:
                # If an intermediate key is missing in dict_from, skip this path.
                break
        else:
            # If we didn't break, check if the final key exists.
            if path[-1] in target_b:
                target_a[path[-1]] = target_b[path[-1]]

    return structure_cache


# ======================================================================================================================
def optimized_deepcopy(d, structure=None):
    """
    Deepcopy a dictionary using cached structure.

    If 'structure' is None, do a full recursive copy and build a structure
    dict that caches which keys correspond to nested dicts. The function returns
    a tuple (copy, structure).

    If 'structure' is provided, it is used to guide the copy process, assuming
    that the input dictionary 'd' has the same nested structure.
    """
    if structure is None:
        new_dict = {}
        struct = {}  # This will mirror the structure of 'd' for dict values.
        for k, v in d.items():
            if isinstance(v, dict):
                copied_v, sub_struct = optimized_deepcopy(v)
                new_dict[k] = copied_v
                struct[k] = sub_struct
            elif isinstance(v, np.ndarray):
                new_dict[k] = v.copy()
            elif isinstance(v, list):
                new_dict[k] = v.copy()
            else:
                new_dict[k] = v  # elementary types are immutable
        return new_dict, struct
    else:
        new_dict = {}
        for k, v in d.items():
            if k in structure:
                # The cached structure tells us that v is a dict.
                new_dict[k] = optimized_deepcopy(v, structure[k])
            elif isinstance(v, np.ndarray):
                new_dict[k] = v.copy()
            elif isinstance(v, list):
                new_dict[k] = v.copy()
            else:
                new_dict[k] = v
        return new_dict


# ======================================================================================================================
def cache_dict_paths_for_flatten(d, parent_path=None, parent_key='', sep='.'):
    """
    Recursively flattens a dictionary while recording the access path (list of keys) for each flattened key.
    Returns a tuple (flattened_dict, paths) where paths maps each flattened key to its key path.
    """
    if parent_path is None:
        parent_path = []
    flat = {}
    paths = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        new_path = parent_path + [k]
        if isinstance(v, dict):
            sub_flat, sub_paths = cache_dict_paths_for_flatten(v, new_path, new_key, sep=sep)
            flat.update(sub_flat)
            paths.update(sub_paths)
        elif isinstance(v, enum.IntEnum):
            flat[new_key] = int(v)
            paths[new_key] = new_path
        else:
            flat[new_key] = v
            paths[new_key] = new_path
    return flat, paths


def optimized_flatten_dict(d, cached_paths):
    """
    Quickly flattens a dictionary using the cached access paths.
    """
    flat = {}
    for flat_key, key_path in cached_paths.items():
        value = d
        try:
            for key in key_path:
                value = value[key]
        except (KeyError, TypeError):
            value = None
        if isinstance(value, enum.IntEnum):
            value = int(value)
        flat[flat_key] = value
    return flat


# ======================================================================================================================
# New Functions for Unflattening (Counterparts for the Flattened Dict Functions)
# ======================================================================================================================

def unflatten_dict_baseline(flat_dict, sep='.'):
    """
    Reconstructs a nested dictionary from a flattened dictionary by splitting keys every time.

    Parameters:
        flat_dict (dict): A flattened dictionary with keys like 'a.b.c'.
        sep (str): The separator used in the flattened keys.

    Returns:
        dict: The reconstructed nested dictionary.
    """
    nested = {}
    for flat_key, value in flat_dict.items():
        parts = flat_key.split(sep)
        d = nested
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        d[parts[-1]] = value
    return nested


def unflatten_dict_optimized(flat_dict, cache=None, sep='.'):
    """
    Reconstructs a nested dictionary from a flattened dictionary using a cache of pre-split key paths.

    If 'cache' is provided, it is used to avoid splitting the keys. If not provided,
    the cache is built and returned along with the nested dictionary.

    Parameters:
        flat_dict (dict): A flattened dictionary with keys like 'a.b.c'.
        cache (dict, optional): A dict mapping flat keys to their key paths (list of keys).
        sep (str): The separator used in the flattened keys.

    Returns:
        tuple: (nested_dict, cache) where nested_dict is the reconstructed nested dictionary and
               cache is the mapping of flat keys to key paths.
    """
    if cache is None:
        cache = {k: k.split(sep) for k in flat_dict.keys()}
    nested = {}
    for flat_key, value in flat_dict.items():
        parts = cache[flat_key]
        d = nested
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        d[parts[-1]] = value
    return nested, cache


def build_template(d):
    """
    Recursively build a blueprint of the dict.
    Every non-dict leaf is replaced with None.
    """
    if isinstance(d, dict):
        return {k: build_template(v) for k, v in d.items()}
    else:
        return None


def fast_copy(template):
    """
    Recursively create a new dict copy from the template.
    Since the template only contains dicts and None values,
    we can do this with a simple recursion.
    """
    # Since None is immutable we can simply use it for leaves.
    return {k: fast_copy(v) if isinstance(v, dict) else None
            for k, v in template.items()}


def optimized_generate_empty_copies(original, num_copies):
    """
    Returns a list of num_copies dicts that have the same structure
    as original but with all elementary values set to None.
    """
    # Build the structure blueprint just once
    template = build_template(original)
    # Use our fast_copy to create new independent dicts from the blueprint
    return [fast_copy(template) for _ in range(num_copies)]


def format_floats(obj, precision=2):
    float_format = f"{{:.{precision}f}}"

    def _format(o):
        if isinstance(o, float):
            return float_format.format(o)
        elif isinstance(o, dict):
            return {k: _format(v) for k, v in o.items()}
        elif isinstance(o, list):
            return [_format(v) for v in o]
        elif isinstance(o, tuple):
            return tuple(_format(v) for v in o)
        else:
            return o

    return _format(obj)


# ======================================================================================================================
# Functions merged from dict.py
# ======================================================================================================================

def _is_mutable_container(v):
    return isinstance(v, (Mapping, MutableSequence, MutableSet))


def update_dict(original: dict,
                *updates: dict,
                allow_add: bool = True,
                prefer_existing: bool = False,
                copy_on_assign: bool = True) -> dict:
    """
    Merge updates into `original` in place and return it.

    - Recurses when both sides have a dict at the same key.
    - If `prefer_existing=True`, existing keys in `original` are NOT overwritten
      (useful when applying defaults).
    - If assigning a whole value (not recursing), we do a defensive copy for
      mutable containers to avoid aliasing, but skip copies for immutables.

    Parameters
    ----------
    original : dict
        Target dict to mutate.
    *updates : dict
        One or more dicts to merge from left to right.
    allow_add : bool
        If False, ignore keys not already in `original`.
    prefer_existing : bool
        If True, keep `original[key]` when it already exists.
    copy_on_assign : bool
        If True, copy mutable containers when assigning.
    """
    for upd in updates:
        for key, value in upd.items():
            # If both sides are dicts, recurse without replacing the object
            if key in original and isinstance(original[key], Mapping) and isinstance(value, Mapping):
                update_dict(original[key], value,
                            allow_add=allow_add,
                            prefer_existing=prefer_existing,
                            copy_on_assign=copy_on_assign)
                continue

            # Respect allow_add / prefer_existing
            if not allow_add and key not in original:
                continue
            if prefer_existing and key in original:
                continue

            # Assign (with copy to avoid aliasing when needed)
            if copy_on_assign and _is_mutable_container(value):
                original[key] = copy.deepcopy(value)
            else:
                original[key] = value
    return original


def flatten_dict(data: dict, indent: int = 0) -> list[tuple[str, str]]:
    """
    Recursively flatten a dictionary into a list of (key, value) tuples.
    The key is indented by two spaces per level. If a value is a dict, the key
    is shown with an empty value, and its contents are flattened below.
    Lists are displayed as a comma-separated list inside square brackets.
    """
    rows = []
    for key, value in data.items():
        prefix = "  " * indent + str(key)
        if isinstance(value, dict):
            rows.append((prefix, ""))
            rows.extend(flatten_dict(value, indent=indent + 1))
        elif isinstance(value, list):
            rows.append((prefix, "[" + ", ".join(str(x) for x in value) + "]"))
        else:
            rows.append((prefix, str(value)))
    return rows


def replaceField(data, expected_type, key, new_value):
    """
    Recursively replaces the value of the specified key(s) with a new value
    if the existing value matches the given type.

    Parameters:
        data (dict or list): The input dictionary (or list of dictionaries) to process.
        expected_type (type): The type to match before replacing the value.
        key (str or list): The key or list of keys to search for.
        new_value: The value to replace with.

    Returns:
        None: Modifies the input dictionary in place.
    """
    if isinstance(key, str):
        keys = [key]
    else:
        keys = key

    if isinstance(data, dict):
        for k in data:
            if k in keys and isinstance(data[k], expected_type):
                data[k] = new_value
            else:
                replaceField(data[k], expected_type, keys, new_value)
    elif isinstance(data, list):
        for item in data:
            replaceField(item, expected_type, keys, new_value)


def replaceStringInDict(
        data: Union[Dict[str, Any], List[Any]],
        key: Union[str, List[str]],
        new_value: str,
        regex: Optional[Union[str, re.Pattern]] = None,
        regex_flags: int = 0
) -> None:
    """
    Recursively replaces the value of the specified key(s) with `new_value`
    **only when the current value is a string**. If `regex` is provided,
    replacement occurs only when the string value matches the pattern.

    Parameters:
        data (dict or list): The input dictionary (or list) to process (modified in place).
        key (str or list[str]): The key or keys whose string values may be replaced.
        new_value (str): The value to write when conditions are met.
        regex (str or Pattern, optional): A regular expression that the current string
            value must match to be replaced. If None, all string values for matching
            keys are replaced.
        regex_flags (int): Flags passed to `re.compile` if `regex` is a string.

    Returns:
        None
    """
    keys = [key] if isinstance(key, str) else key

    # Prepare matcher
    if regex is None:
        def _matches(_: str) -> bool:
            return True
    else:
        pattern = re.compile(regex, regex_flags) if isinstance(regex, str) else regex

        def _matches(s: str) -> bool:
            return bool(pattern.search(s))

    if isinstance(data, dict):
        for k, v in list(data.items()):
            if k in keys and isinstance(v, str) and _matches(v):
                data[k] = new_value
            else:
                if isinstance(v, (dict, list)):
                    replaceStringInDict(v, keys, new_value, regex, regex_flags)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                replaceStringInDict(item, keys, new_value, regex, regex_flags)


# ======================================================================================================================
class ObservableDict(dict):
    def __init__(self, *args, on_change=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_change = on_change

    def _notify(self):
        if self._on_change:
            self._on_change()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._notify()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._notify()

    def clear(self):
        super().clear()
        self._notify()

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._notify()

    def pop(self, *args):
        result = super().pop(*args)
        self._notify()
        return result

    def popitem(self):
        result = super().popitem()
        self._notify()
        return result


# ======================================================================================================================
# Testing and Performance Evaluation
# ======================================================================================================================
if __name__ == "__main__":
    # Create a sample nested dictionary.
    nested_original = {
        "a": {
            "b": {
                "c": "HELLO",
                "d": 2
            },
            "e": 3
        },
        "f": 4,
        "g": {
            "h": 5,
            "i": {
                "j": 6,
                "k": 7
            }
        }
    }

    # Flatten the nested dictionary using the provided optimized flatten function.
    flat_dict, cached_paths = cache_dict_paths_for_flatten(nested_original, sep='.')

    flat_dict2 = optimized_flatten_dict(nested_original, cached_paths)

    print("Flattened dictionary:")
    print(flat_dict)
    print("\nCached paths for flattening:")
    print(cached_paths)

    # ------------------------------
    # Baseline unflatten function test
    # ------------------------------
    start_time = time.time()
    for _ in range(1000000):
        result_baseline = unflatten_dict_baseline(flat_dict, sep='.')
    baseline_duration = time.time() - start_time

    # ------------------------------
    # Optimized unflatten function test
    # ------------------------------
    # First call to build the cache:
    result_optimized, unflatten_cache = unflatten_dict_optimized(flat_dict, cache=None, sep='.')
    start_time = time.time()
    for _ in range(1000000):
        result_opt, _ = unflatten_dict_optimized(flat_dict, cache=unflatten_cache, sep='.')
    optimized_duration = time.time() - start_time

    # Verify that both unflatten methods produce the same result.
    assert result_baseline == result_optimized, "Unflatten functions produced different results!"

    print("\nUnflattened dictionary (baseline):")
    print(result_baseline)
    print("\nPerformance evaluation (100,000 iterations):")
    print(f"Baseline unflatten time: {baseline_duration:.4f} seconds")
    print(f"Optimized unflatten time: {optimized_duration:.4f} seconds")
