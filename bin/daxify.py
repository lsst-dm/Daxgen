#!/usr/bin/env python
import argparse

from daxgen import daxgen


def parse_args():
    """Parse command line arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('file', type=str,
                        help='File with persisted workflow.')
    parser.add_argument('-o', '--output', type=str, default='graph.dax',
                        help='Name of the output file.')
    parser.add_argument('-w', '--wrap', action='store_true',
                        help='Call tasks using a wrapper.')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()

    gen = daxgen.Daxgen()
    gen.read(args.file)
    if args.wrap:
        gen.wrap()
    gen.write(args.output)
