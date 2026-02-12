"""Phase 2 베이스라인: Best Match vs OTP 1순위 비교"""
import pandas as pd

sim = pd.read_parquet("output/similarity_results.parquet")
print(f"전체 쌍: {len(sim):,}")
print(f"체인 수: {sim['chain_id'].nunique():,}")

# 방법 A: Best Match (기존 - sim_total 최대)
best_sim = sim.loc[sim.groupby('chain_id')['sim_total'].idxmax()]
print()
print("=== Best Match (기존 방식) ===")
print(f"exact_match: {best_sim['exact_match'].mean()*100:.2f}%")
print(f"sim_total:   {best_sim['sim_total'].mean():.4f}")

# 방법 B: OTP 1순위 (generalized_cost 최소)
first_pick = sim.loc[sim.groupby('chain_id')['otp_generalized_cost'].idxmin()]
print()
print("=== OTP 1순위 (generalized_cost min) ===")
print(f"exact_match: {first_pick['exact_match'].mean()*100:.2f}%")
print(f"sim_total:   {first_pick['sim_total'].mean():.4f}")

# 차이
print()
print("=== 차이 ===")
print(f"exact_match 차이: {(best_sim['exact_match'].mean() - first_pick['exact_match'].mean())*100:+.2f}%p")
print(f"sim_total 차이:   {best_sim['sim_total'].mean() - first_pick['sim_total'].mean():+.4f}")
