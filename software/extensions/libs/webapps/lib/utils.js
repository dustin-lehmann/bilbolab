/**
 * Common utility functions.
 */

export function normalizeAngle(angle) {
    while (angle > Math.PI) angle -= 2.0 * Math.PI;
    while (angle < -Math.PI) angle += 2.0 * Math.PI;
    return angle;
}

export function clamp(value, lo, hi) {
    return Math.max(lo, Math.min(hi, value));
}

export function deg2rad(deg) {
    return deg * Math.PI / 180.0;
}

export function rad2deg(rad) {
    return rad * 180.0 / Math.PI;
}
