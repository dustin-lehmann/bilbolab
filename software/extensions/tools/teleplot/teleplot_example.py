import time
import math
import random
import argparse
from teleplot import (
    send_value,
    send_values,
    send_xy,
    send_xy_series
)


def example_simple_value():
    """
    Send a single numeric value (auto-timestamped, auto-plotted).
    """
    send_value("temperature_simple", 23.7)
    print("Sent simple temperature value.")


def example_value_with_timestamp_and_unit():
    """
    Send a value with client timestamp, unit, and suppress auto-plot.
    """
    send_value(
        "temperature_custom", 23.7,
        use_client_timestamp=True,
        unit="°C",
        automatic_plot=False
    )
    print("Sent timestamped temperature with unit, no auto-plot.")


def example_batch_values():
    """
    Send a batch of timestamped values in one packet.
    """
    now = int(time.time() * 1000)
    batch = [(now + i * 1000, 20 + random.random() * 5) for i in range(5)]
    send_values("temperature_batch", batch, unit="°C")
    print("Sent batch of temperature readings.")


def example_single_xy():
    """
    Send a single (x,y) point (auto-timestamped).
    """
    x = random.random() * 10
    y = random.random() * 10
    send_xy("trajectory_point", x, y)
    print(f"Sent XY point: x={x:.2f}, y={y:.2f}.")


def example_xy_series():
    """
    Send a series of XY points, some with explicit timestamps.
    """
    now = int(time.time() * 1000)
    pts = [
        (i, math.sin(i / 5), now + i * 100)
        for i in range(10)
    ]
    send_xy_series("trajectory_series", pts)
    print("Sent series of XY points.")


def example_continuous_temperature(interval=1.0, count=0):
    """
    Continuously send a temperature reading every `interval` seconds.
    If count > 0, send that many points; otherwise run indefinitely.
    """
    i = 0
    try:
        while True:
            temp = 20 + 5 * math.sin(time.time() / 10)
            send_value("temperature_stream", temp, unit="°C")
            print(f"[{i}] Sent streaming temperature: {temp:.2f}°C")
            i += 1
            if count and i >= count:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopped continuous temperature stream.")


def example_continuous_trajectory(interval=0.5, count=0):
    """
    Continuously send XY trajectory points along a circle.
    """
    i = 0
    try:
        while True:
            t = time.time()
            x = math.cos(t)
            y = math.sin(t)
            send_xy("trajectory_stream", x, y)
            print(f"[{i}] Sent trajectory point: x={x:.2f}, y={y:.2f}")
            i += 1
            if count and i >= count:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopped continuous trajectory stream.")


def main():
    parser = argparse.ArgumentParser(description="Teleplot Example Runner")
    parser.add_argument(
        "mode",
        choices=[
            "simple_value",
            "value_custom",
            "batch_values",
            "single_xy",
            "xy_series",
            "stream_temp",
            "stream_traj"
        ],
        help="Which example to run"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Interval between sends in streaming modes"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Number of points to send in streaming modes (0 = infinite)"
    )
    args = parser.parse_args()

    if args.mode == "simple_value":
        example_simple_value()
    elif args.mode == "value_custom":
        example_value_with_timestamp_and_unit()
    elif args.mode == "batch_values":
        example_batch_values()
    elif args.mode == "single_xy":
        example_single_xy()
    elif args.mode == "xy_series":
        example_xy_series()
    elif args.mode == "stream_temp":
        example_continuous_temperature(args.interval, args.count)
    elif args.mode == "stream_traj":
        example_continuous_trajectory(args.interval, args.count)


if __name__ == "__main__":
    main()
