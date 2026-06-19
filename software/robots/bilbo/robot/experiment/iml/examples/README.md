# IML experiment examples

`iml_example.yaml` is a fully-commented template for an IML (Iterative Model
Learning) model-identification experiment.

## Running it

From the BILBO CLI:

```
experiment iml -f robot/experiment/iml/examples/iml_example.yaml
```

or programmatically on the host:

```python
handler.run_iml_from_file("robot/experiment/iml/examples/iml_example.yaml")
# or skip the yaml and pass the .bitrj files directly:
handler.run_iml_from_files(["input_1.bitrj", "input_2.bitrj"],
                           initial_conditions=(0.0, 0.0, 0.0), method="rls")
```

## Learning set

The `learning_set` entries (`input_1.bitrj`, `input_2.bitrj`, `input_3.bitrj`)
are **placeholders** — drop your own input trajectory files next to this YAML
(or anywhere on the host's `reference_trajectories` path) and list them here.
Each `.bitrj` contributes one single-channel input; all must share the same
horizon `N` (a multiple of 10). Generate them with the input-trajectory tools
(e.g. the GUI input viewer / `generate_random_input_trajectory`).

## After the run

The robot saves the best identified model as a `.bmvec` and the host downloads
it alongside the results JSON. Generate a report and optionally fit physical
parameters:

```python
import numpy as np
from robots.bilbo.robot.experiment.iml import generate_iml_report, fit_bilbo_parameters

generate_iml_report("iml_iml_example_<timestamp>.json")

# K is REQUIRED: pass the robot's actual balancing gain (the data was recorded
# under it). Shape (1, 4) for the 2D state [s, v, theta, theta_dot].
K = np.array([[0.0, -0.8, -2.5, -0.3]])  # <- use the real gain
fit = fit_bilbo_parameters("iml_iml_example_<timestamp>.json", K,
                           params_to_fit=("l", "m_b", "I_y"))
print(fit.params, fit.std)
```
