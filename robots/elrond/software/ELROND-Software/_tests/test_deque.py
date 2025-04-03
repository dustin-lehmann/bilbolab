from collections import deque

if __name__ == '__main__':
    x = deque(maxlen=10)

    for i in range(20):
        x.append(i)
    print(x[4])