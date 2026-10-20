# Synthetic equation recovery experiment

This report measures recovery of the program's own generated equations. It is not biological or clinical validation.

- Rows: 8000 (6400 train / 1600 holdout)
- Seed: 20261019
- Split: deterministic shuffled 80/20
- Inference estimator: ordinary least squares (prespecified)
- Comparator: ridge regression, alpha=0.01 (fixed before holdout evaluation)

## Holdout metrics

| Target | OLS RMSE | OLS MAE | OLS R² | Ridge RMSE | Ridge MAE | Ridge R² |
|---|---:|---:|---:|---:|---:|---:|
| d_ffa | 2.0069546e-05 | 1.5937989e-05 | 0.9999998 | 2.0079653e-05 | 1.5947719e-05 | 0.9999998 |
| d_tg | 2.0336696e-05 | 1.634857e-05 | 0.99999963 | 2.0328256e-05 | 1.6340465e-05 | 0.99999963 |
| d_ros | 1.9740036e-05 | 1.5984691e-05 | 0.99999977 | 1.973853e-05 | 1.598645e-05 | 0.99999977 |
| d_ecm | 1.9907333e-05 | 1.582065e-05 | 0.99998574 | 1.9912951e-05 | 1.5824205e-05 | 0.99998573 |

Inference latency is a local wall-clock measurement on the holdout batch, reported per 1,000 rows; it is a rough benchmark, not a deployment SLA.

- OLS: 17.7913 ms / 1,000 rows
- Ridge: 18.9837 ms / 1,000 rows

The generated held-out targets are the reference simulator outputs for this equation-recovery experiment; they are not external or biological ground truth.

## Sensitivity

For each input, the table reports the predicted absolute output shift for a 10% holdout input range shift. This is model sensitivity, not biological importance.

| Feature | Input shift | Mean absolute output change (dFFA / dTG / dROS / dECM) |
|---|---:|---|
| uptake | 0.00929394 | 0.00929401 / 3.86514e-08 / 9.28539e-08 / 5.61597e-08 |
| dnl | 0.00699692 | 0.00699681 / 2.60082e-08 / 2.01598e-08 / 2.60511e-08 |
| ffa | 0.147712 | 0.00886275 / 0.00886286 / 0.0132941 / 3.02246e-07 |
| tg | 0.147931 | 1.0078e-07 / 0.00739652 / 2.50382e-08 / 5.31572e-08 |
| beta_oxidation | 0.00511124 | 0.00511118 / 1.67872e-07 / 1.81549e-07 / 1.88009e-07 |
| ros | 0.149257 | 3.05828e-07 / 1.82562e-07 / 0.00522415 / 2.48015e-07 |
| ecm | 0.0988417 | 7.86331e-07 / 9.25648e-07 / 3.06753e-07 / 1.18289e-07 |
| hsc_signal | 0.0847111 | 3.39668e-07 / 3.2911e-07 / 4.7569e-07 / 0.00211749 |
| mmp_signal | 0.112131 | 7.54394e-07 / 8.91567e-07 / 3.52745e-07 / 0.000897018 |

## Numerical convergence and stability

ODE uses forward Euler and is compared at increasing step counts over the same arbitrary duration. PDE time step is automatically bounded from the explicit diffusion/advection stability limit; grid profiles are compared at common spatial locations.

### ODE step refinement

| Steps | Maximum final-state difference from 1,200 steps |
|---:|---:|
| 300 | 0.00082 |
| 600 | 0.00026 |
| 1200 | 0 |

### Oxygen PDE grid refinement

| Cells | Max profile difference from 81-cell grid | Non-negative and finite |
|---:|---:|---|
| 21 | 0.01 | True |
| 41 | 0 | True |
| 81 | 0 | True |

### Initial condition sweep

| Initial state scale | Final mean FFA | TG | ROS | ECM |
|---:|---:|---:|---:|---:|
| 0.5 | 0.79044 | 0.63756 | 1.09218 | 0.46826 |
| 1.0 | 0.8119 | 0.71456 | 1.21604 | 0.52704 |
| 1.5 | 0.83516 | 0.79484 | 1.34612 | 0.574 |

## Assumption-range uncertainty propagation

Deterministic-seed Monte Carlo propagation of uniform ±10% default-rate and ±5% initial-state ranges through the toy ODE.

Sensitivity to invented input ranges only; not fitted parameter uncertainty, a confidence/prediction interval, patient uncertainty, or clinical risk.

| Final mean state | 5th percentile | Median | 95th percentile |
|---|---:|---:|---:|
| ffa | 0.738252 | 0.81259 | 0.889373 |
| triglyceride | 0.665811 | 0.71516 | 0.768264 |
| ros | 1.13204 | 1.21627 | 1.30992 |
| ecm | 0.521475 | 0.52631 | 0.532529 |

## Limitations

- The generated targets use the same illustrative equations that the model fits.
- Numeric coefficients are toy values; literature only motivates qualitative mechanisms.
- No patient data, treatment effects, diagnosis, prognosis, or clinical accuracy are represented.
- Residual visualization: `reports/synthetic_residuals.svg`.
