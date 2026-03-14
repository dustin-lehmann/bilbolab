from extensions.tools.cli.src.cli import CLI, Command, CommandSet, CommandArgument, CLI_Connector


def test_function(alter, b=88):
    print(f"a={alter}, b={b}")


command_test = Command(name='test', description='Test command',
                       callback=test_function,
                       allow_positionals=True,
                       arguments=[
                           CommandArgument(name='a',
                                           type=list[str],
                                           original_name='alter',
                                           array_size=3),
                           CommandArgument(name='b',
                                           type=int,
                                           optional=True)

                       ])

command_set_test = CommandSet(name='test', description='Test command set',
                              commands=[command_test])


def main():
    cli = CLI(command_set_test)

    cli.runCommand('test -a [1,3,5] -b 3')

    cli_dict = cli.getCommandSetDescription()

    cli_connector = CLI_Connector(cli_dict)

    x = cli_connector.parseCommand('test -a [1,3,5]')

    # print(x)
    cli.executeFromConnectorDict(x['command'])


if __name__ == '__main__':
    main()
