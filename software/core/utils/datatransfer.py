import os
import subprocess


def rsync_host_to_client(source, client_host, dest_folder, username="user", port=22, ignore_file=None,
                         delete_files=False):
    """
    Syncs files or folders from the host to a client PC using rsync over SSH.

    Args:
        source (str): Local path to the file or folder on the host.
        client_host (str): Hostname or IP address of the client PC.
        dest_folder (str): Destination folder on the client.
        username (str): SSH username for the client.
        port (int): SSH port on the client.
        ignore_file (str, optional): Path to a file containing patterns to ignore. Defaults to None.
        delete_files (bool, optional): If True, delete files on the client that are not present on the host.

    Raises:
        subprocess.CalledProcessError: If the rsync command fails.
    """
    rsync_cmd = [
        "rsync", "-avz",
    ]
    # Add the --delete flag if delete_files is True.
    if delete_files:
        rsync_cmd.append("--delete")

    # If an ignore file is specified, add the --exclude-from option.
    if ignore_file:
        rsync_cmd.extend(["--exclude-from", ignore_file])

    rsync_cmd.extend([
        "-e", f"ssh -p {port}",
        source,
        f"{username}@{client_host}:{dest_folder}"
    ])

    print("Executing command:", " ".join(rsync_cmd))
    subprocess.run(rsync_cmd, check=True)
    print("Sync from host to client complete.")


def rsync_client_to_host(remote_source, client_host, dest_folder, username="user", port=22, ignore_file=None,
                         delete_files=False):
    """
    Syncs files or folders from a client PC to the host using rsync over SSH.

    Args:
        remote_source (str): Path to the file or folder on the client PC.
        client_host (str): Hostname or IP address of the client.
        dest_folder (str): Local destination folder on the host.
        username (str): SSH username for the client.
        port (int): SSH port on the client.
        ignore_file (str, optional): Path to a file containing patterns to ignore. Defaults to None.
        delete_files (bool, optional): If True, delete files on the host that are not present on the client.

    Raises:
        FileNotFoundError: If the destination folder doesn't exist locally.
        subprocess.CalledProcessError: If the rsync command fails.
    """
    if not os.path.exists(dest_folder):
        raise FileNotFoundError(f"Destination folder '{dest_folder}' does not exist.")

    rsync_cmd = [
        "rsync", "-avz",
    ]
    # Add the --delete flag if delete_files is True.
    if delete_files:
        rsync_cmd.append("--delete")

    # If an ignore file is specified, add the --exclude-from option.
    if ignore_file:
        rsync_cmd.extend(["--exclude-from", ignore_file])

    rsync_cmd.extend([
        "-e", f"ssh -p {port}",
        f"{username}@{client_host}:{remote_source}",
        dest_folder
    ])

    print("Executing command:", " ".join(rsync_cmd))
    subprocess.run(rsync_cmd, check=True)
    print("Sync from client to host complete.")


def copy_from_client(remote_source, client_host, dest_folder, username="user", port=22):
    """
    Copies a file or folder from a client PC to a local folder (on the host) using SCP.

    Args:
        remote_source (str): Path to the file or folder on the client PC.
                             (Example: "/home/lehmann/experiment_data")
        client_host (str): Hostname or IP address of the client PC.
                           (Example: "shire.local" or "192.168.1.101")
        dest_folder (str): Local destination folder on the host.
                           (Example: "/home/admin/data")
        username (str): SSH username for the client PC.
        port (int): SSH port on the client PC.

    Raises:
        FileNotFoundError: If the destination folder doesn't exist locally.
        subprocess.CalledProcessError: If the SCP command fails.
    """
    # Ensure the local destination folder exists
    if not os.path.exists(dest_folder):
        raise FileNotFoundError(f"Destination folder '{dest_folder}' does not exist.")

    # Build the SCP command.
    # We add the recursive flag (-r) if the remote_source seems to be a directory.
    scp_cmd = ["scp", "-P", str(port)]
    # For simplicity, if remote_source ends with a "/" we assume it's a directory.
    if remote_source.endswith("/"):
        scp_cmd.append("-r")

    # Format remote source as username@client_host:remote_source
    remote_path = f"{username}@{client_host}:{remote_source}"
    scp_cmd.append(remote_path)
    scp_cmd.append(dest_folder)

    print("Executing command:", " ".join(scp_cmd))
    subprocess.run(scp_cmd, check=True)
    print("Copy from client complete.")


def copy_to_client(source, dest_host, dest_folder, username="pi", port=22):
    """
    Transfer a file or folder from the local machine (e.g. your Raspberry Pi)
    to a remote machine using SCP.

    Args:
        source (str): Path to the file or folder to transfer.
        dest_host (str): Hostname or IP address of the destination machine.
        dest_folder (str): Destination folder on the remote machine.
        username (str, optional): Username for SSH login on the destination machine.
                                  Defaults to "pi".
        port (int, optional): SSH port on the destination machine. Defaults to 22.

    Raises:
        FileNotFoundError: If the source file/folder does not exist.
        subprocess.CalledProcessError: If the SCP command fails.

    Note:
        This function relies on the system's `scp` command. Ensure that SSH keys are set up,
        or be prepared to enter the password manually when prompted.
    """
    # Verify that the source exists
    if not os.path.exists(source):
        raise FileNotFoundError(f"Source '{source}' does not exist.")

    # Build the SCP command.
    # - If the source is a directory, add the recursive flag (-r)
    scp_cmd = ["scp", "-P", str(port)]
    if os.path.isdir(source):
        scp_cmd.append("-r")
    scp_cmd.append(source)

    # Construct the destination string in the format username@host:dest_folder
    destination = f"{username}@{dest_host}:{dest_folder}"
    scp_cmd.append(destination)

    # Print the command for debugging purposes (optional)
    print("Executing command:", " ".join(scp_cmd))

    # Execute the command. This will raise an error if the transfer fails.
    subprocess.run(scp_cmd, check=True)

    print("Transfer complete.")


# Example usage:
if __name__ == "__main__":

    dest_folder = os.path.expanduser('~/y/')

    try:
        rsync_host_to_client(dest_folder,
                             "shire.local",
                             "/Users/lehmann/Desktop/y/",
                             username="lehmann",
                             ignore_file=None,
                             delete_files=True)  # Set delete_files as needed
    except Exception as e:
        print("Error syncing client to host:", e)
