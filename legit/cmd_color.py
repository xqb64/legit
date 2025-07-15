from __future__ import annotations

SGR_CODES: dict[str, int] = {
    "normal": 0,
    "bold": 1,
    "dim": 2,
    "italic": 3,
    "ul": 4,
    "reverse": 7,
    "strike": 9,
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
}


class Color:
    @staticmethod
    def format(style: str | list[str], text: str) -> str:
        if isinstance(style, str):
            names = [style]
        else:
            names = list(style)

        try:
            codes = [SGR_CODES[name] for name in names]
        except KeyError as e:
            raise ValueError(f"Unknown style name: {e}") from e

        color_is_set = False
        for i, code in enumerate(codes):
            if 30 <= code <= 37:
                if color_is_set:
                    codes[i] += 10
                color_is_set = True

        code_str = ";".join(str(c) for c in codes)
        return f"\x1b[{code_str}m{text}\x1b[0m"
