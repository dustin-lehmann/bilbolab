/**
 * Lightweight linear algebra for small dense matrices.
 *
 * All matrices are stored as flat Float64Arrays in row-major order.
 * This keeps things fast and allocation-light for the 6×6 / 7×7 systems
 * we deal with in BILBO dynamics.
 */

// =====================================================================================================================
// Matrix class
// =====================================================================================================================

export class Matrix {
    /**
     * @param {number} rows
     * @param {number} cols
     * @param {Float64Array|number[]} [data] - row-major, length rows*cols
     */
    constructor(rows, cols, data) {
        this.rows = rows;
        this.cols = cols;
        this.data = data instanceof Float64Array
            ? data
            : new Float64Array(data || rows * cols);
    }

    get(i, j) { return this.data[i * this.cols + j]; }
    set(i, j, v) { this.data[i * this.cols + j] = v; }

    clone() {
        return new Matrix(this.rows, this.cols, new Float64Array(this.data));
    }

    /** Return a plain number[] array (e.g. for state vectors). */
    toArray() { return Array.from(this.data); }

    /** Matrix-matrix multiply: this * B */
    mul(B) {
        const A = this;
        if (A.cols !== B.rows) throw new Error(`mul: incompatible ${A.rows}×${A.cols} * ${B.rows}×${B.cols}`);
        const C = new Matrix(A.rows, B.cols);
        for (let i = 0; i < A.rows; i++) {
            for (let j = 0; j < B.cols; j++) {
                let s = 0;
                for (let k = 0; k < A.cols; k++) {
                    s += A.get(i, k) * B.get(k, j);
                }
                C.set(i, j, s);
            }
        }
        return C;
    }

    /** Matrix-vector multiply: this * v, returns flat array. */
    mulVec(v) {
        if (this.cols !== v.length) throw new Error(`mulVec: incompatible ${this.rows}×${this.cols} * ${v.length}`);
        const out = new Array(this.rows);
        for (let i = 0; i < this.rows; i++) {
            let s = 0;
            for (let k = 0; k < this.cols; k++) {
                s += this.get(i, k) * v[k];
            }
            out[i] = s;
        }
        return out;
    }

    add(B) {
        if (this.rows !== B.rows || this.cols !== B.cols) throw new Error('add: size mismatch');
        const C = new Matrix(this.rows, this.cols);
        for (let i = 0; i < this.data.length; i++) C.data[i] = this.data[i] + B.data[i];
        return C;
    }

    sub(B) {
        if (this.rows !== B.rows || this.cols !== B.cols) throw new Error('sub: size mismatch');
        const C = new Matrix(this.rows, this.cols);
        for (let i = 0; i < this.data.length; i++) C.data[i] = this.data[i] - B.data[i];
        return C;
    }

    scale(s) {
        const C = new Matrix(this.rows, this.cols);
        for (let i = 0; i < this.data.length; i++) C.data[i] = this.data[i] * s;
        return C;
    }

    transpose() {
        const T = new Matrix(this.cols, this.rows);
        for (let i = 0; i < this.rows; i++)
            for (let j = 0; j < this.cols; j++)
                T.set(j, i, this.get(i, j));
        return T;
    }

    /** Create from nested array: [[a,b],[c,d]] */
    static from2D(arr) {
        const rows = arr.length;
        const cols = arr[0].length;
        const m = new Matrix(rows, cols);
        for (let i = 0; i < rows; i++)
            for (let j = 0; j < cols; j++)
                m.set(i, j, arr[i][j]);
        return m;
    }

    /** Create column vector from array */
    static fromCol(arr) {
        return new Matrix(arr.length, 1, new Float64Array(arr));
    }

    /** Pretty-print for debugging */
    toString(precision = 6) {
        const lines = [];
        for (let i = 0; i < this.rows; i++) {
            const row = [];
            for (let j = 0; j < this.cols; j++) {
                row.push(this.get(i, j).toFixed(precision).padStart(precision + 4));
            }
            lines.push('[' + row.join(', ') + ']');
        }
        return lines.join('\n');
    }
}


// =====================================================================================================================
// Convenience constructors
// =====================================================================================================================

/** Create a vector (column matrix) from values. */
export function vec(...values) {
    return new Matrix(values.length, 1, new Float64Array(values));
}

/** Identity matrix */
export function eye(n) {
    const m = new Matrix(n, n);
    for (let i = 0; i < n; i++) m.set(i, i, 1);
    return m;
}

/** Zero matrix */
export function zeros(rows, cols) {
    return new Matrix(rows, cols || rows);
}


// =====================================================================================================================
// Matrix inversion (Gauss-Jordan, for small n)
// =====================================================================================================================

export function inv(A) {
    const n = A.rows;
    if (n !== A.cols) throw new Error('inv: not square');

    // Augmented matrix [A | I]
    const aug = new Matrix(n, 2 * n);
    for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) aug.set(i, j, A.get(i, j));
        aug.set(i, n + i, 1);
    }

    for (let col = 0; col < n; col++) {
        // Partial pivot
        let maxVal = Math.abs(aug.get(col, col));
        let maxRow = col;
        for (let row = col + 1; row < n; row++) {
            const v = Math.abs(aug.get(row, col));
            if (v > maxVal) { maxVal = v; maxRow = row; }
        }
        if (maxVal < 1e-14) throw new Error('inv: singular matrix');

        // Swap rows
        if (maxRow !== col) {
            for (let j = 0; j < 2 * n; j++) {
                const tmp = aug.get(col, j);
                aug.set(col, j, aug.get(maxRow, j));
                aug.set(maxRow, j, tmp);
            }
        }

        // Scale pivot row
        const pivot = aug.get(col, col);
        for (let j = 0; j < 2 * n; j++) aug.set(col, j, aug.get(col, j) / pivot);

        // Eliminate column
        for (let row = 0; row < n; row++) {
            if (row === col) continue;
            const factor = aug.get(row, col);
            for (let j = 0; j < 2 * n; j++) {
                aug.set(row, j, aug.get(row, j) - factor * aug.get(col, j));
            }
        }
    }

    const result = new Matrix(n, n);
    for (let i = 0; i < n; i++)
        for (let j = 0; j < n; j++)
            result.set(i, j, aug.get(i, n + j));

    return result;
}


// =====================================================================================================================
// Complex number helpers (for eigenstructure assignment with complex poles)
// =====================================================================================================================

/** Complex number: [re, im] */
export function complexMul(a, b) {
    return [a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]];
}

export function complexAdd(a, b) {
    return [a[0] + b[0], a[1] + b[1]];
}

/** Invert a complex matrix (n×n). Each element is [re, im]. Returns same format. */
export function complexMatInv(mat, n) {
    // Augment [mat | I]
    const aug = [];
    for (let i = 0; i < n; i++) {
        aug[i] = new Array(2 * n);
        for (let j = 0; j < n; j++) aug[i][j] = [...mat[i][j]];
        for (let j = 0; j < n; j++) aug[i][n + j] = (i === j) ? [1, 0] : [0, 0];
    }

    for (let col = 0; col < n; col++) {
        // Find pivot (largest magnitude)
        let maxMag = 0, maxRow = col;
        for (let row = col; row < n; row++) {
            const mag = aug[row][col][0] ** 2 + aug[row][col][1] ** 2;
            if (mag > maxMag) { maxMag = mag; maxRow = row; }
        }
        if (maxMag < 1e-28) throw new Error('complexMatInv: singular');

        // Swap
        if (maxRow !== col) { const tmp = aug[col]; aug[col] = aug[maxRow]; aug[maxRow] = tmp; }

        // Scale pivot row: divide by pivot
        const piv = aug[col][col];
        const pivMag2 = piv[0] ** 2 + piv[1] ** 2;
        const pivInv = [piv[0] / pivMag2, -piv[1] / pivMag2];
        for (let j = 0; j < 2 * n; j++) aug[col][j] = complexMul(aug[col][j], pivInv);

        // Eliminate
        for (let row = 0; row < n; row++) {
            if (row === col) continue;
            const factor = aug[row][col];
            for (let j = 0; j < 2 * n; j++) {
                const prod = complexMul(factor, aug[col][j]);
                aug[row][j] = [aug[row][j][0] - prod[0], aug[row][j][1] - prod[1]];
            }
        }
    }

    const result = [];
    for (let i = 0; i < n; i++) {
        result[i] = [];
        for (let j = 0; j < n; j++) result[i][j] = aug[i][n + j];
    }
    return result;
}


// =====================================================================================================================
// Matrix exponential (Padé approximation, for c2d conversion)
// =====================================================================================================================

/**
 * Matrix exponential via scaling-and-squaring with Padé(6,6).
 * Good enough for the small matrices we use here.
 */
export function expm(A) {
    const n = A.rows;

    // Determine scaling factor
    let norm = 0;
    for (let i = 0; i < n; i++) {
        let rowSum = 0;
        for (let j = 0; j < n; j++) rowSum += Math.abs(A.get(i, j));
        if (rowSum > norm) norm = rowSum;
    }

    const s = Math.max(0, Math.ceil(Math.log2(norm)));
    const As = A.scale(Math.pow(2, -s));

    // Padé(6,6) coefficients
    const c = [1, 1/2, 1/9, 1/72, 1/1008, 1/30240, 1/1814400];

    // Compute powers of As
    const I = eye(n);
    const A2 = As.mul(As);
    const A4 = A2.mul(A2);
    const A6 = A4.mul(A2);

    // U = As * (c[1]*I + c[3]*A2 + c[5]*A4) -- actually use standard formulation
    // Numerator N = c[0]*I + c[1]*As + c[2]*A2 + c[3]*A3 + c[4]*A4 + c[5]*A5 + c[6]*A6
    // Denominator D = c[0]*I - c[1]*As + c[2]*A2 - c[3]*A3 + c[4]*A4 - c[5]*A5 + c[6]*A6

    const A3 = A2.mul(As);
    const A5 = A4.mul(As);

    const padeCoeffs = [1, 1/2, 5/44, 1/66, 1/792, 1/15840, 1/665280];

    let N = I.scale(padeCoeffs[0]);
    let D = I.scale(padeCoeffs[0]);
    const powers = [null, As, A2, A3, A4, A5, A6];
    for (let k = 1; k <= 6; k++) {
        const sign = (k % 2 === 0) ? 1 : -1;
        N = N.add(powers[k].scale(padeCoeffs[k]));
        D = D.add(powers[k].scale(sign * padeCoeffs[k]));
    }

    let result = inv(D).mul(N);

    // Undo scaling by repeated squaring
    for (let i = 0; i < s; i++) {
        result = result.mul(result);
    }

    return result;
}


// =====================================================================================================================
// Eigenvalue decomposition (QR algorithm for real matrices)
// For our use case we don't actually need full eig — we only use it for
// verifying pole placement. The eigenstructure assignment algorithm
// itself doesn't require computing eigenvalues.
// This is a basic implementation sufficient for small (≤7) matrices.
// =====================================================================================================================

/**
 * Compute eigenvalues of a real square matrix using QR iteration.
 * Returns array of {re, im} objects.
 */
export function eig(A) {
    const n = A.rows;
    let H = A.clone();

    // Reduce to upper Hessenberg form first
    H = _hessenberg(H);

    const maxIter = 200 * n;
    let iter = 0;

    const eigenvalues = [];
    let size = n;

    while (size > 0 && iter < maxIter) {
        if (size === 1) {
            eigenvalues.push({ re: H.get(0, 0), im: 0 });
            break;
        }

        // Check for convergence on sub-diagonal
        const sub = H.get(size - 1, size - 2);
        if (Math.abs(sub) < 1e-12 * (Math.abs(H.get(size - 2, size - 2)) + Math.abs(H.get(size - 1, size - 1)) + 1e-30)) {
            eigenvalues.push({ re: H.get(size - 1, size - 1), im: 0 });
            size--;
            // Deflate: work on top-left (size x size)
            const Hn = new Matrix(size, size);
            for (let i = 0; i < size; i++)
                for (let j = 0; j < size; j++)
                    Hn.set(i, j, H.get(i, j));
            H = Hn;
            continue;
        }

        // Check for 2x2 block
        if (size === 2 || (size > 2 && Math.abs(H.get(size - 2, size - 3)) < 1e-12)) {
            // Extract 2x2 block
            const a = H.get(size - 2, size - 2), b = H.get(size - 2, size - 1);
            const c = H.get(size - 1, size - 2), d = H.get(size - 1, size - 1);
            const trace = a + d;
            const det = a * d - b * c;
            const disc = trace * trace - 4 * det;

            if (disc >= 0) {
                const sqrtDisc = Math.sqrt(disc);
                eigenvalues.push({ re: (trace + sqrtDisc) / 2, im: 0 });
                eigenvalues.push({ re: (trace - sqrtDisc) / 2, im: 0 });
            } else {
                const sqrtDisc = Math.sqrt(-disc);
                eigenvalues.push({ re: trace / 2, im: sqrtDisc / 2 });
                eigenvalues.push({ re: trace / 2, im: -sqrtDisc / 2 });
            }
            size -= 2;
            if (size > 0) {
                const Hn = new Matrix(size, size);
                for (let i = 0; i < size; i++)
                    for (let j = 0; j < size; j++)
                        Hn.set(i, j, H.get(i, j));
                H = Hn;
            }
            continue;
        }

        // Wilkinson shift
        const a = H.get(size - 2, size - 2), b = H.get(size - 2, size - 1);
        const c = H.get(size - 1, size - 2), d = H.get(size - 1, size - 1);
        const trace = a + d;
        const det = a * d - b * c;
        const disc = trace * trace - 4 * det;
        let shift;
        if (disc >= 0) {
            const s1 = (trace + Math.sqrt(disc)) / 2;
            const s2 = (trace - Math.sqrt(disc)) / 2;
            shift = (Math.abs(s1 - d) < Math.abs(s2 - d)) ? s1 : s2;
        } else {
            shift = d; // Use d as real shift for complex eigenvalues
        }

        // Shifted QR step using Givens rotations
        const Hs = new Matrix(size, size);
        for (let i = 0; i < size; i++)
            for (let j = 0; j < size; j++)
                Hs.set(i, j, H.get(i, j));
        for (let i = 0; i < size; i++) Hs.set(i, i, Hs.get(i, i) - shift);

        // QR via Givens
        const cs = new Float64Array(size - 1);
        const sn = new Float64Array(size - 1);
        for (let i = 0; i < size - 1; i++) {
            const xi = Hs.get(i, i);
            const xip1 = Hs.get(i + 1, i);
            const r = Math.hypot(xi, xip1);
            if (r < 1e-30) { cs[i] = 1; sn[i] = 0; continue; }
            cs[i] = xi / r;
            sn[i] = xip1 / r;
            // Apply G to rows i, i+1
            for (let j = 0; j < size; j++) {
                const t1 = Hs.get(i, j);
                const t2 = Hs.get(i + 1, j);
                Hs.set(i, j, cs[i] * t1 + sn[i] * t2);
                Hs.set(i + 1, j, -sn[i] * t1 + cs[i] * t2);
            }
        }
        // R * Q + shift*I
        for (let i = 0; i < size - 1; i++) {
            for (let j = 0; j < size; j++) {
                const t1 = Hs.get(j, i);
                const t2 = Hs.get(j, i + 1);
                Hs.set(j, i, cs[i] * t1 + sn[i] * t2);
                Hs.set(j, i + 1, -sn[i] * t1 + cs[i] * t2);
            }
        }
        for (let i = 0; i < size; i++) Hs.set(i, i, Hs.get(i, i) + shift);

        // Copy back
        for (let i = 0; i < size; i++)
            for (let j = 0; j < size; j++)
                H.set(i, j, Hs.get(i, j));

        iter++;
    }

    return eigenvalues;
}


/** Reduce to upper Hessenberg form via Householder reflections. */
function _hessenberg(A) {
    const n = A.rows;
    const H = A.clone();

    for (let k = 0; k < n - 2; k++) {
        // Build Householder vector for column k, rows k+1..n-1
        const x = [];
        for (let i = k + 1; i < n; i++) x.push(H.get(i, k));

        const alpha = -Math.sign(x[0] || 1) * Math.hypot(...x);
        const v = x.slice();
        v[0] -= alpha;
        const vNorm = Math.hypot(...v);
        if (vNorm < 1e-30) continue;
        for (let i = 0; i < v.length; i++) v[i] /= vNorm;

        // H = H - 2*v*(v'*H) for rows k+1..n-1
        for (let j = 0; j < n; j++) {
            let dot = 0;
            for (let i = 0; i < v.length; i++) dot += v[i] * H.get(k + 1 + i, j);
            for (let i = 0; i < v.length; i++) H.set(k + 1 + i, j, H.get(k + 1 + i, j) - 2 * v[i] * dot);
        }
        // H = H - 2*(H*v)*v' for cols
        for (let i = 0; i < n; i++) {
            let dot = 0;
            for (let j = 0; j < v.length; j++) dot += H.get(i, k + 1 + j) * v[j];
            for (let j = 0; j < v.length; j++) H.set(i, k + 1 + j, H.get(i, k + 1 + j) - 2 * dot * v[j]);
        }
    }

    return H;
}
