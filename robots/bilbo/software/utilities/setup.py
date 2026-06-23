from core.utils.files import file_exists, copyFile
from core.hardware.network import get_own_hostname
from hardware.board_config import generateBoardConfig
from robot.config import get_bilbo_config
from robot.control.bilbo_control_config import generate_default_config
from robot.paths import ROBOT_PATH, SOFTWARE_PATH, CONFIG_PATH


def setup():
    robot_id = get_own_hostname()

    # 1. Write the ID file
    write_id_file(robot_id)

    # 2. Check if there is a config file for the specified ID
    config_file = f"{SOFTWARE_PATH}configs/hardware/{robot_id}.yaml"
    if not file_exists(config_file):
        raise FileNotFoundError(f"Config file for robot ID '{robot_id}' not found at '{config_file}'.")
    else:
        print(f"Config file for robot ID '{robot_id}' found: {config_file}")

    # 3. Copy the config file to the robot's config folder'
    copyFile(config_file, f"{CONFIG_PATH}/{robot_id}.yaml")
    print(f"Config file for robot ID '{robot_id}' copied to {CONFIG_PATH}.")

    # 4. Read the BILBO Config
    config = get_bilbo_config(robot_id)

    # 5. Generate the board config for the pin definitions and such
    board_revision = config.electronics.board_revision
    generateBoardConfig(board_rev=board_revision, cm_type=config.electronics.compute_module)

    # 6. Generate the corresponding control config
    generate_default_config(robot_id)

    # 7. Testbed configs are loaded directly from software/configs/testbed/ at runtime.
    #    No copy needed.


def write_id_file(id: str = None):
    if id is None:
        id = get_own_hostname()

    id_file = f"{ROBOT_PATH}/ID"

    with open(id_file, 'w') as file:
        file.write(id)


if __name__ == '__main__':
    setup()


