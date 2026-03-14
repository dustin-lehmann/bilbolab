"use strict";

const _axisIdentifiers = {
    1: 1, 'x': 1, 'X': 1, 'i': 1,
    2: 2, 'y': 2, 'Y': 2, 'j': 2,
    3: 3, 'z': 3, 'Z': 3, 'k': 3,
};

class Quaternion {
    constructor(...args) {
        // TODO: Quaternion(otherQuaternion), Quaternion(babylonQuaternion), error checking
        if (args.length === 1) {
            if (args[0] instanceof Quaternion)
                this.array = args[0].array.slice();
            else
                this.array = args[0];
        }
        else
            this.array = args;

        this.normalizeInPlace();
    }

    static fromAngleAxis(angle, axis) {
        if (axis === 'x') {
            axis = [1, 0, 0];
        } else if (axis === 'y') {
            axis = [0, 1, 0];
        } else if (axis === 'z') {
            axis = [0, 0, 1];
        }
        console.assert(axis.length === 3, axis);
        axis = normalizeVec(axis);

        return new Quaternion(Math.cos(angle/2), axis[0]*Math.sin(angle/2), axis[1]*Math.sin(angle/2), axis[2]*Math.sin(angle/2));
    }

    static fromEulerAngles(angles, convention, intrinsic) {
        console.assert(convention.length === 3, convention);
        if (intrinsic) {
            let quat = Quaternion.fromAngleAxis(angles[0], convention[0]);
            quat = quat.multiply(Quaternion.fromAngleAxis(angles[1], convention[1]));
            quat = quat.multiply(Quaternion.fromAngleAxis(angles[2], convention[2]));
            return quat;
        } else {
            let quat = Quaternion.fromAngleAxis(angles[0], convention[0]);
            quat = Quaternion.fromAngleAxis(angles[1], convention[1]).multiply(quat);
            quat = Quaternion.fromAngleAxis(angles[2], convention[2]).multiply(quat);
            return quat;
        }
    }

    static from2Vectors(v1, v2) {
        // q.rotate(v1) == v2
        const n1 = vecNorm(v1);
        const n2 = vecNorm(v2);
        const angle = Math.acos((v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2])/n1/n2);
        const axis = angle === 0.0 ? new BABYLON.Vector3(1,0,0) : BABYLON.Vector3.Cross(new BABYLON.Vector3(...v1), new BABYLON.Vector3(...v2));
        // console.log(n1, n2, axis, angle, (n1[0]*n2[0] + n1[1]*n2[1] + n1[2]*n2[2])/n1/n2);
        return Quaternion.fromAngleAxis(angle, [axis.x, axis.y, axis.z]);
    }


    static fromRotationMatrix(matrix){
        let m00 = matrix[0][0],
            m01 = matrix[0][1],
            m02 = matrix[0][2];
        let m10 = matrix[1][0],
            m11 = matrix[1][1],
            m12 = matrix[1][2];
        let m20 = matrix[2][0],
            m21 = matrix[2][1],
            m22 = matrix[2][2];

        let t = m00 + m11 + m22;
        let w = 0, x=0, y=0, z=0;
        if (t > 0) {
            let s = 0.5 / Math.sqrt(t + 1.0);
            x = (m21 - m12) * s;
            y = (m02 - m20) * s;
            z = (m10 - m01) * s;
            w = 0.25 / s;
        } else if (m00 > m11 && m00 > m22) {
            let s = 2.0 * Math.sqrt(1.0 + m00 - m11 - m22);
            x = 0.25 * s;
            y = (m01 + m10) / s;
            z = (m02 + m20) / s;
            w = (m21 - m12) / s;
        } else if (m11 > m22) {
            let s = 2.0 * Math.sqrt(1.0 + m11 - m00 - m22);
            x = (m01 + m10) / s;
            y = 0.25 * s;
            z = (m12 + m21) / s;
            w = (m02 - m20) / s;
        } else {
            let s = 2.0 * Math.sqrt(1.0 + m22 - m00 - m11);
            x = (m02 + m20) / s;
            y = (m12 + m21) / s;
            z = 0.25 * s;
            w = (m10 - m01) / s;
        }
        return new Quaternion([w,x,y,z])
    }

    get w() {return this.array[0]};
    get x() {return this.array[1]};
    get y() {return this.array[2]};
    get z() {return this.array[3]};
    set w(val) {this.array[0] = val};
    set x(val) {this.array[1] = val};
    set y(val) {this.array[2] = val};
    set z(val) {this.array[3] = val};

    angle() {
        return 2*Math.acos(this.w);
    }

    conj() {
        return new Quaternion(this.array[0], -this.array[1], -this.array[2], -this.array[3]);
    }

    norm() {
        return vecNorm(this.array);
    }

    normalizeInPlace() {
        const norm = this.norm();
        this.array = this.array.map(x => x/norm);
    }

    normalized() {
        const norm = this.norm();
        return new Quaternion(this.array.map(x => x/norm));
    }

    multiply(other) {
        return new Quaternion(
            this.w * other.w - this.x * other.x - this.y * other.y - this.z * other.z,
            this.w * other.x + this.x * other.w + this.y * other.z - this.z * other.y,
            this.w * other.y - this.x * other.z + this.y * other.w + this.z * other.x,
            this.w * other.z + this.x * other.y - this.y * other.x + this.z * other.w
        );
    }


    eulerAngles(convention, intrinsic) {
        console.assert(convention.length === 3, convention);
        console.assert(intrinsic === true || intrinsic === false, intrinsic);

        if (intrinsic)
            convention = convention.split('').reverse().join('');

        const a = _axisIdentifiers[convention[0]];
        const b = _axisIdentifiers[convention[1]];
        const c = _axisIdentifiers[convention[2]];
        let d = 'invalid';
        if (a === c) {
            if (a !== 1 && b !== 1)
                d = 1;
            else if (a !== 2 && b !== 2)
                d = 2;
            else
                d = 3;
        }

        console.assert(b !== a && b !== c, [a, b, c]);

        // if np.any(np.isnan(self._e)):
        //     return np.nan * np.zeros(shape=(3,))

        // sign factor depending on the axis order
        let s;
        if (b === (a % 3) + 1)  // cyclic order
            s = 1;
        else  // anti-cyclic order
            s = -1;

        let angle1, angle2, angle3;

        if (a === c) {  // proper Euler angles
            angle1 = Math.atan2(this.array[a] * this.array[b] - s * this.array[d] * this.array[0], this.array[b] * this.array[0] + s * this.array[a] * this.array[d]);
            angle2 = Math.acos(clip(this.array[0] ** 2 + this.array[a] ** 2 - this.array[b] ** 2 - this.array[d] ** 2, -1, 1));
            angle3 = Math.atan2(this.array[a] * this.array[b] + s * this.array[d] * this.array[0], this.array[b] * this.array[0] - s * this.array[a] * this.array[d]);

        } else {  // Tait-Bryan
            angle1 = Math.atan2(2 * (this.array[a] * this.array[0] + s * this.array[b] * this.array[c]),
                this.array[0] ** 2 - this.array[a] ** 2 - this.array[b] ** 2 + this.array[c] ** 2);
            angle2 = Math.asin(clip(2 * (this.array[b] * this.array[0] - s * this.array[a] * this.array[c]), -1, 1));
            angle3 = Math.atan2(2 * (s * this.array[a] * this.array[b] + this.array[c] * this.array[0]),
                this.array[0] ** 2 + this.array[a] ** 2 - this.array[b] ** 2 - this.array[c] ** 2);
        }

        if (intrinsic)
            return [angle3, angle2, angle1];
        else
            return [angle1, angle2, angle3];
    }

    rotate(v) {
        console.assert(v.length === 3, v);
        return [
            (1 - 2*this.array[2]*this.array[2] - 2*this.array[3]*this.array[3])*v[0] + 2*v[1]*(this.array[2]*this.array[1] - this.array[0]*this.array[3]) + 2*v[2]*(this.array[0]*this.array[2] + this.array[3]*this.array[1]),
            2*v[0]*(this.array[0]*this.array[3] + this.array[2]*this.array[1]) + v[1]*(1 - 2*this.array[1]*this.array[1] - 2*this.array[3]*this.array[3]) + 2*v[2]*(this.array[2]*this.array[3] - this.array[1]*this.array[0]),
            2*v[0]*(this.array[3]*this.array[1] - this.array[0]*this.array[2]) + 2*v[1]*(this.array[0]*this.array[1] + this.array[3]*this.array[2]) + v[2]*(1 - 2*this.array[1]*this.array[1] - 2*this.array[2]*this.array[2])
        ];
    }

    project(axis) {
        console.assert(axis.length === 3, axis);
        axis = normalizeVec(axis);
        const phi = wrapToPi(2 * Math.atan2(axis[0] * this.x + axis[1] * this.y + axis[2] * this.z, this.w));
        const qProj = Quaternion.fromAngleAxis(phi, axis);
        const qRes = qProj.conj().multiply(this);
        return [phi, qRes.angle(), qProj, qRes]
    }

    babylon() {
        // return new BABYLON.Quaternion(this.array[1], this.array[2], this.array[3], this.array[0]).normalize();
        return new BABYLON.Quaternion(this.array[1], this.array[3], -this.array[2], this.array[0]).normalize();
    }
}

function clip(value, lower, upper) {
    return Math.max(lower, Math.min(value, upper));
}

function vecNorm(vec) {
    const sqSum = vec.reduce((pv, cv) => pv+cv*cv, 0);
    return Math.sqrt(sqSum);
}

function normalizeVec(vec) {
    const norm = vecNorm(vec);
    return vec.map(x => x/norm);
}

function rad2deg(val) {
    return val*180.0/Math.PI;
}

function deg2rad(val) {
    return val*Math.PI/180.0;
}

function wrapToPi(val) {
    // return (val + Math.PI) % (2 * Math.PI) - Math.PI;
    return (((val + Math.PI) % (2 * Math.PI)) + (2 * Math.PI)) % (2 * Math.PI) - Math.PI;
}
