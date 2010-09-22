#-------------------------------------------------------------------------------
# bob: bytecode.py
#
# Bytecode objects and utilities for the Bob VM.
#
# Eli Bendersky (eliben@gmail.com)
# This code is in the public domain
#-------------------------------------------------------------------------------
from __future__ import print_function
from utils import pack_word
from expr import (Pair, Boolean, Symbol, Number, expr_repr)


OP_CONST    = 0x00
OP_LOADVAR  = 0x10
OP_STOREVAR = 0x11
OP_DEFVAR   = 0x12
OP_FUNCTION = 0x20
OP_POP      = 0x30
OP_JUMP     = 0x40
OP_FJUMP    = 0x41
OP_RETURN   = 0x50
OP_CALL     = 0x51


_opcode2str_map = {
    OP_CONST:       'CONST',
    OP_LOADVAR:     'LOADVAR',
    OP_STOREVAR:    'STOREVAR',
    OP_DEFVAR:      'DEFVAR',
    OP_FUNCTION:    'FUNCTION',
    OP_POP:         'POP',
    OP_JUMP:        'JUMP',
    OP_FJUMP:       'FJUMP',
    OP_RETURN:      'RETURN',
    OP_CALL:        'CALL',
}


def opcode2str(opcode):
    return _opcode2str_map[opcode]


class Instruction(object):
    """ A bytecode instruction. The opcode is one of the OP_... constants 
        defined above. 
        
        The argument will be arbitrary when used in a CompiledProcedure, but
        is always numeric when the Instruction is part of a CodeObject.
    """
    def __init__(self, opcode, arg):
        self.opcode = opcode
        self.arg = arg


class CodeObject(object):
    """ A code object is a Scheme procedure in its compiled and assembled form,
        suitable by execution by the VM.
      
        name: 
            Procedure name for debugging. Some procedures are anonymous (were
            defined by a 'lambda' and not 'define' and don't have a name).
            The top-level procedure that represents a whole file also doesn't
            have a name.
        
        args:
            A list of argument names (strings) for the procedure.
        
        code:
            A list of Instruction objects.
        
        constants:
            A list of constants. Constants are either Scheme expressions 
            (as defined by the types in the expr module) or CodeObjects (for
            compiled procedures). The instructions in the code reference 
            constants by their index in this list.
        
        varnames:
            A list of strings specifying variable names referenced in the code.
            The variables are referenced by their index in this list.
    """
    def __init__(self):
        self.name = ''
        self.args = []
        self.code = []
        self.constants = []
        self.varnames = []

    def __repr__(self, nesting=0):
        repr = ''
        prefix = ' ' * nesting
        
        repr += prefix + '----------\n'
        repr += prefix + 'CodeObject: ' + ('' if self.name is None else self.name) + '\n'
        repr += prefix + 'Args: ' + str(self.args) + '\n'

        for offset, instr in enumerate(self.code):
            repr += prefix + '  %4s %-12s ' % (offset, opcode2str(instr.opcode))
            
            if instr.opcode == OP_CONST:
                repr += '%4s {= %s}\n' % (instr.arg, expr_repr(self.constants[instr.arg]))
            elif instr.opcode in (OP_LOADVAR, OP_STOREVAR, OP_DEFVAR):
                repr += '%4s {= %s}\n' % (instr.arg, self.varnames[instr.arg])
            elif instr.opcode in (OP_FJUMP, OP_JUMP):
                repr += '%4s\n' % instr.arg
            elif instr.opcode == OP_CALL:
                repr += '%4s\n' % instr.arg
            elif instr.opcode in (OP_POP, OP_RETURN):
                repr += '\n'
            elif instr.opcode == OP_FUNCTION:
                # Recursively print out another code object
                repr += '%4s {=\n' % instr.arg
                repr += self.constants[instr.arg].__repr__(nesting + 8)
            else:
                assert False, "Unexpected opcode %s" % instr.opcode
        
        repr += prefix + '----------\n'
        return repr


# The serialization scheme is similar to Python's marshalling of code. Each
# object is serialized by prepending a single "type" byte, followed by 
# the object's serialized representation. See the code of Serializer for the
# details of how each type is serialized - it's pretty simple!
#
# A serialized bytecode consists of a string containing a magic constant
# followed by the serialized top-level CodeObject in the bytecode. This is 
# created by Serializer.serialize_bytecode
#
# The "magic" constant starting any serialized Bob bytecode consists of a 
# version in the high two bytes and 0B0B in the low two bytes.
#
MAGIC_CONST = 0x00010B0B

TYPE_NULL       = '0'
TYPE_BOOLEAN    = 'b'
TYPE_STRING     = 's'
TYPE_NUMBER     = 'n'
TYPE_PAIR       = 'p'
TYPE_INSTR      = 'i'
TYPE_SEQUENCE   = '['
TYPE_CODEOBJECT = 'c'


class Serializer(object):
    def __init__(self):
        # Allows dispatching serialization of Bob objects according to their
        # types
        #
        self._serialize_type_dispatch = {
            type(None):     self._s_null,
            Boolean:        self._s_boolean,
            Number:         self._s_number,
            Symbol:         self._s_symbol,
            Pair:           self._s_pair,
            Instruction:    self._s_instruction,
            CodeObject:     self._s_codeobject,
            type([]):       self._s_sequence,
            type(''):       self._s_string,
        }

    def serialize_bytecode(self, codeobject):
        """ Serialize a top-level CodeObject into a string that can be written
            into a file.
        """
        s = self._s_word(MAGIC_CONST)
        s += self._s_codeobject(codeobject)
        return s
    
    def _s_word(self, wordvalue):
        """ word - a 32-bit integer, serialized in 4 bytes as little-endian
        """
        return pack_word(wordvalue, big_endian=False)

    def _s_string(self, string):
        """ string - a Python string, used for representing names in code
            objects and for Bob Symbol objects.
        """
        return TYPE_STRING + self._s_word(len(string)) + string
           
    def _s_object(self, obj):
        """ Generic dispatcher for serializing an arbitrary object
        """
        return self._serialize_type_dispatch[type(obj)](obj)

    def _s_null(self, *args):
        return TYPE_NULL

    def _s_boolean(self, bool):
        return TYPE_BOOLEAN + ('\x01' if bool.value else '\x00')

    def _s_number(self, number):
        return TYPE_NUMBER + self._s_word(number.value)

    def _s_symbol(self, symbol):
        return self._s_string(symbol.value)

    def _s_pair(self, pair):
        return (    TYPE_PAIR + 
                    self._s_object(pair.first) + 
                    self._s_object(pair.second))

    def _s_sequence(self, seq):
        """ A sequence is just a Python list, used for serializing parts
            of code objects.
        """
        seq = ''.join(self._s_object(obj) for obj in seq)
        return TYPE_SEQUENCE + self._s_word(len(seq)) + seq

    def _s_instruction(self, instr):
        """ Instructions are mapped into words, with the opcode taking 
            the high byte and the argument the low 3 bytes.
        """
        arg = instr.arg or 0
        instr_word = (instr.opcode << 24) | (arg & 0xFFFFFF)
        return TYPE_INSTR + self._s_word(instr_word)
        
    def _s_codeobject(self, codeobject):
        s = TYPE_CODEOBJECT
        s += self._s_string(codeobject.name)
        s += self._s_sequence(codeobject.args)
        s += self._s_sequence(codeobject.constants)
        s += self._s_sequence(codeobject.varnames)
        s += self._s_sequence(codeobject.code)
        return s


#-----------------------------------------------------------------------------
if __name__ == '__main__':
    ss = Serializer()
    print(ss._s_boolean(Boolean(False)).encode('hex'))

    print(ss._s_object(Boolean(False)).encode('hex'))
    print(ss._s_object(Pair(Boolean(False), Symbol('abc'))).encode('hex'))
    
    print(ss._s_instruction(Instruction(OP_CALL, 34)).encode('hex'))


