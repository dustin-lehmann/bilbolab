from extensions.tools.cli.src.cli import Command, CommandSet, CommandArgument, CLI, CLI_Connector


def function1_set1(a: float):
    print(f"Function 1 Set 1: {a=}")


def function2_set1(x: float, y: float):
    print(f"Function 2 Set 1: {x=}, {y=}")


def function1_set2(a, b):
    print(f"Function 1 Set 2: {a=}, {b=}")


def function2_set2(x: float, y: float, z: float):
    print(f"Function 2 Set 2: {x=}, {y=}, {z=}")


def function_root_set(input: str):
    print(f"Function 1 Root Set: {input}")


def main():
    command1_set1 = Command(name='function1',
                            callback=function1_set1,
                            arguments=[CommandArgument(name='a',
                                                       short_name='a',
                                                       type=int), ])

    command2_set1 = Command(name='function2',
                            callback=function2_set1,
                            arguments=[CommandArgument(name='x',
                                                       type=int),
                                       CommandArgument(name='y', type=int)])

    command1_set2 = Command(name='function1',
                            callback=function1_set2,
                            arguments=[CommandArgument(name='a', short_name='a', type=int),
                                       CommandArgument(name='b', short_name='b', type=str)])

    command2_set2 = Command(name='function2',
                            callback=function2_set2,
                            arguments=[CommandArgument(name='x', type=int),
                                       CommandArgument(name='y', type=int),
                                       CommandArgument(name='z', type=int)])

    command_set2 = CommandSet(name='set2',
                              commands=[command1_set2, command2_set2])

    command_set1 = CommandSet(name='set1',
                              commands=[command1_set1, command2_set1],
                              child_sets=[command_set2])

    command_root = Command(name='function-root',
                           callback=function_root_set,
                           arguments=[CommandArgument(name='input',
                                                      short_name='i',
                                                      type=str)],

                           description='Function root command')

    root_set = CommandSet(name='.',
                          commands=[command_root],
                          child_sets=[command_set1])

    cli = CLI(root_set=root_set)

    ret = cli.runCommand('help')
    print(ret)


    return
    # cli.runCommand('set1 set2')
    # cli.runCommand('..')
    # cli.runCommand('function1 -a 2')

    command_set_description = cli.getCommandSetDescription()
    # print(command_set_description)
    cli_connector = CLI_Connector()
    cli_connector.setCommandSets(command_set_description)

    # ret = cli_connector.parseCommand("")
    ret = cli_connector.parseCommand('. set1 set2 function2 --x 2 -y 3 -z 4')

    print(ret)
    cli.executeFromConnectorDict(ret['command'])


def main2():
    default_set = CommandSet(name='default-set',
                             commands=[])
    cli = CLI(default_set)
    command_set_description = cli.getCommandSetDescription()
    print(command_set_description)
    cli_connector = CLI_Connector()
    cli_connector.setCommandSets(command_set_description)


if __name__ == '__main__':
    main()
