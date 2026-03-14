import platform

from core.utils.files import get_absolute_path, file_exists
from core.utils.yaml_utils import load_yaml


def get_joystick_mapping(joystick_name:str):
    os_name = platform.system().lower()
    joystick_name = joystick_name.replace(' ', '_').lower()
    mapping_file = get_absolute_path(f"./mappings/{joystick_name}-{os_name}.yaml")

    if not file_exists(mapping_file):
        raise FileNotFoundError(f"Joystick mapping file not found: {mapping_file}")

    mapping = load_yaml(mapping_file)
    return mapping



# os_name = platform.system()
# if os_name == "Darwin":
#     joystick_mappings = {
#         'PS4 Controller': {
#             'BUTTONS': {
#                 'A': 0,
#                 'B': 1,
#                 'X': 2,
#                 'Y': 3,
#                 'L1': 9,
#                 'R1': 10,
#                 'L3': 7,
#                 'R3': 8,
#                 'START': 6,
#                 'SELECT': 4,
#                 'DPAD_RIGHT': 14,
#                 'DPAD_LEFT': 13,
#                 'DPAD_UP': 11,
#                 'DPAD_DOWN': 12,
#
#             },
#             'AXES': {
#                 'LEFT_VERTICAL': 1,
#                 'LEFT_HORIZONTAL': 0,
#                 'RIGHT_VERTICAL': 3,
#                 'RIGHT_HORIZONTAL': 2,
#                 'LEFT_TRIGGER': 4,
#                 'RIGHT_TRIGGER': 5
#             }
#         },
#         'Nintendo Switch Pro Controller': {
#             'BUTTONS': {
#                 'A': 0,
#                 'B': 1,
#                 'X': 2,
#                 'Y': 3,
#                 'L1': 9,
#                 'R1': 10,
#                 'L3': 7,
#                 'R3': 8,
#                 'START': 6,
#                 'SELECT': 4,
#             },
#             'AXES': {
#                 'LEFT_VERTICAL': 1,
#                 'LEFT_HORIZONTAL': 0,
#                 'RIGHT_VERTICAL': 3,
#                 'RIGHT_HORIZONTAL': 2,
#                 'LEFT_TRIGGER': 4,
#                 'RIGHT_TRIGGER': 5
#             }
#         },
#         'Xbox One S Controller': {
#             'BUTTONS': {
#                 'A': 1,
#                 'B': 0,
#                 'X': 3,
#                 'Y': 2,
#                 'L1': 9,
#                 'R1': 10,
#                 'L3': 7,
#                 'R3': 8,
#                 'START': 6,
#                 'SELECT': 4,
#                 'DPAD_RIGHT': 14,
#                 'DPAD_LEFT': 13,
#                 'DPAD_UP': 11,
#                 'DPAD_DOWN': 12,
#             },
#             'AXES': {
#                 'LEFT_VERTICAL': 1,
#                 'LEFT_HORIZONTAL': 0,
#                 'RIGHT_VERTICAL': 3,
#                 'RIGHT_HORIZONTAL': 2,
#                 'LEFT_TRIGGER': 4,
#                 'RIGHT_TRIGGER': 5
#             }
#         },
#         '8BitDo Lite 2': {
#             'BUTTONS': {
#                 'A': 0,
#                 'B': 1,
#                 'X': 2,
#                 'Y': 3,
#                 'L1': 4,
#                 'R1': 5,
#                 'L3': 6,
#                 'R3': 7,
#                 'START': 10,
#                 'SELECT': 8,
#             },
#             'AXES': {
#                 'LEFT_VERTICAL': 1,
#                 'LEFT_HORIZONTAL': 0,
#                 'RIGHT_VERTICAL': 4,
#                 'RIGHT_HORIZONTAL': 3,
#                 'LEFT_TRIGGER': 2,
#                 'RIGHT_TRIGGER': 5,
#             },
#         },
#     }
# elif os_name == "Windows":
#     joystick_mappings = {}
# elif os_name == "Linux":
#     joystick_mappings = {
#         'PS4 Controller': {
#             'BUTTONS': {
#                 'A': 0,
#                 'B': 1,
#                 'X': 2,
#                 'Y': 3,
#                 'L1': 9,
#                 'R1': 10,
#                 'L3': 7,
#                 'R3': 8,
#                 'START': 6,
#                 'SELECT': 4,
#                 'DPAD_RIGHT': 14,
#                 'DPAD_LEFT': 13,
#                 'DPAD_UP': 11,
#                 'DPAD_DOWN': 12,
#
#             },
#             'AXES': {
#                 'LEFT_VERTICAL': 1,
#                 'LEFT_HORIZONTAL': 0,
#                 'RIGHT_VERTICAL': 3,
#                 'RIGHT_HORIZONTAL': 2,
#                 'LEFT_TRIGGER': 4,
#                 'RIGHT_TRIGGER': 5
#             }
#         },
#         'Nintendo Switch Pro Controller': {
#             'BUTTONS': {
#                 'A': 0,
#                 'B': 1,
#                 'X': 2,
#                 'Y': 3,
#                 'L1': 9,
#                 'R1': 10,
#                 'L3': 7,
#                 'R3': 8,
#                 'START': 6,
#                 'SELECT': 4,
#             },
#             'AXES': {
#                 'LEFT_VERTICAL': 1,
#                 'LEFT_HORIZONTAL': 0,
#                 'RIGHT_VERTICAL': 3,
#                 'RIGHT_HORIZONTAL': 2,
#                 'LEFT_TRIGGER': 4,
#                 'RIGHT_TRIGGER': 5
#             }
#         },
#         'Xbox One S Controller': {
#             'BUTTONS': {
#                 'A': 1,
#                 'B': 0,
#                 'X': 3,
#                 'Y': 2,
#                 'L1': 9,
#                 'R1': 10,
#                 'L3': 7,
#                 'R3': 8,
#                 'START': 6,
#                 'SELECT': 4,
#                 'DPAD_RIGHT': 14,
#                 'DPAD_LEFT': 13,
#                 'DPAD_UP': 11,
#                 'DPAD_DOWN': 12,
#             },
#             'AXES': {
#                 'LEFT_VERTICAL': 1,
#                 'LEFT_HORIZONTAL': 0,
#                 'RIGHT_VERTICAL': 4,
#                 'RIGHT_HORIZONTAL': 3,
#                 'LEFT_TRIGGER': 2,
#                 'RIGHT_TRIGGER': 5
#             }
#         },
#         '8BitDo Lite 2': {
#             'BUTTONS': {
#                 'A': 0,
#                 'B': 1,
#                 'X': 2,
#                 'Y': 3,
#                 'L1': 4,
#                 'R1': 5,
#                 'L3': 6,
#                 'R3': 7,
#                 'START': 10,
#                 'SELECT': 8,
#             },
#             'AXES': {
#                 'LEFT_VERTICAL': 1,
#                 'LEFT_HORIZONTAL': 0,
#                 'RIGHT_VERTICAL': 4,
#                 'RIGHT_HORIZONTAL': 3,
#                 'LEFT_TRIGGER': 2,
#                 'RIGHT_TRIGGER': 5,
#             },
#         },
#     }
# else:
#     print(f"Unknown OS: {os_name}")
