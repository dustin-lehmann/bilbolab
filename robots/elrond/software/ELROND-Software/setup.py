from control_board.board_config import generate_board_config
from robot.control.config import generate_default_config
from robot.hardware import generate_hardware_definition
from robot.setup import setup_bilbo


def setup():

    # 1. Generate Board Config
    board_rev = input("Enter the board revision ('3', '4', '4.1'): ")
    if not (board_rev == '3' or board_rev == '4' or board_rev == '4.1'):
        raise ValueError("Invalid board revision")

    generate_board_config(f'rev{board_rev}')

    print("Board Config Generated")

    # 2. Generate Hardware Config
    hardware_config = input("Enter the hardware config ('small', 'normal', 'big): ")
    if not (hardware_config == 'small' or hardware_config == 'normal' or hardware_config == 'big'):
        raise ValueError("Invalid hardware config")

    generate_hardware_definition(size=hardware_config)
    print("Hardware Config Generated")

    # 3. Generate ID:
    robot_id = input("Enter the robot ID: ")
    setup_bilbo(robot_id)

    # 4. Generate Control Config
    generate_default_config()
    print("Control Config Generated")

if __name__ == '__main__':
    setup()