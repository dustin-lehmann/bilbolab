import numpy as np
from matplotlib import pyplot as plt

if __name__ == '__main__':
    x = np.arange(0, 1.01, 0.01)

    kp = 1

    v = kp * x
    decel_limit = 0.4
    v_new = np.sqrt(2 * decel_limit * abs(v))

    v_new_2 = np.maximum(v, v_new)

    plt.plot(x, v)
    plt.plot(x, v_new)
    plt.plot(x, v_new_2)
    plt.legend(["v", "v_new", "v_new_2"])
    plt.grid()
    plt.show()
