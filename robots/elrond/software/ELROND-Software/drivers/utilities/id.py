from paths import settings_file_path
from utils.files import fileExists
from utils.json_utils import readJSON


def readID() -> str:
    if not fileExists(settings_file_path):
        raise FileNotFoundError("Settings file not found. Run Bilbo Setup first")

    data = readJSON(settings_file_path)
    if not 'ID' in data:
        raise KeyError("ID not found. Run Bilbo Setup first")

    return data['ID']
