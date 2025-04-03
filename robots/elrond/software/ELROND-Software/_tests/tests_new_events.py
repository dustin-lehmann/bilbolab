import threading
import time

from utils.events import ConditionEvent, waitForEvents


# Assume the previously provided classes and functions (ConditionEvent, waitForEvents, etc.) are imported or defined above.


# =============================================================================
# Example 1: Multiple Event Waiting
def example_multiple_events():
    # Create two events with flag definitions and assign explicit IDs.
    event1 = ConditionEvent(flags=[('value', int)], id="event1")
    event2 = ConditionEvent(flags=[('text', str)], id="event2")

    # Worker functions to trigger events with a delay.
    def trigger_event1():
        time.sleep(2)
        event1.set(resource="Resource for event1", flags={'value': 42})
        print("[Trigger] event1 fired.")

    def trigger_event2():
        time.sleep(3)
        event2.set(resource="Resource for event2", flags={'text': 'hello'})
        print("[Trigger] event2 fired.")

    threading.Thread(target=trigger_event1).start()
    threading.Thread(target=trigger_event2).start()

    # Wait for the first event to fire with its matching flag.
    result = waitForEvents(events=[(event1, {'value': 42}),
                                   (event2, {'text': 'hello'})],
                           wait_for_all=True,
                            timeout=5)
    if result:
        print("Example 1 (Multiple Events): Received event with id:", result.id,
              "and resource:", result.get_data())
    else:
        print("Example 1 (Multiple Events): Timeout occurred.")


# =============================================================================
# Example 2: Resource-Based Filtering
def example_resource_filtering():
    # Create an event that expects a flag and will use resource filtering.
    event = ConditionEvent(flags=[('status', str)], id="resource_event")

    def trigger_event():
        time.sleep(2)
        # Set resource as a dict that meets the filtering condition.
        event.set(resource={'status': 'ready', 'info': 'All systems go'},
                  flags={'status': 'ready'})
        event.set(resource="hallo",
                  flags={'status': 'ready'})
        print("[Trigger] resource_event fired with resource dict.")

    threading.Thread(target=trigger_event).start()

    # Wait until the event's resource is a dict with 'status' equal to 'ready'.
    result = event.wait(timeout=5, flags={'status': 'ready'}, resource_filter="hallo")
    if result:
        print("Example 2 (Resource Filtering): Received event with resource:", event.get_data())
    else:
        print("Example 2 (Resource Filtering): Timeout occurred.")


# =============================================================================
# Example 3: Combined Multiple Event Waiting with Resource-Based Filtering
# In this example, one event uses resource-based filtering while the other uses simple flag matching.
def example_both():
    # Create two events.
    event1 = ConditionEvent(flags=[('value', int)], id="event1_both")
    event2 = ConditionEvent(flags=[('text', str)], id="event2_both")

    def trigger_event1():
        time.sleep(2)
        # event1's resource is a dict that must pass resource_filter checking.
        event1.set(resource={'value': 100, 'extra': 'foo'}, flags={'value': 100})
        print("[Trigger] event1_both fired with resource dict.")

    def trigger_event2():
        time.sleep(3)
        event2.set(resource="hello world", flags={'text': 'hello world'})
        print("[Trigger] event2_both fired.")

    threading.Thread(target=trigger_event1).start()
    threading.Thread(target=trigger_event2).start()

    # --- Custom multiple-event waiter supporting resource_filter ---
    # For demonstration we define an inline function that accepts an optional resource_filter.
    def waitForEventsBoth(events, timeout=None, wait_for_all=False):
        """
        Each item in events can be a tuple (event, flags) or (event, flags, resource_filter).
        """
        results = {}
        lock = threading.Lock()
        done_event = threading.Event()
        start_time = time.time()
        threads = []

        def worker(ev, flags, resource_filter, key, overall_timeout):
            remaining = overall_timeout - (time.time() - start_time) if overall_timeout is not None else None
            if remaining is not None and remaining <= 0:
                return
            ret = ev.wait(timeout=remaining, flags=flags, resource_filter=resource_filter)
            if ret:
                with lock:
                    results[key] = ev
                if not wait_for_all:
                    done_event.set()

        for idx, item in enumerate(events):
            if len(item) == 3:
                ev, flags, resource_filter = item
            else:
                ev, flags = item
                resource_filter = None
            key = f"event{idx}"
            t = threading.Thread(target=worker, args=(ev, flags, resource_filter, key, timeout))
            t.daemon = True
            t.start()
            threads.append(t)

        if wait_for_all:
            for t in threads:
                remaining = timeout - (time.time() - start_time) if timeout is not None else None
                t.join(timeout=remaining)
            if len(results) == len(events):
                return [results[f"event{i}"] for i in range(len(events))]
            else:
                return None
        else:
            done_event.wait(timeout=timeout)
            if results:
                # Return the first event that fired.
                return list(results.values())[0]
            else:
                return None

    # Use the custom waiter:
    # For event1 we add a resource filter; for event2 we use a simple flag match.
    events_to_wait = [
        (event1, {'value': 100}, {'value': 100}),  # resource filter: resource must be a dict with value==100
        (event2, {'text': 'hello world'})          # no resource filter
    ]
    # Wait for both events to fire.
    results = waitForEventsBoth(events=events_to_wait, timeout=10, wait_for_all=True)
    if results:
        print("Example 3 (Combined):")
        for ev in results:
            print("  Received event with id:", ev.id, "and resource:", ev.get_data())
    else:
        print("Example 3 (Combined): Timeout occurred waiting for both events.")


# =============================================================================
if __name__ == '__main__':
    # print("Running Example 1: Multiple Event Waiting")
    # example_multiple_events()
    # time.sleep(6)  # Allow time for example 1 to complete

    print("\nRunning Example 2: Resource-Based Filtering")
    example_resource_filtering()
    time.sleep(6)  # Allow time for example 2 to complete
    #
    # print("\nRunning Example 3: Combined Multiple Event Waiting with Resource-Based Filtering")
    # example_both()
