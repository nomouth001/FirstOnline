#!/usr/bin/env python3
"""차트 생성 함수 수정 테스트"""

from services.chart_service import generate_chart

def test_chart_generation():
    """차트 생성 함수 테스트"""
    try:
        result = generate_chart('AAPL')
        print('Chart generation result:')
        print(f'Charts: {result["charts"]}')
        print(f'Data shape: {result["data"].shape if not result["data"].empty else "Empty"}')
        print(f'End date: {result["end_date"]}')
        print('\nTest PASSED: Chart generation returns correct format')
        return True
    except Exception as e:
        print(f'Test FAILED: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_chart_generation() 