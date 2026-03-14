from core.utils.dict_utils import update_dict
from extensions.libs.babylon.src.babylon import BabylonObject


class PathDrawing(BabylonObject):
    """A path (polyline) drawn on the floor surface.

    Points are specified as [x, y] pairs in z-up world coordinates.
    The path is rendered as a tube at floor level.
    """
    type = 'path_drawing'

    def __init__(self, object_id: str, **kwargs):
        super().__init__(object_id, **kwargs)

        default_config = {
            'pathColor': [1, 1, 1, 0.95],
            'pathWidth': 0.01,
            'groundY': 0,
            'lift': 0.001,
        }
        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)
        self._points: list[list[float]] = []

    def setPoints(self, points: list[list[float]]):
        """Replace the entire path with a new list of [x, y] points and push to frontend."""
        self._points = [list(p) for p in points]
        self.update()

    def addPoint(self, x: float, y: float):
        """Append a single point. Does NOT push to frontend — call update() when ready."""
        self._points.append([x, y])

    def clearPoints(self):
        """Remove all points and push to frontend."""
        self._points = []
        self.update()

    def getConfig(self) -> dict:
        return {**self.config}

    def getData(self) -> dict:
        return {
            'points': self._points,
        }
