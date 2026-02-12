"""
MNL 확률 1순위 vs OTP generalized_cost 1순위 비교 테스트

기존 Phase 2 전체 데이터(1.32M 체인)에서:
  1. OTP 1순위: generalized_cost 최소 → exact_match (현재 20.34%)
  2. MNL 1순위: V_j = Σ β×X 최대 → exact_match (이게 몇 %?)
  3. Best Match: sim_total 최대 → exact_match (현재 28.62%)

OTP 재실행 없이, 기존 데이터로 MNL 확률 기반 재순위화 효과 검증.

실행:
    cd main
    python scripts/calibration/test_mnl_probability_ranking.py
"""

import subprocess
import sys
import os
import time
import json
import numpy as np
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
os.chdir(PROJECT_ROOT)

RESULTS_DIR = PROJECT_ROOT / "results"
OUTPUT_DIR = PROJECT_ROOT / "output"

# ─────────────────────────────────────────
# MNL β 계수 (Phase 3 결과)
# ─────────────────────────────────────────
MNL_BETAS = {
    "pooled": {
        "T_ride": -0.07498770610598887,
        "T_walk": -0.6441589132495491,
        "N_transfer": -3.051072746767041,
        "D_subway": 2.5379894848151454,
    },
    "GENERAL": {
        "T_ride": -0.07847618693371328,
        "T_walk": -0.6283492422815684,
        "N_transfer": -2.9662034150581422,
        "D_subway": 2.3622194545159676,
    },
    "YOUTH": {
        "T_ride": -0.11452109982658194,
        "T_walk": -0.7469108516609095,
        "N_transfer": -3.295156986515721,
        "D_subway": 2.238237605781155,
    },
    "ELDERLY": {
        "T_ride": -0.03202585311224609,
        "T_walk": -0.7233903787410852,
        "N_transfer": -3.996075762065534,
        "D_subway": 4.551235043260515,
    },
    # CHILDREN, DISABLED: 별도 MNL 없음 → pooled 사용
}

def compute_utility(df, betas):
    """V_j = β_ride×(ride/60) + β_walk×(walk/60) + β_transfer×n_transfers + β_subway×has_subway"""
    V = (betas["T_ride"] * (df["ride_time_sec"] / 60.0)
         + betas["T_walk"] * (df["walk_time_sec"] / 60.0)
         + betas["N_transfer"] * df["n_transfers"]
         + betas["D_subway"] * df["has_subway"])
    return V


def main():
    t0 = time.time()

    print("=" * 80)
    print("  MNL 확률 1순위 vs OTP 1순위 비교 테스트")
    print("=" * 80)
    print()

    # ─────────────────────────────────────────
    # Phase 1: 전체 데이터 복원 (step4 + step5)
    # ─────────────────────────────────────────
    # 현재 파일 크기 확인
    sim_path = OUTPUT_DIR / "similarity_results.parquet"
    otp_path = OUTPUT_DIR / "otp_alternatives.parquet"

    need_rebuild = False
    if sim_path.exists():
        size_mb = sim_path.stat().st_size / (1024**2)
        if size_mb < 50:  # 전체 데이터 ~123MB, 서브샘플 ~0.2MB
            print(f"  similarity_results.parquet = {size_mb:.1f}MB (서브샘플 → 재구축 필요)")
            need_rebuild = True
        else:
            print(f"  similarity_results.parquet = {size_mb:.1f}MB (전체 데이터 OK)")
    else:
        print("  similarity_results.parquet 없음 → 재구축 필요")
        need_rebuild = True

    if need_rebuild:
        print()
        print("─" * 80)
        print("  전체 데이터 재구축: step4 + step5 실행 (~14분)")
        print("─" * 80)
        print()

        env = os.environ.copy()
        env["ITERATION"] = "0"
        env.pop("SUBSAMPLE_MODE", None)
        env.pop("OTP_NDJSON_PATH", None)

        print("[1/2] Step 4: OTP 결과 파싱...")
        t_s4 = time.time()
        ret = subprocess.run(
            [sys.executable, "scripts/matching/step4_parse_otp_results.py"],
            env=env,
        )
        if ret.returncode != 0:
            print("Step 4 실패!")
            sys.exit(1)
        print(f"  → Step 4 완료: {(time.time()-t_s4)/60:.1f}분")
        print()

        print("[2/2] Step 5: 유사도 계산...")
        t_s5 = time.time()
        ret = subprocess.run(
            [sys.executable, "scripts/matching/step5_calculate_similarity.py"],
            env=env,
        )
        if ret.returncode != 0:
            print("Step 5 실패!")
            sys.exit(1)
        print(f"  → Step 5 완료: {(time.time()-t_s5)/60:.1f}분")
        print()

    # ─────────────────────────────────────────
    # Phase 2: 데이터 로드 + 병합
    # ─────────────────────────────────────────
    print("─" * 80)
    print("  데이터 로드 및 MNL 유틸리티 계산")
    print("─" * 80)
    print()

    print("  similarity_results.parquet 로드...")
    sim_df = pd.read_parquet(sim_path)
    print(f"    → {len(sim_df):,} 행, {sim_df['chain_id'].nunique():,} 체인")

    print("  otp_alternatives.parquet 로드...")
    otp_df = pd.read_parquet(otp_path)
    print(f"    → {len(otp_df):,} 행")

    # 병합: similarity + route attributes
    # sim_df: chain_id, od_id, alt_id, exact_match, sim_total, otp_generalized_cost
    # otp_df: od_id, alt_id, ride_time_sec, walk_time_sec, n_transfers, has_subway
    print("  데이터 병합 (od_id + alt_id)...")
    merged = sim_df.merge(
        otp_df[['od_id', 'alt_id', 'ride_time_sec', 'walk_time_sec',
                'n_transfers', 'has_subway', 'generalized_cost']],
        on=['od_id', 'alt_id'],
        how='left'
    )
    print(f"    → 병합 완료: {len(merged):,} 행")

    # null 체크
    n_null = merged['ride_time_sec'].isna().sum()
    if n_null > 0:
        print(f"    ⚠ 병합 실패 {n_null:,}행 ({n_null/len(merged)*100:.2f}%) → 제외")
        merged = merged.dropna(subset=['ride_time_sec'])
    print()

    # user_type 매핑
    print("  user_type 매핑...")
    trip_attrs = pd.read_parquet(OUTPUT_DIR / "trip_attributes_matched.parquet")
    chain_utype = trip_attrs.set_index('chain_id')['user_type'].to_dict()
    merged['user_type'] = merged['chain_id'].map(chain_utype)
    print(f"    → user_type 매핑 완료")
    print()

    # ─────────────────────────────────────────
    # Phase 3: MNL 유틸리티 계산
    # ─────────────────────────────────────────
    print("  MNL 유틸리티 계산...")

    # Pooled β로 전체 계산
    merged['V_pooled'] = compute_utility(merged, MNL_BETAS["pooled"])

    # 유형별 β 적용
    merged['V_typed'] = merged['V_pooled'].copy()  # 기본 = pooled
    for utype, betas in MNL_BETAS.items():
        if utype == "pooled":
            continue
        mask = merged['user_type'] == utype
        if mask.sum() > 0:
            merged.loc[mask, 'V_typed'] = compute_utility(merged.loc[mask], betas)
            print(f"    → {utype}: {mask.sum():,}행에 유형별 β 적용")

    # MNL 확률 계산 (softmax)
    print("  MNL 선택확률 계산 (softmax)...")
    # 수치 안정성을 위해 chain 내 최대 V를 빼고 exp
    merged['V_max'] = merged.groupby('chain_id')['V_typed'].transform('max')
    merged['exp_V'] = np.exp(merged['V_typed'] - merged['V_max'])
    merged['sum_exp_V'] = merged.groupby('chain_id')['exp_V'].transform('sum')
    merged['P_mnl'] = merged['exp_V'] / merged['sum_exp_V']
    print(f"    → 평균 선택확률: {merged['P_mnl'].mean():.4f}")
    print(f"    → 확률 합 체크 (첫 10 체인): {merged.groupby('chain_id')['P_mnl'].sum().head(10).mean():.6f}")
    print()

    # ─────────────────────────────────────────
    # Phase 4: 3가지 순위 비교
    # ─────────────────────────────────────────
    print("=" * 100)
    print("  순위 방법별 비교 (전체 + 유형별)")
    print("=" * 100)
    print()

    # 1. OTP 1순위: otp_generalized_cost 최소
    idx_otp = merged.groupby('chain_id')['otp_generalized_cost'].idxmin()
    pick_otp = merged.loc[idx_otp]

    # 2. MNL 1순위: V_typed 최대 (= P_mnl 최대)
    idx_mnl = merged.groupby('chain_id')['V_typed'].idxmax()
    pick_mnl = merged.loc[idx_mnl]

    # 3. Best Match: sim_total 최대
    idx_best = merged.groupby('chain_id')['sim_total'].idxmax()
    pick_best = merged.loc[idx_best]

    # 결과 테이블 함수
    def print_comparison(label, n, otp_exact, mnl_exact, best_exact,
                         otp_sim, mnl_sim, best_sim):
        print(f"  {label:12s} | n={n:>9,} | "
              f"OTP={otp_exact*100:5.2f}% | "
              f"MNL={mnl_exact*100:5.2f}% | "
              f"Best={best_exact*100:5.2f}% || "
              f"Sim: OTP={otp_sim:.4f} | MNL={mnl_sim:.4f} | Best={best_sim:.4f}")

    header = (f"  {'유형':12s} | {'n':>11s} | "
              f"{'OTP Exact':>10s} | "
              f"{'MNL Exact':>10s} | "
              f"{'Best Exact':>10s} || "
              f"{'OTP Sim':>10s} | {'MNL Sim':>10s} | {'Best Sim':>10s}")
    print(header)
    print("  " + "─" * 120)

    # 전체
    print_comparison("전체", len(pick_otp),
                     pick_otp['exact_match'].mean(),
                     pick_mnl['exact_match'].mean(),
                     pick_best['exact_match'].mean(),
                     pick_otp['sim_total'].mean(),
                     pick_mnl['sim_total'].mean(),
                     pick_best['sim_total'].mean())
    print("  " + "─" * 120)

    # 유형별
    results_by_type = {}
    for utype in ['GENERAL', 'ELDERLY', 'YOUTH', 'CHILDREN', 'DISABLED']:
        mask_o = pick_otp['user_type'] == utype
        mask_m = pick_mnl['user_type'] == utype
        mask_b = pick_best['user_type'] == utype
        n = mask_o.sum()
        if n > 0:
            otp_e = pick_otp.loc[mask_o, 'exact_match'].mean()
            mnl_e = pick_mnl.loc[mask_m, 'exact_match'].mean()
            best_e = pick_best.loc[mask_b, 'exact_match'].mean()
            otp_s = pick_otp.loc[mask_o, 'sim_total'].mean()
            mnl_s = pick_mnl.loc[mask_m, 'sim_total'].mean()
            best_s = pick_best.loc[mask_b, 'sim_total'].mean()
            print_comparison(utype, n, otp_e, mnl_e, best_e, otp_s, mnl_s, best_s)
            results_by_type[utype] = {
                'n': n, 'otp_exact': otp_e, 'mnl_exact': mnl_e,
                'best_exact': best_e, 'otp_sim': otp_s, 'mnl_sim': mnl_s,
                'best_sim': best_s,
            }

    print("  " + "─" * 120)
    print()

    # ─────────────────────────────────────────
    # Phase 5: 개선 폭 분석
    # ─────────────────────────────────────────
    print("=" * 80)
    print("  MNL vs OTP 개선 폭 (MNL - OTP)")
    print("=" * 80)
    print()

    otp_total_exact = pick_otp['exact_match'].mean()
    mnl_total_exact = pick_mnl['exact_match'].mean()
    best_total_exact = pick_best['exact_match'].mean()
    otp_total_sim = pick_otp['sim_total'].mean()
    mnl_total_sim = pick_mnl['sim_total'].mean()
    best_total_sim = pick_best['sim_total'].mean()

    print(f"  전체:")
    print(f"    Exact Match: OTP={otp_total_exact*100:.2f}% → MNL={mnl_total_exact*100:.2f}%  "
          f"(차이: {(mnl_total_exact-otp_total_exact)*100:+.2f}%p)")
    print(f"    Sim Total:   OTP={otp_total_sim:.4f}  → MNL={mnl_total_sim:.4f}  "
          f"(차이: {mnl_total_sim-otp_total_sim:+.4f})")
    print(f"    (참고) Best Match: Exact={best_total_exact*100:.2f}%, Sim={best_total_sim:.4f}")
    print()

    # ─────────────────────────────────────────
    # Phase 6: MNL 확률 분포 분석
    # ─────────────────────────────────────────
    print("=" * 80)
    print("  MNL 1순위의 선택확률 분포")
    print("=" * 80)
    print()

    mnl_top_prob = pick_mnl['P_mnl']
    print(f"  평균 P(1순위): {mnl_top_prob.mean():.4f}")
    print(f"  중앙값: {mnl_top_prob.median():.4f}")
    print(f"  표준편차: {mnl_top_prob.std():.4f}")
    print()

    # 확률 구간별 분포
    bins = [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]
    for lo, hi in bins:
        mask = (mnl_top_prob >= lo) & (mnl_top_prob < hi)
        n = mask.sum()
        pct = n / len(mnl_top_prob) * 100
        bar = "#" * int(pct / 2)
        print(f"  {lo:.1f}~{hi:.1f}: {n:>9,} ({pct:5.1f}%) {bar}")
    print()

    # ─────────────────────────────────────────
    # Phase 7: OTP순위 vs MNL순위 일치도
    # ─────────────────────────────────────────
    print("=" * 80)
    print("  OTP 1순위 vs MNL 1순위 일치 분석")
    print("=" * 80)
    print()

    # 같은 대안을 선택했는지?
    otp_choice = pick_otp[['chain_id', 'alt_id']].set_index('chain_id')['alt_id']
    mnl_choice = pick_mnl[['chain_id', 'alt_id']].set_index('chain_id')['alt_id']
    same_choice = (otp_choice == mnl_choice)
    n_same = same_choice.sum()
    n_total = len(same_choice)
    print(f"  동일 대안 선택: {n_same:,} / {n_total:,} ({n_same/n_total*100:.1f}%)")
    print(f"  다른 대안 선택: {n_total-n_same:,} ({(n_total-n_same)/n_total*100:.1f}%)")
    print()

    # 다른 대안을 선택한 경우, MNL이 더 좋은지?
    diff_chains = same_choice[~same_choice].index
    if len(diff_chains) > 0:
        otp_diff = pick_otp.set_index('chain_id').loc[diff_chains]
        mnl_diff = pick_mnl.set_index('chain_id').loc[diff_chains]

        mnl_better_exact = (mnl_diff['exact_match'].values > otp_diff['exact_match'].values).sum()
        otp_better_exact = (otp_diff['exact_match'].values > mnl_diff['exact_match'].values).sum()
        tie_exact = len(diff_chains) - mnl_better_exact - otp_better_exact

        mnl_better_sim = (mnl_diff['sim_total'].values > otp_diff['sim_total'].values).sum()
        otp_better_sim = (otp_diff['sim_total'].values > mnl_diff['sim_total'].values).sum()
        tie_sim = len(diff_chains) - mnl_better_sim - otp_better_sim

        print(f"  다른 대안 선택한 {len(diff_chains):,} 체인 중:")
        print(f"    Exact Match: MNL 승={mnl_better_exact:,} | OTP 승={otp_better_exact:,} | 무승부={tie_exact:,}")
        print(f"    Sim Total:   MNL 승={mnl_better_sim:,} | OTP 승={otp_better_sim:,} | 무승부={tie_sim:,}")
        print()

        # 평균 유사도 비교 (다른 대안 선택 시)
        print(f"  다른 대안 선택 시 평균 유사도:")
        print(f"    OTP 선택: exact={otp_diff['exact_match'].mean()*100:.2f}%, sim={otp_diff['sim_total'].mean():.4f}")
        print(f"    MNL 선택: exact={mnl_diff['exact_match'].mean()*100:.2f}%, sim={mnl_diff['sim_total'].mean():.4f}")
    print()

    # ─────────────────────────────────────────
    # Phase 8: 환승 횟수별 비교
    # ─────────────────────────────────────────
    print("=" * 80)
    print("  환승 횟수별 비교")
    print("=" * 80)
    print()

    chain_transfers = trip_attrs.set_index('chain_id')['n_transfers'].to_dict()
    pick_otp_nt = pick_otp['chain_id'].map(chain_transfers)
    pick_mnl_nt = pick_mnl['chain_id'].map(chain_transfers)

    for nt in sorted(pick_otp_nt.dropna().unique()):
        mask_o = pick_otp_nt == nt
        mask_m = pick_mnl_nt == nt
        n = mask_o.sum()
        if n > 0:
            otp_e = pick_otp.loc[mask_o.values, 'exact_match'].mean()
            mnl_e = pick_mnl.loc[mask_m.values, 'exact_match'].mean()
            diff = (mnl_e - otp_e) * 100
            print(f"  환승 {int(nt)}회 | n={n:>9,} | "
                  f"OTP={otp_e*100:5.2f}% | MNL={mnl_e*100:5.2f}% | "
                  f"차이={diff:+.2f}%p")
    print()

    # ─────────────────────────────────────────
    # Phase 9: 결과 저장
    # ─────────────────────────────────────────
    t_total = time.time() - t0

    # TXT 저장
    txt_file = RESULTS_DIR / "mnl_ranking_test_results.txt"
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("  MNL 확률 1순위 vs OTP generalized_cost 1순위 비교\n")
        f.write(f"  총 체인: {len(pick_otp):,}\n")
        f.write(f"  총 소요시간: {t_total/60:.1f}분\n")
        f.write("=" * 80 + "\n\n")

        f.write("─" * 80 + "\n")
        f.write("  전체 결과\n")
        f.write("─" * 80 + "\n")
        f.write(f"  OTP 1순위:  Exact={otp_total_exact*100:.2f}%, Sim={otp_total_sim:.4f}\n")
        f.write(f"  MNL 1순위:  Exact={mnl_total_exact*100:.2f}%, Sim={mnl_total_sim:.4f}\n")
        f.write(f"  Best Match: Exact={best_total_exact*100:.2f}%, Sim={best_total_sim:.4f}\n")
        f.write(f"  MNL-OTP 차이: Exact={((mnl_total_exact-otp_total_exact)*100):+.2f}%p, "
                f"Sim={mnl_total_sim-otp_total_sim:+.4f}\n\n")

        f.write("─" * 80 + "\n")
        f.write("  유형별 결과\n")
        f.write("─" * 80 + "\n")
        for utype, r in results_by_type.items():
            f.write(f"  {utype:12s} | n={r['n']:>9,} | "
                    f"OTP={r['otp_exact']*100:.2f}% → MNL={r['mnl_exact']*100:.2f}% "
                    f"({(r['mnl_exact']-r['otp_exact'])*100:+.2f}%p) | "
                    f"Best={r['best_exact']*100:.2f}%\n")
        f.write("\n")

        f.write("─" * 80 + "\n")
        f.write("  OTP vs MNL 순위 일치도\n")
        f.write("─" * 80 + "\n")
        f.write(f"  동일 선택: {n_same:,} / {n_total:,} ({n_same/n_total*100:.1f}%)\n")
        f.write(f"  다른 선택: {n_total-n_same:,} ({(n_total-n_same)/n_total*100:.1f}%)\n\n")

        f.write("─" * 80 + "\n")
        f.write("  MNL β 계수 (Pooled)\n")
        f.write("─" * 80 + "\n")
        for var, val in MNL_BETAS["pooled"].items():
            f.write(f"  {var}: {val:.6f}\n")

    print(f"결과 저장: {txt_file}")
    print()
    print(f"총 소요시간: {t_total/60:.1f}분")
    print("완료!")


if __name__ == "__main__":
    main()
