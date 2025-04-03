import dataclasses
import time

from utils.callbacks import Callback
from utils.events import EventListener, ConditionEvent, Condition
from utils.python_utils import is_immutable
from utils.dataclass_utils import freeze_dataclass_instance

x = 0
def testfunction1(id, *args, **kwargs):
    print(f"Listener {id}: {x}")

def main():
    global x
    event = ConditionEvent()

    listener1 = EventListener(event, callback=Callback(function=testfunction1, inputs={'id': 1}), once=False)
    listener1.start()
    listener2 = EventListener(event, callback=Callback(function=testfunction1, inputs={'id': 2}), once=False)
    listener2.start()

    while True:
        x = x + 1
        event.set()

        if x==5:
            listener1.stop()

        time.sleep(1)


@dataclasses.dataclass
class DataClass2:
    x1: float

@dataclasses.dataclass
class TestDataClass:
    a: int
    b: float
    c: DataClass2
    d: list

def dataclass_test():
    x = TestDataClass(a=1, b=2.0, c = DataClass2(x1=3), d=[1,2,3])
    y = freeze_dataclass_instance(x)
    z = freeze_dataclass_instance(x)
    x.d[0] = 88
    print(x)
    print(z)


if __name__ == '__main__':
    # main()
    dataclass_test()