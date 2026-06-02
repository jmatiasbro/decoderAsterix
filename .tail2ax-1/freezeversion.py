#!/usr/bin/env python
# -*- coding: utf-8 -*-
import time

SCRIPT = './tail2ax.py'

ver_actual = ''
build_actual = ''
ver_line = ''
build_line = ''

lines = []
f = open(SCRIPT)
for line in f.readlines():
    if 'VERSION = ' in line:
        ver_line = line
        ver_actual = line.split('=')[1].strip()
    elif 'BUILD = ' in line:
        build_line = line
        build_actual = line.split('=')[1].strip()
    else:
        pass
    lines.append(line)
f.close()

print(">>> version actual %s. Build %s" % (ver_actual, build_actual))
ver_new = ''
while not ver_new:
    ver_new = input(">>> nueva version: ")

build_new = time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))

new_ver_line = "VERSION = '%s'\n" % ver_new
new_build_line = "BUILD = '%s'\n" % build_new
print("freezing '%s'" % SCRIPT)
print('>>> {}>>> {}'.format(new_ver_line, new_build_line))


f = open(SCRIPT, 'w')
for n in range(len(lines)):
    if lines[n] == ver_line:
        line = new_ver_line
    elif lines[n] == build_line:
        line = new_build_line
    else:
        line = lines[n]
    f.write(line)
f.close()
