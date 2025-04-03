import copy
import time

# Global cache mapping a structure descriptor to a fast copy function
_template_cache = {}

def _make_template(d):
    """
    Recursively build a structure descriptor for dict d.
    The descriptor is a tuple of (key, subtemplate) pairs in insertion order.
    For non-dict values, subtemplate is None.
    """
    items = []
    for k, v in d.items():
        if isinstance(v, dict):
            # Recursively build a template for subdicts.
            subtemplate = _make_template(v)
        else:
            subtemplate = None
        items.append((k, subtemplate))
    return tuple(items)

def _build_copy_func(template):
    """
    Given a template (a tuple of (key, subtemplate) pairs), build a function
    that efficiently copies a dict matching that structure.
    For keys whose values are dicts, we use a recursively cached copy function.
    """
    # Build a dictionary of sub-copy functions for nested dicts.
    sub_funcs = {}
    for key, subtemplate in template:
        if subtemplate is not None:
            sub_funcs[key] = get_copy_func(subtemplate)
        else:
            sub_funcs[key] = None

    def copy_func(d):
        # It is assumed that d has exactly the structure of template.
        result = {}
        for key, subtemplate in template:
            if subtemplate is not None:
                # Use the sub-copy function recursively.
                result[key] = sub_funcs[key](d[key])
            else:
                result[key] = d[key]
        return result

    return copy_func

def get_copy_func(template):
    """
    Retrieve (or create and cache) a fast copy function for the given structure template.
    """
    if template in _template_cache:
        return _template_cache[template]
    else:
        func = _build_copy_func(template)
        _template_cache[template] = func
        return func

def optimized_deepcopy(d):
    """
    Perform an optimized deepcopy for dicts using a cached copy function.
    For non-dict objects (assumed immutable), the object is returned as is.
    """
    if not isinstance(d, dict):
        return d  # Elementary types are immutable.
    template = _make_template(d)
    copy_func = get_copy_func(template)
    return copy_func(d)

# === Taxing Example ===

def build_nested_dict(depth, width):
    """
    Build a nested dictionary:
      - `depth` controls how many levels of nested dicts.
      - `width` controls the number of keys at each level.
    Leaves are set to an immutable integer.
    """
    if depth == 0:
        return 1  # Leaf node, immutable.
    return {f'key{i}': build_nested_dict(depth-1, width) for i in range(width)}

# Create a nested dictionary (adjust depth and width for a taxing structure)
d = build_nested_dict(depth=3, width=50)

# Warm-up: run optimized_deepcopy once so its template is cached.
optimized_deepcopy(d)

# Time the optimized_deepcopy
num_iterations = 100
start = time.time()
for _ in range(num_iterations):
    _ = optimized_deepcopy(d)
optimized_time = time.time() - start
print("optimized_deepcopy time:", optimized_time)

# Time the standard copy.deepcopy
start = time.time()
for _ in range(num_iterations):
    _ = copy.deepcopy(d)
deepcopy_time = time.time() - start
print("copy.deepcopy time:", deepcopy_time)
