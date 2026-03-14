import re
import subprocess
import sys
import threading
import time
import json
import os

from robot.utilities.buzzer import beep

# Path to the devices.json file
devices_file_path = os.path.join(os.path.dirname(__file__), 'devices.json')
# Add the top-level module to the Python path
top_level_module = os.path.expanduser("~/software")
if top_level_module not in sys.path:
    sys.path.insert(0, top_level_module)

def restart_bluetooth_service():
    """
    Restart the Bluetooth service and cycle the Bluetooth adapter on the Raspberry Pi.
    """
    try:
        subprocess.check_output(['sudo', 'systemctl', 'restart', 'bluetooth'], universal_newlines=True)
        print("Bluetooth service has been restarted.")
        # Bring the Bluetooth adapter down and back up
        subprocess.check_output(['sudo', 'hciconfig', 'hci0', 'down'], universal_newlines=True)
        time.sleep(1)
        subprocess.check_output(['sudo', 'hciconfig', 'hci0', 'up'], universal_newlines=True)
        print("Bluetooth adapter has been cycled.")
    except subprocess.CalledProcessError:
        print("Error: Unable to restart Bluetooth service or cycle Bluetooth adapter.")


def list_paired_devices():
    """
    List all paired Bluetooth devices with their addresses and names using bluetoothctl.

    Returns:
    list of tuple: A list of paired devices, each represented as a tuple (address, name).
    """
    try:
        output = subprocess.check_output(['bluetoothctl', 'paired-devices'], universal_newlines=True)
    except subprocess.CalledProcessError:
        print("Error: Unable to run bluetoothctl command.")
        return []

    devices = []
    for line in output.splitlines():
        match = re.match(r"Device ([0-9A-F:]+) (.+)", line)
        if match:
            address, name = match.groups()
            devices.append((address, name))
    return devices


def get_known_devices_with_pattern(pattern) -> dict:
    """
    Find all Bluetooth devices that have a certain pattern in their name using bluetoothctl.

    Parameters:
    pattern (str): The pattern to search for within the device names.

    Returns:
    list of tuple: A list of matched devices, each represented as a tuple (address, name).
    """
    devices = list_paired_devices()
    regex = re.compile(pattern, re.IGNORECASE)
    matched_devices = [address for address, name in devices if regex.search(name)]

    if len(matched_devices) == 0:
        return None
    return matched_devices


def remove_paired_device(address):
    """
    Remove a paired Bluetooth device by its address using bluetoothctl, including removing trust.

    Parameters:
    address (str): The Bluetooth address of the device to be removed.

    Returns:
    bool: True if the device was successfully removed, False otherwise.
    """
    print("Remove")
    try:
        subprocess.check_output(['bluetoothctl', 'remove', address], universal_newlines=True)
    except subprocess.CalledProcessError:
        print(f"Error: Unable to remove device {address}.")
    try:
        subprocess.check_output(['bluetoothctl', 'untrust', address], universal_newlines=True)
    except subprocess.CalledProcessError:
        print(f"Error: Unable to remove device {address}.")
    try:
        subprocess.check_output(['bluetoothctl', 'remove', address], universal_newlines=True)
    except subprocess.CalledProcessError:
        print(f"Error: Unable to remove device {address}.")

        return True


def pair_and_connect_device(address):
    """
    Pair, trust, and connect to a Bluetooth device using a single bluetoothctl session.

    Parameters:
    address (str): The Bluetooth address of the device to pair, trust, and connect.

    Returns:
    bool: True if the device was successfully paired, trusted, and connected; False otherwise.
    """
    try:
        process = subprocess.Popen(['bluetoothctl'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, universal_newlines=True)
        commands = [
            f"pair {address}\n",
            f"trust {address}\n",
            f"connect {address}\n",
        ]
        for command in commands:
            process.stdin.write(command)
            process.stdin.flush()
            time.sleep(2)  # Allow time for each command to take effect

        output, error = process.communicate()
        if "Connected: yes" in output:
            print(f"Device {address} has been paired, trusted, and connected.")
            return True
        else:
            print(f"Failed to connect to device {address}. Output: {output}")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def scan_for_devices_with_pattern(pattern, scan_time):
    """
    Scan the Bluetooth environment for a given amount of time and return a list of devices that match the pattern,
    including their connected, paired, and trusted status.

    Parameters:
    pattern (str): The pattern to search for within the device names.
    scan_time (int): The number of seconds to scan for devices.

    Returns:
    list: A list of matched devices, each represented as a dictionary with address, name, connected, paired, and trusted status.
    """
    try:
        print(f"Start scanning for devices with pattern '{pattern}' for {scan_time} seconds.")
        # Start scanning
        scan_process = subprocess.Popen(['bluetoothctl', 'scan', 'on'], stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)
        start_time = time.time()
        regex = re.compile(pattern, re.IGNORECASE)
        matched_devices = {}

        while time.time() - start_time < scan_time:
            # Get the list of devices
            output = subprocess.check_output(['bluetoothctl', 'devices'], universal_newlines=True)
            for line in output.splitlines():
                match = re.match(r"Device ([0-9A-F:]+) (.+)", line)
                if match:
                    address, name = match.groups()
                    if regex.search(name):
                        if address not in matched_devices:
                            matched_devices[address] = {"address": address, "name": name, "connected": None,
                                                        "paired": None, "trusted": None}
            time.sleep(1)

        # Stop scanning
        subprocess.Popen(['bluetoothctl', 'scan', 'off'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Check the info for each matched device
        for address in matched_devices:
            try:
                info_output = subprocess.check_output(['bluetoothctl', 'info', address], universal_newlines=True)
                connected = re.search(r"Connected:\s+(yes|no)", info_output)
                paired = re.search(r"Paired:\s+(yes|no)", info_output)
                trusted = re.search(r"Trusted:\s+(yes|no)", info_output)

                matched_devices[address]["connected"] = connected.group(1) if connected else "unknown"
                matched_devices[address]["paired"] = paired.group(1) if paired else "unknown"
                matched_devices[address]["trusted"] = trusted.group(1) if trusted else "unknown"
            except subprocess.CalledProcessError:
                print(f"Error: Unable to retrieve info for device {address}.")
                matched_devices[address]["connected"] = "unknown"
                matched_devices[address]["paired"] = "unknown"
                matched_devices[address]["trusted"] = "unknown"

        print(f"Scan complete. Found {len(matched_devices)} matching device(s).")
        return list(matched_devices.values())

    except subprocess.CalledProcessError:
        print("Error: Unable to run bluetoothctl command.")
        return []


def ping_bluetooth_device(address, password):
    """
    Ping a Bluetooth device to check connectivity using sudo with a provided password.

    Parameters:
    address (str): The Bluetooth address of the device to ping.
    password (str): The sudo password for the user.

    Returns:
    bool: True if the ping was successful, False otherwise.
    """
    try:
        command = f'echo {password} | sudo -S l2ping -c 1 {address}'
        output = subprocess.check_output(command, shell=True, universal_newlines=True)
        if "1 received" in output:
            return True
    except subprocess.CalledProcessError:
        print(f"Error: Unable to ping device {address}.")
    return False


def is_device_connected(address):
    """
    Check if a Bluetooth device with a given address is currently connected using bluetoothctl.

    Parameters:
    address (str): The Bluetooth address of the device to check.

    Returns:
    bool: True if the device is currently connected, False otherwise.
    """
    try:
        output = subprocess.check_output(['bluetoothctl', 'info', address], universal_newlines=True)
        if re.search(r'Connected: yes', output):
            # Try to ping the device
            # ping_success = ping_bluetooth_device(address, 'beutlin')  # TODO: store the passwd somewhere else
            # if ping_success:
            #     return True
            # return False
            return True
    except subprocess.CalledProcessError:
        print(f"Error: Unable to get info for device {address}.")
    return False


def find_connected_device_with_pattern(pattern):
    matched_devices = get_known_devices_with_pattern(pattern)
    if matched_devices is None:
        return None

    for address in matched_devices:
        if is_device_connected(address):
            return address

    return None


class JoystickScanner:
    _thread: threading.Thread
    pattern: str
    _exit: bool = False

    connected: bool = False
    connected_controller: str = None
    known_devices: list

    def __init__(self, pattern: str = '8BitDo'):

        self.scan_time = 5
        self.pattern = pattern
        self.known_devices = []
        self._thread = threading.Thread(target=self._task, daemon=True)

    def init(self):
        ...

    def start(self):
        self._thread.start()

    def close(self):
        self._exit = True
        self._thread.join()

    def resetKnownDevices(self):
        known_controllers = get_known_devices_with_pattern(self.pattern)

        if known_controllers is not None:
            for controller in known_controllers:
                remove_paired_device(controller)

    # def

    def _task(self):
        while not self._exit:
            if self.connected:
                # Check if the controller is still connected:
                still_connected = is_device_connected(self.connected_controller)
                if still_connected:
                    print(f"Controller {self.connected_controller} is still connected.")
                    time.sleep(5)
                    continue
                else:
                    self.connected = False
                    self.connected_controller = None

            # Check for known controllers
            known_controllers = get_known_devices_with_pattern(self.pattern)
            if known_controllers is not None:
                # Check if they are currently connected
                for address in known_controllers:
                    print(f"A controller with address {address} is known")
                    if address not in self.known_devices:
                        self.known_devices.append(address)
                    controller_is_connected: bool = is_device_connected(address)
                    if controller_is_connected:
                        print(f"A known controller with address {address} is currently connected")
                        self.connected = True
                        self.connected_controller = address
                    else:
                        print(f"The known controller {address} is not currently connected")

            if not self.connected:
                # If there are no currently connected controllers, scan for controllers
                scanned_controllers = scan_for_devices_with_pattern(self.pattern, self.scan_time)

                if len(scanned_controllers) > 0:
                    for controller in scanned_controllers:
                        if controller not in self.known_devices:
                            if controller['paired'] == 'no' and controller['trusted'] == 'yes':
                                # remove_paired_device(controller['address'])
                                continue
                            result = pair_and_connect_device(controller['address'])
                            if result:
                                print(f"Successfully connected to {controller['address']}")

            time.sleep(1)


def scan_and_connect(pattern, retries=8, scan_time=5) -> bool:
    # Check if a joystick is connected:
    known_controllers = get_known_devices_with_pattern(pattern)
    if known_controllers is not None:
        # Check if they are currently connected
        for address in known_controllers:
            print(f"A controller with address {address} is known")
            controller_is_connected: bool = is_device_connected(address)
            if controller_is_connected:
                print(f"A known controller with address {address} is currently connected")
                return True

    # If not: remove all devices and start scanning:
    known_controllers = get_known_devices_with_pattern(pattern)
    if known_controllers is not None:
        for controller in known_controllers:
            print("Remove")
            remove_paired_device(controller)

    for i in range(0, retries):
        scanned_controllers = scan_for_devices_with_pattern(pattern, scan_time)

        if len(scanned_controllers) > 0:
            for controller in scanned_controllers:
                if controller['paired'] == 'no' and controller['trusted'] == 'yes':
                    remove_paired_device(controller['address'])
                    continue
                result = pair_and_connect_device(controller['address'])
                if result:
                    print(f"Successfully connected to {controller['address']}")
                    beep(frequency='high', repeats=3)
                    return True

    return False


if __name__ == '__main__':
    result = scan_and_connect(pattern='8BitDo')
    print(result)
