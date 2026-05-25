"""Transfer error metrics.

Implements the error metrics defined in the dissertation section
*Transfer Error Metrics* (``sec:transfer-fund-error-metrics``) on a single
source trajectory pair :math:`(\\mathbf{u}^{(\\alpha)}, \\mathbf{y}^{(\\alpha)})`
with :math:`\\mathbf{y}^{(\\alpha)} = \\mathcal{F}^{(\\alpha)}(\\mathbf{u}^{(\\alpha)})`
and an estimated input transfer map
:math:`\\hat{\\mathcal{T}}: \\mathbb{R}^N \\to \\mathbb{R}^N`.

Three quantities are exposed:

* the **deployment error** vector
  :math:`\\mathbf{e}_d = \\mathbf{y}^{(\\alpha)} - \\mathcal{F}^{(\\beta)}(\\hat{\\mathcal{T}}\\mathbf{u}^{(\\alpha)})`
  (eq. ``transfer_deployment_error``);
* the **output-magnitude-normalised** scalar
  :math:`\\varepsilon_\\mathrm{out} = \\|\\mathbf{e}_d\\|_2 / \\|\\mathbf{y}^{(\\alpha)}\\|_2`
  (eq. ``transfer_norm_output``);
* the **identity-normalised** scalar
  :math:`\\varepsilon_\\mathrm{id}  = \\|\\mathbf{e}_d\\|_2 /
  \\|\\mathbf{y}^{(\\alpha)} - \\mathcal{F}^{(\\beta)}(\\mathbf{u}^{(\\alpha)})\\|_2`
  (eq. ``transfer_norm_id``);

plus a polarity classifier (defn. ``transfer_polarity``) that labels a transfer
as positive / neutral / negative according to the unit-threshold
:math:`\\varepsilon_\\mathrm{id} \\lessgtr 1`.

Edge cases follow the convention in remark ``transfer_metric_edge_cases``:
when a denominator falls at or below the supplied tolerance the metric is
returned as ``np.nan`` so that aggregates can filter such trajectories out
without special-casing in the caller.
"""
import numpy as np

ArrayLike = np.ndarray


# ======================================================================================================================
def deployment_error(
        y_source: ArrayLike,
        y_target_hat: ArrayLike,
) -> np.ndarray:
    r"""Deployment error vector :math:`\mathbf{e}_d = \mathbf{y}^{(\alpha)} - \mathbf{y}^{\hat\beta}`.

    Parameters
    ----------
    y_source : ndarray
        Source-side reference output :math:`\mathbf{y}^{(\alpha)}` produced by
        the source agent on the source input :math:`\mathbf{u}^{(\alpha)}`.
    y_target_hat : ndarray
        Target-side output
        :math:`\mathcal{F}^{(\beta)}(\hat{\mathcal{T}}\mathbf{u}^{(\alpha)})`,
        obtained by feeding the transferred input through the target agent.
    """
    return np.asarray(y_source) - np.asarray(y_target_hat)


# ======================================================================================================================
def deployment_error_norm(
        y_source: ArrayLike,
        y_target_hat: ArrayLike,
) -> float:
    r"""Euclidean norm of the deployment error, :math:`\lVert\mathbf{e}_d\rVert_2`.

    Dimensional and trajectory-magnitude-dependent; for evaluation prefer one
    of the two normalised variants below (cf. the interpretation note
    `transfer_deployment_error_interp` in the dissertation).
    """
    return float(np.linalg.norm(deployment_error(y_source, y_target_hat)))


# ======================================================================================================================
def output_normalized_error(
        y_source: ArrayLike,
        y_target_hat: ArrayLike,
        tol: float = 0.0,
) -> float:
    r"""Output-magnitude-normalised deployment error.

    .. math::
       \varepsilon_\mathrm{out}
       \;=\;
       \frac{\lVert \mathbf{y}^{(\alpha)} - \mathcal{F}^{(\beta)}(\hat{\mathcal{T}}\mathbf{u}^{(\alpha)}) \rVert_2}
            {\lVert \mathbf{y}^{(\alpha)} \rVert_2}

    Reports the residual as a fraction of the source-output magnitude.

    Parameters
    ----------
    y_source : ndarray
        Source output :math:`\mathbf{y}^{(\alpha)}`.
    y_target_hat : ndarray
        Target output
        :math:`\mathcal{F}^{(\beta)}(\hat{\mathcal{T}}\mathbf{u}^{(\alpha)})`.
    tol : float, optional
        Trajectories with :math:`\lVert\mathbf{y}^{(\alpha)}\rVert_2 \le tol` are
        treated as at-rest and the metric is returned as ``np.nan`` so that
        the caller can exclude them from aggregates.

    Returns
    -------
    float
        :math:`\varepsilon_\mathrm{out}` if the denominator exceeds ``tol``,
        ``np.nan`` otherwise.
    """
    y_source = np.asarray(y_source)
    den = float(np.linalg.norm(y_source))
    if den <= tol:
        return float("nan")
    num = float(np.linalg.norm(y_source - np.asarray(y_target_hat)))
    return num / den


# ======================================================================================================================
def identity_normalized_error(
        y_source: ArrayLike,
        y_target_hat: ArrayLike,
        y_target_identity: ArrayLike,
        tol: float = 0.0,
) -> float:
    r"""Identity-normalised deployment error.

    .. math::
       \varepsilon_\mathrm{id}
       \;=\;
       \frac{\lVert \mathbf{y}^{(\alpha)} - \mathcal{F}^{(\beta)}(\hat{\mathcal{T}}\mathbf{u}^{(\alpha)}) \rVert_2}
            {\lVert \mathbf{y}^{(\alpha)} - \mathcal{F}^{(\beta)}(\mathbf{u}^{(\alpha)}) \rVert_2}

    The denominator is the deployment error of the do-nothing identity
    transfer :math:`\hat{\mathcal{T}} = \mathrm{id}`: the residual obtained by
    feeding the raw source input directly to the target without correction.
    The unit threshold separates positive transfer
    (:math:`\varepsilon_\mathrm{id} < 1`) from negative transfer.

    Parameters
    ----------
    y_source : ndarray
        Source output :math:`\mathbf{y}^{(\alpha)}`.
    y_target_hat : ndarray
        Target output for the transferred input,
        :math:`\mathcal{F}^{(\beta)}(\hat{\mathcal{T}}\mathbf{u}^{(\alpha)})`.
    y_target_identity : ndarray
        Target output for the **raw** source input,
        :math:`\mathcal{F}^{(\beta)}(\mathbf{u}^{(\alpha)})` -- the
        identity-transfer baseline.
    tol : float, optional
        Agent-distinguishability floor.  Trajectories on which source and
        target nearly agree
        (:math:`\lVert\mathbf{y}^{(\alpha)} - \mathcal{F}^{(\beta)}(\mathbf{u}^{(\alpha)})\rVert_2 \le tol`)
        return ``np.nan``; they carry no information about transfer fidelity
        and are conventionally excluded from aggregates.

    Returns
    -------
    float
        :math:`\varepsilon_\mathrm{id}` if the denominator exceeds ``tol``,
        ``np.nan`` otherwise.
    """
    y_source = np.asarray(y_source)
    y_target_identity = np.asarray(y_target_identity)
    den = float(np.linalg.norm(y_source - y_target_identity))
    if den <= tol:
        return float("nan")
    num = float(np.linalg.norm(y_source - np.asarray(y_target_hat)))
    return num / den


# ======================================================================================================================
def transfer_polarity(eps_id: float, neutral_tol: float = 0.0) -> str:
    r"""Classify a transfer as ``"positive"``, ``"neutral"``, or ``"negative"``.

    The classification follows definition ``transfer_polarity``: a transfer is
    *positive* when its deployment error is strictly smaller than that of the
    identity transfer on the same trajectory, *negative* when it is strictly
    larger, and *neutral* when they agree.

    Parameters
    ----------
    eps_id : float
        Identity-normalised error :math:`\varepsilon_\mathrm{id}` from
        :func:`identity_normalized_error`.
    neutral_tol : float, optional
        Half-width of the neutral band around 1.  ``"neutral"`` is reported
        for ``eps_id`` in ``[1 - neutral_tol, 1 + neutral_tol]``.  Defaults to
        ``0.0`` (strict equality).

    Returns
    -------
    str
        One of ``"positive"``, ``"neutral"``, ``"negative"``, or
        ``"undefined"`` if ``eps_id`` is not finite (e.g. below the
        agent-distinguishability floor).
    """
    if not np.isfinite(eps_id):
        return "undefined"
    if eps_id < 1.0 - neutral_tol:
        return "positive"
    if eps_id > 1.0 + neutral_tol:
        return "negative"
    return "neutral"
