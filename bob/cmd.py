#-------------------------------------------------------------------------------
# bob: cmd.py
#
# Command-line functions
#
# Dustin J. Mitchell (dustin@v.igoro.us)
# This code is in the public domain
#-------------------------------------------------------------------------------

from __future__ import print_function

import os, sys
import argparse
import byteplay
import marshal
import imp
import struct
import dis
import time

from bob.compiler import compile_code
from bob.bobparser import BobParser
from bob.interpreter import (interpret_code, BobInterpreter, Procedure, expr_repr)
from bob import py3compat

def _write_code(code, filename):
    with open(filename, "wb") as f:
        f.write(imp.get_magic())
        f.write(struct.pack('i', time.time()))
        marshal.dump(code, f)

def _read_code(filename):
    with open(filename, "rb") as f:
        magic, datestamp = struct.unpack('ii', f.read(8))
        code = marshal.load(f)
        return magic, datestamp, code

def compile_file(filename=None, out_filename=None, disassemble=False):
    """ Given the name of a .scm file, compile it with the Bob compiler
        to produce a corresponding .bobc file.
    """
    if not filename:
        filename = sys.argv[1]
    code_str = open(filename).read()
    codeobject = compile_code(code_str)
    if disassemble:
        byteplay.printcodelist(codeobject.code)
        return

    # Create the output file
    if not out_filename:
        filename_without_ext = os.path.splitext(filename)[0]
        out_filename = filename_without_ext + '.pyc'

    _write_code(codeobject.to_code(), out_filename)

def interactive_interpreter():
    """ Interactive interpreter 
    """
    interp = BobInterpreter() # by default output_stream is sys.stdout
    parser = BobParser()
    print("Interactive Bob interpreter. Type a Scheme expression or 'quit'")

    while True:
        inp = py3compat.input("[bob] >> ")
        if inp == 'quit':
            break
        parsed = parser.parse(inp)
        val = interp.interpret(parsed[0])
        if val is None:
            pass
        elif isinstance(val, Procedure):
            print(": <procedure object>")
        else:
            print(":", expr_repr(val))

def interpret_file(filename=None):
    if not filename:
        filename = sys.argv[1]
    with open(filename) as f:
        interpret_code(f.read())

def run_compiled(filename=None):
    """ Given the name of a compiled Bob file (.bobc), run it with the 
        Bob VM with output redirected to stdout.
    """
    if not filename:
        filename = sys.argv[1]
    magic, datestamp, code = _read_code(filename)
    rv = eval(code, {'+': lambda *args: sum(args), 'write': lambda *args: print(args)})
    if rv is not None:
        print("Result:", rv)

def disassemble_file(filename=None):
    """ Given the name of a compiled file (.pyc), display its operands.
    """
    if not filename:
        filename = sys.argv[1]
    magic, datestamp, code = _read_code(filename)
    print("Magic: {:#08x}".format(magic))
    print("Datestamp: {}".format(datestamp))
    byteplay.printcodelist(byteplay.Code.from_code(code).code)

def main():
    parser = argparse.ArgumentParser(
        description='Bob is a suite of implementations of the Scheme language in Python')
    parser.add_argument('-c', '--compile',
            help="Compile a scheme file to bytecode", action='store_true')
    parser.add_argument('-d', '--disassemble',
            help="Disassemble a bytecode file", action='store_true')
    parser.add_argument('-o', '--output',
            help="Output filename for copmilation", type=str)
    parser.add_argument('filename', nargs="?", help='filename to compile (-c) or run')

    args = parser.parse_args(sys.argv[1:])

    if not args.filename:
        if args.compile:
            parser.error("specify a source file to compile")
        interactive_interpreter()
    else:
        is_scm = args.filename.endswith('.scm')
        if args.compile:  # and possibly args.disassemble
            if not is_scm:
                parser.error("can only compile .scm files")
            compile_file(args.filename, args.output, args.disassemble)
        elif args.disassemble:
            if is_scm:
                parser.error("can only disassemble bytecode files")
            disassemble_file(args.filename)
        else:
            if is_scm:
                interpret_file(args.filename)
            else:
                run_compiled(args.filename)
