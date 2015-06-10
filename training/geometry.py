__author__ = 'user'

from geom2d.point import Point

l = [Point(i, i*i) for i in range(-5, 6)]

l2 = [ ]

for el in l:
    l2.append(Point(el.x, -el.y))


print(l)
print(l2)