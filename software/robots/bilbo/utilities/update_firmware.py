import tkinter as tk
from tkinter import simpledialog, filedialog, messagebox
import subprocess
import os


class CredentialDialog(simpledialog.Dialog):
    def body(self, master):
        self.title("Enter SSH Credentials")

        tk.Label(master, text="Hostname or IP:").grid(row=0)
        tk.Label(master, text="Username:").grid(row=1)
        tk.Label(master, text="Password:").grid(row=2)

        self.hostname_entry = tk.Entry(master)
        self.username_entry = tk.Entry(master)
        self.password_entry = tk.Entry(master, show="*")

        self.hostname_entry.grid(row=0, column=1)
        self.username_entry.grid(row=1, column=1)
        self.password_entry.grid(row=2, column=1)

        self.username_entry.insert(0, "admin")
        self.password_entry.insert(0, "beutlin")

        return self.hostname_entry

    def apply(self):
        self.result = (
            self.hostname_entry.get(),
            self.username_entry.get(),
            self.password_entry.get()
        )


def ask_for_credentials():
    root = tk.Tk()
    root.withdraw()
    dialog = CredentialDialog(root)
    return dialog.result


def test_ssh_connection(hostname, username, password):
    try:
        test_cmd = [
            "sshpass", "-p", password,
            "ssh", "-o", "StrictHostKeyChecking=no",
            f"{username}@{hostname}", "echo connected"
        ]
        result = subprocess.run(test_cmd, capture_output=True, text=True)
        return "connected" in result.stdout
    except FileNotFoundError:
        messagebox.showerror("Missing sshpass", "The tool 'sshpass' is not installed.")
        return False
    except Exception as e:
        print(f"SSH connection failed: {e}")
        return False


def transfer_file(hostname, username, password, local_path, remote_path="/home/admin/"):
    file_name = os.path.basename(local_path)
    destination = f"{username}@{hostname}:{remote_path}/{file_name}"

    scp_cmd = [
        "sshpass", "-p", password,
        "scp", local_path, destination
    ]
    result = subprocess.run(scp_cmd)
    return result.returncode == 0, f"{remote_path}/{file_name}"


def run_remote_command(hostname, username, password, remote_file_path):
    cmd = f"python3 /home/admin/robot/software/utilities/firmware_update.py {remote_file_path}"
    ssh_cmd = [
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no",
        f"{username}@{hostname}", cmd
    ]
    result = subprocess.run(ssh_cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout.strip(), result.stderr.strip()


def main():
    creds = ask_for_credentials()
    if not creds or not all(creds):
        messagebox.showinfo("Cancelled", "All credentials must be entered.")
        return

    hostname, username, password = creds

    if not test_ssh_connection(hostname, username, password):
        messagebox.showerror("SSH Failed", "Could not connect via SSH.")
        return

    file_path = filedialog.askopenfilename(title="Select a file to send to the Pi")
    if not file_path:
        messagebox.showinfo("Cancelled", "No file selected.")
        return

    success, remote_file_path = transfer_file(hostname, username, password, file_path)
    if not success:
        messagebox.showerror("Transfer Failed", "File transfer failed.")
        return

    success, stdout, stderr = run_remote_command(hostname, username, password, remote_file_path)
    if success:
        messagebox.showinfo("Success", f"Firmware update command executed successfully!\n")
    else:
        messagebox.showerror("Execution Failed", f"Failed to execute firmware update:\n\n{stderr}")

    # Delete remote firmware
    delete_cmd = [
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no",
        f"{username}@{hostname}", f"rm {remote_file_path}"
    ]
    subprocess.run(delete_cmd)


if __name__ == "__main__":
    main()
