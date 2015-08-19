from __future__ import print_function
import sys
import types
from bob.bytecode import (
        OP_CONST, OP_LOADVAR, OP_STOREVAR, OP_DEFVAR, OP_FUNCTION, OP_POP,
        OP_JUMP, OP_FJUMP, OP_RETURN, OP_CALL, Deserializer)
from bob import expr
from bob.utils import list_find_or_append
from byteplay import *

class FunctionMap(dict):

    def __call__(self, key):
        def dec(f):
            assert key not in self
            self[key] = f
            return f
        return dec


class Environment(object):
    
    def __init__(self, parent):
        self.parent = parent
        self.locals = []
        self.vars = {}  # name : (type, arg)

    def set_var(self, name, type, arg):
        assert name not in self.vars
        self.vars[name] = (type, arg)

    def local_index(self, name):
        try:
            type, arg = self.vars[name]
            assert type == 'LOCAL'
            return arg
        except KeyError:
            idx = list_find_or_append(self.locals, name)
            self.vars[name] = ('LOCAL', idx)
            return idx

    def lookup_var(self, name):
        try:
            return self.vars[name]
        except KeyError:
            if self.parent:
                return self.parent.lookup_var(name)
            else:
                raise KeyError("Unknown variable %r" % name)


class CodeGenerator(object):

    ## direct translation of each bobcode operand

    bob_ops = FunctionMap()

    @bob_ops(OP_CONST)
    def op_const(self, env, bobcode, instr):
        const = bobcode.constants[instr.arg]
        if expr.is_self_evaluating(const):
            # TODO; can LIST_APPEND be used here??
            self.instr(LOAD_FAST, "S")
            self.instr(LOAD_ATTR, "append")
            self.instr(LOAD_CONST, const.value)
            self.instr(CALL_FUNCTION, 1)
            self.instr(POP_TOP, None)
        else:
            assert 0  # not sure..

    @bob_ops(OP_LOADVAR)
    def op_loadvar(self, env, bobcode, instr):
        # TODO: might be from a closure
        name = bobcode.varnames[instr.arg]
        type, arg = env.lookup_var(name)
        if type == 'BUILTIN':
            arg(self, env, bobcode, instr)
        elif type == 'ARG':
            # XXX: assumes end-of-stack addressing; use frame instead?
            self.instr(LOAD_FAST, "S")
            self.instr(LOAD_ATTR, "append")
            self.instr(LOAD_FAST, "S")
            self.instr(LOAD_CONST, -1 - arg)
            self.instr(BINARY_SUBSCR, None)
            self.instr(CALL_FUNCTION, 1)
            self.instr(POP_TOP, None)
        elif type == 'LOCAL':
            self.instr(LOAD_FAST, "S")
            self.instr(LOAD_ATTR, "append")
            self.instr(LOAD_FAST, "F")
            self.instr(LOAD_CONST, 1)
            self.instr(BINARY_SUBSCR, None)
            self.instr(LOAD_CONST, arg)
            self.instr(BINARY_SUBSCR, None)
            self.instr(CALL_FUNCTION, 1)
            self.instr(POP_TOP, None)
        else:
            assert 0

    @bob_ops(OP_STOREVAR)
    def op_storevar(self, env, bobcode, instr):
        # TODO: need to set in appropriate scope; fail if not already defined
        self.instr(STORE_FAST, bobcode.varnames[instr.arg])

    @bob_ops(OP_DEFVAR)
    def op_defvar(self, env, bobcode, instr):
        idx = env.local_index(bobcode.varnames[instr.arg])
        self.instr(LOAD_FAST, "S")
        self.instr(LOAD_ATTR, "pop")
        self.instr(CALL_FUNCTION, 0)  # top of scheme stack -> value
        self.instr(LOAD_FAST, "F")
        self.instr(LOAD_CONST, 1)
        self.instr(BINARY_SUBSCR, None)  # locals array -> object
        self.instr(LOAD_CONST, idx)  # index
        self.instr(STORE_SUBSCR, None)

    @bob_ops(OP_POP)
    def op_pop(self, env, bobcode, instr):
        self.instr(POP_TOP, None)

    @bob_ops(OP_JUMP)
    def op_jump(self, env, bobcode, instr):
        self.instr(JUMP_ABSOLUTE, labels[instr.arg])

    @bob_ops(OP_FJUMP)
    def op_fjump(self, env, bobcode, instr):
        self.instr(POP_JUMP_IF_FALSE, labels[instr.arg])

    @bob_ops(OP_FUNCTION)
    def op_function(self, env, bobcode, instr):
        func_bobcode = bobcode.constants[instr.arg]
        label = Label()
        self.scheme_functions.append((label, func_bobcode, "unknown"))  # TODO too bad
        # XXX: how to do indirect jump?? linear search for now
        func_idx = len(self.scheme_functions)

        # build the function object (idx, closure) and put it on the
        # scheme stack
        self.instr(LOAD_FAST, "S")
        self.instr(LOAD_ATTR, "append")
        self.instr(LOAD_CONST, func_idx)
        self.instr(LOAD_CONST, None)  # TODO: closures
        self.instr(BUILD_TUPLE, 2)
        self.instr(CALL_FUNCTION, 1)
        self.instr(POP_TOP, None)

        #closure = Closure(func_bobcode, self.frame.env)
        #self.valuestack.push(closure)
        # TODO: closure
        #code.append((LOAD_CONST, py_code_obj_for(func_bobcode, toplevel=False)))

    @bob_ops(OP_CALL)
    def op_call(self, env, bobcode, instr):
        pass
        #code.append((CALL_FUNCTION, instr.arg))

    @bob_ops(OP_RETURN)
    def op_return(self, env, bobcode, instr):
        self.instr(RETURN_VALUE, None)

    builtins = FunctionMap()

    @builtins('+')
    def bi_add(self, env, bobcode, instr):
        # TODO: this is kinda wrong, for loadvar at least; inject this as a "library"
        # function and call it?
        n = instr.arg
        assert n > 0
        # pop the top N items from the scheme stack onto the python stack
        self.instr(LOAD_FAST, "S")
        for i in range(n):
            # TODO: is this ordering correct?
            self.instr(DUP_TOP, None)
            self.instr(LOAD_ATTR, "pop")
            self.instr(CALL_FUNCTION, 0)
            self.instr(ROT_TWO)
        # and call ADD N-1 times
        for i in range(n - 1):
            self.instr(BINARY_ADD)

    ## output functions

    def instr(self, op, arg):
        self.ops.append((op, arg))

    ## generate python bytecode for a scheme file

    def generate(self, bobcode):
        self.ops = []
        self.scheme_functions = [(Label(), bobcode, '__main__')]

        # global environment
        env = Environment(None)
        for name, method in self.builtins.iteritems():
            env.set_var(name, 'BUILTIN', method)

        # preamble
        self.instr(BUILD_LIST, 0)
        self.instr(STORE_FAST, "S")  # initialize stack as []
        self.instr(LOAD_CONST, None)
        self.instr(STORE_FAST, "F")  # initialize frame as None

        # loop over all as-yet undefined scheme functions; note that
        # this list grows as compilation proceeds, since the bob bytecode
        # is tree-structured
        i = 0
        while i < len(self.scheme_functions):
            label, bobcode, func_name = self.scheme_functions[i]
            self.instr(label, None)
            self._function(func_name, bobcode, env)
            i += 1

        c = Code(self.ops, [], [], False, False, False,
                 "__main__", '<scheme>>', 0, None)

        # postamble
        self.instr(LOAD_CONST, None)
        self.instr(RETURN_VALUE, None)  # and return as Python value

        print("result:")
        printcodelist(c.code)
        return c

    ## generate python bytecode for a single scheme function

    def _function(self, func_name, bobcode, env):
        print("compiling %s:" % func_name)
        print(bobcode)

        # make a new child environment for this function
        env = Environment(env)
        for i, arg in enumerate(bobcode.args):
            env.set_var(arg, 'ARG', i)

        # preamble: frame setup
        self.instr(LOAD_FAST, "F")
        self.instr(LOAD_CONST, None)
        self.instr(LOAD_CONST, None)
        self.instr(BUILD_LIST, 2)  # XXX: initialize with enough space; 2 is a guess
        self.instr(BUILD_LIST, 2)
        self.instr(STORE_FAST, "F")  # initialize frame as [parent, vars]
        self.instr(LOAD_FAST, "F")
        self.instr(PRINT_EXPR, None)

        # set up labels
        labels = {}
        for instr in bobcode.code:
            if instr.opcode == OP_JUMP or instr.opcode == OP_FJUMP:
                labels[instr.arg] = Label()

        for addr, instr in enumerate(bobcode.code):
            if addr in labels:
                self.instr((labels[addr], None))
            self.bob_ops[instr.opcode](self, env, bobcode, instr)

        # postamble: frame teardown
        self.instr(LOAD_FAST, "F")
        self.instr(LOAD_CONST, 0)
        self.instr(BINARY_SUBSCR, None)
        self.instr(STORE_FAST, "F")

def bob2py(filename=None):
    bytecode = open(filename, 'rb').read()
    bobcode = Deserializer().deserialize_bytecode(bytecode)

    f = types.FunctionType(
            CodeGenerator().generate(bobcode).to_code(),
            {})
    print(f())

if __name__ == "__main__":
    bob2py(sys.argv[1])
