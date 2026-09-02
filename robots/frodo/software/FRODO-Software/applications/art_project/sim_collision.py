# =====================================================================================
#  Offline simulation of the multi-robot collision-avoidance ROUTING logic
#  (Approach A). No hardware, no camera - pure grid stepping - so the path
#  planning / right-of-way rules can be checked before a two-robot field test.
#
#  It does NOT simulate line following, turning dynamics or vision noise. What it
#  DOES check: given random start/target pairs, do the priority + BFS-detour
#  rules get both robots to their targets without ever standing on the same cell?
#
#  Run:  python sim_collision.py            (one random scenario, drawn each step)
#        python sim_collision.py 500        (stress-test 500 random scenarios)
# =====================================================================================
import random
import sys

from grid_nav import shortest_path, direction_between, grid_nodes, DIRECTIONS

COLS, ROWS = 9, 6
NODES = grid_nodes(COLS, ROWS)

# Same idea as OTHER_ROBOT_*_BEARING/DISTANCE in art_project_frodo.py, but here
# expressed on the grid: a lower-priority robot "sees" a higher-priority robot if
# it is on the lower robot's current cell's forward neighbour, or the one after.
LOOKAHEAD_CELLS = 2


class SimRobot:
    def __init__(self, name, priority, start, target, heading):
        self.name = name
        self.priority = priority
        self.pos = start
        self.target = target
        self.heading = heading
        self.done = start == target
        self.path_log = [start]

    def forward_cells(self, n):
        dx, dy = DIRECTIONS[self.heading]
        return [(self.pos[0] + dx * k, self.pos[1] + dy * k) for k in range(1, n + 1)]

    def plan_step(self, others):
        """Return the next cell to move onto (or None to wait)."""
        if self.done:
            return None

        # Cells occupied / claimed by robots I must yield to.
        blocked = set()
        for o in others:
            if o.priority < self.priority:
                blocked.add(o.pos)                 # where it is now (parked or not)
                if not o.done:
                    nxt = o.plan_step_naive()      # and where it's about to go
                    if nxt is not None:
                        blocked.add(nxt)

        path = shortest_path(self.pos, self.target, NODES, blocked=blocked)
        if path is None or len(path) < 2:
            # no detour - fall back to the plain shortest path and let the
            # step-time collision check (below) make me wait instead
            path = shortest_path(self.pos, self.target, NODES)
            if path is None or len(path) < 2:
                return None
        return path[1]

    def plan_step_naive(self):
        if self.done:
            return None
        path = shortest_path(self.pos, self.target, NODES)
        if path is None or len(path) < 2:
            return None
        return path[1]


def run_scenario(seed, draw=False, max_steps=200):
    rng = random.Random(seed)

    def rand_node():
        return (rng.randrange(COLS), rng.randrange(ROWS))

    starts = rand_node(), rand_node()
    targets = rand_node(), rand_node()
    while starts[0] == starts[1]:
        starts = starts[0], rand_node()

    robots = [
        SimRobot("frodo1", 0, starts[0], targets[0], rng.choice(list(DIRECTIONS))),
        SimRobot("frodo4", 1, starts[1], targets[1], rng.choice(list(DIRECTIONS))),
    ]

    for step in range(max_steps):
        if all(r.done for r in robots):
            if draw:
                print(f"\nboth arrived in {step} steps")
            return True, step

        # higher priority moves first, lower priority plans around the result
        order = sorted(robots, key=lambda r: r.priority)
        moves = {}
        for r in order:
            nxt = r.plan_step([o for o in robots if o is not r])
            for o in order:
                if o is r:
                    continue
                claimed = {o.pos}
                if o.name in moves and moves[o.name] is not None:
                    claimed.add(moves[o.name])
                # don't enter a claimed cell, and don't head-on swap
                if nxt in claimed or (nxt == o.pos and moves.get(o.name) == r.pos):
                    if o.priority < r.priority:      # only YIELD to higher priority
                        nxt = None
            moves[r.name] = nxt

        for r in robots:
            nxt = moves[r.name]
            if nxt is None:
                continue
            r.heading = direction_between(r.pos, nxt)
            r.pos = nxt
            r.path_log.append(nxt)
            if r.pos == r.target:
                r.done = True

        if robots[0].pos == robots[1].pos:
            print(f"!!! COLLISION at {robots[0].pos} (seed {seed}, step {step})")
            return False, step

        if draw:
            _draw(robots, step)

    print(f"!!! did not finish in {max_steps} steps (seed {seed})")
    return False, max_steps


def _draw(robots, step):
    print(f"\nstep {step}")
    for y in range(ROWS - 1, -1, -1):
        row = []
        for x in range(COLS):
            c = "."
            for r in robots:
                if (x, y) == r.pos:
                    c = r.name[-1]
                elif (x, y) == r.target and not r.done:
                    c = c if c != "." else "*"
            row.append(c)
        print("  " + " ".join(row))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        n = int(sys.argv[1])
        ok = 0
        for s in range(n):
            success, _ = run_scenario(s, draw=False)
            ok += success
        print(f"\n{ok}/{n} scenarios: both robots reached target, no collision")
    else:
        run_scenario(random.randrange(10_000), draw=True)
