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


class SetupParamsDialog(simpledialog.Dialog):
    def __init__(self, parent: tk.Misc | None, title: str | None = None):
        super().__init__(parent, title)
        self.size_entry = None
        self.revision_entry = None
        self.result = None

    def body(self, master):
        self.title("Setup Parameters")

        tk.Label(master, text="Board Revision (3, 4, 4.1):").grid(row=0)
        tk.Label(master, text="Size (small, normal, big):").grid(row=1)
        tk.Label(master, text="ID:").grid(row=2)

        self.revision_entry = tk.Entry(master)
        self.size_entry = tk.Entry(master)
        self.id_entry = tk.Entry(master)

        self.revision_entry.grid(row=0, column=1)
        self.size_entry.grid(row=1, column=1)
        self.id_entry.grid(row=2, column=1)

        return self.revision_entry

    def apply(self):
        self.result = (
            self.revision_entry.get(),
            self.size_entry.get(),
            self.id_entry.get()
        )


class SetupOptionDialog(simpledialog.Dialog):
    def body(self, master):
        self.title("Select Setup Option")
        tk.Label(master, text="Choose Option:").grid(row=0, column=0, padx=5, pady=5)

        self.option_var = tk.StringVar(master)
        self.option_var.set("BILBO")  # default value

        # Create dropdown with "BILBO" and "FRODO"
        option_menu = tk.OptionMenu(master, self.option_var, "BILBO", "FRODO")
        option_menu.grid(row=0, column=1, padx=5, pady=5)

        return option_menu

    def apply(self):
        self.result = self.option_var.get()


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
    except Exception as e:
        messagebox.showerror("SSH Error", str(e))
        return False


def ensure_remote_folder_exists(hostname, username, password, folder_path):
    cmd = f"mkdir -p {folder_path}"
    ssh_cmd = [
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no",
        f"{username}@{hostname}", cmd
    ]
    subprocess.run(ssh_cmd)


def select_software_directory():
    root = tk.Tk()
    root.withdraw()
    while True:
        folder = filedialog.askdirectory(title="Choose the Software Directory")
        if not folder:
            return None
        version_file = os.path.join(folder, "VERSION")
        if os.path.exists(version_file):
            return folder
        else:
            messagebox.showerror("Invalid Directory",
                                 "The chosen directory does not contain a VERSION file. Please choose a valid Software Directory.")
            return None


def rsync_folder(local_folder, hostname, username, password, remote_folder):
    cmd = [
        "sshpass", "-p", password,
        "rsync", "-avz",
        "--exclude", ".idea",
        "--exclude", "*.o",
        "--exclude", "*.a",
        "--exclude", "*.pyc",
        "--exclude", "__pycache__",
        "-e", "ssh -o StrictHostKeyChecking=no",
        "--delete-excluded",
        "--delete",
        f"{local_folder}/",  # trailing slash to copy content not folder
        f"{username}@{hostname}:{remote_folder}"
    ]
    result = subprocess.run(cmd)
    return result.returncode == 0


def ask_setup_parameters():
    root = tk.Tk()
    root.withdraw()
    dialog = SetupParamsDialog(root)
    return dialog.result


def run_setup_script(hostname, username, password, option, revision, size, device_id):
    # The option selected from the dropdown is passed as the first parameter
    remote_command = f"python3 /home/admin/robot/software/utilities/setup.py {revision} {size} {device_id}"
    ssh_cmd = [
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no",
        f"{username}@{hostname}", remote_command
    ]
    result = subprocess.run(ssh_cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout, result.stderr


def main():
    creds = ask_for_credentials()
    if not creds or not all(creds):
        messagebox.showinfo("Cancelled", "All credentials must be provided.")
        return

    hostname, username, password = creds

    if not test_ssh_connection(hostname, username, password):
        messagebox.showerror("Connection Failed", "SSH connection failed.")
        return

    remote_folder = "/home/admin/robot/software"
    ensure_remote_folder_exists(hostname, username, password, remote_folder)

    local_folder = select_software_directory()
    if not local_folder:
        messagebox.showinfo("Cancelled", "No valid Software Directory selected.")
        return

    success = rsync_folder(local_folder, hostname, username, password, remote_folder)
    if not success:
        messagebox.showerror("Upload Failed", "Could not upload folder.")
        return

    if messagebox.askyesno("Run Setup?", "Do you want to run setup.py now?"):
        # First, ask for the setup option via a dropdown
        root = tk.Tk()
        root.withdraw()
        option_dialog = SetupOptionDialog(root)
        option = option_dialog.result
        if not option:
            messagebox.showwarning("Incomplete Input", "Setup option must be selected.")
            return

        # Then ask for the rest of the parameters
        params = ask_setup_parameters()
        if not all(params):
            messagebox.showwarning("Incomplete Input", "All fields are required to run setup.")
            return

        revision, size, device_id = params
        success, stdout, stderr = run_setup_script(hostname, username, password, option, revision, size, device_id)

        if success:
            messagebox.showinfo("Setup Complete", f"Setup completed successfully:\n\n{stdout}")
        else:
            messagebox.showerror("Setup Failed", f"Error running setup.py:\n\n{stderr}")


if __name__ == "__main__":
    main()
