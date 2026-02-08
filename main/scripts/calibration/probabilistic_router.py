#!/usr/bin/env python3
"""
Phase 4: 확률적 경로 배정 모듈

OTP가 생성한 대안 경로에 대해 이용자 유형별 MNL 선택확률을 산출한다.
동일한 경로 세트에 대해 유형별로 다른 β를 적용하여 확률이 달라지는 것이 핵심.

예시 출력:
    명동→역삼  |  4호선→2호선: General 70.8%, Elderly 76.7%
               |  463번 직행:  General 29.2%, Elderly 23.3%

사용법:
    python probabilistic_router.py                     # 전체 OD 배치 실행
    python probabilistic_router.py --test-cases        # 논문 테스트 케이스만
    python probabilistic_router.py --output probs.json # 출력 경로 지정
"""

import json
import math
import argparse
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results"
OUTPUT_DIR = ROOT / "output"

USER_TYPE_LABELS = {1: "General", 2: "Children", 3: "Youth",
                    4: "Elderly", 5: "Disabled"}

# 효용함수 변수
UTILITY_VARS = ["T_ride", "T_walk", "N_transfer", "D_subway"]
INTERACTION_VARS = ["Peak_T_ride", "Peak_N_transfer"]


def load_mnl_params(results_path=None):
    """이용자 유형별 MNL β 파라미터를 로드한다.

    반환: {유형명: {변수명: 계수, ...}, ...}
    """
    path = results_path or (RESULTS_DIR / "mnl_results.json")
    with open(path) as f:
        mnl = json.load(f)

    params = {}
    for type_id, label in USER_TYPE_LABELS.items():
        key = f"type_{type_id}"
        if key in mnl:
            p = mnl[key]["parameters"]
        elif label in mnl:
            p = mnl[label]["parameters"]
        else:
            # 유형별 결과 없으면 Pooled 사용
            p = mnl["pooled"]["parameters"]

        params[label] = {var: p[var]["coef"] for var in UTILITY_VARS
                         if var in p}

        # 교호작용 항 추가
        for iv in INTERACTION_VARS:
            if iv in p:
                params[label][iv] = p[iv]["coef"]

    return params


def compute_utility(alternative, beta, include_interactions=True):
    """단일 대안의 확정 효용(V)을 계산한다.

    V_j = β_ride×T_ride + β_walk×T_walk + β_transfer×N_transfer + β_subway×D_subway
          + β_peak_ride×(D_peak×T_ride) + β_peak_transfer×(D_peak×N_transfer)
    """
    V = 0.0
    for var in UTILITY_VARS:
        if var in beta and var in alternative:
            V += beta[var] * alternative[var]

    if include_interactions:
        d_peak = alternative.get("D_peak", 0)
        if d_peak and "Peak_T_ride" in beta:
            V += beta["Peak_T_ride"] * alternative.get("T_ride", 0) * d_peak
        if d_peak and "Peak_N_transfer" in beta:
            V += beta["Peak_N_transfer"] * alternative.get("N_transfer", 0) * d_peak

    return V


def compute_probabilities(alternatives, beta):
    """대안 집합에 대해 MNL 선택확률을 계산한다.

    Max-normalization으로 수치 안정성 확보:
        P(j) = exp(V_j - V_max) / Σ exp(V_k - V_max)

    Parameters
    ----------
    alternatives : list of dict
        각 dict에 T_ride, T_walk, N_transfer, D_subway 등 포함.
    beta : dict
        한 이용자 유형의 {변수: 계수, ...}.

    Returns
    -------
    list of float
        합이 1.0인 확률 리스트.
    """
    utilities = [compute_utility(alt, beta) for alt in alternatives]
    v_max = max(utilities)
    exp_v = [math.exp(v - v_max) for v in utilities]
    sum_exp = sum(exp_v)
    return [e / sum_exp for e in exp_v]


def compute_all_probabilities(alternatives, all_params):
    """전체 이용자 유형에 대해 확률을 계산한다.

    반환: {유형명: [경로1확률, 경로2확률, ...], ...}
    """
    result = {}
    for user_type, beta in all_params.items():
        result[user_type] = compute_probabilities(alternatives, beta)
    return result


def format_route_output(od_info, alternatives, all_probs):
    """단일 OD 쌍의 결과를 출력 형식으로 정리한다."""
    routes = []
    for i, alt in enumerate(alternatives):
        route = {
            "index": i,
            "ride_min": round(alt.get("T_ride", 0), 1),
            "walk_min": round(alt.get("T_walk", 0), 1),
            "transfers": int(alt.get("N_transfer", 0)),
            "has_subway": bool(alt.get("D_subway", 0)),
            "probabilities": {}
        }
        if "route_name" in alt:
            route["route_name"] = alt["route_name"]
        if "modes" in alt:
            route["modes"] = alt["modes"]

        for user_type, probs in all_probs.items():
            route["probabilities"][user_type] = f"{probs[i]:.1%}"

        routes.append(route)

    return {
        "od_pair": od_info,
        "n_alternatives": len(alternatives),
        "alternatives": routes
    }


def run_test_cases(params):
    """논문의 테스트 케이스를 실행하여 모듈을 검증한다.

    전 논문(ITSWC 2026)의 Table 12-14에 대응하는 3개 OD 쌍.
    """
    print("\n" + "=" * 60)
    print("  확률적 경로 배정 — 테스트 케이스")
    print("=" * 60)

    # 테스트 1: 명동 → 역삼 (09:00)
    test1 = {
        "od": {"from": "명동", "to": "역삼", "departure": "09:00"},
        "alternatives": [
            {"route_name": "4호선→2호선", "T_ride": 29.5, "T_walk": 1.8,
             "N_transfer": 1, "D_subway": 1, "D_peak": 1},
            {"route_name": "463번 직행", "T_ride": 35.6, "T_walk": 3.7,
             "N_transfer": 0, "D_subway": 0, "D_peak": 1},
        ]
    }

    # 테스트 2: 구로디지털단지 → 종로 (10:00)
    test2 = {
        "od": {"from": "구로디지털단지", "to": "종로", "departure": "10:00"},
        "alternatives": [
            {"route_name": "2호선→1호선", "T_ride": 29.0, "T_walk": 1.9,
             "N_transfer": 1, "D_subway": 1, "D_peak": 0},
            {"route_name": "2호선 직통", "T_ride": 29.0, "T_walk": 8.1,
             "N_transfer": 0, "D_subway": 1, "D_peak": 0},
            {"route_name": "2호선 직통(대안)", "T_ride": 29.5, "T_walk": 8.1,
             "N_transfer": 0, "D_subway": 1, "D_peak": 0},
        ]
    }

    # 테스트 3: 합정 → 선릉 (09:30)
    test3 = {
        "od": {"from": "합정", "to": "선릉", "departure": "09:30"},
        "alternatives": [
            {"route_name": "2호선(직통)", "T_ride": 39.5, "T_walk": 6.5,
             "N_transfer": 0, "D_subway": 1, "D_peak": 1},
            {"route_name": "6호선→버스", "T_ride": 39.4, "T_walk": 6.0,
             "N_transfer": 1, "D_subway": 1, "D_peak": 1},
        ]
    }

    results = []
    for i, test in enumerate([test1, test2, test3], 1):
        print(f"\n  테스트 {i}: {test['od']['from']} → {test['od']['to']} "
              f"({test['od']['departure']})")
        print(f"  {'-'*50}")

        all_probs = compute_all_probabilities(test["alternatives"], params)
        output = format_route_output(test["od"], test["alternatives"], all_probs)
        results.append(output)

        # 표 출력
        header = f"  {'경로':<20}"
        for ut in ["General", "Elderly", "Disabled", "Children"]:
            if ut in all_probs:
                header += f" {ut:>10}"
        print(header)

        for j, alt in enumerate(test["alternatives"]):
            row = f"  {alt['route_name']:<20}"
            for ut in ["General", "Elderly", "Disabled", "Children"]:
                if ut in all_probs:
                    row += f" {all_probs[ut][j]:>9.1%}"
            ride = alt['T_ride']
            walk = alt['T_walk']
            trans = int(alt['N_transfer'])
            row += f"  (차내={ride}분, 보행={walk}분, 환승={trans})"
            print(row)

    return results


def run_batch(otp_alternatives_path=None, output_path=None, params=None):
    """전체 OD 쌍에 대해 유형별 확률을 계산한다.

    otp_alternatives.parquet를 읽어 route_probabilities.json으로 출력.
    """
    if params is None:
        params = load_mnl_params()

    alts_path = otp_alternatives_path or (OUTPUT_DIR / "otp_alternatives.parquet")
    out_path = output_path or (RESULTS_DIR / "route_probabilities.json")

    print(f"\n  OTP 대안 로드: {alts_path.name}...")
    df = pd.read_parquet(alts_path)

    # chain_id 또는 od_id로 그룹화
    group_col = "chain_id" if "chain_id" in df.columns else "od_id"
    if group_col not in df.columns:
        print("  오류: chain_id 또는 od_id 컬럼을 찾을 수 없음")
        return

    required = ["T_ride", "T_walk", "N_transfer", "D_subway"]

    # 초 단위 → 분 단위 변환 (필요 시)
    for col in ["T_ride", "T_walk"]:
        if col not in df.columns:
            sec_col = col.replace("T_", "") + "_time_sec"
            if sec_col in df.columns:
                df[col] = df[sec_col] / 60.0

    # 컬럼명 매핑 시도
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"  경고: 누락 컬럼 {missing}, 컬럼 매핑 시도 중...")
        col_map = {
            "ride_time_sec": ("T_ride", 1/60),
            "walk_time_sec": ("T_walk", 1/60),
            "n_transfers": ("N_transfer", 1),
            "has_subway": ("D_subway", 1),
        }
        for src, (dst, factor) in col_map.items():
            if src in df.columns and dst not in df.columns:
                df[dst] = df[src] * factor

    if "D_peak" not in df.columns:
        df["D_peak"] = 0

    print(f"  {df[group_col].nunique():,}개 OD 그룹 처리 중...")

    summary_stats = {ut: {"mean_prob": [], "chosen_count": 0, "total": 0}
                     for ut in params}

    n_groups = df[group_col].nunique()
    results_sample = []  # JSON 출력용 처음 100개 저장

    for idx, (gid, group) in enumerate(df.groupby(group_col)):
        alternatives = group[required + ["D_peak"]].to_dict("records")
        if len(alternatives) < 2:
            continue

        all_probs = compute_all_probabilities(alternatives, params)

        # 통계 수집
        for ut, probs in all_probs.items():
            summary_stats[ut]["mean_prob"].append(max(probs))
            summary_stats[ut]["total"] += 1

        # 샘플 저장
        if len(results_sample) < 100:
            od_info = {"chain_id": str(gid)}
            output = format_route_output(od_info, alternatives, all_probs)
            results_sample.append(output)

        if (idx + 1) % 50000 == 0:
            print(f"    {idx+1:,}/{n_groups:,} 그룹 처리됨...")

    # 요약 출력
    print(f"\n  {'='*50}")
    print(f"  확률 배정 요약")
    print(f"  {'='*50}")
    print(f"  {'이용자 유형':<12} {'평균 최대확률':>14} {'그룹 수':>10}")
    for ut in params:
        stats = summary_stats[ut]
        if stats["mean_prob"]:
            mean_max = sum(stats["mean_prob"]) / len(stats["mean_prob"])
            print(f"  {ut:<12} {mean_max:>13.1%} {stats['total']:>10,}")

    # 결과 저장
    output_data = {
        "metadata": {
            "n_od_groups": n_groups,
            "n_user_types": len(params),
            "sample_size": len(results_sample),
        },
        "summary": {ut: {
            "mean_max_probability": (sum(s["mean_prob"]) / len(s["mean_prob"])
                                     if s["mean_prob"] else 0),
            "n_groups": s["total"]
        } for ut, s in summary_stats.items()},
        "sample_results": results_sample,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"\n  출력: {out_path}")

    return output_data


def main():
    parser = argparse.ArgumentParser(
        description="Phase 4: 확률적 경로 배정 모듈")
    parser.add_argument("--test-cases", action="store_true",
                        help="논문 테스트 케이스만 실행")
    parser.add_argument("--mnl-results", type=str, default=None,
                        help="MNL 결과 JSON 경로")
    parser.add_argument("--alternatives", type=str, default=None,
                        help="OTP 대안 parquet 경로")
    parser.add_argument("--output", type=str, default=None,
                        help="확률 결과 JSON 출력 경로")
    args = parser.parse_args()

    params = load_mnl_params(args.mnl_results)

    if args.test_cases:
        results = run_test_cases(params)
        out_path = RESULTS_DIR / "test_case_probabilities.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n  테스트 결과 저장: {out_path}")
    else:
        alts_path = Path(args.alternatives) if args.alternatives else None
        out_path = Path(args.output) if args.output else None
        run_batch(alts_path, out_path, params)


if __name__ == "__main__":
    main()
