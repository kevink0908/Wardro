"""Quick tests for the pure clothing logic — no internet needed.

Run:  python test_wardro.py
This isolates the part of Wardro you most want to be correct (the thresholds)
from the part that depends on the network (the API calls).
"""

from Wardro import outfit_advice

# Each tuple: (temperature, a keyword we expect to appear in the advice).
CASES = [
    (25, "jacket"),     # < 40  -> thick jacket + accessories
    (39, "beanie"),     # boundary just under 40
    (40, "sweater"),    # 40-59 -> sweater
    (59, "sweater"),
    (65, "windbreaker"),# 60-69 -> long sleeve / windbreaker
    (75, "t-shirt"),    # 70-79 -> t-shirt + light layer
    (85, "Short-sleeve"),  # 80-89
    (95, "shorts"),     # 90-99 -> short sleeve + shorts
    (105, "heatstroke"),# 100+  -> stay indoors
]


def main():
    passed = 0
    for temp, keyword in CASES:
        result = outfit_advice(temp)
        ok = keyword.lower() in result.lower()
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {temp:>3}°F -> {result}")
        if ok:
            passed += 1
        else:
            print(f"        expected to find '{keyword}'")
    print(f"\n{passed}/{len(CASES)} cases passed.")
    if passed != len(CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
