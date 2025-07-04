from legit.revision import Revision

revstr = "master~5"

print(Revision.parse(revstr))
