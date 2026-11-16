"""Fixed design constants from PREREGISTRATION.md (sections 2-5). Do not edit."""

WINDOW_S = 60                       # 2.1 analysis window
DURATION_S = 1800                   # 2.1 run length
SEEDS = (1, 2, 3)                   # 2.1
SCENARIOS = ("S1", "S2", "S3", "S4")  # 2.2

# 3. consumers
T1_FRESHNESS_S = 60                 # data age at arrival <= 60 s
T1_FLOOR_BPS = 10_000               # relative-error denominator floor (10 kbps)
T2_HISTORY_S = 60                   # past 60 s as features
T2_HORIZON_S = 10                   # predict mean of the next 10 s
T2_TRAIN_FRAC = 0.70                # time split, first 70 % train
T2_RANDOM_STATE = 0

# 4. policies
B2_P = (1, 5, 10, 30, 60)
B2_K = (1, 5, 10)
SUMMARIES = {                       # name -> statistics carried in one report
    "mean": ("mean",),
    "mean+max": ("mean", "max"),
    "mean+max+var": ("mean", "max", "var"),
}
B3_LEVELS = (1, 2, 5, 10, 30, 60)
B3_THETA_HIGH = (0.2, 0.5, 1.0)
B3_THETA_LOW = (0.05, 0.1, 0.2)
B3_SUMMARY = "mean+max"

# 5. criteria
EPSILONS = (0.01, 0.02, 0.05, 0.10, 0.20)
EPS_MAIN = 0.05
H1_MIN_REDUCTION = 0.50
H2_MIN_REGRET = 0.30
B3_MAX_REGRET = 0.10
H3_MIN_R2 = 0.95
H3_UE_COUNTS = (6, 26, 46)


def b3_theta_pairs():
    return [(hi, lo) for hi in B3_THETA_HIGH for lo in B3_THETA_LOW if lo < hi]
