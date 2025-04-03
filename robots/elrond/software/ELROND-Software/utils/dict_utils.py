import enum
import time


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
            else:
                new_dict[k] = v  # elementary types are immutable
        return new_dict, struct
    else:
        new_dict = {}
        for k, v in d.items():
            if k in structure:
                # The cached structure tells us that v is a dict.
                new_dict[k] = optimized_deepcopy(v, structure[k])
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
