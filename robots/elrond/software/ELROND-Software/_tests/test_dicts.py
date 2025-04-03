from utils.time import PerformanceTimer


def copy_from_b_to_a(a, b, structure_cache=None):
    """
    Copies elementary values from dict B to dict A.

    Both dictionaries must have the same structure. Elementary values are those
    that are not dicts (e.g., int, float, enum.IntEnum).

    Parameters:
        a (dict): The target dictionary to update.
        b (dict): The source dictionary from which to copy values.
        structure_cache (list, optional): A list of key paths that lead to elementary
            values. If None, the cache will be built recursively.

    Returns:
        list: The structure_cache built or reused for copying.
    """
    # If cache is not provided, traverse the structure of A to cache all key paths.
    if structure_cache is None:
        structure_cache = []

        def build_cache(current_dict, current_path):
            for key, value in current_dict.items():
                new_path = current_path + [key]
                if isinstance(value, dict):
                    build_cache(value, new_path)
                else:
                    structure_cache.append(new_path)

        build_cache(a, [])

    # Use the cached paths to update the values in A from the values in B.
    for path in structure_cache:
        # Navigate through both A and B following the path.
        target_a = a
        target_b = b
        for key in path[:-1]:
            target_a = target_a[key]
            target_b = target_b[key]
        # Update the elementary value.
        target_a[path[-1]] = target_b[path[-1]]

    return structure_cache


# Example usage:
if __name__ == '__main__':
    # Assume we have two dictionaries with the same structure:
    A = {
        'sub1': {
            'sub2': {
                'x': 1,
                'y': 2
            },
            'z': 3
        },
        'w': 4
    }
    B = {
        'sub1': {
            'sub2': {
                'x': 10,
                'y': 20
            },
            'z': 30
        },
        'w': 40
    }

    # First pass: cache is built.
    timer1 = PerformanceTimer(print_output=True)
    cache = copy_from_b_to_a(A, B)
    print("After first copy:", A)
    timer1.stop()

    # Modify B for subsequent updates.
    B['sub1']['sub2']['x'] = 100
    B['w'] = 400

    # Subsequent pass: reuse the cache.
    timer2 = PerformanceTimer(print_output=True)
    copy_from_b_to_a(A, B, structure_cache=cache)
    timer2.stop()
    print("After second copy:", A)
