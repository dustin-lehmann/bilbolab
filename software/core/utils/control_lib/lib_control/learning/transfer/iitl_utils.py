"""IITL helpers: the source learning-set pair type, learning-set generation,
Q-filter construction, and a thin lifted-matrix alias.

Lives in the core control library (rather than the research tree) so the
on-robot IITL experiment and the shared sim runners can import it without a
``research`` dependency. Kept deliberately small so example scripts remain
explicit about the trial-domain mechanics.
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Tuple

import numpy as np

from core.utils.control_lib.lib_control.learning.filters import (
    fir_lowpass,
    fir_lowpass_zero_padded,
)
from core.utils.control_lib.lib_control.learning.lifted import (
    vector_to_lifted_matrix as vec2liftedMatrix,
)
from core.utils.data import generate_random_input, generate_time_vector_by_length


# ---------------------------------------------------------------------------
# Thin alias
# ---------------------------------------------------------------------------

def lifted(u: np.ndarray) -> np.ndarray:
    r"""Alias for :func:`vec2liftedMatrix`, i.e.\ :math:`\mathcal{M}(\mathbf{u})`."""
    return vec2liftedMatrix(u)


# === TRAJECTORIES ===========================================================
@dataclasses.dataclass
class TrajectoryPair:
    input: np.ndarray
    output: np.ndarray
    Ts: float = 0.01

    @property
    def time_vector(self) -> np.ndarray:
        return generate_time_vector_by_length(num_samples=len(self.input),
                                              dt=self.Ts, )


# ---------------------------------------------------------------------------
# Learning-set generation
# ---------------------------------------------------------------------------

def generate_learning_trajectories(
        simulate_fn: Callable[[np.ndarray], np.ndarray],
        t_vec: np.ndarray,
        N_L: int,
        f_range: Tuple[float, float],
        sigma_range: Tuple[float, float],
        rng: np.random.Generator | None = None,
) -> Tuple[list[np.ndarray], list[np.ndarray]]:
    r"""Build a source learning set :math:`\mathfrak{L}` *ahead of the trial loop*.

    Each input is a low-pass filtered random sequence drawn with cut-off
    :math:`f_\mathrm{cut} \sim \mathcal{U}(f_\mathrm{min}, f_\mathrm{max})` and
    amplitude :math:`\sigma_I \sim \mathcal{U}(\sigma_\mathrm{min}, \sigma_\mathrm{max})`.
    The corresponding output is obtained by one call to ``simulate_fn``.

    Parameters
    ----------
    simulate_fn : callable ``u -> y`` simulating the source system over ``t_vec``
                  and returning a 1-D output trajectory of length ``len(t_vec)``.
    t_vec       : time grid used for input generation (length ``N``).
    N_L         : number of learning trajectories to generate.
    f_range     : (min, max) cut-off in Hz passed to
                  :func:`core.utils.data.generate_random_input`.
    sigma_range : (min, max) input amplitude.
    rng         : optional numpy Generator for reproducibility.

    Returns
    -------
    (learning_inputs, learning_outputs) : lists of length ``N_L`` with 1-D arrays.
    """
    if rng is None:
        rng = np.random.default_rng()

    inputs: list[np.ndarray] = []
    outputs: list[np.ndarray] = []
    for _ in range(N_L):
        f_cutoff = float(rng.uniform(*f_range))
        sigma_I = float(rng.uniform(*sigma_range))
        u = generate_random_input(t_vec, f_cutoff=f_cutoff, sigma_I=sigma_I, rng=rng)
        y = simulate_fn(u)
        inputs.append(u)
        outputs.append(y)
    return inputs, outputs


# ---------------------------------------------------------------------------
# Q-filter construction
# ---------------------------------------------------------------------------

def build_qfilter_fir(N: int,
                      fc: float,
                      L: int,
                      window: str = "hann",
                      kind: str = "TtT") -> np.ndarray:
    r"""FIR zero-phase Q-filter (Eq.~iitl_q_fir, :math:`\mathbf{Q} = \mathbf{H}^\top\mathbf{H}`).

    Parameters
    ----------
    N      : horizon length.
    fc     : cut-off in cycles per sample (0 < fc < 0.5).
    L      : odd FIR tap count.
    window : ``"hann" | "hamming" | "blackman"`` (passed to scipy.signal.firwin).
    kind   : ``"TtT"`` (SPD, :math:`|H|^2` response, matches Eq.~iitl_q_fir) or
             ``"zero_padded"`` (single-sided :math:`|H|` response).
    """
    if L % 2 != 1:
        raise ValueError(f"L must be odd (so L-1 is even); got {L}")
    order = L - 1
    if kind == "TtT":
        return fir_lowpass(N, cutoff_cps=fc, order=order, window=window)
    if kind == "zero_padded":
        return fir_lowpass_zero_padded(N, cutoff_cps=fc, order=order, window=window)
    raise ValueError(f"Unknown kind: {kind!r}")


def build_qfilter_norm_optimal(P_j: np.ndarray,
                               W_e: np.ndarray,
                               W_dt: np.ndarray,
                               W_t: np.ndarray) -> np.ndarray:
    r"""Norm-optimal Q-filter (Eq.~iitl_q_noilc_Q).

    .. math::
        \mathbf{Q} = (\mathbf{P}_j^\top \mathbf{W}_e \mathbf{P}_j
                      + \mathbf{W}_{\Delta t} + \mathbf{W}_t)^{-1}
                     (\mathbf{P}_j^\top \mathbf{W}_e \mathbf{P}_j + \mathbf{W}_{\Delta t}).

    ``W_e`` and ``W_dt`` must be positive definite, ``W_t`` positive semidefinite.
    The unfiltered case :math:`\mathbf{Q} = \mathbf{I}_N` is recovered for
    ``W_t = 0``.
    """
    PtWeP = P_j.T @ W_e @ P_j
    A = PtWeP + W_dt + W_t
    B = PtWeP + W_dt
    return np.linalg.solve(A, B)


__all__ = [
    "lifted",
    "TrajectoryPair",
    "generate_learning_trajectories",
    "build_qfilter_fir",
    "build_qfilter_norm_optimal",
]
