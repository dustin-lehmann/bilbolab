# =====================================================================================
#  Robot-independent grid path planning for the art project.
#
#  The floor is a rectangular grid of nodes (each node = one ArUco marker, see
#  CITY_MAP in art_project_frodo.py). A robot can only travel along grid edges
#  (4-connected: N/S/E/W) and only turns +-90 degrees at a node.
#
#  shortest_path() does a breadth-first search from start to goal. Optionally a
#  set of "blocked" nodes can be given (e.g. the cell another robot is sitting
#  on / driving through) - BFS then routes around them. Because every edge costs
#  the same, BFS already returns a minimum-length path.
#
#  Nothing here touches hardware or the camera, so it can be unit-tested on any
#  machine:  python -m applications.art_project.grid_nav
# =====================================================================================
from collections import deque

# Cardinal directions as (dx, dy) steps on the grid. +x = EAST, +y = NORTH
# (matches CITY_MAP / MARKER_WORLD_MAP: id -> (id % cols, id // cols)).
DIRECTIONS = {
    "EAST": (1, 0),
    "WEST": (-1, 0),
    "NORTH": (0, 1),
    "SOUTH": (0, -1),
}
_STEP_TO_DIR = {step: name for name, step in DIRECTIONS.items()}


def grid_nodes(cols: int, rows: int) -> set[tuple[int, int]]:
    """All (x, y) nodes of a full cols x rows grid."""
    return {(x, y) for x in range(cols) for y in range(rows)}


def neighbors(node: tuple[int, int], nodes: set[tuple[int, int]]):
    """The up-to-4 grid neighbors of `node` that are in `nodes`."""
    x, y = node
    for dx, dy in DIRECTIONS.values():
        cand = (x + dx, y + dy)
        if cand in nodes:
            yield cand


def shortest_path(start, goal, nodes, blocked=None):
    """BFS shortest path from `start` to `goal` over `nodes` (a set of (x, y)).

    `blocked`: iterable of nodes that may NOT be entered. `start` is always
    allowed even if listed in `blocked` (you can't teleport off it); `goal` is
    NOT force-allowed - if the goal itself is blocked there is no path.

    Returns the node list [start, ..., goal] (length >= 1), or None if
    unreachable.
    """
    if start == goal:
        return [start]

    blocked = set(blocked or ())
    blocked.discard(start)

    frontier = deque([start])
    came_from = {start: None}

    while frontier:
        current = frontier.popleft()
        for nxt in neighbors(current, nodes):
            if nxt in came_from or nxt in blocked:
                continue
            came_from[nxt] = current
            if nxt == goal:
                return _reconstruct(came_from, goal)
            frontier.append(nxt)

    return None


def _reconstruct(came_from, goal):
    path = [goal]
    while came_from[path[-1]] is not None:
        path.append(came_from[path[-1]])
    path.reverse()
    return path


def direction_between(a: tuple[int, int], b: tuple[int, int]) -> str:
    """Cardinal name ("EAST"/.. ) of the single grid step from `a` to `b`.
    Raises ValueError if `a` and `b` are not 4-connected neighbors."""
    step = (b[0] - a[0], b[1] - a[1])
    if step not in _STEP_TO_DIR:
        raise ValueError(f"{a} and {b} are not grid neighbors (step {step})")
    return _STEP_TO_DIR[step]


def next_heading(start, goal, nodes, blocked=None):
    """Cardinal direction of the FIRST step of the shortest path start->goal.
    Returns None if start == goal or no path exists."""
    path = shortest_path(start, goal, nodes, blocked)
    if path is None or len(path) < 2:
        return None
    return direction_between(path[0], path[1])


def turn_for(current_heading: str, desired_heading: str) -> str:
    """What the robot must do to go from `current_heading` to `desired_heading`:
    "STRAIGHT", "LEFT", "RIGHT", or "BACK" (180)."""
    order = ["EAST", "NORTH", "WEST", "SOUTH"]   # CCW
    if current_heading == desired_heading:
        return "STRAIGHT"
    diff = (order.index(desired_heading) - order.index(current_heading)) % 4
    return {1: "LEFT", 3: "RIGHT", 2: "BACK"}[diff]


# =====================================================================================
if __name__ == "__main__":
    COLS, ROWS = 9, 6
    nodes = grid_nodes(COLS, ROWS)

    def show(start, goal, blocked=None):
        p = shortest_path(start, goal, nodes, blocked)
        print(f"  {start} -> {goal}  blocked={sorted(blocked) if blocked else '-'}")
        print(f"    path: {p}")
        if p and len(p) > 1:
            print(f"    first step: {direction_between(p[0], p[1])}  (len {len(p) - 1})")

    print("open grid:")
    show((0, 0), (5, 3))
    show((8, 5), (0, 0))
    print("\nwith a blocked node forcing a detour:")
    show((0, 0), (2, 0), blocked=[(1, 0)])
    show((3, 3), (5, 3), blocked=[(4, 3)])
    print("\nno path (goal itself blocked):")
    show((0, 0), (1, 0), blocked=[(1, 0)])

    print("\nturn_for():")
    for ch in ("EAST", "NORTH", "WEST", "SOUTH"):
        for dh in ("EAST", "NORTH", "WEST", "SOUTH"):
            print(f"  {ch:5} -> {dh:5} = {turn_for(ch, dh)}")
