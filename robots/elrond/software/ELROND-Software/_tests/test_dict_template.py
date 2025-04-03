import copy
import time


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


# Test and compare performance against copy.deepcopy
def test_performance(original, num_copies, iterations=100):
    # Test our optimized function
    start = time.time()
    for _ in range(iterations):
        copies = optimized_generate_empty_copies(original, num_copies)
    optimized_time = time.time() - start

    # Test deepcopy: each copy is made by deepcopy-ing the original dict
    start = time.time()
    for _ in range(iterations):
        copies = [copy.deepcopy(original) for _ in range(num_copies)]
    deepcopy_time = time.time() - start

    print("Optimized function time: {:.6f} seconds".format(optimized_time))
    print("Deepcopy time: {:.6f} seconds".format(deepcopy_time))


if __name__ == '__main__':
    # Example nested dictionary
    sample_dict = {
        'a': 1,
        'b': {
            'c': 2,
            'd': 3,
            'e': {'f': 4, 'g': 5}
        },
        'h': 6
    }
    # Adjust the number of copies and iterations as needed.
    test_performance(sample_dict, num_copies=10000, iterations=1)
