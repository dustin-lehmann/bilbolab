import dataclasses
import time
from collections import deque
from copy import copy, deepcopy

from robot.logging.bilbo_sample import BILBO_Sample
from utils.dataclass_utils import freeze_dataclass_instance, asdict_optimized
from utils.time import PerformanceTimer


def main():
    sample_buffer = deque(maxlen=10000)
    # x = BILBO_Sample()
    samples = [BILBO_Sample()] * 10000
    sample_index = 0
    time1 = time.perf_counter()
    while True:
        # timer = PerformanceTimer(print_output=False)
        for i in range(10):
            x = asdict_optimized(samples[sample_index])
            sample_index = (sample_index + 1) % 10000
            sample_buffer.append(x)

        elapsed_time = (time.perf_counter() - time1)
        time1 = time.perf_counter()

        if elapsed_time > 0.1:
            print(f"Elapsed time: {elapsed_time}")

        time.sleep(0.01)


if __name__ == '__main__':
    main()
