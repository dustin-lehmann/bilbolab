import os
from paths import robot_path, settings_file_path
from utils.files import fileExists, createFile
from utils.json_utils import readJSON, writeJSON


def setup_bilbo(ID):
    # Generate settings.json file
    if fileExists(settings_file_path):
        data = readJSON(settings_file_path)

    else:
        data = {}

    data['ID'] = ID
    writeJSON(settings_file_path, data)

    if not fileExists(f"{robot_path}/{ID}"):
        createFile(f"{robot_path}/{ID}")


if __name__ == '__main__':
    setup_bilbo('bilbo1')
