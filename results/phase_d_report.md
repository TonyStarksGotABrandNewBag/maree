### Headline finding — random vs temporal hold-out, all 7 models

AUC degrades modestly under temporal evaluation; accuracy at the 0.5 threshold collapses. The asymmetry is the calibration-vs-ranking distinction (Pendlebury et al., 2019): models still rank samples correctly, but the decision threshold no longer separates classes after distribution shift.

| Model | Random hold-out AUC | Temporal hold-out AUC | Δ AUC | Random hold-out ACC | Temporal hold-out ACC | Δ ACC |
|---|---|---|---|---|---|---|
| logistic_regression | 0.9488 | 0.9059 | −0.0430 | 0.8791 | 0.8266 | −0.0525 |
| decision_tree | 0.9917 | 0.8467 | −0.1450 | 0.9685 | 0.6524 | −0.3161 |
| random_forest | 0.9975 | 0.9602 | −0.0372 | 0.9833 | 0.6557 | −0.3275 |
| torch_mlp | 0.9944 | 0.9555 | −0.0390 | 0.9720 | 0.8773 | −0.0947 |
| xgboost | 0.9984 | 0.9352 | −0.0631 | 0.9886 | 0.7564 | −0.2321 |
| lightgbm | 0.9984 | 0.9024 | −0.0960 | 0.9885 | 0.7533 | −0.2352 |
| catboost | 0.9979 | 0.9292 | −0.0687 | 0.9867 | 0.7653 | −0.2214 |

### Cross-validation AUC under both protocols

CV is computed within the *training portion* of each split, so both protocols see internally i.i.d. data here — the temporal-vs-random asymmetry only appears when testing on post-cutoff data the model has never seen (the hold-out table above).

| Model | Random CV AUC | Temporal CV AUC |
|---|---|---|
| logistic_regression | 0.9470 ± 0.0028 | 0.9557 ± 0.0027 |
| decision_tree | 0.9910 ± 0.0015 | 0.9942 ± 0.0007 |
| random_forest | 0.9975 ± 0.0006 | 0.9983 ± 0.0005 |
| torch_mlp | 0.9932 ± 0.0010 | 0.9960 ± 0.0007 |
| xgboost | 0.9983 ± 0.0005 | 0.9987 ± 0.0004 |
| lightgbm | 0.9984 ± 0.0005 | 0.9988 ± 0.0004 |
| catboost | 0.9978 ± 0.0006 | 0.9985 ± 0.0005 |

### Full CV statistics (mean ± std across 10 folds)

| Model | Protocol | AUC | Accuracy | Mean fit (s) |
|---|---|---|---|---|
| catboost | random | 0.9978 ± 0.0006 | 0.9865 ± 0.0022 | 1.3 |
| catboost | temporal | 0.9985 ± 0.0005 | 0.9888 ± 0.0017 | 1.3 |
| decision_tree | random | 0.9910 ± 0.0015 | 0.9679 ± 0.0035 | 0.1 |
| decision_tree | temporal | 0.9942 ± 0.0007 | 0.9776 ± 0.0020 | 0.1 |
| lightgbm | random | 0.9984 ± 0.0005 | 0.9888 ± 0.0015 | 1.3 |
| lightgbm | temporal | 0.9988 ± 0.0004 | 0.9907 ± 0.0012 | 1.3 |
| logistic_regression | random | 0.9470 ± 0.0028 | 0.8777 ± 0.0049 | 0.2 |
| logistic_regression | temporal | 0.9557 ± 0.0027 | 0.8913 ± 0.0052 | 0.1 |
| maree_lightgbm | temporal | 0.9930 ± 0.0016 | 0.9252 ± 0.0094 | 18.8 |
| maree_random_forest | temporal | 0.9911 ± 0.0022 | 0.9318 ± 0.0065 | 16.4 |
| random_forest | random | 0.9975 ± 0.0006 | 0.9849 ± 0.0025 | 1.3 |
| random_forest | temporal | 0.9983 ± 0.0005 | 0.9876 ± 0.0013 | 1.2 |
| torch_mlp | random | 0.9932 ± 0.0010 | 0.9663 ± 0.0021 | 1.6 |
| torch_mlp | temporal | 0.9960 ± 0.0007 | 0.9769 ± 0.0022 | 1.6 |
| xgboost | random | 0.9983 ± 0.0005 | 0.9888 ± 0.0014 | 0.4 |
| xgboost | temporal | 0.9987 ± 0.0004 | 0.9906 ± 0.0010 | 0.3 |