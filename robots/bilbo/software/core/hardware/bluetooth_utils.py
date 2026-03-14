# import bluetooth
# import subprocess
# import time
# import re
#
#
import re
import subprocess
import time

import bluetooth


def scan_for_device(pattern):
    """Scan for Bluetooth devices and return the address of the first device matching the pattern."""
    print("Scanning for Bluetooth devices...")
    nearby_devices = bluetooth.discover_devices(duration=5, lookup_names=True)
    print(nearby_devices)
    for addr, name in nearby_devices:
        if re.search(pattern, name):
            print(f"Found matching device {name} with address {addr}")
            return addr
    print("No matching devices found.")
    return None


def run_bluetoothctl_command(command_list, retries=5, wait_time=2):
    """Run a bluetoothctl command with retries and delays."""
    for attempt in range(retries):
        try:
            result = subprocess.run(command_list, check=True, text=True, capture_output=True)
            if result.returncode == 0:
                return True
        except subprocess.CalledProcessError as e:
            print(f"Attempt {attempt + 1} failed with error: {e.stderr.strip()}")
        time.sleep(wait_time)
    print(f"Command '{' '.join(command_list)}' failed after {retries} attempts.")
    return False


def pair_trust_connect_device(address):
    """Pair, trust, and connect to the Bluetooth device."""
    try:
        # Start a new bluetoothctl process to pair, trust, and connect
        process = subprocess.Popen(['bluetoothctl'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, bufsize=1)

        # Pair with the device
        print(f"Pairing with device {address}...")
        process.stdin.write(f'pair {address}\n')
        process.stdin.flush()
        time.sleep(5)  # Allow time for pairing to complete
        read_process_output(process)  # Read and print output

        # Trust the device
        print(f"Trusting device {address}...")
        process.stdin.write(f'trust {address}\n')
        process.stdin.flush()
        time.sleep(2)  # Allow time for trust command to complete

        # Connect to the device
        print(f"Connecting to device {address}...")
        process.stdin.write(f'connect {address}\n')
        process.stdin.flush()
        time.sleep(5)  # Allow time for connection to complete

        # Terminate the process
        process.terminate()

        return True
        # Verify if the device is connected
        # if self.is_device_connected(address):
        #     print(f"Device {address} is successfully connected.")
        #     self.connected = True
        #     if self.callback:
        # #         self.callback()
        # else:
        #     print(f"Failed to connect to device {address}. Retrying...")

    except subprocess.CalledProcessError as e:
        print(f"Error during pairing/trusting/connecting: {e}")
        return False


def remove_known_devices(pattern):
    """Remove all known Bluetooth devices that match the given pattern in their name."""
    try:
        print(f"Retrieving paired devices to match pattern: {pattern}")
        result = subprocess.run(
            ["bluetoothctl", "devices"],
            check=True,
            text=True,
            capture_output=True,
        )
        devices = result.stdout.strip().split("\n")
        for device in devices:
            match = re.search(r"Device ([0-9A-F:]+) (.+)", device)
            if match:
                addr, name = match.groups()
                if re.search(pattern, name):
                    print(f"Removing device {name} ({addr})...")
                    run_bluetoothctl_command(["bluetoothctl", "remove", addr])
    except subprocess.CalledProcessError as e:
        print(f"Failed to remove devices: {e}")


def is_device_connected(pattern):
    """Check if a Bluetooth device matching the pattern is connected and powered on."""
    try:
        print(f"Checking connected devices for pattern: {pattern}")
        result = subprocess.run(
            ["bluetoothctl", "info"],
            check=True,
            text=True,
            capture_output=True,
        )
        devices_info = result.stdout.strip().split("\n")
        for line in devices_info:
            if "Device" in line and re.search(pattern, line):
                print(f"Device matching {pattern} is currently connected.")
                return True
        print(f"No devices matching {pattern} are connected.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error checking connected devices: {e}")
        return False


def main():
    target_pattern = "SN30.*"

    # Example usage of remove_known_devices
    print("Removing all SN30 devices from known devices list...")
    remove_known_devices(target_pattern)

    # Example usage of is_device_connected
    if is_device_connected(target_pattern):
        print("A device matching SN30 is already connected.")
    else:
        print("No SN30 devices connected. Proceeding to scan and connect...")

    while True:
        device_address = scan_for_device(target_pattern)
        if device_address:
            if pair_trust_connect_device(device_address):
                break  # Exit the loop if successfully paired, trusted, and connected
        else:
            print("Retrying scan in 2 seconds...")
            time.sleep(2)


if __name__ == "__main__":
    main()
