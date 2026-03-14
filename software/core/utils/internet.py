import subprocess

def check_internet_connection():
    try:
        # Ping Google's public DNS server
        subprocess.check_output(["ping", "-c", "1", "8.8.8.8"], stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        return False