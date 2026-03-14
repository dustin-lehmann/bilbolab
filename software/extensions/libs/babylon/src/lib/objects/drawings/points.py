from core.utils.dict_utils import update_dict
from extensions.libs.babylon.src.babylon import BabylonObject


class PointsDrawing(BabylonObject):
    """A set of dots drawn on the floor surface.

    Points are specified as [x, y] pairs in z-up world coordinates.
    Rendered as small discs with a border ring at floor level.
    """
    type = 'points_drawing'

    def __init__(self, object_id: str, **kwargs):
        super().__init__(object_id, **kwargs)

        default_config = {
            'fillColor': [1, 1, 1, 0.8],
            'pointSize': 0.02,
            'groundY': 0,
            'lift': 0.002,
        }
        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)
        self._points: list[list[float]] = []

    def setPoints(self, points: list[list[float]]):
        """Replace all points and push to frontend."""
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
