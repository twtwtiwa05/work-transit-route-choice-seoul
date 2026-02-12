"""
전체 Phase 2 데이터 베이스라인 재산출

원본 step4 + step5를 전체 데이터로 실행한 뒤,
OTP 1순위(generalized_cost min) vs Best Match(sim_total max) 비교

실행:
    cd main
    python scripts/calibration/run_full_baseline.py
"""

import subprocess
import sys
import os
import time
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
os.chdir(PROJECT_ROOT)

# 환경변수: ITERATION=0, SUBSAMPLE_MODE/OTP_NDJSON_PATH 해제 → 원본 iter0 사용
env = os.environ.copy()
env["ITERATION"] = "0"
env.pop("SUBSAMPLE_MODE", None)
env.pop("OTP_NDJSON_PATH", None)  # 이전 보정에서 남은 경로 제거 → batch_result_iter0.ndjson 사용

print("=" * 70)
print("  전체 Phase 2 데이터 베이스라인 재산출")
print("  step4 → step5 → OTP 1순위 vs Best Match")
print("=" * 70)
print()

# ─────────────────────────────────────────
# Step 4: OTP 결과 파싱
# ─────────────────────────────────────────
print("[1/3] Step 4: OTP 결과 파싱 (32.6GB ndjson)...")
print()
t0 = time.time()

ret = subprocess.run(
    [sys.executable, "scripts/matching/step4_parse_otp_results.py"],
    env=env,
)
if ret.returncode != 0:
    print("Step 4 실패!")
    sys.exit(1)

t1 = time.time()
print(f"\nStep 4 완료: {(t1-t0)/60:.1f}분")
print()

# ─────────────────────────────────────────
# Step 5: 유사도 계산
# ─────────────────────────────────────────
print("[2/3] Step 5: 유사도 계산...")
print()

ret = subprocess.run(
    [sys.executable, "scripts/matching/step5_calculate_similarity.py"],
    env=env,
)
if ret.returncode != 0:
    print("Step 5 실패!")
    sys.exit(1)

t2 = time.time()
print(f"\nStep 5 완료: {(t2-t1)/60:.1f}분")
print()

# ─────────────────────────────────────────
# OTP 1순위 vs Best Match 비교
# ─────────────────────────────────────────
print("[3/3] OTP 1순위 vs Best Match 비교...")
print()

sim = pd.read_parquet("output/similarity_results.parquet")
trip_attrs = pd.read_parquet("output/trip_attributes_matched.parquet")

# chain_id → user_type 매핑
chain_utype = trip_attrs.set_index('chain_id')['user_type'].to_dict()
sim['user_type'] = sim['chain_id'].map(chain_utype)

# chain_id → n_transfers 매핑
chain_transfers = trip_attrs.set_index('chain_id')['n_transfers'].to_dict()
sim['tcd_n_transfers'] = sim['chain_id'].map(chain_transfers)

# Best Match: sim_total 최대
best_idx = sim.groupby('chain_id')['sim_total'].idxmax()
best = sim.loc[best_idx]

# OTP 1순위: generalized_cost 최소
first_idx = sim.groupby('chain_id')['otp_generalized_cost'].idxmin()
first = sim.loc[first_idx]

def print_row(label, n, exact_1st, exact_best, sim_1st, sim_best):
    gap_e = exact_best - exact_1st
    gap_s = sim_best - sim_1st
    print(f"  {label:12s} | n={n:>9,} | "
          f"Exact(1st)={exact_1st*100:5.2f}% | "
          f"Exact(best)={exact_best*100:5.2f}% | "
          f"Sim(1st)={sim_1st:.4f} | "
          f"Sim(best)={sim_best:.4f} | "
          f"Gap_exact={gap_e*100:+.2f}%p | "
          f"Gap_sim={gap_s:+.4f}")

print()
print("=" * 150)
print("  전체 + 유형별 OTP 1순위 vs Best Match 비교 (원본 step4+step5)")
print("=" * 150)
print()

# 전체
print_row("전체", len(best),
          first['exact_match'].mean(), best['exact_match'].mean(),
          first['sim_total'].mean(), best['sim_total'].mean())
print("-" * 150)

# 유형별
for utype in ['GENERAL', 'ELDERLY', 'YOUTH', 'CHILDREN', 'DISABLED']:
    mask_b = best['user_type'] == utype
    mask_f = first['user_type'] == utype
    if mask_b.sum() > 0:
        print_row(utype, mask_b.sum(),
                  first.loc[mask_f, 'exact_match'].mean(),
                  best.loc[mask_b, 'exact_match'].mean(),
                  first.loc[mask_f, 'sim_total'].mean(),
                  best.loc[mask_b, 'sim_total'].mean())

print("-" * 150)
print()

# 환승 횟수별
print("=" * 100)
print("  환승 횟수별 Exact Match (OTP 1순위)")
print("=" * 100)
for nt in sorted(first['tcd_n_transfers'].dropna().unique()):
    mask_f = first['tcd_n_transfers'] == nt
    mask_b = best['tcd_n_transfers'] == nt
    n = mask_f.sum()
    if n > 0:
        print(f"  환승 {int(nt)}회 | n={n:>9,} | "
              f"Exact(1st)={first.loc[mask_f, 'exact_match'].mean()*100:5.2f}% | "
              f"Exact(best)={best.loc[mask_b, 'exact_match'].mean()*100:5.2f}%")

print()

# 대안 수 통계
alts_per_chain = sim.groupby('chain_id').size()
print(f"평균 대안 수: {alts_per_chain.mean():.2f}")
print(f"대안 1개 (선택지 없음): {(alts_per_chain==1).sum():,} ({(alts_per_chain==1).mean()*100:.1f}%)")
print()

t3 = time.time()
print(f"총 소요시간: {(t3-t0)/60:.1f}분")
print("완료!")
