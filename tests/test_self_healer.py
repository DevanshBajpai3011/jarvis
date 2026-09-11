import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from brain.self_healer import SelfHealer



async def run_exception_tests():
    healer = SelfHealer()
    print("=== STARTING AGENTIC SELF-HEALING TEST SUITE ===")

    # Test Case 1: Division by Zero Exception
    code_zero_div = "result = 10 / 0"
    print("\n[Test 1] Executing zero division code...")
    try:
        exec(code_zero_div)
    except Exception as e:
        traceback_str = str(e)
        print(f"Caught Exception: {traceback_str}")
        repaired_code = await healer.repair_code(code_zero_div, traceback_str)
        print(f"Repaired Code Patch:\n{repaired_code}")

    # Test Case 2: Missing Target Path / FileNotFoundError
    code_file = "open('Z:/invalid_dir/test.txt', 'w').write('hello')"
    print("\n[Test 2] Executing invalid path write...")
    try:
        exec(code_file)
    except Exception as e:
        traceback_str = str(e)
        print(f"Caught Exception: {traceback_str}")
        repaired_code = await healer.repair_code(code_file, traceback_str)
        print(f"Repaired Code Patch:\n{repaired_code}")


if __name__ == "__main__":
    asyncio.run(run_exception_tests())
