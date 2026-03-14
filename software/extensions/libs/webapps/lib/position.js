/**
 * Position control: turn-to-heading, drive-to-point, follow-path.
 *
 * Faithful JS port of bilbo_position_control.py, which itself matches
 * the firmware position control module.
 *
 * Output: { vCmd, psiDotCmd } velocity commands fed into the velocity layer.
 */

import { normalizeAngle, clamp } from './utils.js';

const EPSILON = 1e-6;
const PROJECTION_SEARCH_WINDOW = 30;
const SPEED_SMOOTH_TAU = 0.1;
const HEADING_ARRIVAL_TOLERANCE = 0.05;

// Modes
export const POS_IDLE = 0;
export const POS_TURN_TO_HEADING = 1;
export const POS_DRIVE_TO_POINT = 2;
export const POS_FOLLOW_PATH = 3;

const PATH_IDLE = 0;
const PATH_RUNNING = 1;
const PATH_PAUSED = 2;


export class PositionControlConfig {
    constructor(params = {}) {
        this.Ts = params.Ts ?? 0.01;
        this.kpAngular = params.kpAngular ?? 10.0;
        this.kiAngular = params.kiAngular ?? 0.3;
        this.kpAngularHeading = params.kpAngularHeading ?? 0.0;
        this.kiAngularHeading = params.kiAngularHeading ?? 0.0;
        this.kpLinear = params.kpLinear ?? 2.0;
        this.kiLinear = params.kiLinear ?? 0.0;
        this.kdLinear = params.kdLinear ?? 0.5;
        this.maxSpeed = params.maxSpeed ?? 1.0;
        this.maxTurnRate = params.maxTurnRate ?? 5.0;
        this.lookaheadBase = params.lookaheadBase ?? 0.15;
        this.lookaheadMin = params.lookaheadMin ?? 0.03;
        this.arrivalTolerance = params.arrivalTolerance ?? 0.05;
        this.arrivalDwellTime = params.arrivalDwellTime ?? 0.5;
        this.stopDwellTime = params.stopDwellTime ?? 1.0;
        this.reverseEnterAngle = params.reverseEnterAngle ?? 2.1;
        this.reverseExitAngle = params.reverseExitAngle ?? 1.05;
        this.decelLimit = params.decelLimit ?? 0.6;
        this.curvatureGain = params.curvatureGain ?? 0.2;
        this.curvatureLookahead = params.curvatureLookahead ?? 0.05;
    }
}


export class PositionControl {
    /**
     * @param {PositionControlConfig} [config]
     */
    constructor(config = null) {
        this.config = config || new PositionControlConfig();
        this.mode = POS_IDLE;

        // Path buffer
        this._path = [];       // Array of [x, y]
        this._cumulDist = [];   // Cumulative arc-length
        this._stopIndices = [];

        // Path state
        this._pathState = PATH_IDLE;
        this._progress = 0;
        this._pathMaxSpeed = 0;
        this._pathMaxSpacing = 0;
        this._pathTotalLength = 0;
        this._nextStopPtr = 0;

        // Carrot
        this._carrotX = 0;
        this._carrotY = 0;

        // Control state
        this._angularIntegral = 0;
        this._linearIntegral = 0;
        this._arrivalTimer = 0;
        this._elapsedTime = 0;
        this._reverseModeActive = false;
        this._stopReachedSent = false;
        this._vTargetSmooth = 0;

        // Active commands
        this._turnCmd = { headingRef: 0, timeout: 0, maxAngularSpeed: 0 };
        this._moveCmd = { xTarget: 0, yTarget: 0, timeout: 0, maxSpeed: 0 };
        this._pathCmd = { maxSpeed: 0, maxSpacing: 0, timeout: 0, allowReverse: false };

        // Callbacks
        this.onPathFinished = null;
        this.onPathTimeout = null;
        this.onMoveCompleted = null;
        this.onTurnCompleted = null;
        this.onStopReached = null;
        this.onStopCompleted = null;
    }

    // === Status ===

    get isIdle() { return this.mode === POS_IDLE; }
    get isRunning() { return this._pathState === PATH_RUNNING; }
    get progress() { return this._progress; }
    get carrotX() { return this._carrotX; }
    get carrotY() { return this._carrotY; }

    // === Commands ===

    turnToHeading(headingRef, timeout = 0, maxAngularSpeed = 0) {
        if (this.mode !== POS_IDLE) return false;
        this._turnCmd = { headingRef, timeout, maxAngularSpeed };
        this._elapsedTime = 0;
        this._angularIntegral = 0;
        this._arrivalTimer = 0;
        this.mode = POS_TURN_TO_HEADING;
        return true;
    }

    moveToPoint(x, y, timeout = 0, maxSpeed = 0) {
        if (this.mode !== POS_IDLE) return false;
        this._moveCmd = { xTarget: x, yTarget: y, timeout, maxSpeed };
        this._elapsedTime = 0;
        this._angularIntegral = 0;
        this._linearIntegral = 0;
        this._arrivalTimer = 0;
        this._reverseModeActive = false;
        this.mode = POS_DRIVE_TO_POINT;
        return true;
    }

    setPath(points, stopIndices = null) {
        this._path = points.map(p => [p[0], p[1]]);
        this._stopIndices = stopIndices ? [...stopIndices] : [];
    }

    startPath(cmd = {}) {
        const n = this._path.length;
        if (n < 2 || this.mode !== POS_IDLE) return false;

        this._computeCumulativeDistances();

        this._pathMaxSpeed = (cmd.maxSpeed > 0) ? cmd.maxSpeed : this.config.maxSpeed;

        if (cmd.maxSpacing > 0) {
            this._pathMaxSpacing = cmd.maxSpacing;
        } else {
            let maxDiff = 0.01;
            for (let i = 1; i < this._cumulDist.length; i++) {
                const d = this._cumulDist[i] - this._cumulDist[i - 1];
                if (d > maxDiff) maxDiff = d;
            }
            this._pathMaxSpacing = maxDiff < EPSILON ? 0.01 : maxDiff;
        }

        this._pathTotalLength = this._cumulDist[n - 1];
        this._progress = 0;
        this._angularIntegral = 0;
        this._linearIntegral = 0;
        this._arrivalTimer = 0;
        this._elapsedTime = 0;
        this._reverseModeActive = false;
        this._stopReachedSent = false;
        this._nextStopPtr = 0;
        this._vTargetSmooth = 0;

        this._carrotX = this._path[0][0];
        this._carrotY = this._path[0][1];

        this._pathCmd = {
            maxSpeed: cmd.maxSpeed || 0,
            maxSpacing: cmd.maxSpacing || 0,
            timeout: cmd.timeout || 0,
            allowReverse: cmd.allowReverse || false,
        };

        this._pathState = PATH_RUNNING;
        this.mode = POS_FOLLOW_PATH;
        return true;
    }

    pausePath() { if (this._pathState === PATH_RUNNING) this._pathState = PATH_PAUSED; }
    resumePath() { if (this._pathState === PATH_PAUSED) this._pathState = PATH_RUNNING; }
    abortPath() {
        if (this.mode === POS_FOLLOW_PATH) {
            this._pathState = PATH_IDLE;
            this.mode = POS_IDLE;
        }
    }

    // === Main Update ===

    /**
     * @param {number} x - Robot X position [m]
     * @param {number} y - Robot Y position [m]
     * @param {number} psi - Robot heading [rad]
     * @param {number} v - Forward velocity [m/s]
     * @returns {{ vCmd: number, psiDotCmd: number }}
     */
    update(x, y, psi, v) {
        const out = { vCmd: 0, psiDotCmd: 0 };

        if (this.mode !== POS_IDLE) this._elapsedTime += this.config.Ts;

        if (this.mode === POS_TURN_TO_HEADING)  return this._updateTurnToHeading(x, y, psi);
        if (this.mode === POS_DRIVE_TO_POINT)   return this._updateDriveToPoint(x, y, psi, v);
        if (this.mode === POS_FOLLOW_PATH)      return this._updateFollowPath(x, y, psi, v);

        return out;
    }

    reset() {
        this._angularIntegral = 0;
        this._linearIntegral = 0;
        this._arrivalTimer = 0;
        this._elapsedTime = 0;
        this._reverseModeActive = false;
        this._path = [];
        this._cumulDist = [];
        this._stopIndices = [];
        this._pathState = PATH_IDLE;
        this._progress = 0;
        this._pathMaxSpeed = 0;
        this._pathMaxSpacing = 0;
        this._pathTotalLength = 0;
        this._stopReachedSent = false;
        this._nextStopPtr = 0;
        this._vTargetSmooth = 0;
        this.mode = POS_IDLE;
    }

    // === Turn To Heading ===

    _updateTurnToHeading(x, y, psi) {
        const cfg = this.config;
        const cmd = this._turnCmd;
        const out = { vCmd: 0, psiDotCmd: 0 };

        const headingError = normalizeAngle(cmd.headingRef - psi);
        const maxRate = (cmd.maxAngularSpeed > 0) ? cmd.maxAngularSpeed : cfg.maxTurnRate;

        const effKp = (cfg.kpAngularHeading > 0) ? cfg.kpAngularHeading : cfg.kpAngular;
        const effKi = (cfg.kiAngularHeading > 0) ? cfg.kiAngularHeading : cfg.kiAngular;

        const wP = effKp * headingError;
        const wI = this._angularIntegral;
        const wUnsat = wP + wI;
        const wSat = clamp(wUnsat, -maxRate, maxRate);

        const isSaturated = Math.abs(wUnsat - wSat) > EPSILON;
        const wouldPushFurther = isSaturated && (
            (wUnsat > wSat && headingError > 0) || (wUnsat < wSat && headingError < 0));

        if (!wouldPushFurther) {
            this._angularIntegral += effKi * headingError * cfg.Ts;
            const maxIntegral = maxRate / Math.max(effKi, 0.01);
            this._angularIntegral = clamp(this._angularIntegral, -maxIntegral, maxIntegral);
        }

        out.psiDotCmd = wSat;

        if (Math.abs(headingError) < HEADING_ARRIVAL_TOLERANCE) {
            this._arrivalTimer += cfg.Ts;
            if (this._arrivalTimer >= cfg.arrivalDwellTime) {
                this._angularIntegral = 0;
                this._arrivalTimer = 0;
                this.mode = POS_IDLE;
                if (this.onTurnCompleted) this.onTurnCompleted();
                return out;
            }
        } else {
            this._arrivalTimer = 0;
        }

        if (cmd.timeout > 0 && this._elapsedTime > cmd.timeout) {
            this._angularIntegral = 0;
            this._arrivalTimer = 0;
            this.mode = POS_IDLE;
        }

        return out;
    }

    // === Drive To Point ===

    _updateDriveToPoint(x, y, psi, v) {
        const cfg = this.config;
        const cmd = this._moveCmd;
        const out = { vCmd: 0, psiDotCmd: 0 };

        const dx = cmd.xTarget - x;
        const dy = cmd.yTarget - y;
        const dist = Math.hypot(dx, dy);

        if (dist < cfg.arrivalTolerance) {
            this._arrivalTimer += cfg.Ts;
            if (this._arrivalTimer >= cfg.arrivalDwellTime) {
                this._angularIntegral = 0;
                this._linearIntegral = 0;
                this._arrivalTimer = 0;
                this._reverseModeActive = false;
                this.mode = POS_IDLE;
                if (this.onMoveCompleted) this.onMoveCompleted();
                return out;
            }
            return out;
        }
        this._arrivalTimer = 0;

        // Reverse mode with hysteresis
        const angleToTarget = Math.atan2(dy, dx);
        const headingErrorFwd = normalizeAngle(angleToTarget - psi);
        const absHeadingError = Math.abs(headingErrorFwd);

        if (!this._reverseModeActive && absHeadingError > cfg.reverseEnterAngle) {
            this._reverseModeActive = true;
            this._angularIntegral = 0;
        } else if (this._reverseModeActive && absHeadingError < cfg.reverseExitAngle) {
            this._reverseModeActive = false;
            this._angularIntegral = 0;
        }

        // Carrot
        const lookahead = cfg.lookaheadBase;
        let carrotX = cmd.xTarget, carrotY = cmd.yTarget;
        if (dist > EPSILON && lookahead > EPSILON) {
            const stepBack = Math.max(0, dist - lookahead);
            const invDist = 1 / (dist + EPSILON);
            carrotX = cmd.xTarget - dx * invDist * stepBack;
            carrotY = cmd.yTarget - dy * invDist * stepBack;
        }

        const dxC = carrotX - x, dyC = carrotY - y;
        let psiCarrot = Math.atan2(dyC, dxC);
        const carrotDist = Math.hypot(dxC, dyC);

        if (this._reverseModeActive) psiCarrot = normalizeAngle(psiCarrot + Math.PI);
        const headingError = normalizeAngle(psiCarrot - psi);

        // Speed
        const maxSpeed = (cmd.maxSpeed > 0) ? cmd.maxSpeed : cfg.maxSpeed;
        let vP = (cfg.decelLimit > 0 && dist > 0)
            ? Math.sqrt(2 * cfg.decelLimit * dist)
            : cfg.kpLinear * dist;
        vP = Math.max(0, vP - cfg.kdLinear * Math.abs(v));

        const vI = this._linearIntegral;
        const vUnsat = vP + vI;
        const vSat = clamp(vUnsat, 0, maxSpeed);

        if (Math.abs(vUnsat - vSat) < EPSILON) {
            this._linearIntegral += cfg.kiLinear * carrotDist * cfg.Ts;
            this._linearIntegral = clamp(this._linearIntegral, 0, maxSpeed);
        }

        let vCmd = vSat * Math.max(0, Math.cos(headingError));
        if (this._reverseModeActive) vCmd = -vCmd;
        out.vCmd = vCmd;

        // Angular
        const wP = cfg.kpAngular * headingError;
        const wI = this._angularIntegral;
        const wUnsat = wP + wI;
        const wSat = clamp(wUnsat, -cfg.maxTurnRate, cfg.maxTurnRate);

        const isSat = Math.abs(wUnsat - wSat) > EPSILON;
        const wouldPush = isSat && ((wUnsat > wSat && headingError > 0) || (wUnsat < wSat && headingError < 0));
        if (!wouldPush) {
            this._angularIntegral += cfg.kiAngular * headingError * cfg.Ts;
            const maxInt = cfg.maxTurnRate / Math.max(cfg.kiAngular, 0.01);
            this._angularIntegral = clamp(this._angularIntegral, -maxInt, maxInt);
        }

        const fadeRadius = 2 * cfg.arrivalTolerance;
        out.psiDotCmd = wSat * clamp(dist / fadeRadius, 0, 1);

        if (cmd.timeout > 0 && this._elapsedTime > cmd.timeout) {
            this._angularIntegral = 0;
            this._linearIntegral = 0;
            this._arrivalTimer = 0;
            this._reverseModeActive = false;
            this.mode = POS_IDLE;
        }

        return out;
    }

    // === Follow Path ===

    _updateFollowPath(x, y, psi, v) {
        const cfg = this.config;
        const n = this._path.length;
        const out = { vCmd: 0, psiDotCmd: 0 };

        if (this._pathState !== PATH_RUNNING || n < 2) return out;

        // Timeout
        if (this._pathCmd.timeout > 0 && this._elapsedTime > this._pathCmd.timeout) {
            this._pathState = PATH_IDLE;
            this.mode = POS_IDLE;
            if (this.onPathTimeout) this.onPathTimeout();
            return out;
        }

        // Project
        this._progress = this._projectOntoPath(x, y, this._progress);

        // Curvature-based speed
        const kappa = this._estimateCurvatureAhead(this._progress, cfg.curvatureLookahead);
        let vTargetRaw = this._pathMaxSpeed / (1 + cfg.curvatureGain * kappa);
        vTargetRaw = clamp(vTargetRaw, 0, this._pathMaxSpeed);

        // Exponential smoothing
        const alphaSmooth = cfg.Ts / (cfg.Ts + SPEED_SMOOTH_TAU);
        this._vTargetSmooth = alphaSmooth * vTargetRaw + (1 - alphaSmooth) * this._vTargetSmooth;
        let vTarget = this._vTargetSmooth;

        // Decel toward stops and end
        const robotArc = this._cumulDistAt(this._progress);

        if (this._nextStopPtr < this._stopIndices.length) {
            const stopIdx = this._stopIndices[this._nextStopPtr];
            const dToStop = this._cumulDist[stopIdx] - robotArc;
            if (dToStop > 0) {
                const vBrake = (cfg.decelLimit > 0) ? Math.sqrt(2 * cfg.decelLimit * dToStop) : cfg.kpLinear * dToStop;
                vTarget = Math.min(vTarget, vBrake);
            }
        }

        const dToEnd = this._cumulDist[n - 1] - robotArc;
        if (dToEnd > 0) {
            const vBrakeEnd = (cfg.decelLimit > 0) ? Math.sqrt(2 * cfg.decelLimit * dToEnd) : cfg.kpLinear * dToEnd;
            vTarget = Math.min(vTarget, vBrakeEnd);
        } else {
            vTarget = 0;
        }

        // Lookahead
        let lookahead;
        if (cfg.kpLinear > EPSILON) {
            lookahead = vTarget / cfg.kpLinear;
        } else {
            lookahead = cfg.lookaheadBase * (vTarget / Math.max(this._pathMaxSpeed, EPSILON));
        }
        lookahead = Math.max(lookahead, cfg.lookaheadMin);

        // Carrot
        let carrotProgress = this._advanceAlongPath(this._progress, lookahead);
        if (this._nextStopPtr < this._stopIndices.length) {
            const stopIdx = this._stopIndices[this._nextStopPtr];
            if (carrotProgress > stopIdx) carrotProgress = stopIdx;
        }
        carrotProgress = Math.min(carrotProgress, n - 1);

        const [cx, cy] = this._interpolatePath(carrotProgress);
        this._carrotX = cx;
        this._carrotY = cy;

        const dxC = cx - x, dyC = cy - y;
        const carrotDist = Math.hypot(dxC, dyC);
        const angleToCarrot = Math.atan2(dyC, dxC);

        let headingErrorFwd = normalizeAngle(angleToCarrot - psi);
        let headingError = headingErrorFwd;

        // Reverse mode
        if (this._pathCmd.allowReverse) {
            const absHe = Math.abs(headingErrorFwd);
            if (!this._reverseModeActive && absHe > cfg.reverseEnterAngle) {
                this._reverseModeActive = true;
                this._angularIntegral = 0;
            } else if (this._reverseModeActive && absHe < cfg.reverseExitAngle) {
                this._reverseModeActive = false;
                this._angularIntegral = 0;
            }
            if (this._reverseModeActive) headingError = normalizeAngle(headingErrorFwd + Math.PI);
        }

        // Speed
        let vCmd;
        if (cfg.decelLimit > EPSILON) {
            vCmd = vTarget * (1 + cfg.kdLinear);
        } else {
            vCmd = Math.min(vTarget, cfg.kpLinear * carrotDist);
        }
        vCmd = Math.max(0, vCmd - cfg.kdLinear * Math.abs(v));
        vCmd *= Math.max(0, Math.cos(headingError));
        if (this._reverseModeActive) vCmd = -vCmd;
        out.vCmd = vCmd;

        // Angular
        const wP = cfg.kpAngular * headingError;
        const wI = this._angularIntegral;
        const wUnsat = wP + wI;
        const wSat = clamp(wUnsat, -cfg.maxTurnRate, cfg.maxTurnRate);

        const isSat = Math.abs(wUnsat - wSat) > EPSILON;
        const wouldPush = isSat && ((wUnsat > wSat && headingError > 0) || (wUnsat < wSat && headingError < 0));
        if (!wouldPush) {
            this._angularIntegral += cfg.kiAngular * headingError * cfg.Ts;
            const maxInt = cfg.maxTurnRate / Math.max(cfg.kiAngular, 0.01);
            this._angularIntegral = clamp(this._angularIntegral, -maxInt, maxInt);
        }

        const fadeRadius = 2 * cfg.arrivalTolerance;
        out.psiDotCmd = wSat * clamp(carrotDist / fadeRadius, 0, 1);

        // Arrival checks
        const lastPt = this._path[n - 1];
        const lastPtDist = Math.hypot(x - lastPt[0], y - lastPt[1]);
        const progressThreshold = n - 2;
        const nearEnd = (this._progress >= progressThreshold && lastPtDist < cfg.arrivalTolerance);

        let nearStop = false;
        let currentStopIdx = 0;
        if (this._nextStopPtr < this._stopIndices.length) {
            currentStopIdx = this._stopIndices[this._nextStopPtr];
            const stopPt = this._path[currentStopIdx];
            const stopPtDist = Math.hypot(x - stopPt[0], y - stopPt[1]);
            nearStop = (this._progress >= currentStopIdx - 1 && stopPtDist < cfg.arrivalTolerance);
        }

        if (nearEnd) {
            out.vCmd = 0;
            out.psiDotCmd = 0;
            this._arrivalTimer += cfg.Ts;
            if (this._arrivalTimer >= cfg.arrivalDwellTime) {
                this._pathState = PATH_IDLE;
                this.mode = POS_IDLE;
                if (this.onPathFinished) this.onPathFinished();
            }
            return out;
        }

        if (nearStop) {
            if (!this._stopReachedSent) {
                if (this.onStopReached) this.onStopReached(currentStopIdx);
                this._stopReachedSent = true;
            }
            out.vCmd = 0;
            out.psiDotCmd = 0;
            this._arrivalTimer += cfg.Ts;
            if (this._arrivalTimer >= cfg.stopDwellTime) {
                if (this.onStopCompleted) this.onStopCompleted(currentStopIdx);
                this._nextStopPtr++;
                this._arrivalTimer = 0;
                this._angularIntegral = 0;
                this._stopReachedSent = false;
            }
            return out;
        }

        this._arrivalTimer = 0;
        this._stopReachedSent = false;

        // Final approach
        const stoppingDistEnd = (cfg.decelLimit > EPSILON)
            ? (this._pathMaxSpeed ** 2 / (2 * cfg.decelLimit)) : 0.5;
        const approachingEnd = (dToEnd < stoppingDistEnd) || (dToEnd < 0);

        if (approachingEnd && !nearEnd) {
            const dxLast = lastPt[0] - x, dyLast = lastPt[1] - y;
            const distLast = Math.hypot(dxLast, dyLast);
            const angleToLast = Math.atan2(dyLast, dxLast);
            let heLast = normalizeAngle(angleToLast - psi);

            let vFinal = (cfg.decelLimit > EPSILON)
                ? Math.sqrt(2 * cfg.decelLimit * distLast)
                : cfg.kpLinear * distLast;
            vFinal = Math.max(0, vFinal - cfg.kdLinear * Math.abs(v));
            vFinal = Math.min(vFinal, this._pathMaxSpeed);

            if (Math.abs(heLast) > cfg.reverseEnterAngle) {
                heLast = normalizeAngle(heLast + Math.PI);
                out.vCmd = -vFinal * Math.max(0, Math.cos(heLast));
            } else {
                out.vCmd = vFinal * Math.max(0, Math.cos(heLast));
            }

            const wLast = clamp(cfg.kpAngular * heLast, -cfg.maxTurnRate, cfg.maxTurnRate);
            out.psiDotCmd = wLast * clamp(distLast / (2 * cfg.arrivalTolerance), 0, 1);
        }

        return out;
    }

    // === Path Geometry ===

    _computeCumulativeDistances() {
        const n = this._path.length;
        this._cumulDist = new Array(n).fill(0);
        for (let i = 1; i < n; i++) {
            const dx = this._path[i][0] - this._path[i - 1][0];
            const dy = this._path[i][1] - this._path[i - 1][1];
            this._cumulDist[i] = this._cumulDist[i - 1] + Math.hypot(dx, dy);
        }
    }

    _projectOntoPath(robotX, robotY, lastProgress) {
        const n = this._path.length;
        let startSeg = Math.floor(lastProgress);
        if (startSeg >= n - 1) startSeg = n - 2;
        const endSeg = Math.min(startSeg + PROJECTION_SEARCH_WINDOW, n - 2);

        let bestProgress = lastProgress;
        let bestDistSq = 1e30;

        for (let i = startSeg; i <= endSeg; i++) {
            const [ax, ay] = this._path[i];
            const [bx, by] = this._path[i + 1];
            const dx = bx - ax, dy = by - ay;
            const lenSq = dx * dx + dy * dy;

            let t = (lenSq < EPSILON) ? 0 : clamp(((robotX - ax) * dx + (robotY - ay) * dy) / lenSq, 0, 1);

            const projX = ax + t * dx, projY = ay + t * dy;
            const distSq = (robotX - projX) ** 2 + (robotY - projY) ** 2;
            const candidate = i + t;

            if (candidate >= lastProgress && distSq < bestDistSq) {
                bestDistSq = distSq;
                bestProgress = candidate;
            }
        }
        return bestProgress;
    }

    _advanceAlongPath(fromProgress, distanceMeters) {
        const n = this._path.length;
        if (n < 2) return fromProgress;

        const currentArc = this._cumulDistAt(fromProgress);
        const targetArc = currentArc + distanceMeters;

        if (targetArc >= this._cumulDist[n - 1]) return n - 1;
        if (targetArc <= 0) return 0;

        let lo = 0, hi = n - 1;
        while (lo < hi - 1) {
            const mid = (lo + hi) >> 1;
            if (this._cumulDist[mid] <= targetArc) lo = mid; else hi = mid;
        }

        const segStart = this._cumulDist[lo];
        const segEnd = this._cumulDist[lo + 1];
        const segLen = segEnd - segStart;
        const t = (segLen > EPSILON) ? clamp((targetArc - segStart) / segLen, 0, 1) : 0;
        return lo + t;
    }

    _interpolatePath(progress) {
        const n = this._path.length;
        if (n === 0) return [0, 0];
        if (progress <= 0) return [this._path[0][0], this._path[0][1]];
        if (progress >= n - 1) return [this._path[n - 1][0], this._path[n - 1][1]];

        const idx = Math.floor(progress);
        const t = progress - idx;
        return [
            this._path[idx][0] + t * (this._path[idx + 1][0] - this._path[idx][0]),
            this._path[idx][1] + t * (this._path[idx + 1][1] - this._path[idx][1]),
        ];
    }

    _cumulDistAt(progress) {
        const n = this._path.length;
        if (n < 2) return 0;
        if (progress <= 0) return this._cumulDist[0];
        if (progress >= n - 1) return this._cumulDist[n - 1];
        const idx = Math.floor(progress);
        const t = progress - idx;
        return this._cumulDist[idx] + t * (this._cumulDist[idx + 1] - this._cumulDist[idx]);
    }

    _estimateCurvatureAhead(atProgress, lookaheadDist) {
        const n = this._path.length;
        if (n < 3) return 0;

        let startIdx = Math.floor(atProgress);
        if (startIdx >= n - 1) startIdx = n - 2;

        const startArc = this._cumulDist[startIdx];
        const endArc = startArc + lookaheadDist;

        let endIdx = startIdx;
        while (endIdx < n - 1 && this._cumulDist[endIdx] < endArc) endIdx++;

        const avgSpacing = (n > 1) ? (this._pathTotalLength / (n - 1)) : 0.015;
        let stride = Math.round(0.05 / Math.max(avgSpacing, 0.001));
        stride = Math.max(1, Math.min(stride, 15));

        if (endIdx < startIdx + 2 * stride) {
            if (startIdx + 2 * stride < n) endIdx = startIdx + 2 * stride;
            else return 0;
        }

        let maxKappa = 0;
        let i = startIdx;
        while (i + 2 * stride <= endIdx && i + 2 * stride < n) {
            const [ax, ay] = this._path[i];
            const [bx, by] = this._path[i + stride];
            const [cx, cy] = this._path[i + 2 * stride];

            const abx = bx - ax, aby = by - ay;
            const acx = cx - ax, acy = cy - ay;
            const crossMag = Math.abs(abx * acy - aby * acx);
            const abLen = Math.hypot(abx, aby);
            const bcLen = Math.hypot(cx - bx, cy - by);
            const acLen = Math.hypot(acx, acy);

            const denom = abLen * bcLen * acLen;
            if (denom > 1e-10) {
                const kappa = 2 * crossMag / denom;
                if (kappa > maxKappa) maxKappa = kappa;
            }
            i++;
        }

        return maxKappa;
    }
}
