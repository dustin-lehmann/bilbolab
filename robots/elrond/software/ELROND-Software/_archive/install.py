#
#
#
# def generateBoardConfig():
#     def generateNewBoardConfig():
#         if result == "y":
#             revision = input("What revision is the board? (3 or 4)")
#             if revision == "3":
#                 generate_board_config('rev3')
#             elif revision == "4":
#                 generate_board_config('rev4')
#             else:
#                 print("Invalid revision")
#                 return
#
#     print("-------------------------------")
#     print("Board Configuration")
#
#     board_config = getBoardConfig()
#
#     if board_config is None:
#         print("No board configuration found")
#         result = input("Would you like to generate a board configuration? (y/n) ")
#         generateNewBoardConfig()
#     else:
#         print("Board configuration found")
#         result = input("Would you like to generate a new board configuration? (y/n) ")
#         generateNewBoardConfig()
#
# # ======================================================================================================================
# def installPackages():
#     print("-------------------------------")
#     print("Installing packages")
#     internet_connection = check_internet_connection()
#     if not internet_connection:
#         print("No internet connection, cannot install packages")
#         return
#
#     # TODO
#
#
# def compileFirmwareFlasher():
#     print("-------------------------------")
#     print("Compiling STM32Flash")
#     compileSTM32Flash()
#
# def setupStartUpTasks():
#     print("-------------------------------")
#     print("Setting up startup tasks")
#
# def generateRobotConfig():
#     ...
#
# def checkHardware():
#     ...
#
# def install():
#     # Install Packages
#     installPackages()
#
#     # Compile STM32Flash
#     compileFirmwareFlasher()
#
#     # Setup startup tasks
#     setupStartUpTasks()
#
#     # Generate Board config
#     generateBoardConfig()
#
#     # Generate Robot Config
#     generateRobotConfig()
#
#     # Test and check hardware
#     checkHardware()
#
# if __name__ == '__main__':
#     install()