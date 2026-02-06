"""
Peak×N_transfer 양수 계수 원인 분석
"""
import pandas as pd
from pathlib import Path

# 경로 설정
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

# 데이터 로드
df = pd.read_parquet(OUTPUT_DIR / "model_input_train.parquet")
chosen = df[df['choice'] == 1]

print("=" * 60)
print("Peak×N_transfer 양수 계수 원인 분석")
print("=" * 60)

print("\n1. 기본 정보")
print(f"   총 행: {len(df):,}")
print(f"   체인 수: {df['chain_id'].nunique():,}")
print(f"   D_peak=1 비율: {df['D_peak'].mean()*100:.1f}%")

print("\n2. 첨두/비첨두 시간대별 선택된 경로의 평균 환승 횟수")
print(chosen.groupby('D_peak')['N_transfer'].mean())

print("\n3. 전체 대안의 D_peak별 N_transfer 평균")
print(df.groupby('D_peak')['N_transfer'].mean())

print("\n4. 첨두/비첨두 시간대별 N_transfer 분포 (선택된 경로)")
print("\n비첨두(D_peak=0):")
print(chosen[chosen['D_peak']==0]['N_transfer'].value_counts().sort_index())
print(f"평균: {chosen[chosen['D_peak']==0]['N_transfer'].mean():.3f}")

print("\n첨두(D_peak=1):")
print(chosen[chosen['D_peak']==1]['N_transfer'].value_counts().sort_index())
print(f"평균: {chosen[chosen['D_peak']==1]['N_transfer'].mean():.3f}")

print("\n5. 핵심 비교: 같은 OD에서 첨두 vs 비첨두 선택 차이")
# chain별로 D_peak와 N_transfer 확인
chain_summary = chosen.groupby('chain_id').agg({
    'D_peak': 'first',
    'N_transfer': 'first'
})
print(f"\n첨두시간대 체인: {(chain_summary['D_peak']==1).sum():,}")
print(f"비첨두시간대 체인: {(chain_summary['D_peak']==0).sum():,}")

print("\n첨두 vs 비첨두 선택된 경로의 N_transfer:")
print(chain_summary.groupby('D_peak')['N_transfer'].describe())

print("\n6. 상호작용 변수 확인")
df['Peak_N_transfer'] = df['D_peak'] * df['N_transfer']
print(f"Peak_N_transfer 비영(>0) 비율: {(df['Peak_N_transfer']>0).mean()*100:.1f}%")
print(f"Peak_N_transfer 평균 (D_peak=1일때만): {df[df['D_peak']==1]['N_transfer'].mean():.3f}")

print("\n" + "=" * 60)
print("분석 완료")
print("=" * 60)
