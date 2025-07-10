from __future__ import annotations

from legit.revision import Revision

revstr = "@^"

print(Revision.parse(revstr))
