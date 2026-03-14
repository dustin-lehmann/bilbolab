/**
 * Velocity PID controller (forward velocity + yaw rate).
 *
 * Matches the Python VelocityControllerConfig and _velocity_control()
 * from bilbo_complete_agent.py.
 */

import { clamp } from './utils.js';


export class VelocityControllerConfig {
    constructor(params = {}) {
        // Longitudinal velocity PID
        this.kpV = params.kpV ?? -0.179;
        this.kiV = params.kiV ?? -0.8;
        this.kdV = params.kdV ?? -0.005;

        // Yaw rate PID
        this.kpPsiDot = params.kpPsiDot ?? 0.35121;
        this.kiPsiDot = params.kiPsiDot ?? 7.6256;
        this.kdPsiDot = params.kdPsiDot ?? 0.0023;

        // Integral limits
        this.integralMaxV = params.integralMaxV ?? 10.0;
        this.integralMaxPsiDot = params.integralMaxPsiDot ?? 10.0;
    }
}


export class VelocityController {
    /**
     * @param {number} Ts - Sample time [s]
     * @param {VelocityControllerConfig} [config]
     */
    constructor(Ts, config = null) {
        this.Ts = Ts;
        this.config = config || new VelocityControllerConfig();

        this._vIntegral = 0;
        this._vLastError = 0;
        this._psiDotIntegral = 0;
        this._psiDotLastError = 0;
    }

    /**
     * Compute motor torques from velocity commands and current state.
     *
     * @param {number} vCmd - Desired forward velocity [m/s]
     * @param {number} psiDotCmd - Desired yaw rate [rad/s]
     * @param {number} v - Current forward velocity [m/s]
     * @param {number} psiDot - Current yaw rate [rad/s]
     * @returns {number[]} [uLeft, uRight] - Motor torque commands
     */
    update(vCmd, psiDotCmd, v, psiDot) {
        const cfg = this.config;

        const eV = vCmd - v;
        const ePsiDot = psiDotCmd - psiDot;

        // Integrals
        this._vIntegral += eV * this.Ts;
        this._psiDotIntegral += ePsiDot * this.Ts;

        // Derivatives
        const eVDot = (eV - this._vLastError) / this.Ts;
        this._vLastError = eV;

        const ePsiDotDot = (ePsiDot - this._psiDotLastError) / this.Ts;
        this._psiDotLastError = ePsiDot;

        // Saturate integrals (anti-windup)
        this._vIntegral = clamp(this._vIntegral, -cfg.integralMaxV, cfg.integralMaxV);
        this._psiDotIntegral = clamp(this._psiDotIntegral, -cfg.integralMaxPsiDot, cfg.integralMaxPsiDot);

        // PID for v
        const uV = cfg.kpV * eV + cfg.kiV * this._vIntegral + cfg.kdV * eVDot;

        // PID for psi_dot
        const uPsi = cfg.kpPsiDot * ePsiDot + cfg.kiPsiDot * this._psiDotIntegral + cfg.kdPsiDot * ePsiDotDot;

        return [uV - uPsi, uV + uPsi];
    }

    reset() {
        this._vIntegral = 0;
        this._vLastError = 0;
        this._psiDotIntegral = 0;
        this._psiDotLastError = 0;
    }
}
