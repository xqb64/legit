from __future__ import annotations

import textwrap

from legit.diff3 import Diff3

a = textwrap.dedent("""\
    celery
    salmon
    tomatoes
    garlic
    onions
    wine""")

b = textwrap.dedent("""\
    celery
    salmon
    garlic
    onions
    tomatoes
    wine""")

original = textwrap.dedent("""\
    celery
    garlic
    onions
    salmon
    tomatoes
    wine""")


merged = Diff3.merge(original, a, b)
print(merged.to_string())
