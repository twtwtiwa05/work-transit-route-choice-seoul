"""
Phase 4 핵심 분석: MNL 재순위 vs OTP 순위 상세 비교

전체 Phase 2 데이터(1.32M 체인)에서:
  1. OTP 1순위 (generalized_cost min)
  2. MNL 1순위 (V = β'x max)
  3. Best Match (sim_total max)
를 비교하고, 유형별·환승별·시간대별 상세 분석 수행.

실행:
    cd main
    python scripts/calibration/mnl_reranking_analysis.py
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
    # CHILDREN, DISABLED → pooled
}


def compute_utility(df, betas):
    return (betas["T_ride"] * (df["ride_time_sec"] / 60.0)
            + betas["T_walk"] * (df["walk_time_sec"] / 60.0)
            + betas["N_transfer"] * df["n_transfers"]
            + betas["D_subway"] * df["has_subway"])


def get_beta_for_type(utype):
    if utype in MNL_BETAS:
        return MNL_BETAS[utype]
    return MNL_BETAS["pooled"]


def main():
    t0 = time.time()

    print("=" * 80)
    print("  Phase 4: MNL 재순위 분석 (전체 1.32M 체인)")
    print("=" * 80)
    print()

    # ─────────────────────────────────────────
    # 1. 전체 데이터 확보
    # ─────────────────────────────────────────
    sim_path = OUTPUT_DIR / "similarity_results.parquet"
    otp_path = OUTPUT_DIR / "otp_alternatives.parquet"

    need_rebuild = False
    if sim_path.exists():
        size_mb = sim_path.stat().st_size / (1024**2)
        if size_mb < 50:
            print(f"  similarity_results.parquet = {size_mb:.1f}MB (서브샘플 → 재구축 필요)")
            need_rebuild = True
        else:
            print(f"  similarity_results.parquet = {size_mb:.1f}MB (전체 데이터 OK)")
    else:
        need_rebuild = True

    if need_rebuild:
        print()
        print("─" * 80)
        print("  전체 데이터 재구축: step4 + step5 (~14분)")
        print("─" * 80)
        print()

        env = os.environ.copy()
        env["ITERATION"] = "0"
        env.pop("SUBSAMPLE_MODE", None)
        env.pop("OTP_NDJSON_PATH", None)

        print("[1/2] Step 4: OTP 결과 파싱...")
        t_s = time.time()
        ret = subprocess.run([sys.executable, "scripts/matching/step4_parse_otp_results.py"], env=env)
        if ret.returncode != 0:
            print("Step 4 실패!")
            sys.exit(1)
        print(f"  → Step 4 완료: {(time.time()-t_s)/60:.1f}분")

        print("[2/2] Step 5: 유사도 계산...")
        t_s = time.time()
        ret = subprocess.run([sys.executable, "scripts/matching/step5_calculate_similarity.py"], env=env)
        if ret.returncode != 0:
            print("Step 5 실패!")
            sys.exit(1)
        print(f"  → Step 5 완료: {(time.time()-t_s)/60:.1f}분")
        print()

    # ─────────────────────────────────────────
    # 2. 데이터 로드 + 병합
    # ─────────────────────────────────────────
    print("─" * 80)
    print("  데이터 로드")
    print("─" * 80)

    sim_df = pd.read_parquet(sim_path)
    print(f"  similarity_results: {len(sim_df):,}행, {sim_df['chain_id'].nunique():,}체인")

    otp_df = pd.read_parquet(otp_path)
    print(f"  otp_alternatives: {len(otp_df):,}행")

    merged = sim_df.merge(
        otp_df[['od_id', 'alt_id', 'ride_time_sec', 'walk_time_sec',
                'n_transfers', 'has_subway', 'generalized_cost']],
        on=['od_id', 'alt_id'], how='left'
    )
    n_null = merged['ride_time_sec'].isna().sum()
    if n_null > 0:
        print(f"  ⚠ 병합 실패 {n_null:,}행 제외")
        merged = merged.dropna(subset=['ride_time_sec'])

    # user_type, n_transfers(관측), board_time 매핑
    trip_attrs = pd.read_parquet(OUTPUT_DIR / "trip_attributes_matched.parquet")
    chain_info = trip_attrs.set_index('chain_id')[['user_type', 'n_transfers', 'board_time']].to_dict('index')
    merged['user_type'] = merged['chain_id'].map(lambda c: chain_info.get(c, {}).get('user_type'))
    merged['tcd_n_transfers'] = merged['chain_id'].map(lambda c: chain_info.get(c, {}).get('n_transfers'))
    merged['board_time'] = merged['chain_id'].map(lambda c: chain_info.get(c, {}).get('board_time'))

    # 피크 시간대 (7-9시, 18-20시)
    bt_hour = merged['board_time'] / 3600.0
    merged['is_peak'] = ((bt_hour >= 7) & (bt_hour < 9)) | ((bt_hour >= 18) & (bt_hour < 20))

    # 체인별 대안 수
    merged['n_alts'] = merged.groupby('chain_id')['alt_id'].transform('count')

    n_chains = merged['chain_id'].nunique()
    n_pairs = len(merged)
    print(f"  최종: {n_pairs:,}쌍, {n_chains:,}체인")
    print()

    # ─────────────────────────────────────────
    # 3. MNL 유틸리티 + 확률 계산
    # ─────────────────────────────────────────
    print("  MNL 유틸리티 계산...")

    # 기본 = pooled
    merged['V'] = compute_utility(merged, MNL_BETAS["pooled"])

    # 유형별 β 적용
    for utype in ['GENERAL', 'YOUTH', 'ELDERLY']:
        mask = merged['user_type'] == utype
        if mask.sum() > 0:
            merged.loc[mask, 'V'] = compute_utility(merged.loc[mask], MNL_BETAS[utype])

    # softmax (수치 안정성)
    merged['V_max'] = merged.groupby('chain_id')['V'].transform('max')
    merged['exp_V'] = np.exp(merged['V'] - merged['V_max'])
    merged['sum_exp'] = merged.groupby('chain_id')['exp_V'].transform('sum')
    merged['P_mnl'] = merged['exp_V'] / merged['sum_exp']
    print(f"  → 완료 (평균 P: {merged['P_mnl'].mean():.4f})")
    print()

    # ─────────────────────────────────────────
    # 4. 3가지 순위 추출
    # ─────────────────────────────────────────
    idx_otp = merged.groupby('chain_id')['otp_generalized_cost'].idxmin()
    idx_mnl = merged.groupby('chain_id')['V'].idxmax()
    idx_best = merged.groupby('chain_id')['sim_total'].idxmax()

    pick_otp = merged.loc[idx_otp].copy()
    pick_mnl = merged.loc[idx_mnl].copy()
    pick_best = merged.loc[idx_best].copy()

    # ─────────────────────────────────────────
    # 5. 분석 결과 수집
    # ─────────────────────────────────────────
    results = {}

    # --- 5.1 전체 ---
    results['overall'] = {
        'n_chains': n_chains,
        'n_pairs': n_pairs,
        'avg_alts': n_pairs / n_chains,
        'otp_exact': float(pick_otp['exact_match'].mean()),
        'mnl_exact': float(pick_mnl['exact_match'].mean()),
        'best_exact': float(pick_best['exact_match'].mean()),
        'otp_sim': float(pick_otp['sim_total'].mean()),
        'mnl_sim': float(pick_mnl['sim_total'].mean()),
        'best_sim': float(pick_best['sim_total'].mean()),
        'mnl_minus_otp_exact': float(pick_mnl['exact_match'].mean() - pick_otp['exact_match'].mean()),
    }

    # --- 5.2 유형별 ---
    results['by_user_type'] = {}
    for utype in ['GENERAL', 'ELDERLY', 'YOUTH', 'CHILDREN', 'DISABLED']:
        mo = pick_otp['user_type'] == utype
        mm = pick_mnl['user_type'] == utype
        mb = pick_best['user_type'] == utype
        n = mo.sum()
        if n > 0:
            results['by_user_type'][utype] = {
                'n': int(n),
                'otp_exact': float(pick_otp.loc[mo, 'exact_match'].mean()),
                'mnl_exact': float(pick_mnl.loc[mm, 'exact_match'].mean()),
                'best_exact': float(pick_best.loc[mb, 'exact_match'].mean()),
                'otp_sim': float(pick_otp.loc[mo, 'sim_total'].mean()),
                'mnl_sim': float(pick_mnl.loc[mm, 'sim_total'].mean()),
                'best_sim': float(pick_best.loc[mb, 'sim_total'].mean()),
            }
            results['by_user_type'][utype]['delta_exact'] = (
                results['by_user_type'][utype]['mnl_exact'] -
                results['by_user_type'][utype]['otp_exact']
            )

    # --- 5.3 환승 횟수별 ---
    results['by_transfers'] = {}
    for nt in [0, 1, 2, 3]:
        label = f"{nt}t" if nt < 3 else "3t+"
        if nt < 3:
            mo = pick_otp['tcd_n_transfers'] == nt
            mm = pick_mnl['tcd_n_transfers'] == nt
            mb = pick_best['tcd_n_transfers'] == nt
        else:
            mo = pick_otp['tcd_n_transfers'] >= 3
            mm = pick_mnl['tcd_n_transfers'] >= 3
            mb = pick_best['tcd_n_transfers'] >= 3
        n = mo.sum()
        if n > 0:
            results['by_transfers'][label] = {
                'n': int(n),
                'otp_exact': float(pick_otp.loc[mo, 'exact_match'].mean()),
                'mnl_exact': float(pick_mnl.loc[mm, 'exact_match'].mean()),
                'best_exact': float(pick_best.loc[mb, 'exact_match'].mean()),
                'delta_exact': float(
                    pick_mnl.loc[mm, 'exact_match'].mean() -
                    pick_otp.loc[mo, 'exact_match'].mean()
                ),
            }

    # --- 5.4 피크/비피크 ---
    results['by_peak'] = {}
    for is_peak, label in [(True, 'peak'), (False, 'off_peak')]:
        mo = pick_otp['is_peak'] == is_peak
        mm = pick_mnl['is_peak'] == is_peak
        n = mo.sum()
        if n > 0:
            results['by_peak'][label] = {
                'n': int(n),
                'otp_exact': float(pick_otp.loc[mo, 'exact_match'].mean()),
                'mnl_exact': float(pick_mnl.loc[mm, 'exact_match'].mean()),
                'delta_exact': float(
                    pick_mnl.loc[mm, 'exact_match'].mean() -
                    pick_otp.loc[mo, 'exact_match'].mean()
                ),
            }

    # --- 5.5 대안 수별 ---
    results['by_n_alts'] = {}
    for na_lo, na_hi, label in [(1, 1, '1'), (2, 2, '2'), (3, 4, '3-4'), (5, 10, '5+')]:
        mo = (pick_otp['n_alts'] >= na_lo) & (pick_otp['n_alts'] <= na_hi)
        mm = (pick_mnl['n_alts'] >= na_lo) & (pick_mnl['n_alts'] <= na_hi)
        n = mo.sum()
        if n > 0:
            results['by_n_alts'][label] = {
                'n': int(n),
                'otp_exact': float(pick_otp.loc[mo, 'exact_match'].mean()),
                'mnl_exact': float(pick_mnl.loc[mm, 'exact_match'].mean()),
                'delta_exact': float(
                    pick_mnl.loc[mm, 'exact_match'].mean() -
                    pick_otp.loc[mo, 'exact_match'].mean()
                ),
            }

    # --- 5.6 OTP vs MNL 일치/불일치 ---
    otp_alt = pick_otp.set_index('chain_id')['alt_id']
    mnl_alt = pick_mnl.set_index('chain_id')['alt_id']
    same = (otp_alt == mnl_alt)
    n_same = int(same.sum())
    n_diff = int((~same).sum())

    results['agreement'] = {
        'same_choice': n_same,
        'diff_choice': n_diff,
        'same_pct': n_same / len(same) * 100,
    }

    # 불일치 시 누가 더 좋은가?
    diff_chains = same[~same].index
    if len(diff_chains) > 0:
        otp_d = pick_otp.set_index('chain_id').loc[diff_chains]
        mnl_d = pick_mnl.set_index('chain_id').loc[diff_chains]

        mnl_win_exact = int((mnl_d['exact_match'].values > otp_d['exact_match'].values).sum())
        otp_win_exact = int((otp_d['exact_match'].values > mnl_d['exact_match'].values).sum())
        tie_exact = len(diff_chains) - mnl_win_exact - otp_win_exact

        mnl_win_sim = int((mnl_d['sim_total'].values > otp_d['sim_total'].values).sum())
        otp_win_sim = int((otp_d['sim_total'].values > mnl_d['sim_total'].values).sum())
        tie_sim = len(diff_chains) - mnl_win_sim - otp_win_sim

        results['disagreement'] = {
            'n_disagree': len(diff_chains),
            'exact_match': {
                'mnl_wins': mnl_win_exact,
                'otp_wins': otp_win_exact,
                'tie': tie_exact,
                'mnl_win_ratio': f"{mnl_win_exact}:{otp_win_exact}",
            },
            'sim_total': {
                'mnl_wins': mnl_win_sim,
                'otp_wins': otp_win_sim,
                'tie': tie_sim,
            },
            'avg_when_disagree': {
                'otp_exact': float(otp_d['exact_match'].mean()),
                'mnl_exact': float(mnl_d['exact_match'].mean()),
                'otp_sim': float(otp_d['sim_total'].mean()),
                'mnl_sim': float(mnl_d['sim_total'].mean()),
            }
        }

    # --- 5.7 MNL 확률 분포 ---
    top_p = pick_mnl['P_mnl']
    results['mnl_probability'] = {
        'mean': float(top_p.mean()),
        'median': float(top_p.median()),
        'std': float(top_p.std()),
        'distribution': {},
    }
    for lo, hi in [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]:
        mask = (top_p >= lo) & (top_p < hi)
        n = int(mask.sum())
        results['mnl_probability']['distribution'][f"{lo:.1f}-{hi:.1f}"] = {
            'n': n, 'pct': round(n / len(top_p) * 100, 1)
        }

    # --- 5.8 F₁, F₂ (확률 가중 지표) ---
    merged['p_sim'] = merged['P_mnl'] * merged['sim_total']
    merged['p_exact'] = merged['P_mnl'] * merged['exact_match']
    f1 = merged.groupby('chain_id')['p_sim'].sum().mean()
    f2 = merged.groupby('chain_id')['p_exact'].sum().mean()
    results['probabilistic_metrics'] = {
        'F1_expected_similarity': float(f1),
        'F2_expected_exact_match': float(f2),
    }

    # --- 5.9 MNL 선택 경로 vs OTP 선택 경로의 특성 차이 ---
    results['route_characteristics'] = {
        'otp_choice': {
            'avg_ride_min': float(pick_otp['ride_time_sec'].mean() / 60),
            'avg_walk_min': float(pick_otp['walk_time_sec'].mean() / 60),
            'avg_transfers': float(pick_otp['n_transfers'].mean()),
            'subway_pct': float(pick_otp['has_subway'].mean() * 100),
        },
        'mnl_choice': {
            'avg_ride_min': float(pick_mnl['ride_time_sec'].mean() / 60),
            'avg_walk_min': float(pick_mnl['walk_time_sec'].mean() / 60),
            'avg_transfers': float(pick_mnl['n_transfers'].mean()),
            'subway_pct': float(pick_mnl['has_subway'].mean() * 100),
        },
    }

    # ─────────────────────────────────────────
    # 6. 결과 출력
    # ─────────────────────────────────────────
    elapsed = time.time() - t0

    print("=" * 90)
    print("  MNL 재순위 분석 결과")
    print("=" * 90)
    print()

    r = results['overall']
    print(f"  전체: {r['n_chains']:,}체인, 평균 {r['avg_alts']:.1f}개 대안")
    print()
    print(f"  {'방법':<16s}  {'Exact Match':>12s}  {'Sim Total':>10s}")
    print(f"  {'─'*48}")
    print(f"  {'OTP 1순위':<16s}  {r['otp_exact']*100:>11.2f}%  {r['otp_sim']:>10.4f}")
    print(f"  {'MNL 1순위':<16s}  {r['mnl_exact']*100:>11.2f}%  {r['mnl_sim']:>10.4f}")
    print(f"  {'Best Match':<16s}  {r['best_exact']*100:>11.2f}%  {r['best_sim']:>10.4f}")
    print(f"  {'─'*48}")
    print(f"  MNL-OTP 차이:   {r['mnl_minus_otp_exact']*100:>+10.2f}%p")
    print()

    print("  [유형별]")
    print(f"  {'유형':<12s} {'n':>10s}  {'OTP':>8s}  {'MNL':>8s}  {'Δ':>8s}  {'Best':>8s}")
    print(f"  {'─'*60}")
    for utype, d in results['by_user_type'].items():
        print(f"  {utype:<12s} {d['n']:>10,}  {d['otp_exact']*100:>7.2f}%  "
              f"{d['mnl_exact']*100:>7.2f}%  {d['delta_exact']*100:>+7.2f}%  "
              f"{d['best_exact']*100:>7.2f}%")
    print()

    print("  [환승 횟수별]")
    print(f"  {'환승':<8s} {'n':>10s}  {'OTP':>8s}  {'MNL':>8s}  {'Δ':>8s}  {'Best':>8s}")
    print(f"  {'─'*56}")
    for label, d in results['by_transfers'].items():
        print(f"  {label:<8s} {d['n']:>10,}  {d['otp_exact']*100:>7.2f}%  "
              f"{d['mnl_exact']*100:>7.2f}%  {d['delta_exact']*100:>+7.2f}%  "
              f"{d['best_exact']*100:>7.2f}%")
    print()

    print("  [피크/비피크]")
    for label, d in results['by_peak'].items():
        name = "피크(7-9,18-20)" if label == 'peak' else "비피크"
        print(f"  {name:<18s} n={d['n']:>10,}  OTP={d['otp_exact']*100:.2f}%  "
              f"MNL={d['mnl_exact']*100:.2f}%  Δ={d['delta_exact']*100:+.2f}%p")
    print()

    print("  [대안 수별]")
    for label, d in results['by_n_alts'].items():
        print(f"  {label+'개':<8s} n={d['n']:>10,}  OTP={d['otp_exact']*100:.2f}%  "
              f"MNL={d['mnl_exact']*100:.2f}%  Δ={d['delta_exact']*100:+.2f}%p")
    print()

    print("  [OTP vs MNL 순위 일치도]")
    ag = results['agreement']
    print(f"  동일 선택: {ag['same_choice']:,} ({ag['same_pct']:.1f}%)")
    print(f"  다른 선택: {ag['diff_choice']:,} ({100-ag['same_pct']:.1f}%)")
    if 'disagreement' in results:
        dg = results['disagreement']
        print(f"  불일치 시 Exact: MNL 승 {dg['exact_match']['mnl_wins']:,} : "
              f"OTP 승 {dg['exact_match']['otp_wins']:,} "
              f"(MNL {dg['exact_match']['mnl_wins']/max(1,dg['exact_match']['otp_wins']):.1f}배)")
        print(f"  불일치 시 Sim:   MNL 승 {dg['sim_total']['mnl_wins']:,} : "
              f"OTP 승 {dg['sim_total']['otp_wins']:,}")
        avg = dg['avg_when_disagree']
        print(f"  불일치 시 평균: OTP exact={avg['otp_exact']*100:.2f}% sim={avg['otp_sim']:.4f}"
              f" → MNL exact={avg['mnl_exact']*100:.2f}% sim={avg['mnl_sim']:.4f}")
    print()

    print("  [MNL 1순위 확률 분포]")
    mp = results['mnl_probability']
    print(f"  평균={mp['mean']:.4f}, 중앙값={mp['median']:.4f}")
    for rng, d in mp['distribution'].items():
        bar = "█" * int(d['pct'] / 2)
        print(f"  P={rng}: {d['n']:>10,} ({d['pct']:>5.1f}%) {bar}")
    print()

    print("  [확률 가중 지표]")
    pm = results['probabilistic_metrics']
    print(f"  F₁ (기대 유사도):    {pm['F1_expected_similarity']:.4f}")
    print(f"  F₂ (기대 완전일치):  {pm['F2_expected_exact_match']*100:.2f}%")
    print()

    print("  [MNL vs OTP 선택 경로 특성 비교]")
    rc = results['route_characteristics']
    print(f"  {'':15s}  {'차내(분)':>8s}  {'보행(분)':>8s}  {'환승(회)':>8s}  {'지하철%':>8s}")
    print(f"  {'─'*55}")
    o, m = rc['otp_choice'], rc['mnl_choice']
    print(f"  {'OTP 선택':<15s}  {o['avg_ride_min']:>8.1f}  {o['avg_walk_min']:>8.1f}  "
          f"{o['avg_transfers']:>8.2f}  {o['subway_pct']:>7.1f}%")
    print(f"  {'MNL 선택':<15s}  {m['avg_ride_min']:>8.1f}  {m['avg_walk_min']:>8.1f}  "
          f"{m['avg_transfers']:>8.2f}  {m['subway_pct']:>7.1f}%")
    print(f"  {'차이':<15s}  {m['avg_ride_min']-o['avg_ride_min']:>+8.1f}  "
          f"{m['avg_walk_min']-o['avg_walk_min']:>+8.1f}  "
          f"{m['avg_transfers']-o['avg_transfers']:>+8.2f}  "
          f"{m['subway_pct']-o['subway_pct']:>+7.1f}%")
    print()

    print(f"  총 소요시간: {elapsed/60:.1f}분")

    # ─────────────────────────────────────────
    # 7. 결과 저장
    # ─────────────────────────────────────────
    results['elapsed_min'] = elapsed / 60
    results['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')

    # JSON
    json_path = RESULTS_DIR / "mnl_reranking_analysis.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  JSON 저장: {json_path}")

    # TXT (위 출력 그대로)
    txt_path = RESULTS_DIR / "mnl_reranking_analysis.txt"
    import io
    # re-run print section to file
    buf = io.StringIO()
    def p(s=""): buf.write(s + "\n")

    p("=" * 90)
    p("  Phase 4 핵심 분석: MNL 재순위 vs OTP 순위")
    p(f"  {results['timestamp']}")
    p(f"  전체 체인: {r['n_chains']:,}, 소요시간: {elapsed/60:.1f}분")
    p("=" * 90)
    p()
    p(f"  {'방법':<16s}  {'Exact Match':>12s}  {'Sim Total':>10s}")
    p(f"  {'─'*48}")
    p(f"  {'OTP 1순위':<16s}  {r['otp_exact']*100:>11.2f}%  {r['otp_sim']:>10.4f}")
    p(f"  {'MNL 1순위':<16s}  {r['mnl_exact']*100:>11.2f}%  {r['mnl_sim']:>10.4f}")
    p(f"  {'Best Match':<16s}  {r['best_exact']*100:>11.2f}%  {r['best_sim']:>10.4f}")
    p(f"  MNL-OTP:        {r['mnl_minus_otp_exact']*100:>+10.2f}%p")
    p()

    p("─" * 70)
    p("  유형별")
    p("─" * 70)
    for utype, d in results['by_user_type'].items():
        p(f"  {utype:<12s} n={d['n']:>10,}  OTP={d['otp_exact']*100:.2f}%  "
          f"MNL={d['mnl_exact']*100:.2f}%  Δ={d['delta_exact']*100:+.2f}%p  "
          f"Best={d['best_exact']*100:.2f}%")
    p()

    p("─" * 70)
    p("  환승 횟수별")
    p("─" * 70)
    for label, d in results['by_transfers'].items():
        p(f"  {label:<8s} n={d['n']:>10,}  OTP={d['otp_exact']*100:.2f}%  "
          f"MNL={d['mnl_exact']*100:.2f}%  Δ={d['delta_exact']*100:+.2f}%p  "
          f"Best={d['best_exact']*100:.2f}%")
    p()

    p("─" * 70)
    p("  피크/비피크")
    p("─" * 70)
    for label, d in results['by_peak'].items():
        name = "피크(7-9,18-20)" if label == 'peak' else "비피크"
        p(f"  {name:<18s} n={d['n']:>10,}  OTP={d['otp_exact']*100:.2f}%  "
          f"MNL={d['mnl_exact']*100:.2f}%  Δ={d['delta_exact']*100:+.2f}%p")
    p()

    p("─" * 70)
    p("  대안 수별")
    p("─" * 70)
    for label, d in results['by_n_alts'].items():
        p(f"  {label+'개':<8s} n={d['n']:>10,}  OTP={d['otp_exact']*100:.2f}%  "
          f"MNL={d['mnl_exact']*100:.2f}%  Δ={d['delta_exact']*100:+.2f}%p")
    p()

    p("─" * 70)
    p("  OTP vs MNL 일치도")
    p("─" * 70)
    p(f"  동일: {ag['same_choice']:,} ({ag['same_pct']:.1f}%)")
    p(f"  다름: {ag['diff_choice']:,} ({100-ag['same_pct']:.1f}%)")
    if 'disagreement' in results:
        dg = results['disagreement']
        p(f"  불일치 시 Exact: MNL승 {dg['exact_match']['mnl_wins']:,} : "
          f"OTP승 {dg['exact_match']['otp_wins']:,}")
        p(f"  불일치 시 Sim: MNL승 {dg['sim_total']['mnl_wins']:,} : "
          f"OTP승 {dg['sim_total']['otp_wins']:,}")
        avg = dg['avg_when_disagree']
        p(f"  불일치 평균: OTP exact={avg['otp_exact']*100:.2f}% → MNL exact={avg['mnl_exact']*100:.2f}%")
    p()

    p("─" * 70)
    p("  MNL 확률 분포")
    p("─" * 70)
    p(f"  평균={mp['mean']:.4f}, 중앙값={mp['median']:.4f}")
    for rng, d in mp['distribution'].items():
        p(f"  P={rng}: {d['n']:>10,} ({d['pct']:>5.1f}%)")
    p()

    p("─" * 70)
    p("  확률 가중 지표")
    p("─" * 70)
    p(f"  F₁ (기대 유사도):   {pm['F1_expected_similarity']:.4f}")
    p(f"  F₂ (기대 완전일치): {pm['F2_expected_exact_match']*100:.2f}%")
    p()

    p("─" * 70)
    p("  선택 경로 특성 비교")
    p("─" * 70)
    p(f"  {'':15s}  {'차내(분)':>8s}  {'보행(분)':>8s}  {'환승':>6s}  {'지하철%':>8s}")
    p(f"  {'OTP':<15s}  {o['avg_ride_min']:>8.1f}  {o['avg_walk_min']:>8.1f}  "
      f"{o['avg_transfers']:>6.2f}  {o['subway_pct']:>7.1f}%")
    p(f"  {'MNL':<15s}  {m['avg_ride_min']:>8.1f}  {m['avg_walk_min']:>8.1f}  "
      f"{m['avg_transfers']:>6.2f}  {m['subway_pct']:>7.1f}%")
    p(f"  {'Δ':<15s}  {m['avg_ride_min']-o['avg_ride_min']:>+8.1f}  "
      f"{m['avg_walk_min']-o['avg_walk_min']:>+8.1f}  "
      f"{m['avg_transfers']-o['avg_transfers']:>+6.2f}  "
      f"{m['subway_pct']-o['subway_pct']:>+7.1f}%")

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(buf.getvalue())
    print(f"  TXT 저장: {txt_path}")
    print()
    print("  완료!")


if __name__ == "__main__":
    main()
