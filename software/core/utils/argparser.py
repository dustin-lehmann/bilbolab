import dataclasses

@dataclasses.dataclass
class CommandArgument:
    optional: bool = False
    name: str = ""
    type: str = ""
    function_argument: str = ""
    description: str = ""
    identifiers: list[str] = dataclasses.field(default_factory=list)

@dataclasses.dataclass
class Command:
    name: str = ""
    description: str = ""
    arguments: list[CommandArgument] = dataclasses.field(default_factory=list)
    function: callable = None


class CommandLineParser:
    commands: list[Command] = []
