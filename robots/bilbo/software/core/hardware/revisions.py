import os

VERSION_FILE_PATH = '~/software/VERSION'


def get_versions():
    # Resolve the full path of the version file
    version_file_path = os.path.expanduser(VERSION_FILE_PATH)

    with open(version_file_path, 'r') as version_file:
        # Read the file contents
        lines = version_file.read().strip().splitlines()

        # Initialize variables to hold extracted values
        software_version = None
        stm32_firmware_requirement = None
        repository = None

        # Parse the lines based on the new format
        for line in lines:
            if line.startswith("Software:"):
                software_version = line.split(':')[1].strip()
            elif line.startswith("STM32_Firmware:"):
                stm32_firmware_requirement = line.split('>')[1].strip()
            elif line.startswith("Repo:"):
                repository = line.split(':', 1)[1].strip()

        # Extract major and minor versions
        software_major, software_minor = map(int, software_version.split('.'))
        stm32_major, stm32_minor = map(int, stm32_firmware_requirement.split('.'))

        # Construct the output dictionary
        output = {
            'software': {
                'major': software_major,
                'minor': software_minor,
            },
            'stm32_firmware': {
                'major': stm32_major,
                'minor': stm32_minor,
            },
            'repository': repository
        }

        return output


def is_ll_version_compatible(current_ll_version, min_ll_version):
    current_major, current_minor = current_ll_version
    min_major, min_minor = min_ll_version

    if current_major > min_major:
        return True
    elif current_major == min_major and current_minor >= min_minor:
        return True
    return False
