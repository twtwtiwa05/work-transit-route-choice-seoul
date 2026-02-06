import json
import re

def fix_json_escapes(line):
    """
    polyline에서 백슬래시로 끝날 때 JSON 파싱 에러 해결

    문제: polyline이 \로 끝나면 \"} 가 되어 "가 이스케이프됨
    해결: \"} → \\"} (백슬래시 추가해서 \\는 이스케이프된 백슬래시, "는 문자열 종료)
    """
    # \와 "}를 찾아서 \\"}로 변경 (백슬래시 하나 추가)
    # pattern: 백슬래시 + 따옴표 + (중괄호/대괄호/콤마)
    # replacement: 백슬래시 2개 + 따옴표 + (중괄호/대괄호/콤마)
    pattern = r'\\("[\}\]\,])'
    replacement = r'\\\\\1'  # 백슬래시 2개 + 캡처그룹
    fixed = re.sub(pattern, replacement, line)
    return fixed

# 테스트 1: 간단한 문자열로 확인
print("=== 패턴 테스트 ===")
test = r'{"points":"abc\"}}'  # polyline이 \로 끝남
fixed = fix_json_escapes(test)
print(f"원본: {repr(test)}")
print(f"수정: {repr(fixed)}")
try:
    json.loads(fixed)
    print("파싱: OK")
except json.JSONDecodeError as e:
    print(f"파싱: Error - {e.msg}")

print()

# 테스트 2: 실제 문제 라인
print("=== 실제 파일 테스트 ===")
problem_lines = [110419, 110371, 110390, 110394, 110397]

with open(r'C:\Users\USER\OneDrive\Desktop\연구실\강릉ITS\korean-otp\batch_result_iter0.ndjson', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i+1 in problem_lines:
            fixed = fix_json_escapes(line)
            try:
                json.loads(fixed)
                print(f'Line {i+1}: OK')
            except json.JSONDecodeError as e:
                print(f'Line {i+1}: Error - {e.msg} at pos {e.pos}')
                # 에러 위치 주변 출력
                start = max(0, e.pos - 30)
                end = min(len(fixed), e.pos + 30)
                print(f'  Context: {repr(fixed[start:end])}')
        if i+1 > max(problem_lines):
            break
