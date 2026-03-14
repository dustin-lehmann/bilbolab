import time

# sys.path.append("/Users/lehmann/work_dir/work_dir/projects/testbed/software/host/scioi_robot_manager")
from extensions.tools.cli.src.cli import CommandArgument, Command, CLI, CommandSet


def testfunction(input_a, input_b, input_string="HALLO"):
    print(f"{input_string}: A: {input_a} B: {input_b}, Sum: {input_a + input_b}")


def example_arguments():
    # testfunction(input_a=1, input_b=2, input_string="TEST")

    cmd = Command(arguments={
        'input_a': CommandArgument(name='input_a',
                                   short_name='a',
                                   type=int,
                                   ),
        'input_b': CommandArgument(name='b',
                                   short_name='b',
                                   type=int,
                                   mapped_name='input_b'),

        'input_string': CommandArgument(name='input_string',
                                        short_name='s',
                                        type=str),
    },
        callback=testfunction)

    cmd.execute(a=1, b=2, input_string="HALLO")


def example_parser():
    command_string = 'stop -a agent1 -time 13.2 --nonverbose'
    command, params = parse_command(command_string)
    print(f'Command: {command}')
    print('Parameters:')
    for key, value in params.items():
        print(f'  {key}: {value}')


def example_cli():
    cli = CLI()

    cmd1 = Command(
        name='command1',
        arguments=[
            CommandArgument(name='input_a',
                            short_name='a',
                            type=int,
                            description="First Input"
                            ),
            CommandArgument(name="input_b",
                            type=int,
                            description='Second Input',
                            short_name='b',
                            mapped_name='input_b'),
            CommandArgument(name='input_string',
                            short_name='s',
                            type=str),
        ],
        callback=testfunction)

    command_set_1 = CommandSet(name='Main')
    command_set_1.addCommand(cmd1)

    command_set_2 = CommandSet(name='subset')
    command_set_2.addCommand(cmd1)
    command_set_1.addChild(command_set_2)

    command_set_3 = CommandSet(name='subset2')
    command_set_2.addChild(command_set_3)
    time.sleep(1)
    cli.start(commandSet=command_set_1)

    while True:
        time.sleep(1)


if __name__ == '__main__':
    example_cli()
