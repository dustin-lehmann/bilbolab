import dataclasses

from utils.dataclass_utils import freeze_dataclass_instance


@dataclasses.dataclass(frozen=True)
class ClassA:
    x: float = 0
    y: list = dataclasses.field(default_factory=list)


def main():
    list1 = [1, 2, 3]

    a1 = ClassA(
        x=3
        , y=list1
    )

    a2 = ClassA(
        x=3
        , y=list1
    )

    a1 = freeze_dataclass_instance(a1)

    list1.append(4)
    print(a1)
    print(a2)
    ...


if __name__ == '__main__':
    main()
