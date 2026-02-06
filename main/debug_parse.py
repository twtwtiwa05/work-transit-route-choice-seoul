import json
import re

def fix_json_escapes(line):
    """step4에서 사용하는 fix 함수 - points 필드 제거"""
    fixed = re.sub(r'"points":"[^"]*(?:\\.[^"]*)*"', '"points":""', line)
    return fixed

# 문제 라인들 테스트 (이전 + 새로운 것들)
problem_lines = [37669, 37672, 37682, 37688, 37693, 37696, 37697, 110371, 110390, 110394, 110397, 110419]

with open(r'C:\Users\USER\OneDrive\Desktop\연구실\강릉ITS\korean-otp\batch_result_iter0.ndjson', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i + 1 in problem_lines:  # 1-indexed
            print(f'=== Line {i+1} ===')

            # 원본 테스트
            try:
                json.loads(line)
                print('  원본: OK')
            except json.JSONDecodeError as e:
                print(f'  원본 에러: {e.msg} at pos {e.pos}')
                print(f'  근처: {repr(line[max(0,e.pos-20):e.pos+20])}')

            # fix 적용 후 테스트
            fixed = fix_json_escapes(line)
            try:
                json.loads(fixed)
                print('  수정 후: OK')
            except json.JSONDecodeError as e:
                print(f'  수정 후 에러: {e.msg} at pos {e.pos}')
                print(f'  근처: {repr(fixed[max(0,e.pos-20):e.pos+20])}')

            print()

        if i + 1 > max(problem_lines):
            break
