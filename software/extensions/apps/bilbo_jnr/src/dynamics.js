/**
 * BILBO 2D Linear Dynamics
 *
 * State: [s, v, theta, theta_dot]
 *   s         - forward position [m]
 *   v         - forward velocity [m/s]
 *   theta     - pitch angle [rad], 0 = upright, positive = leaning forward
 *   theta_dot - pitch angular velocity [rad/s]
 *
 * Input: M (torque, sum of both wheels)
 *
 * Linearised around the upright equilibrium.
 * Controller via pole placement using the default BILBO 2D poles.
 */

const g = 9.81;

// Default BILBO model parameters (from bilbo_model.py)
export const MODEL = {
  m_b: 1.2,       // body mass [kg]
  m_w: 0.4,       // wheel mass [kg]
  l: 0.026,       // COG height above wheel axis [m]
  d_w: 0.22,      // wheel separation [m]
  I_w: 2e-4,      // wheel inertia [kg·m²]
  I_y: 0.005,     // body pitch inertia [kg·m²]
  I_x: 0.02,      // body roll inertia
  I_z: 0.03,      // body yaw inertia
  c_alpha: 4.6302e-4, // drag coeff
  r_w: 0.06,      // wheel radius [m]
  tau_theta: 0.4,  // theta drag
  tau_x: 0.4,      // speed drag
  max_pitch: 105 * Math.PI / 180,  // max pitch for floor contact [rad]
};

// Visual dimensions (from bilbo_plot.py)
export const VISUAL = {
  wheel_radius: 0.06,
  wheel_inner_ratio: 0.65,
  body_height: 0.185,
  body_width: 0.085,
  body_corner_radius: 0.005,
};

// =====================================================================================================================
// Linear model matrices (continuous-time)
// =====================================================================================================================

function getLinearModel(model) {
  const { m_b, m_w, I_w, r_w, I_y, l, c_alpha } = model;

  const C_21 = (m_b + 2 * m_w + 2 * I_w / (r_w ** 2)) * m_b * l;
  const V_1 = (m_b + 2 * m_w + 2 * I_w / (r_w ** 2)) * (I_y + m_b * l ** 2) - m_b ** 2 * l ** 2;
  const D_22 = (m_b + 2 * m_w + 2 * I_w / (r_w ** 2)) * 2 * c_alpha + m_b * l * 2 * c_alpha / r_w;
  const D_21 = (m_b + 2 * m_w + 2 * I_w / (r_w ** 2)) * 2 * c_alpha / r_w + m_b * l * 2 * c_alpha / (r_w ** 2);
  const C_11 = m_b ** 2 * l ** 2;
  const D_12 = (I_y + m_b * l ** 2) * 2 * c_alpha / r_w - m_b * l * 2 * c_alpha;
  const D_11 = (I_y + m_b * l ** 2) * 2 * c_alpha / (r_w ** 2) - m_b * l * 2 * c_alpha / r_w;

  const A = [
    [0, 1, 0, 0],
    [0, -D_11 / V_1, -C_11 * g / V_1, D_12 / V_1],
    [0, 0, 0, 1],
    [0, D_21 / V_1, C_21 * g / V_1, -D_22 / V_1],
  ];

  const B_1 = (I_y + m_b * l ** 2) / r_w + m_b * l;
  const B_2 = m_b * l / r_w + m_b + 2 * m_w + 2 * I_w / (r_w ** 2);

  const B = [
    [0],
    [B_1 / V_1],
    [0],
    [-B_2 / V_1],
  ];

  return { A, B };
}

// =====================================================================================================================
// Matrix utilities (small 4x4 only, no external deps)
// =====================================================================================================================

function matMul(A, B) {
  const n = A.length, m = B[0].length, p = B.length;
  const C = Array.from({ length: n }, () => new Float64Array(m));
  for (let i = 0; i < n; i++)
    for (let j = 0; j < m; j++)
      for (let k = 0; k < p; k++)
        C[i][j] += A[i][k] * B[k][j];
  return C;
}

function matAdd(A, B) {
  return A.map((row, i) => row.map((v, j) => v + B[i][j]));
}

function matScale(A, s) {
  return A.map(row => row.map(v => v * s));
}

function eye(n) {
  return Array.from({ length: n }, (_, i) =>
    Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))
  );
}

function matVecMul(A, x) {
  return A.map(row => row.reduce((s, v, j) => s + v * x[j], 0));
}

// =====================================================================================================================
// Discretise with matrix exponential (Padé approximation via Taylor for small Ts)
// =====================================================================================================================

function discretise(Ac, Bc, Ts) {
  // Use 12-term Taylor series for matrix exponential: e^(A*Ts) ≈ I + A*Ts + (A*Ts)^2/2! + ...
  const n = Ac.length;
  const ATs = matScale(Ac, Ts);
  let Ad = eye(n);
  let power = eye(n);
  for (let k = 1; k <= 12; k++) {
    power = matScale(matMul(power, ATs), 1 / k);
    Ad = matAdd(Ad, power);
  }

  // Bd ≈ (integral from 0 to Ts of e^(A*t) dt) * Bc
  // Using Taylor: Bd ≈ (I*Ts + A*Ts²/2! + A²*Ts³/3! + ...) * Bc
  let integ = matScale(eye(n), Ts);
  power = eye(n);
  for (let k = 1; k <= 12; k++) {
    power = matMul(power, ATs);
    integ = matAdd(integ, matScale(power, Ts / ((k + 1) * factorial(k))));
  }
  // Actually simpler: Bd = Ad_integral * Bc where we just computed integ wrongly.
  // Let's redo properly:
  // Integral of e^(A*t) from 0 to Ts = sum_{k=0}^inf A^k * Ts^{k+1} / (k+1)!
  let integ2 = Array.from({ length: n }, () => new Array(n).fill(0));
  power = eye(n);
  for (let k = 0; k <= 12; k++) {
    integ2 = matAdd(integ2, matScale(power, Math.pow(Ts, k + 1) / factorial(k + 1)));
    power = matMul(power, Ac);
  }
  const Bd = matMul(integ2, Bc);

  return { Ad, Bd };
}

function factorial(n) {
  let f = 1;
  for (let i = 2; i <= n; i++) f *= i;
  return f;
}

// =====================================================================================================================
// Pole placement via Ackermann's formula (for SISO 4th order system)
// =====================================================================================================================

function polePlacement(Ad, Bd, poles) {
  // poles are continuous-time, convert to discrete: z = e^(p*Ts) already done by caller
  const n = Ad.length;

  // Controllability matrix [Bd, Ad*Bd, Ad²*Bd, Ad³*Bd]
  const cols = [Bd.map(r => r[0])];
  for (let i = 1; i < n; i++) {
    cols.push(matVecMul(Ad, cols[i - 1]));
  }

  // Ctrb as matrix
  const Ctrb = cols[0].map((_, i) => cols.map(c => c[i]));

  // Inverse of controllability matrix (4x4)
  const CInv = inv4(Ctrb);
  if (!CInv) throw new Error('Controllability matrix is singular');

  // Desired characteristic polynomial: prod(zI - z_i)
  // phi(Ad) = Ad^4 + a3*Ad^3 + a2*Ad^2 + a1*Ad + a0*I
  const charPoly = polyFromRoots(poles); // coefficients [a0, a1, a2, a3, 1]

  // phi(Ad) = sum of charPoly[k] * Ad^k
  let phiA = Array.from({ length: n }, () => new Array(n).fill(0));
  let Ak = eye(n);
  for (let k = 0; k <= n; k++) {
    phiA = matAdd(phiA, matScale(Ak, charPoly[k]));
    if (k < n) Ak = matMul(Ak, Ad);
  }

  // K = last row of CInv * phi(Ad)
  const lastRow = CInv[n - 1];
  const K = matVecMul(transposeForVec(phiA), lastRow);
  return K;
}

function transposeForVec(A) {
  const n = A.length, m = A[0].length;
  return Array.from({ length: m }, (_, j) => Array.from({ length: n }, (_, i) => A[i][j]));
}

// Polynomial from roots: (z-r1)(z-r2)...(z-rn), returns [a0, a1, ..., an] with an=1
// Handles complex roots (which come in conjugate pairs, so result is real)
function polyFromRoots(roots) {
  // Start with [1] and multiply
  let poly = [{ re: 1, im: 0 }];
  for (const root of roots) {
    const r = typeof root === 'object' ? root : { re: root, im: 0 };
    const newPoly = new Array(poly.length + 1).fill(null).map(() => ({ re: 0, im: 0 }));
    for (let i = 0; i < poly.length; i++) {
      // multiply by (z - r): shift up and subtract r*current
      newPoly[i + 1].re += poly[i].re;
      newPoly[i + 1].im += poly[i].im;
      newPoly[i].re -= poly[i].re * r.re - poly[i].im * r.im;
      newPoly[i].im -= poly[i].re * r.im + poly[i].im * r.re;
    }
    poly = newPoly;
  }
  return poly.map(c => c.re); // imaginary parts should be ~0 for conjugate pairs
}

// Complex exponential
function cexp(re, im) {
  const mag = Math.exp(re);
  return { re: mag * Math.cos(im), im: mag * Math.sin(im) };
}

// 4x4 matrix inverse (Gauss-Jordan)
function inv4(M) {
  const n = 4;
  const aug = M.map((row, i) => [...row, ...Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))]);
  for (let col = 0; col < n; col++) {
    let maxRow = col;
    for (let row = col + 1; row < n; row++) {
      if (Math.abs(aug[row][col]) > Math.abs(aug[maxRow][col])) maxRow = row;
    }
    [aug[col], aug[maxRow]] = [aug[maxRow], aug[col]];
    const pivot = aug[col][col];
    if (Math.abs(pivot) < 1e-12) return null;
    for (let j = 0; j < 2 * n; j++) aug[col][j] /= pivot;
    for (let row = 0; row < n; row++) {
      if (row === col) continue;
      const f = aug[row][col];
      for (let j = 0; j < 2 * n; j++) aug[row][j] -= f * aug[col][j];
    }
  }
  return aug.map(row => row.slice(n));
}

// =====================================================================================================================
// BilboDynamics2D class
// =====================================================================================================================

export class BilboDynamics2D {
  constructor(Ts = 0.01, model = MODEL) {
    this.Ts = Ts;
    this.model = model;

    // State: [s, v, theta, theta_dot]
    this.state = [0, 0, 0, 0];

    // Get continuous linear model
    const { A, B } = getLinearModel(model);

    // Discretise
    const { Ad, Bd } = discretise(A, B, Ts);
    this.Ad = Ad;
    this.Bd = Bd;

    // Pole placement with BILBO_2D_POLES = [0, -10, -5+3j, -5-3j]
    const continuousPoles = [
      { re: 0, im: 0 },
      { re: -10, im: 0 },
      { re: -5, im: 3 },
      { re: -5, im: -3 },
    ];
    const discretePoles = continuousPoles.map(p => cexp(p.re * Ts, p.im * Ts));
    this.K = polePlacement(Ad, Bd, discretePoles);

    // Precompute closed-loop A for ground dynamics: A_cl = Ad - Bd * K
    this.Ad_cl = Ad.map((row, i) =>
      row.map((v, j) => v - Bd[i][0] * this.K[j])
    );
  }

  /** Reset state */
  reset(s = 0, v = 0, theta = 0, thetaDot = 0) {
    this.state = [s, v, theta, thetaDot];
  }

  /**
   * Step the dynamics with external torque offset.
   * The controller is: u = u_ext - K * x
   * @param {number} uExt - external torque input offset
   */
  step(uExt = 0) {
    const x = this.state;
    // Controller: u = uExt - K·x
    const MAX_TORQUE = 5.0; // saturate controller output to prevent runaway at large theta
    let u = uExt - (this.K[0] * x[0] + this.K[1] * x[1] + this.K[2] * x[2] + this.K[3] * x[3]);
    u = Math.max(-MAX_TORQUE, Math.min(MAX_TORQUE, u));
    // x_next = Ad * x + Bd * u
    const xNext = [
      this.Ad[0][0] * x[0] + this.Ad[0][1] * x[1] + this.Ad[0][2] * x[2] + this.Ad[0][3] * x[3] + this.Bd[0][0] * u,
      this.Ad[1][0] * x[0] + this.Ad[1][1] * x[1] + this.Ad[1][2] * x[2] + this.Ad[1][3] * x[3] + this.Bd[1][0] * u,
      this.Ad[2][0] * x[0] + this.Ad[2][1] * x[1] + this.Ad[2][2] * x[2] + this.Ad[2][3] * x[3] + this.Bd[2][0] * u,
      this.Ad[3][0] * x[0] + this.Ad[3][1] * x[1] + this.Ad[3][2] * x[2] + this.Ad[3][3] * x[3] + this.Bd[3][0] * u,
    ];
    // Apply additional drag terms tau_x and tau_theta (Euler integration, matches nonlinear model)
    xNext[1] -= this.model.tau_x * x[1] * this.Ts;
    xNext[3] -= this.model.tau_theta * x[3] * this.Ts;
    this.state = xNext;
    return this.state;
  }

  /**
   * Step with frozen theta during airtime.
   * Only updates s and v; theta and theta_dot are held constant.
   */
  stepAirborne(uExt = 0, frozenTheta = 0, frozenThetaDot = 0) {
    const x = this.state;
    // During airtime: direct velocity steering for responsive air control
    const AIR_ACCEL = 6.0;            // Acceleration toward target [m/s²]
    const AIR_DECEL = 4.0;            // Deceleration (drift to stop) [m/s²]
    const MAX_AIR_SPEED = 1.5;        // Max air speed [m/s]

    let v = x[1];
    if (uExt !== 0) {
      // Steer: accelerate toward input direction
      const targetDir = -Math.sign(uExt);
      v += targetDir * AIR_ACCEL * this.Ts;
    } else {
      // No input: gently decelerate (drift)
      if (Math.abs(v) < AIR_DECEL * this.Ts) {
        v = 0;
      } else {
        v -= Math.sign(v) * AIR_DECEL * this.Ts;
      }
    }
    v = Math.max(-MAX_AIR_SPEED, Math.min(MAX_AIR_SPEED, v));
    const s = x[0] + v * this.Ts;
    this.state = [s, v, frozenTheta, frozenThetaDot];
    return this.state;
  }

  get s() { return this.state[0]; }
  get v() { return this.state[1]; }
  get theta() { return this.state[2]; }
  get thetaDot() { return this.state[3]; }
}
