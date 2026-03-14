/**
 * Control design: eigenstructure assignment, pole placement, DLQR.
 *
 * Matches the Python implementations in lib_control/general.py and bilbo_model.py.
 */

import { Matrix, eye, zeros, inv } from './linalg.js';
import { complexMatInv } from './linalg.js';
import { linearizeReduced, c2d } from './dynamics.js';

// Default poles and eigenvectors for BILBO 3D eigenstructure assignment
export const DEFAULT_POLES = [
    { re: 0, im: 0 },
    { re: -10, im: 0 },
    { re: -5, im: 3 },
    { re: -5, im: -3 },
    { re: 0, im: 0 },
    { re: -15, im: 0 },
];

// Eigenvector constraints: NaN = free, number = constrained
// Each column corresponds to one pole
export const DEFAULT_EIGENVECTORS = [
    [1,   NaN, NaN, NaN, 0,   NaN],
    [NaN, 1,   NaN, NaN, NaN, NaN],
    [NaN, NaN, 1,   1,   NaN, 0  ],
    [NaN, NaN, NaN, NaN, NaN, NaN],
    [0,   NaN, NaN, NaN, 1,   1  ],
    [NaN, 0,   0,   0,   NaN, NaN],
];


/**
 * Eigenstructure assignment for MIMO systems.
 *
 * Given continuous-time A (n×n), B (n×m), desired poles (complex),
 * and eigenvector constraints, computes gain K (m×n) such that
 * (A - B*K) has the specified eigenstructure.
 *
 * @param {Matrix} A - System matrix (n×n)
 * @param {Matrix} B - Input matrix (n×m)
 * @param {Array<{re: number, im: number}>} poles - Desired poles
 * @param {number[][]} eigenvectors - Constraint matrix (n×n), NaN = free
 * @returns {Matrix} K - Gain matrix (m×n)
 */
export function eigenstructureAssignment(A, B, poles, eigenvectors) {
    const N = A.rows;
    const M = B.cols;

    const reducedEv = [];
    const D = [];

    for (let i = 0; i < N; i++) {
        // Extract non-NaN entries from column i of eigenvectors
        const constrained = [];
        const constrainedIndices = [];
        for (let j = 0; j < N; j++) {
            if (!isNaN(eigenvectors[j][i])) {
                constrained.push(eigenvectors[j][i]);
                constrainedIndices.push(j);
            }
        }
        reducedEv.push(constrained);

        // Build D_i matrix (M × N)
        const Di = [];
        for (let j = 0; j < M; j++) {
            const row = new Array(N).fill(0);
            if (j < constrainedIndices.length) {
                row[constrainedIndices[j]] = 1;
            }
            Di.push(row);
        }
        D.push(Di);
    }

    // Solve for each pole
    const X_re = []; // n×n real parts
    const X_im = []; // n×n imag parts
    const R_re = []; // m×n real parts
    const R_im = []; // m×n imag parts

    for (let i = 0; i < N; i++) {
        const pole = poles[i];

        // Build augmented system: [[A - lambda*I, B], [D_i, 0]] * [x; r] = [0; v_constrained]
        const sz = N + M;

        // Complex augmented matrix
        const mat = [];
        for (let row = 0; row < sz; row++) {
            mat[row] = [];
            for (let col = 0; col < sz; col++) {
                mat[row][col] = [0, 0]; // [re, im]
            }
        }

        // Top-left: A - lambda*I
        for (let r = 0; r < N; r++) {
            for (let c = 0; c < N; c++) {
                let re = A.get(r, c);
                let im = 0;
                if (r === c) {
                    re -= pole.re;
                    im -= pole.im;
                }
                mat[r][c] = [re, im];
            }
        }

        // Top-right: B
        for (let r = 0; r < N; r++) {
            for (let c = 0; c < M; c++) {
                mat[r][N + c] = [B.get(r, c), 0];
            }
        }

        // Bottom-left: D_i
        for (let r = 0; r < M; r++) {
            for (let c = 0; c < N; c++) {
                mat[N + r][c] = [D[i][r][c], 0];
            }
        }

        // Bottom-right: zeros (already initialized)

        // RHS vector
        const rhs = [];
        for (let r = 0; r < N; r++) rhs.push([0, 0]);
        for (let r = 0; r < M; r++) rhs.push([reducedEv[i][r] || 0, 0]);

        // Solve via complex matrix inversion
        const matInv = complexMatInv(mat, sz);

        // Multiply matInv * rhs
        const b = [];
        for (let r = 0; r < sz; r++) {
            let re = 0, im = 0;
            for (let c = 0; c < sz; c++) {
                const mr = matInv[r][c][0], mi = matInv[r][c][1];
                const vr = rhs[c][0], vi = rhs[c][1];
                re += mr * vr - mi * vi;
                im += mr * vi + mi * vr;
            }
            b.push([re, im]);
        }

        // x = b[0:N], r = -b[N:N+M]
        const xi_re = [], xi_im = [];
        for (let j = 0; j < N; j++) { xi_re.push(b[j][0]); xi_im.push(b[j][1]); }

        const ri_re = [], ri_im = [];
        for (let j = 0; j < M; j++) { ri_re.push(-b[N + j][0]); ri_im.push(-b[N + j][1]); }

        X_re.push(xi_re);
        X_im.push(xi_im);
        R_re.push(ri_re);
        R_im.push(ri_im);
    }

    // Assemble X (n×n) and R (m×n) as complex, then K = Re(R * X^{-1})
    const Xc = [];
    for (let i = 0; i < N; i++) {
        Xc[i] = [];
        for (let j = 0; j < N; j++) {
            Xc[i][j] = [X_re[j][i], X_im[j][i]]; // Column j is eigenvector j
        }
    }

    const XcInv = complexMatInv(Xc, N);

    // R is m×n (column j is the j-th r vector)
    const Rc = [];
    for (let i = 0; i < M; i++) {
        Rc[i] = [];
        for (let j = 0; j < N; j++) {
            Rc[i][j] = [R_re[j][i], R_im[j][i]];
        }
    }

    // K = Re(R * X^{-1})
    const K = new Matrix(M, N);
    for (let i = 0; i < M; i++) {
        for (let j = 0; j < N; j++) {
            let re = 0;
            for (let k = 0; k < N; k++) {
                const r = Rc[i][k];
                const x = XcInv[k][j];
                re += r[0] * x[0] - r[1] * x[1];
            }
            K.set(i, j, re);
        }
    }

    // Check for NaN
    for (let i = 0; i < K.data.length; i++) {
        if (isNaN(K.data[i])) throw new Error('Eigenstructure assignment failed: NaN in K');
    }

    return K;
}


/**
 * Compute the full 7-state K matrix for BILBO 3D using eigenstructure assignment
 * on the reduced 6-state model, then prepend a zero column for x-position.
 *
 * This matches the Python BILBO_Dynamics_3D.eigenstructureAssignment() method.
 *
 * @param {BilboModel} model
 * @param {Array<{re: number, im: number}>} [poles] - 6 desired poles
 * @param {number[][]} [eigenvectors] - 6×6 eigenvector constraints
 * @returns {Matrix} K - Gain matrix (2×7)
 */
export function bilboEigenstructureAssignment(model, poles = null, eigenvectors = null) {
    const p = poles || DEFAULT_POLES;
    const ev = eigenvectors || DEFAULT_EIGENVECTORS;

    const { A, B } = linearizeReduced(model);
    const K6 = eigenstructureAssignment(A, B, p, ev);

    // Prepend zero column (x state is not part of reduced model, mapped to index 0 of full state)
    // Full K is 2×7: [0, K6_row]
    const K = new Matrix(2, 7);
    for (let i = 0; i < 2; i++) {
        K.set(i, 0, 0); // x column
        for (let j = 0; j < 6; j++) {
            K.set(i, j + 1, K6.get(i, j));
        }
    }

    return K;
}


/**
 * Simple pole placement for 2D BILBO (4-state SISO).
 *
 * Uses the linearized 2D model and Ackermann-style placement via the
 * discrete-time system: K_d = place(A_d, B_d, exp(poles * Ts)).
 *
 * For the 2D case the state is [s, v, theta, theta_dot] with input M (scalar).
 *
 * @param {BilboModel} model
 * @param {number[]} poles - 4 continuous-time poles (real)
 * @param {number} [Ts=0.01]
 * @returns {Matrix} K - Gain matrix (1×4)
 */
export function polePlacement2D(model, poles, Ts = 0.01) {
    // Build the 2D linear model
    const { m_b, m_w, l, d_w, I_w, I_y, I_x, I_z, c_alpha, r_w } = model;

    const C_21 = (m_b + 2 * m_w + 2 * I_w / r_w ** 2) * m_b * l;
    const V_1  = (m_b + 2 * m_w + 2 * I_w / r_w ** 2) * (I_y + m_b * l ** 2) - m_b ** 2 * l ** 2;
    const D_22 = (m_b + 2 * m_w + 2 * I_w / r_w ** 2) * 2 * c_alpha + m_b * l * 2 * c_alpha / r_w;
    const D_21 = (m_b + 2 * m_w + 2 * I_w / r_w ** 2) * 2 * c_alpha / r_w + m_b * l * 2 * c_alpha / r_w ** 2;
    const C_11 = m_b ** 2 * l ** 2;
    const D_12 = (I_y + m_b * l ** 2) * 2 * c_alpha / r_w - m_b * l * 2 * c_alpha;
    const D_11 = (I_y + m_b * l ** 2) * 2 * c_alpha / r_w ** 2 - m_b * l * 2 * c_alpha / r_w;
    const B_1  = (I_y + m_b * l ** 2) / r_w + m_b * l;
    const B_2  = m_b * l / r_w + m_b + 2 * m_w + 2 * I_w / r_w ** 2;

    const Ac = Matrix.from2D([
        [0, 1, 0, 0],
        [0, -D_11 / V_1, -C_11 * 9.81 / V_1, D_12 / V_1],
        [0, 0, 0, 1],
        [0, D_21 / V_1, C_21 * 9.81 / V_1, -D_22 / V_1],
    ]);
    const Bc = Matrix.from2D([
        [0],
        [B_1 / V_1],
        [0],
        [-B_2 / V_1],
    ]);

    // Discrete-time poles
    const discretePoles = poles.map(p => Math.exp(p * Ts));

    // For SISO systems, use Ackermann's formula
    const { Ad, Bd } = c2d(Ac, Bc, Ts);
    return _ackermannSISO(Ad, Bd, discretePoles);
}


/**
 * Ackermann's formula for SISO pole placement.
 * Returns K such that eig(A - B*K) = desired poles.
 */
function _ackermannSISO(A, B, desiredPoles) {
    const n = A.rows;

    // Controllability matrix: [B, A*B, A^2*B, ...]
    const Ctrb = new Matrix(n, n);
    let col = B;
    for (let j = 0; j < n; j++) {
        for (let i = 0; i < n; i++) Ctrb.set(i, j, col.get(i, 0));
        if (j < n - 1) col = A.mul(col);
    }

    const CtrbInv = inv(Ctrb);

    // Characteristic polynomial: product of (A - p_i * I)
    let phiA = eye(n);
    for (const p of desiredPoles) {
        const shifted = A.sub(eye(n).scale(p));
        phiA = phiA.mul(shifted);
    }

    // K = e_n^T * Ctrb^{-1} * phi(A)
    // e_n^T is [0, 0, ..., 0, 1] (last row of Ctrb^{-1})
    const lastRow = new Matrix(1, n);
    for (let j = 0; j < n; j++) lastRow.set(0, j, CtrbInv.get(n - 1, j));

    return lastRow.mul(phiA);
}


/**
 * Discrete LQR via solving the discrete algebraic Riccati equation (DARE).
 * Iterative solution suitable for small systems.
 *
 * @param {Matrix} A - Discrete system matrix
 * @param {Matrix} B - Discrete input matrix
 * @param {Matrix} Q - State cost matrix
 * @param {Matrix} R - Input cost matrix
 * @param {number} [maxIter=1000]
 * @returns {{ K: Matrix, P: Matrix }} - Gain and solution of DARE
 */
export function dlqr(A, B, Q, R, maxIter = 1000) {
    const n = A.rows;
    let P = Q.clone();

    const BT = B.transpose();
    const AT = A.transpose();

    for (let iter = 0; iter < maxIter; iter++) {
        // K = (R + B'PB)^{-1} B'PA
        const BtP = BT.mul(P);
        const BtPB = BtP.mul(B);
        const BtPA = BtP.mul(A);
        const K = inv(R.add(BtPB)).mul(BtPA);

        // P_new = Q + A'PA - A'PB*K
        const AtP = AT.mul(P);
        const AtPA = AtP.mul(A);
        const AtPB = AtP.mul(B);
        const Pnew = Q.add(AtPA).sub(AtPB.mul(K));

        // Check convergence
        let maxDiff = 0;
        for (let i = 0; i < Pnew.data.length; i++) {
            maxDiff = Math.max(maxDiff, Math.abs(Pnew.data[i] - P.data[i]));
        }
        P = Pnew;
        if (maxDiff < 1e-12) {
            const Kfinal = inv(R.add(BT.mul(P).mul(B))).mul(BT.mul(P).mul(A));
            return { K: Kfinal, P };
        }
    }

    const Kfinal = inv(R.add(BT.mul(P).mul(B))).mul(BT.mul(P).mul(A));
    return { K: Kfinal, P };
}
