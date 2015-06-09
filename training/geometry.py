__author__ = 'user'

from geom2d.point import *

l1 = [Point(3, 1), Point(0, 0), Point(1, 2)]


l2 = sorted(l1, cmp=lambda p1, p2: cmp=(p1.y, p2.y))

print(l1)
print(l2)
