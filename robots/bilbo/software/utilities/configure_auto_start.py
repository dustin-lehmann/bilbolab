import argparse
import subprocess

CRON_ENTRY = "@reboot sleep 20 && /bin/bash -lic 'python3 /home/admin/robot/software/main.py' >> /home/admin/robot/autostart.log 2>&1 &"

def configure_auto_start(enable: bool):
    """Add or remove the BILBO auto-start entry from crontab."""
    result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""

    lines = [line for line in existing.splitlines() if line.strip() != CRON_ENTRY]

    if enable:
        lines.append(CRON_ENTRY)
        print("Auto-start enabled.")
    else:
        print("Auto-start disabled.")

    new_crontab = "\n".join(lines) + "\n" if lines else ""
    subprocess.run(['crontab', '-'], input=new_crontab, text=True, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Configure BILBO auto-start on boot')
    parser.add_argument('enable', type=str, choices=['true', 'false'], help='Enable or disable auto-start')

    args = parser.parse_args()
    configure_auto_start(args.enable == 'true')

