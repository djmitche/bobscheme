#-------------------------------------------------------------------------------
# bob: compiler.py
#
# Scheme compiler. 
#
# Eli Bendersky (eliben@gmail.com)
# This code is in the public domain
#-------------------------------------------------------------------------------
from __future__ import print_function

import contextlib

from .utils import flatten
from .expr import *
from .bobparser import BobParser
from byteplay import *


DEBUG = False


class GlobalFrame(object):

    def __init__(self):
        self.vars = set()

    def load(self, name):
        return [(LOAD_GLOBAL, name)]

    def store(self, name):
        self.vars.add(name)
        return [(STORE_GLOBAL, name)]


class LocalFrame(object):

    def __init__(self, parent):
        self.parent = parent
        self.vars = []

    def load(self, name):
        if name in self.vars:
            return [(LOAD_FAST, name)]
        else:
            return self.parent.load(name)

    def store(self, name):
        self.vars.add(name)
        return [(STORE_FAST, name)]


class BobCompiler(object):
    """ A Scheme compiler. 
    """
    class CompileError(Exception): pass

    def __init__(self):
        self.labelstate = 0
        
    def compile(self, exprlist):
        """ Compile a list of parsed expressions (what's returned by 
            BobParser.parse) into a single argument-less Code object 
        """
        self.frame = GlobalFrame()
        compiled_exprs = self._comp_exprlist(exprlist)
        module = self._instr_seq(
                compiled_exprs,
                self._instr(RETURN_VALUE))
        return Code(CodeList(module), [], [], False, False, False,
                    "__main__", '<scheme>>', 0, None)

    def _instr(self, opcode, arg=None):
        """ A helper creator for instructions.
        """
        return [(opcode, arg)]
        
    def _instr_seq(self, *args):
        """ Create a sequence (list) of instructions, where each argument can
            be either a single instruction or a sequence of instructions.
        """
        return list(flatten(args))

    def _comp(self, expr):
        """ Compile an expression.
        
            Always returns a (Python) list of instructions.
        """
        if DEBUG: print('~~~~ Comp called on %s [%s]' % (expr_repr(expr), type(expr)))

        if is_self_evaluating(expr):
            return self._instr(LOAD_CONST, expr.value)
        elif is_variable(expr):
            # TODO: need to do some static analysis to see where this var comes from
            # - closure
            # - local
            # - global
            return self._instr(LOAD_NAME, expr.value.encode('utf-8'))  # XXX: assume global
        elif is_quoted(expr):
            return self._instr(OP_CONST, text_of_quotation(expr)) # XXX: need to build value?
        elif is_assignment(expr):
            return self._instr_seq(
                            self._comp(assignment_value(expr)),
                            self._instr(STORE_FAST, assignment_variable(expr).value.encode('utf-8')))
        elif is_definition(expr):
            return self._comp_definition(expr)
        elif is_if(expr):
            return self._comp_if(expr)
        elif is_cond(expr):
            return self._comp(convert_cond_to_ifs(expr))
        elif is_let(expr):
            return self._comp(convert_let_to_application(expr))
        elif is_lambda(expr):
            return self._comp_lambda(expr)
        elif is_begin(expr):
            return self._comp_begin(begin_actions(expr))
        elif is_application(expr):
            return self._comp_application(expr)
        else:
            raise self.CompileError("Unknown expression in COMPILE: %s" % expr)
    
    @contextlib.contextmanager
    def _local_frame(self):
        parent = self.frame
        self.frame = f = LocalFrame(parent)
        yield f
        self.frame = parent

    def _comp_lambda(self, expr):
        # The lambda parameters are in Scheme's nested Pair format. Convert
        # them into a normal Python list
        #
        args = expand_nested_pairs(lambda_parameters(expr))
        arglist = []
        
        # Some sanity checking: only symbol arguments are supported
        #
        for sym in args:
            if isinstance(sym, Symbol):
                arglist.append(sym.value)
            else:
                raise self.CompileError("Expected symbol in argument list, got: %s" % expr_repr(sym))
        
        # For the code - compile lambda body as a sequence and append a RETURN
        # instruction to the end
        #
        with self._local_frame():
            ops = self._instr_seq(self._comp_begin(lambda_body(expr)),
                                self._instr(RETURN_VALUE))
        proc_code = Code(CodeList(ops), [], arglist, False, False, True, "lambda", "<<scheme>>", 0, None)
        
        return self._instr_seq(
                self._instr(LOAD_CONST, proc_code),
                self._instr(MAKE_FUNCTION, 0))

    def _comp_begin(self, exprs):
        # To compile a 'begin' we append the compiled versions of all the 
        # expressions in it, with a POP instruction inserted after each one 
        # except the last. 
        #
        exprlist = expand_nested_pairs(exprs, recursive=False)
        return self._comp_exprlist(exprlist)

    def _comp_exprlist(self, exprlist):
        instr_pop_pairs = list(self._instr_seq(self._comp(expr), self._instr(POP_TOP)) for expr in exprlist)
        instrs = self._instr_seq(*instr_pop_pairs)        
        return instrs[:-1] if len(instrs) > 0 else instrs

    def _comp_definition(self, expr):        
        compiled_val = self._comp(definition_value(expr))
        var = definition_variable(expr)
        
        # If the value is a procedure (a lambda), assign its .name attribute
        # to the variable name (for debugging)
        #
        # TODO
#        if (    isinstance(compiled_val[-1], Instruction) and 
#                isinstance(compiled_val[-1].arg, CompiledProcedure)):
#            compiled_val[-1].arg.name = var.value
        
        return self._instr_seq(
                compiled_val,
                self._instr(STORE_FAST, var.value.encode('utf-8')),
                self._instr(LOAD_CONST, None),  # so the expression has a value
                )

    def _comp_if(self, expr):
        label_else = Label()
        label_after_else = Label()
        
        return self._instr_seq(
                        self._comp(if_predicate(expr)),
                        self._instr(POP_JUMP_IF_FALSE, label_else),
                        self._comp(if_consequent(expr)),
                        self._instr(JUMP_ABSOLUTE, label_after_else),
                        [label_else],
                        self._comp(if_alternative(expr)),
                        [label_after_else])
    
    def _comp_application(self, expr):
        args = expand_nested_pairs(application_operands(expr), recursive=False)
        compiled_args = self._instr_seq(*[self._comp(arg) for arg in args])
        compiled_op = self._comp(application_operator(expr))
        return self._instr_seq(
                        compiled_op,
                        compiled_args,
                        self._instr(CALL_FUNCTION, len(args)))


def compile_code(code_str):
    """ Convenience function for compiling (& assembling) a string containing 
        Scheme code into a code object.
    """
    parsed_exprs = BobParser().parse(code_str)    
    compiled = BobCompiler().compile(parsed_exprs)
    return compiled


#-------------------------------------------------------------------------------
if __name__ == '__main__':
    pass
