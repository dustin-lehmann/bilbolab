import qmt


def align_angle(reference: float, angle: float) -> float:
    diff = qmt.wrapToPi(angle-reference)
    return reference + diff