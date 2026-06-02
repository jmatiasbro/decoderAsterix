#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys

files = [
    './tail2axd',
    './shutdown_tail2ax.service'
]

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Error! invocar '{} SOURCE DEST'".format(__file__))
        sys.exit()

    src = sys.argv[1]
    dest = sys.argv[2]

    for i, fn in enumerate(files):
        try:
            with open(fn, 'r') as f:
                print("{}) Leyendo '{}'...".format(i + 1, fn))
                old_lines = [line for line in f.readlines()]
                new_lines = []
                for line in old_lines:
                    if src in line:
                        new_line = line.replace(src, dest)
                        print('{} -> {}'.format(line.rstrip('\n'), new_line.rstrip('\n')))
                    else:
                        new_line = line
                    new_lines.append(new_line)
            with open(fn, 'w') as f:
                print("{}) Escribiendo '{}'...".format(i + 1, fn))
                for line in new_lines:
                    f.write(line)
        except:
            print("{}) Error al procesar '{}'".format(i + 1, fn))
        print()
