# runtime support; this module is star-imported in compiled bytecode.  Global variables

__to_del = ['__to_del', 'non_identifier']

def non_identifier(sym):
    def dec(f):
        globals()[sym] = f
        __to_del.append(f.func_name)
        return f
    return dec

@non_identifier('+')
def add(*args):
    return sum(args)

def write(obj):
    print obj

# clean up
for d in __to_del:
    del globals()[d]
del d
