from __future__ import annotations
import dataclasses
import inspect
import re
import threading
import time
from collections.abc import Callable
from typing import Any

# === CUSTOM MODULES ===================================================================================================
from core.utils.callbacks import Callback, CallbackContainer, callback_definition
from core.utils.logging_utils import Logger


# === HELPER FUNCTIONS =================================================================================================
def splitCommandString(command_string: str) -> list[str]:
    ...


def typecastArgument(arg: CommandArgument, value: Any) -> Any:
    print(f"typecastArgument({arg.name}, {value})")
    return arg.cast(value)


# === CommandArgument ==================================================================================================
@dataclasses.dataclass
class CommandArgument:
    name: str
    type: type
    short_name: str = None
    array_size: int = 0
    original_name: str = None
    description: str = None
    default: object = None
    optional: bool = False
    is_flag: bool = False
    position: int | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def cast(self, value) -> Any:
        """
        Convert `value` to the expected type.  Flags ('is_flag') get special treatment:
          - bool values pass through
          - '0' or '1' strings (or ints) map to False/True
          - anything else raises ValueError
        Arrays still work as before.
        """
        # --- FLAG SHORT-CIRCUIT ---
        if self.is_flag:
            # if they already gave us a bool
            if isinstance(value, bool):
                return value
            # try 0 or 1
            s = str(value).strip()
            if s in ('0', '1'):
                return s == '1'
            raise ValueError(f"Cannot convert value '{value}' for flag '{self.name}' to boolean.")

        # --- ARRAY HANDLING (unchanged) ---
        if self.array_size > 0:
            inner_type = self.type
            if hasattr(self.type, '__origin__') and self.type.__origin__ == list:
                inner_type = self.type.__args__[0]
            if isinstance(value, list):
                if len(value) != self.array_size:
                    raise ValueError(f"Expected {self.array_size} values, got {len(value)}.")
                return [inner_type(v) for v in value]
            elif isinstance(value, str):
                match = re.fullmatch(r'\[(.*)]', value.strip())
                if not match:
                    raise ValueError(f"Value for argument '{self.name}' must be enclosed in brackets [].")
                parts = [v.strip() for v in match.group(1).split(',')]
                if len(parts) != self.array_size:
                    raise ValueError(f"Expected {self.array_size} values, got {len(parts)}.")
                return [inner_type(v) for v in parts]
            else:
                raise ValueError(f"Unsupported value type for argument '{self.name}'.")

        # --- NON-ARRAY FALLBACK ---
        if hasattr(self.type, '__origin__') and self.type.__origin__ == list:
            inner_type = self.type.__args__[0]
            return inner_type(value)
        return self.type(value)

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'name': self.name,
            'type': self.type.__name__,
            'array_size': self.array_size,
            'short_name': self.short_name,
            'original_name': self.original_name,
            'description': self.description,
            'default': self.default,
            'optional': self.optional,
            'is_flag': self.is_flag,
            'position': self.position,
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def __post_init__(self):
        if self.short_name is None:
            self.short_name = self.name


# === Command ==========================================================================================================
@callback_definition
class Command_Callbacks:
    completed: CallbackContainer


class Command:
    name: str
    description: str
    arguments: dict[str, CommandArgument] = None
    function: Callback
    execute_in_thread: bool
    allow_positionals: bool

    set: CommandSet = None

    # === INIT =========================================================================================================
    def __init__(self, name,
                 function: Callback | Callable = None,
                 description='',
                 arguments: list[CommandArgument] = None,
                 allow_positionals=True,
                 execute_in_thread=False):
        self.name = name
        self.execute_in_thread = execute_in_thread
        self.description = description
        self.allow_positionals = allow_positionals
        self.function = function

        self.callbacks = Command_Callbacks()

        self.logger = Logger(f"Command \"{self.name}\"", "WARNING")

        if not hasattr(self, 'arguments') or self.arguments is None:
            self.arguments = {}

        if arguments is not None:
            for position, argument in enumerate(arguments):
                self.arguments[argument.name] = argument
                argument.position = position + 1 if allow_positionals else None

    # ------------------------------------------------------------------------------------------------------------------
    def call(self, *args, **kwargs) -> Any | None:
        if self.function is not None:
            if self.execute_in_thread:
                try:
                    threading.Thread(target=self._run, args=args, kwargs=kwargs).start()
                except Exception as e:
                    self.logger.error(f"Error in thread: {e}")
            else:
                return_value = self.function(*args, **kwargs)
                self.callbacks.completed.call(return_value)
                return return_value
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _run(self, *args, **kwargs):
        return_value = self.function(*args, **kwargs)
        self.callbacks.completed.call(return_value)

    # ------------------------------------------------------------------------------------------------------------------
    def runFromCommandInput(self, command: str) -> Any | None:
        """
        Parse the raw command string, fill in defaults/flags, and execute the associated callback.
        """
        # 1. Parse the input into positional and keyword argument dictionaries
        parsed = self._parseCommandString(command)
        if parsed is None:
            return None

        positional_args: dict[str, Any] = parsed['positional_args']
        keyword_args: dict[str, Any] = parsed['keyword_args']

        # 2. Inspect callback signature for any default parameter values
        cb_signature = None
        if self.function is not None:
            try:
                cb_signature = inspect.signature(self.function)
            except Exception as e:
                self.logger.error(f"Error inspecting callback signature: {e}")

        # 3. Populate missing arguments: optional, defaults, or flags
        for name, arg in self.arguments.items():
            # Skip if already provided
            if name in positional_args or name in keyword_args:
                continue

            # Optional or has explicit default
            if arg.optional or arg.default is not None:
                # Use default from argument definition unless overridden by function signature
                if arg.default is None and cb_signature and name in cb_signature.parameters:
                    param = cb_signature.parameters[name]
                    if param.default is not inspect.Parameter.empty:
                        keyword_args[name] = param.default
                    else:
                        keyword_args[name] = arg.default
                else:
                    keyword_args[name] = arg.default

            # Boolean flag: default to False if absent
            elif arg.is_flag:
                keyword_args[name] = False

            # Required argument missing -> error
            else:
                self.logger.error(f"Argument '{name}' was not provided")
                return None

        # 4. Build positional values list (in defined order)
        positional_defs = sorted(
            (a for a in self.arguments.values() if a.position is not None),
            key=lambda a: a.position
        )
        pos_values: list[Any] = [positional_args[a.name] for a in positional_defs if a.name in positional_args]

        # 5. Map keyword argument keys to their original names if specified
        mapped_kwargs: dict[str, Any] = {}
        for name, value in keyword_args.items():
            arg = self.arguments[name]
            final_key = arg.original_name if arg.original_name else name
            mapped_kwargs[final_key] = value

        # 6. Log the execution details
        log_parts = []
        if pos_values:
            log_parts.append(f"*args: {pos_values}")
        if mapped_kwargs:
            log_parts.append(f"**kwargs: {mapped_kwargs}")
        self.logger.debug(f"Execute command: {self.name} ({', '.join(log_parts)})")

        # 7. Execute the command and handle exceptions (with full traceback info)
        try:
            return self.call(*pos_values, **mapped_kwargs)
        except Exception as e:
            import traceback

            tb = e.__traceback__
            frames = traceback.extract_tb(tb)
            last = frames[-1] if frames else None
            location = (
                f"{last.filename}:{last.lineno} in {last.name}"
                if last else "unknown location"
            )

            # Full chained traceback (includes __cause__/__context__)
            full_tb = "".join(traceback.format_exception(type(e), e, tb))

            # Include command name, where it failed, and the full traceback
            self.logger.error(
                f"Error executing command '{self.name}' at {location}: {e}\n{full_tb}"
            )
            return None

    def _parseCommandString(self, command_string: str | None) -> dict | None:
        """
        Tokenize the input, parse --long and -s flags, handle arrays, booleans,
        negative numeric literals as positionals, and '--' end-of-options.
        """
        if command_string is None:
            return {"positional_args": {}, "keyword_args": {}}

        # --- TOKENIZE ---
        if isinstance(command_string, list):
            tokens = command_string[:]
        else:
            pattern = r'\[.*?\]|\'[^\']*\'|"[^"]*"|\S+'
            tokens = re.findall(pattern, command_string)

        keyword_args: dict[str, Any] = {}
        raw_positionals: list[str] = []
        i = 0
        L = len(tokens)

        # helper: numeric literal (int/float, optional leading sign, sci notation)
        num_lit = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z')

        while i < L:
            tok = tokens[i]

            # --- END OF OPTIONS: everything after '--' is positional ---
            if tok == '--':
                # consume '--'
                i += 1
                # remaining tokens are all positionals (strip quotes)
                while i < L:
                    raw_positionals.append(tokens[i].strip('"').strip("'"))
                    i += 1
                break

            # --- LONG FLAG ---
            if tok.startswith('--'):
                name = tok[2:]
                if name == '':
                    # bare '--' handled above; if we get here it's malformed like '---'
                    self.logger.error("Malformed long option.")
                    return None

                if name not in self.arguments:
                    self.logger.error(f"Unknown argument: {name}")
                    return None
                arg = self.arguments[name]

                # flag with optional explicit 0/1
                if arg.is_flag:
                    if (i + 1 < L) and (not tokens[i + 1].startswith('-')) and re.fullmatch(r'[01]', tokens[i + 1]):
                        try:
                            keyword_args[name] = arg.cast(tokens[i + 1])
                        except ValueError as e:
                            self.logger.error(f"Error parsing flag {name}: {e}")
                            return None
                        i += 2
                    else:
                        keyword_args[name] = True
                        i += 1

                # non-flag consumes exactly one value (or bracketed list)
                else:
                    i += 1
                    if i >= L:
                        self.logger.error(f"Argument {name} expects a value.")
                        return None
                    val = tokens[i]
                    if arg.array_size > 0:
                        m = re.match(r'\[(.*)]', val)
                        if not m:
                            self.logger.error(f"Argument {name} expects a list enclosed in brackets.")
                            return None
                        parts = [v.strip() for v in m.group(1).split(',')]
                        if len(parts) != arg.array_size:
                            self.logger.error(f"Argument {name} expects a list of {arg.array_size} values.")
                            return None
                        try:
                            keyword_args[name] = arg.cast(parts)
                        except ValueError as e:
                            self.logger.error(f"Error parsing argument {name}: {e}")
                            return None
                    else:
                        stripped = val.strip('"').strip("'")
                        try:
                            keyword_args[name] = arg.cast(stripped)
                        except ValueError as e:
                            self.logger.error(f"Error parsing argument {name}: {e}")
                            return None
                    i += 1

            # --- SHORT FLAG OR NEGATIVE NUMBER ---
            elif tok.startswith('-') and not tok.startswith('--'):
                # If it's a numeric literal (e.g., -1, -3.14, -.5, -1e-3), treat as positional
                # (but not the lone '-' which is not a number)
                if tok != '-' and num_lit.fullmatch(tok):
                    raw_positionals.append(tok.strip('"').strip("'"))
                    i += 1
                    continue

                short = tok[1:]
                arg = next((a for a in self.arguments.values() if a.short_name == short), None)
                if arg is None:
                    self.logger.error(f"Unknown argument: {short}")
                    return None

                if arg.is_flag:
                    if (i + 1 < L) and (not tokens[i + 1].startswith('-')) and re.fullmatch(r'[01]', tokens[i + 1]):
                        try:
                            keyword_args[arg.name] = arg.cast(tokens[i + 1])
                        except ValueError as e:
                            self.logger.error(f"Error parsing flag {arg.name}: {e}")
                            return None
                        i += 2
                    else:
                        keyword_args[arg.name] = True
                        i += 1
                else:
                    i += 1
                    if i >= L:
                        self.logger.error(f"Argument {arg.name} expects a value.")
                        return None
                    val = tokens[i]
                    if arg.array_size > 0:
                        m = re.match(r'\[(.*)]', val)
                        if not m:
                            self.logger.error(f"Argument {arg.name} expects a list enclosed in brackets.")
                            return None
                        parts = [v.strip() for v in m.group(1).split(',')]
                        if len(parts) != arg.array_size:
                            self.logger.error(f"Argument {arg.name} expects a list of {arg.array_size} values.")
                            return None
                        try:
                            keyword_args[arg.name] = arg.cast(parts)
                        except ValueError as e:
                            self.logger.error(f"Error parsing argument {arg.name}: {e}")
                            return None
                    else:
                        stripped = val.strip('"').strip("'")
                        try:
                            keyword_args[arg.name] = arg.cast(stripped)
                        except ValueError as e:
                            self.logger.error(f"Error parsing argument {arg.name}: {e}")
                            return None
                    i += 1

            # --- POSITIONAL TOKEN ---
            else:
                raw_positionals.append(tok.strip('"').strip("'"))
                i += 1

        # --- POST-PROCESS TRAILING BOOL FOR A SINGLE UNSET FLAG ---
        positional_defs = sorted(
            (a for a in self.arguments.values() if a.position is not None and not a.is_flag),
            key=lambda a: a.position
        )
        max_pos = len(positional_defs)
        if len(raw_positionals) > max_pos:
            extra = len(raw_positionals) - max_pos
            unset_flags = [a for a in self.arguments.values() if a.is_flag and a.name not in keyword_args]
            candidate = raw_positionals[-1]
            if extra == 1 and len(unset_flags) == 1 and re.fullmatch(r'[01]', candidate):
                flag_arg = unset_flags[0]
                try:
                    keyword_args[flag_arg.name] = flag_arg.cast(candidate)
                except ValueError as e:
                    self.logger.error(f"Error parsing trailing flag {flag_arg.name}: {e}")
                    return None
                raw_positionals.pop()
            else:
                self.logger.error(
                    f"Too many positional arguments provided. Expected at most {max_pos} but got {len(raw_positionals)}."
                )
                return None

        # --- ASSIGN POSITIONALS ---
        positional_args: dict[str, Any] = {}
        for idx, raw in enumerate(raw_positionals):
            arg = positional_defs[idx]
            try:
                positional_args[arg.name] = arg.cast(raw)
            except Exception as e:
                self.logger.error(f"Error parsing positional #{idx + 1} ('{arg.name}'): {e}")
                return None

        return {"positional_args": positional_args, "keyword_args": keyword_args}

    def getPayload(self) -> dict:
        payload = {
            'name': self.name,
            'description': self.description,
            'inputs': {k: v.getPayload() for k, v in self.arguments.items()},
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def getHelp(self, string_format: str = 'html') -> str:
        ...


# === CommandSet =======================================================================================================
@callback_definition
class CommandSet_Callbacks:
    update: CallbackContainer


class CommandSet:
    name: str
    commands: dict[str, Command]
    parent: CommandSet | CLI | None = None
    children: dict[str, CommandSet] = None
    description: str = ''
    callbacks: CommandSet_Callbacks

    # === INIT =========================================================================================================
    def __init__(self, name: str,
                 commands: list[Command] = None,
                 children: list[CommandSet] = None,
                 description: str = ''):
        self.name = name
        self.commands = {}
        self.children = {}
        self.description = description

        self.callbacks = CommandSet_Callbacks()

        self.logger = Logger(f"CommandSet {name}", "WARNING")

        # Loop through the commands and children and add them to the CommandSet
        if commands is not None:
            for command in commands:
                self.addCommand(command)
        if children is not None:
            for child in children:
                self.addChild(child)

    # === PROPERTIES ===================================================================================================
    @property
    def path(self) -> str:
        if self.parent is None:
            return self.name
        else:
            return f"{self.parent.path}/{self.name}"

    # === METHODS ======================================================================================================
    def getRoot(self) -> CommandSet:
        if self.parent:
            return self.parent.getRoot()
        else:
            return self

    # ------------------------------------------------------------------------------------------------------------------
    def addCommand(self, command: Command) -> Command:

        # noinspection PyUnreachableCode
        if not isinstance(command, Command):
            raise ValueError("Command must be a Command.")

        if command.name in self.commands or command.name in self.children:
            raise ValueError(f"Command/Set with name '{command.name}' already exists.")

        if isinstance(command, dict):
            for key, value in command.items():
                self.commands[value.name] = value
        elif isinstance(command, Command):
            self.commands[command.name] = command

        self.callbacks.update.call()
        command.set = self
        return command

    # ------------------------------------------------------------------------------------------------------------------
    def removeCommand(self, command: Command | str):
        raise NotImplementedError("CommandSet.removeCommand() is not yet implemented.")

    # ------------------------------------------------------------------------------------------------------------------
    def addChild(self, child: CommandSet) -> CommandSet:

        # noinspection PyUnreachableCode
        if not isinstance(child, CommandSet):
            raise ValueError("Child must be a CommandSet.")

        if child.name in self.children or child.name in self.commands:
            raise ValueError(f"Command/Set with name '{child.name}' already exists.")

        self.children[child.name] = child
        child.parent = self
        child.callbacks.update.register(self.callbacks.update.call)
        self.callbacks.update.call()
        return child

    # ------------------------------------------------------------------------------------------------------------------
    def removeChild(self, child: CommandSet | str) -> None:

        # noinspection PyUnreachableCode
        if isinstance(child, CommandSet):
            if child.name not in self.children:
                raise ValueError(f"Child with name '{child.name}' does not exist.")
        elif isinstance(child, str):
            if child not in self.children:
                raise ValueError(f"Child with name '{child}' does not exist.")
            child = self.children[child]
        else:
            raise ValueError("Child must be a CommandSet or a string.")

        self.children.pop(child.name)
        child.callbacks.update.remove(self.callbacks.update.call)
        self.callbacks.update.call()

    # ------------------------------------------------------------------------------------------------------------------
    def parseCommandString(self, command_string: str) -> tuple[CommandSet, Command | None, str | None] | None:
        """
        Parses a command string and returns:
          - the CommandSet to run in,
          - the Command (or None if none was specified),
          - the raw remainder of the string (or None).
        Returns None if the string is not a valid path/command.
        """
        # split tokens but keep quoted/bracketed pieces intact
        pattern = r'\[.*?\]|\'[^\']*\'|"[^"]*"|\S+'
        matches = list(re.finditer(pattern, command_string))
        tokens = [m.group() for m in matches]
        if not tokens:
            return self, None, None

        current = self
        idx = 0
        L = len(tokens)

        # single loop: handle ~ / . (root), .. (up), and child names (down)
        while idx < L:
            tok = tokens[idx]
            if tok in ('.', '~'):
                # go all the way up to the root
                while isinstance(current.parent, CommandSet):
                    current = current.parent
                idx += 1
            elif tok == '..':
                # go up one level
                if isinstance(current.parent, CommandSet):
                    current = current.parent
                    idx += 1
                else:
                    return None
            elif tok in current.children:
                current = current.children[tok]
                idx += 1
            else:
                break

        # if we consumed all tokens, it's just a set-selection
        if idx >= L:
            return current, None, None

        # next token must be a command
        cmd_name = tokens[idx]
        if cmd_name not in current.commands:
            return None

        # find the raw remainder of the string after this token
        end_pos = matches[idx].end()
        remainder = command_string[end_pos:].lstrip()
        if remainder == '':
            remainder = None

        return current, current.commands[cmd_name], remainder

    # ------------------------------------------------------------------------------------------------------------------
    def getByPath(self, path) -> CommandSet | Command | None:
        """
        Retrieves a CommandSet or Command within this command set by a given path.
        The input 'path' can be a string with tokens separated by '/' (e.g. "subset1/function1")
        or a list of tokens. Special tokens:
          - "." refers to the root of the CLI (ascends via parent until None).
          - ".." moves to the parent set.
        If the final token matches a command in the current set (and not a child set),
        that Command is returned; otherwise the CommandSet is returned.
        Returns None if any token in the path is not found.
        """

        if isinstance(path, str):
            tokens = [token for token in path.split(' ') if token]
        else:
            tokens = path

        current = self
        for i, token in enumerate(tokens):
            if token in ['.', '~']:
                # Move to CLI root.
                while current.parent is not None:
                    current = current.parent
            elif token == '..':
                # noinspection PyUnreachableCode
                if current.parent is not None:
                    current = current.parent
                else:
                    return None
            else:
                if token in current.children:
                    current = current.children[token]
                elif token in current.commands:
                    # If this is the final token, return the command.
                    if i == len(tokens) - 1:
                        return current.commands[token]
                    else:
                        # Cannot descend further from a command.
                        return None
                else:
                    return None
        return current

    # ------------------------------------------------------------------------------------------------------------------
    def runCommandString(self, command_string: str) -> CommandSet | Any | None:
        self.logger.debug(f"Running command string: '{command_string}'")
        parsed = self.parseCommandString(command_string)

        if parsed is None:
            self.logger.error(f"Invalid command string: '{command_string}'")
            return

        set, command, remainder = parsed

        self.logger.debug(
            f"Parsed: set={set.name}({set.path}), command={command.name if command else None}, remainder={remainder}")
        # Check if the command is just a set selection.
        if command is None:
            self.logger.debug(f"Command string '{command_string}' is a set selection: {set.name}({set.path})")
            return set

        # Run the command
        try:
            self.logger.debug(f"Running command '{command.name}' with input '{remainder}'")
            return command.runFromCommandInput(remainder)
        except Exception as e:
            self.logger.error(f"Error running command '{command.name}': {e}")

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'name': self.name,
            'description': self.description,
            'commands': {k: v.getPayload() for k, v in self.commands.items()},
            'sets': {k: v.getPayload() for k, v in self.children.items()},
        }
        return payload


# === CLI ==============================================================================================================
@callback_definition
class CLI_Callbacks:
    update: CallbackContainer
    set_changed: CallbackContainer


class CLI:
    id: str

    allow_set_change: bool = False

    root: CommandSet | None
    current_set: CommandSet | None
    callbacks: CLI_Callbacks

    # === INIT =========================================================================================================
    def __init__(self, id: str,
                 root: CommandSet | None = None,
                 allow_set_change: bool = False,
                 ):
        assert isinstance(id, str) and id != ''
        self.id = id
        self.callbacks = CLI_Callbacks()
        self.logger = Logger(f"CLI {id}", "WARNING")
        self.current_set = None
        self.allow_set_change = allow_set_change

        self.root = root

    # === PROPERTIES ===================================================================================================
    @property
    def root(self):
        return self._root

    @root.setter
    def root(self, root: CommandSet):
        if root is None:
            root = CommandSet(name='generic_root')
        if root.parent is not None:
            raise ValueError("Root must not have a parent.")

        self._root = root
        self.callbacks.update.call()

        self._root.callbacks.update.register(self.callbacks.update.call)
        self.setCommandSet(self._root)

    # === METHODS ======================================================================================================
    def setCommandSet(self, command_set: CommandSet):
        # Check if this command set's root is the root of the CLI.
        if command_set.getRoot() != self.root:
            self.logger.error(
                f"Root of command set '{command_set.name}' is not the root of the CLI ({command_set.getRoot().name} != {self.root.name}).")
            return

        if not self.allow_set_change and command_set != self.root:
            self.logger.error(
                f"Cannot change the set of the CLI to '{command_set.name}'. Set allow_set_change to True.")
            return
        self.current_set = command_set
        self.callbacks.set_changed.call(self.current_set)

    # ------------------------------------------------------------------------------------------------------------------
    def runCommand(self,
                   command_string: str,
                   from_root: bool = False,
                   set: CommandSet | str | None = None,
                   allow_set_change: bool = True) -> Any:

        # Check if the user has set from_root and set at the same time
        if from_root and set:
            raise ValueError("from_root and set cannot be set at the same time.")

        if from_root:
            set = self.root
        elif set is None:
            set = self.current_set

        if isinstance(set, str):
            set = self.getByPath(set)

        if set is None:
            self.logger.error(f"Cannot run command '{command_string}': Set does not exist'")
            return None

        return_value = set.runCommandString(command_string)

        if isinstance(return_value, CommandSet) and self.allow_set_change and allow_set_change:
            self.setCommandSet(return_value)

        return return_value

    # ------------------------------------------------------------------------------------------------------------------
    def getByPath(self, path, from_root=False) -> CommandSet | Any | None:
        if from_root:
            return self.root.getByPath(path)
        else:
            return self.current_set.getByPath(path)

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        self.setCommandSet(self.root)

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self):
        payload = {
            'id': self.id,
            'root': self.root.getPayload(),
        }
        return payload


# === CLI CONNECTOR ====================================================================================================
class CLI_Instance:
    cli: CLI

    current_set: CommandSet | None

    # === INIT =========================================================================================================
    def __init__(self, cli: CLI):
        self.cli = cli
        self.current_set = cli.root

    # === METHODS ======================================================================================================
    def runCommand(self, command_string: str):
        ...
    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------


# === TESTS ============================================================================================================
if __name__ == '__main__':
    print('=== CASTING ARGUMENTS ===')
    # 1. Check: CommandArgument
    arg = CommandArgument(name='test', type=int, array_size=2)
    assert (arg.cast(['1', '2']) == [1, 2])

    arg = CommandArgument(name='test_float', type=float)
    assert ((arg.cast('1.2') - 1.2) < 1e-10)

    try:
        arg = CommandArgument(name='test_int_fail', type=int)
        arg.cast('1.2')
        assert False, "Expected ValueError but none was raised."
    except ValueError as e:
        assert True

    print('OK')
    # ------------------------------------------------------------------------------------------------------------------
    # 2. Check: parsing arguments
    print('=== PARSING ARGUMENTS ===')
    arguments = [
        CommandArgument(name='filename', type=str),  # Positional
        CommandArgument(name='count', type=int),  # Positional
        CommandArgument(name='mode', type=str, short_name='m'),  # Keyword
        CommandArgument(name='values', type=list[int], array_size=3),  # Keyword array
        CommandArgument(name='verbose', type=bool, is_flag=True, short_name='v'),  # Flag
    ]
    cmd = Command(name='test', arguments=arguments, allow_positionals=True)

    input_str = 'file.txt 5 --mode "fast"'
    parsed = cmd._parseCommandString(input_str)
    assert parsed == {
        'positional_args': {'filename': 'file.txt', 'count': 5},
        'keyword_args': {'mode': 'fast'}
    }

    input_str = 'input.csv 10 -m "safe" --verbose'
    parsed = cmd._parseCommandString(input_str)
    assert parsed == {
        'positional_args': {'filename': 'input.csv', 'count': 10},
        'keyword_args': {'mode': 'safe', 'verbose': True}
    }

    input_str = 'data.bin 3 --values [1, 2, 3] --mode "batch"'
    parsed = cmd._parseCommandString(input_str)
    assert parsed == {
        'positional_args': {'filename': 'data.bin', 'count': 3},
        'keyword_args': {'values': [1, 2, 3], 'mode': 'batch'}
    }

    input_str = '"hello.txt" 42 -v -m "deep-mode" --values [10,20,30]'
    parsed = cmd._parseCommandString(input_str)
    assert parsed == {
        'positional_args': {'filename': 'hello.txt', 'count': 42},
        'keyword_args': {'verbose': True, 'mode': 'deep-mode', 'values': [10, 20, 30]}
    }
    print('OK')

    # === RUN FROM COMMAND INPUT TESTS ===
    print('=== RUN FROM COMMAND INPUT ===')


    # A sample callback that just returns its received parameters for inspection.
    def sample_callback(a, b, c='default', verbose=False):
        return {'a': a, 'b': b, 'c': c, 'verbose': verbose}


    # Define arguments: a & b are positional, c is optional with default, verbose is a boolean flag.
    arguments = [
        CommandArgument(name='a', type=int),  # Positional #1
        CommandArgument(name='b', type=str),  # Positional #2
        CommandArgument(name='c', type=str, optional=True, default='default'),  # Optional kw
        CommandArgument(name='verbose', type=bool, is_flag=True, short_name='v')  # Flag
    ]
    cmd = Command(name='sample', function=sample_callback, arguments=arguments, allow_positionals=True)

    # 1) Only positionals: should fill c with its default, verbose=False
    result = cmd.runFromCommandInput('10 hello')
    assert result == {'a': 10, 'b': 'hello', 'c': 'default', 'verbose': False}

    # 2) Override the optional c via long flag
    result = cmd.runFromCommandInput('42 world --c custom_value')
    assert result == {'a': 42, 'b': 'world', 'c': 'custom_value', 'verbose': False}

    # 3) Use the short flag to set verbose to True
    result = cmd.runFromCommandInput('7 test -v')
    assert result == {'a': 7, 'b': 'test', 'c': 'default', 'verbose': True}

    # 4) Mix positional and keyword order arbitrarily
    result = cmd.runFromCommandInput('--c mixed 99 mix -v')
    # positional args: a=99, b='mix'; c='mixed'; verbose=True
    assert result == {'a': 99, 'b': 'mix', 'c': 'mixed', 'verbose': True}

    # 5) Error cases:
    # 5a) Missing required positional 'b'
    assert cmd.runFromCommandInput('5') is None

    # 5b) Unknown argument
    assert cmd.runFromCommandInput('1 2 --unknown foo') is None

    print('OK')

    # === TESTS for CommandSet.parseCommandString ===
    print('=== CommandSet.parseCommandString ===')
    root = CommandSet('root')
    set1 = CommandSet('set1')
    set2 = CommandSet('set2')
    root.addChild(set1)
    set1.addChild(set2)
    cmdX = Command('commandX')
    set2.addCommand(cmdX)

    # 1) full path + args
    res = root.parseCommandString('~ set1 set2 commandX 3 -b 2')
    assert res is not None
    s, c, args = res
    assert s is set2
    assert c is cmdX
    assert args == '3 -b 2'

    # 2) just drilling down to a set
    res = root.parseCommandString('set1 set2')
    assert res == (set2, None, None)

    # 3) relative up to parent
    res = set1.parseCommandString('..')
    assert res == (root, None, None)

    # 
    res = root.parseCommandString('~ set1 .. set1 set2 ..')
    assert res == (set1, None, None)

    # 4) invalid child after '..'
    assert set1.parseCommandString('.. unknown') is None

    # 5) unknown at top level
    assert root.parseCommandString('unknown') is None

    # 6) command in current set
    res = set2.parseCommandString('commandX foo bar')
    assert res[0] is set2 and res[1] is cmdX and res[2] == 'foo bar'

    res = set2.parseCommandString('.. set2 commandX foo bar -a 23')
    assert res[0] is set2 and res[1] is cmdX and res[2] == 'foo bar -a 23'

    print('OK')

    # === TESTS for CLI.runCommandString ===
    print('=== TESTING: CommandSet.runCommandString ===')


    # === DEFINE CALLBACKS ===
    def sum_values(numbers: list[int], verbose=False):
        if verbose:
            print(f"Summing: {numbers}")
        return sum(numbers)


    def echo(msg: str, suffix: str = '', shout: bool = False):
        response = msg + suffix
        return response.upper() if shout else response


    # === DEFINE COMMANDS ===
    cmd_sum = Command(
        name='sum_values',
        function=sum_values,
        arguments=[
            CommandArgument(name='numbers', type=list[int], array_size=3),
            CommandArgument(name='verbose', type=bool, is_flag=True, short_name='v')
        ]
    )

    cmd_echo = Command(
        name='echo',
        function=echo,
        allow_positionals=True,
        arguments=[
            CommandArgument(name='msg', type=str),  # positional
            CommandArgument(name='suffix', type=str, optional=True, default='!'),
            CommandArgument(name='shout', type=bool, is_flag=True, short_name='s')
        ]
    )

    # === CREATE SET STRUCTURE ===
    root = CommandSet('root')
    groupA = CommandSet('groupA')
    subgroupA1 = CommandSet('subgroupA1')
    groupB = CommandSet('groupB')

    # Add hierarchy
    root.addChild(groupA)
    groupA.addChild(subgroupA1)
    root.addChild(groupB)

    # Add commands
    subgroupA1.addCommand(cmd_sum)
    groupB.addCommand(cmd_echo)

    # === TEST CASES ===

    # 1. Run nested command with full path using array and flag
    res = root.runCommandString('~ groupA subgroupA1 sum_values --numbers [10,20,30] --verbose')
    assert res == 60

    # 2. Run echo with positionals and optional keyword
    res = root.runCommandString('groupB echo "hello" --suffix "!!!"')
    assert res == 'hello!!!'

    # 3. Run echo with short flag (-s)
    res = root.runCommandString('groupB echo "hello world" -s')
    assert res == 'HELLO WORLD!'

    # 4. Run echo with default suffix
    res = root.runCommandString('groupB echo "test"')
    assert res == 'test!'

    # 5. Invalid command path
    res = root.runCommandString('groupA subgroupA1 nonexistent')
    assert res is None

    # 6. Missing required array
    res = root.runCommandString('groupA subgroupA1 sum_values')
    assert res is None

    # 7. Malformed array input
    res = root.runCommandString('groupA subgroupA1 sum_values --numbers 1,2,3')
    assert res is None

    # 8. Root set selection only
    res = root.runCommandString('~')
    assert isinstance(res, CommandSet)
    assert res is root

    # 9. Path that selects a set, not a command
    res = root.runCommandString('groupA subgroupA1')
    assert isinstance(res, CommandSet)
    assert res.name == 'subgroupA1'

    print('OK')

    # RUN CLI TESTS
    print("=== CLI TESTS ===")


    # Sample command functions
    def multiply(x: int, y: int) -> int:
        return x * y


    def greet(name: str, enthusiastic: bool = False):
        return f"Hello, {name}!" if not enthusiastic else f"HELLO, {name.upper()}!!!"


    # Commands
    cmd_multiply = Command(
        name="multiply",
        function=multiply,
        allow_positionals=True,
        arguments=[
            CommandArgument(name="x", type=int),
            CommandArgument(name="y", type=int)
        ]
    )

    cmd_greet = Command(
        name="greet",
        function=greet,
        allow_positionals=True,
        arguments=[
            CommandArgument(name="name", type=str),
            CommandArgument(name="enthusiastic", type=bool, is_flag=True, short_name='e')
        ]
    )

    # Sets
    root_set = CommandSet("root")
    math_set = CommandSet("math", commands=[cmd_multiply])
    social_set = CommandSet("social", commands=[cmd_greet])
    nested_set = CommandSet("deep")

    # Nesting
    root_set.addChild(math_set)
    root_set.addChild(social_set)
    social_set.addChild(nested_set)

    # CLI with set changing allowed
    cli = CLI("TestCLI", root=root_set, allow_set_change=True)

    # --- TEST 1: Run command from current set (math)
    cli.setCommandSet(math_set)
    result = cli.runCommand("multiply 3 4")
    assert result == 12

    # --- TEST 1.2: Run command from current set (math)
    cli.reset()
    cli.runCommand("math")
    result = cli.runCommand("multiply 3 4")
    assert result == 12

    # --- TEST 2: Run command from root explicitly
    cli.reset()
    result = cli.runCommand("math multiply 6 7", from_root=True)
    assert result == 42

    # --- TEST 3: Explicitly set the target set
    result = cli.runCommand("multiply 2 5", set=math_set)
    assert result == 10

    # --- TEST 4: Move into another set (social) and run a command
    cli.runCommand("~ social")
    res = cli.runCommand("greet Alice")
    assert res == "Hello, Alice!"
    assert cli.current_set.name == "social"

    # --- TEST 5: Shout greeting with short flag
    res = cli.runCommand("greet Bob -e")
    assert res == "HELLO, BOB!!!"

    # --- TEST 6: Change into nested set by command string
    res = cli.runCommand("deep")
    assert isinstance(res, CommandSet)
    assert cli.current_set.name == "deep"

    # --- TEST 7: Back out to root using path
    res = cli.runCommand("~")
    assert cli.current_set.name == "root"

    # --- TEST 8: Run invalid command
    assert cli.runCommand("math does_not_exist", from_root=True) is None

    # --- TEST 9: Try using `from_root=True` and `set=...` together (should raise)
    try:
        cli.runCommand("multiply 2 2", from_root=True, set=math_set)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    print("OK")

    time.sleep(0.25)
    print("ALL TESTS OK")
