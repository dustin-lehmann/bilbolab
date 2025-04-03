import os
import subprocess
import getpass
import pexpect
import sys


def enable_ssh(user=None, address=None):
    """
    Ensures that an SSH key exists and copies it to the given user@address via ssh-copy-id.

    Workflow:
    1. Pings the host to ensure it is reachable.
       If not, prints an error and exits.
    2. Checks for the existence of ~/.ssh/id_rsa; if missing, generates an RSA key pair.
    3. If 'user' is not provided (empty or None), prompts the user for a username.
    4. Uses ssh-copy-id (via pexpect) to copy the public key to the remote host.
    5. Parses the ssh-copy-id output to give a more readable status message.

    Parameters:
        user (str): The username for the remote host. If empty, the user will be prompted.
        address (str): The hostname or IP address of the remote host.
    """

    # Ping the host first to ensure it is reachable
    if address is None or not address:
        address = input("Enter hostname or IP address of the remote host: ")

    print(f"Pinging {address}...")
    try:
        ping = subprocess.run(["ping", "-c", "1", address],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ping.returncode != 0:
            print(f"Error: Host {address} is not reachable on the network.")
            sys.exit(1)
    except Exception as e:
        print(f"Error while trying to ping {address}: {e}")
        sys.exit(1)

    # If no user is provided, prompt for it
    if not user:
        user = input("Enter username for the remote host: ")

    remote = f"{user}@{address}"

    # Ensure the SSH directory exists and check for id_rsa key
    ssh_dir = os.path.expanduser("~/.ssh")
    id_rsa = os.path.join(ssh_dir, "id_rsa")
    if not os.path.exists(ssh_dir):
        os.makedirs(ssh_dir, mode=0o700)

    # Generate SSH key if it does not exist
    if not os.path.exists(id_rsa):
        print("SSH key not found. Generating a new RSA key pair...")
        try:
            subprocess.run(
                ["ssh-keygen", "-t", "rsa", "-N", "", "-f", id_rsa],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print("Error generating SSH key:", e)
            return

    # Prompt for the SSH password for the remote host
    password = getpass.getpass(f"Enter SSH password for {remote}: ")

    # Use pexpect to run ssh-copy-id and handle the password prompt
    command = f"ssh-copy-id {remote}"
    try:
        child = pexpect.spawn(command, timeout=30)
        index = child.expect(["assword:", pexpect.EOF, pexpect.TIMEOUT])

        if index == 0:
            # Found a password prompt; send the password.
            child.sendline(password)
            child.expect(pexpect.EOF)
        elif index == 1:
            # EOF encountered immediately (e.g. key already exists)
            pass
        elif index == 2:
            print("Timed out waiting for ssh-copy-id.")
            return

        # Get the output of ssh-copy-id
        output = child.before.decode('utf-8') if child.before else ""
        # Parse output for known messages
        if "already" in output.lower():
            print(f"Notice: SSH key already exists on the remote host {remote}.")
        elif "failed" in output.lower():
            print(f"Error: SSH key copy failed for {remote}. Details:\n{output}")
        else:
            print(f"Success: SSH key successfully copied to {remote}.")

    except pexpect.exceptions.TIMEOUT:
        print("Timed out waiting for ssh-copy-id. Please try again.")
    except pexpect.exceptions.ExceptionPexpect as e:
        print("An error occurred during ssh-copy-id:", e)


if __name__ == "__main__":
    # Example usage: provide an empty string for user to test prompting,
    # or supply the username directly.

    enable_ssh()
