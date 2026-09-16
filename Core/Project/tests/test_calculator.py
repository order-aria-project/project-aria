from tools.calculator_tools import calculate


def main() -> None:
    tests = [
        "196 * 874",
        "25 * 4",
        "17.5 / 100 * 840",
        "(25 + 5) * 3",
    ]

    for expression in tests:
        print(f"{expression} = {calculate(expression)}")


if __name__ == "__main__":
    main()