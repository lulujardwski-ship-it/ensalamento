"""Compile the C++ engine, without downloading or executing a remote build script."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', help='Path to g++ or clang++')
    parser.add_argument('--zig', help='Path to a portable Zig executable; uses zig c++')
    parser.add_argument('--include', help='Directory containing nlohmann/json.hpp')
    args = parser.parse_args()
    compiler = args.compiler or os.getenv('CXX') or shutil.which('g++') or shutil.which('clang++')
    if not args.zig and not compiler:
        parser.error('Install g++/clang++ and nlohmann-json3-dev, or use --zig and --include.')
    command = [args.zig, 'c++'] if args.zig else [compiler]
    output = ROOT / 'core' / ('ensalamento-core.exe' if os.name == 'nt' else 'ensalamento-core')
    command += ['-std=c++17', '-O2', '-Wall', '-Wextra', '-Wpedantic']
    if args.include:
        command += ['-I', str(Path(args.include).resolve())]
    command += [str(ROOT / 'core' / 'main.cpp'), '-o', str(output)]
    subprocess.run(command, check=True, cwd=ROOT)
    print(f'Compiled: {output}')


if __name__ == '__main__':
    main()
