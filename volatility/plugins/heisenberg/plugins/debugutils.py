import volatility.plugins.heisenberg.core as heisenberg
import volatility.utils as utils
import volatility.obj as obj
import struct
import gdb
import sys
import distorm3
from volatility.plugins.heisenberg.core import Breakpoint

import pickle

XPSP3_CR3_SWITCH = 0x804db9ce

def get_reg(reg):
    return (reg, int(gdb.execute('info register {0}'.format(reg),False, True).split('\t')[0].split(' ')[-1],0))


class ViewRegisters(heisenberg.AbstractHeisenbergPlugin):
    name = 'regs'

    def calculate(self):
        regs = {}
        for reg in ["eax", "ebx", "ecx", "edx", "edi", "esi", "ebp", "esp", "eip"]:
#            regs.append(get_reg(reg))
            regs[reg] = self.functions.gr.calculate(reg)
        return regs

    def render_text(self, regs):
        for reg in regs.keys():
            print("%s: 0x%08x" % (reg, regs[reg]))

class ViewRegisters2(heisenberg.AbstractHeisenbergPlugin):
    name = 'regs2'

    def calculate(self):
        regs = {}
        for reg in ["cs", "ss", "ds", "es", "fs", "gs"]:
#            regs.append(get_reg(reg))
            regs[reg] = self.functions.gr.calculate(reg)
        return regs

    def render_text(self, regs):
        for reg in regs.keys():
            print("%s: 0x%08x" % (reg, regs[reg]))

class ViewRegisters3(heisenberg.AbstractHeisenbergPlugin):
    name = 'regs3'

    def calculate(self):
        eflags = self.functions.gr.calculate("eflags")
        regs = {}

        regs["c"] = eflags & 0x1
        eflags >>= 1
        #reserved
        eflags >>= 1
        regs["p"] = eflags & 0x1
        eflags >>= 1
        #reserved
        eflags >>= 1
        regs["a"] = eflags & 0x1
        eflags >>= 1
        #reserved
        eflags >>= 1
        regs["z"] = eflags & 0x1
        eflags >>= 1
        regs["s"] = eflags & 0x1
        eflags >>= 1
        regs["t"] = eflags & 0x1
        eflags >>= 1
        regs["i"] = eflags & 0x1
        eflags >>= 1
        regs["d"] = eflags & 0x1
        eflags >>= 1
        regs["o"] = eflags & 0x1
        eflags >>= 1
        return regs

    def render_text(self, regs):
        for reg in regs.keys():
            print("%s: 0x%08x" % (reg, regs[reg]))

class ViewRegisters4(heisenberg.AbstractHeisenbergPlugin):
    name = 'regs4'

    def calculate(self):
        regs = []
        for reg in ["cr3"]:
            regs.append(get_reg(reg))
        return regs

    def render_text(self, regs):
        for reg in regs:
            print("%s: 0x%08x" % (reg[0], reg[1]))

class GetRegister(heisenberg.AbstractHeisenbergApiFunction):
    name = 'gr'

    def calculate(self, regname):
        return int(gdb.execute('info register {0}'.format(regname),False, True).split('\t')[0].split(' ')[-1],0)

class SetBpDtb(heisenberg.AbstractHeisenbergApiFunction):
    name = 'bd'

    def calculate(self, address, cr3 = None):
        if(cr3 is None): cr3 = self.functions.gr("cr3")
        gdb.execute('b *{0} if $cr3=={1}'.format(address, cr3),False, True)


class StackUnwind(heisenberg.AbstractHeisenbergPlugin):
    name = 'su'

    def calculate(self):
        esp = self.core.functions.gr("esp")
        space = (self.core.reading_context or self.core.current_context) # or self.functions.get_context()).get_process_address_space() 
        data = space.read(esp, 0x10*0x4)
        entry_count = int(len(data)/4)
        fmts = "<"
        for i in range(0,entry_count):
            fmts += "I"
        stack_entries = struct.unpack(fmts, data)
        return stack_entries

    def render_text(self, stack_entries):
        for entry in stack_entries:
            print("0x%08x" % entry)

class Continue(heisenberg.AbstractHeisenbergPlugin):
    name = 'c'

    def calculate(self, location=None, dtb = None):
        gdb.execute('c',False, True)

class LoadBpList(heisenberg.AbstractHeisenbergPlugin):
    name = 'bpl'

    def calculate(self, path, eproc):
        f = open(path, "r")
        for bp in f.readlines():
            print("Setting bp on: %s" % bp[:-1])
            self.core.functions.b.calculate(bp[:-1], eproc)
        f.close()

class SetBp(heisenberg.AbstractHeisenbergPlugin):
    name = 'b'

    def calculate(self, location=None, eproc = None):
        if(location == None):
            location = self.core.functions.gr("eip")

        if(isinstance(location, int)):
            address = location
        elif(isinstance(location, str)):
            try:
                address = self.core.symbols_by_name[location]
            except KeyError:
                print("No symbol found")
                return

        if(eproc is not None): 
            dtb = self.functions.e2d.calculate(eproc)
#            gdb.execute('b *{0} if $cr3=={1}'.format(address, dtb),False, True)
        else:
            dtb = None
#            dtb = self.functions.e2d.calculate()
#            gdb.execute('b *{0}'.format(address),False, True)
        self.core.bp_index.addBpt(Breakpoint(address), dtb)

#        gdb.execute('b *{0} if $cr3=={1}'.format(address, dtb),False, True)
#        self.core.bpts[address] = dtb

#class DelBp(heisenberg.AbstractHeisenbergPlugin):
#    name = 'db'
#
#    def calculate(self, bp_id):
#        gdb.execute('del {0}'.format(bp_id),False, True)
#        #delete from list

class IterateList(heisenberg.AbstractHeisenbergApiFunction):
    name = 'itl'

    def calculate(self, head, objname, offset = -1, fieldname = None, forward = True):
        """Traverse a _LIST_ENTRY.
 
        Traverses a _LIST_ENTRY starting at virtual address head made up of
        objects of type objname. The value of offset should be set to the
        offset of the _LIST_ENTRY within the desired object."""
 
        vm = self.core.current_context.get_process_address_space()
        seen = set()

        if fieldname:
            offset = vm.profile.get_obj_offset(objname, fieldname)
            #if typ != "_LIST_ENTRY":
            #    print ("WARN: given field is not a LIST_ENTRY, attempting to "
            #           "continue anyway.")
 
        lst = obj.Object("_LIST_ENTRY", head, vm)
        seen.add(lst)
        if not lst.is_valid():
            return
        while True:
            if forward:
                lst = lst.Flink
            else:
                lst = lst.Blink
 
            if not lst.is_valid():
                return
 
            if lst in seen:
                break
            else:
                seen.add(lst)
 
            nobj = obj.Object(objname, lst.obj_offset - offset, vm)
            yield nobj

class WaitForEproc(heisenberg.AbstractHeisenbergPlugin):
    name = 'eprocWait'

    def calculate(self, eproc):
        cr3 = self.functions.e2d.calculate(eproc)
        location = "*0x%x" % XPSP3_CR3_SWITCH
        gdb.execute('b {0} if $cr3 == {1}'.format(location, cr3),False, True)
        gdb.execute('c')
        # removing bp, ugly
        if(gdb.breakpoints()[-1].location == location):
            gdb.breakpoints()[-1].delete()
        return self.functions.gr("cr3")

    def render_text(self, cr3):
        print("Thread arrived, current DTB: 0x%x" % cr3)

class ProcessName2Eproc(heisenberg.AbstractHeisenbergPlugin):
    name = 'pn2e'

    def calculate(self, process_name = "System"):
        processes = self.core.functions.ps.calculate()
        for process in processes:
            if(process_name in process.ImageFileName.v()):
                return process.v()

    def render_text(self, eproc):
        print('EPROC: 0x%x' % (eproc))


class Eproc2Dtb(heisenberg.AbstractHeisenbergPlugin):
    name = 'e2d'

    def calculate(self, eproc_addr = None):
        if(eproc_addr == None):
            if(self.core.current_context == None):
                self.core.functions.cc.calculate()
            context = self.core.current_context
        else:
            context = self.functions.get_context(eproc_addr)
        dtb = context.Pcb.DirectoryTableBase.v()
        return dtb

    def render_text(self, dtb):
        print('DTB: 0x%x' % (dtb))

class Eproc2Peb(heisenberg.AbstractHeisenbergPlugin):
    name = 'e2peb'
    
    def calculate(self, eproc_addr):
        eproc = self.functions.create_process_object(eproc_addr)
        peb = eproc.Peb
        return peb

    def render_text(self, peb):
        print('PEB: 0x%x' % (peb.v()))


class Eproc2ImageBase(heisenberg.AbstractHeisenbergPlugin):
    name = 'e2ib'

    def calculate(self, eproc_addr):
        peb = self.functions.e2peb.calculate(eproc_addr)
        return peb.ImageBaseAddress
        
    def render_text(self, ib):
        print('ImageBase: 0x%x' % (ib.v()))

class Eproc2InMemoryOrderModuleList(heisenberg.AbstractHeisenbergPlugin):
    name = 'e2imoml'

    def calculate(self, eproc_addr):
        eproc = self.functions.create_process_object(eproc_addr)
        modules = eproc.get_mem_modules()
        return modules
        
    def render_text(self, modules):
        print("Process modules (in memory order):")
        modules.next() # drop first empty
        for module in modules:
            print("[0x%x]\t%s" % (module.DllBase, module.BaseDllName))

class ImageName2DosHeader(heisenberg.AbstractHeisenbergPlugin):
    name = 'in2dh'

    def calculate(self, name):
        modules = self.functions.e2imoml.calculate(self.core.current_context.v())
        found = None
        for module in modules:
            if(str(module.BaseDllName).upper() == name.upper()):
                found = module
                break

        if(found == None or not module.is_valid()): return None # maybe we should change to NoneObject?
        dh = obj.Object("_IMAGE_DOS_HEADER", offset = found.DllBase.v(), vm = self.core.current_context.get_process_address_space())
        return dh

    def render_text(self, dh):
        print("0x%x" % dh.v())

"""
class ImageBase2Module(heisenberg.AbstractHeisenbergPlugin):
    name = 'ib2mod'

    def calculate(self, ib_addr):
        modules = self.functions.e2imoml.calculate(self.core.current_context.v())
        found = None
        for module in modules:
            if(module.DllBase == ib_addr):
                found = module
                break

        if(found == None or not module.is_valid()): return None # maybe we should change to NoneObject?
        return found

    def render_text(self, mod):
        print("0x%x" % mod.v())
"""

class ImageBase2DosHeader(heisenberg.AbstractHeisenbergPlugin):
    name = 'ib2dh'

    def calculate(self, ib_addr):
        dh = obj.Object("_IMAGE_DOS_HEADER", offset = ib_addr, vm = self.core.current_context.get_process_address_space())
        return dh

    def render_text(self, dh):
        print('_IMAGE_DOS_HEADER off: 0x%x' % (dh.v()))

class ImageBase2NtHeaders(heisenberg.AbstractHeisenbergPlugin):
    name = 'ib2nth'

    def calculate(self, ib_addr):
        dh = self.functions.ib2dh.calculate(ib_addr)
        nth = obj.Object("_IMAGE_NT_HEADERS", offset = ib_addr + dh.e_lfanew.v(), vm = self.core.current_context.get_process_address_space())
        return nth
        
    def render_text(self, nth):
        print('_IMAGE_NT_HEADERS off: 0x%x' % (nth.v()))

class ImageBase2OptionalHeader(heisenberg.AbstractHeisenbergPlugin):
    name = 'ib2oh'

    def calculate(self, ib_addr):
        nth = self.functions.ib2nth.calculate(ib_addr)
        oh = nth.OptionalHeader
        return oh
        
    def render_text(self, oh):
        print('_IMAGE_OPTIONAL_HEADER off: 0x%x' % (oh.v()))

class ImageBase2EntryPointOffset(heisenberg.AbstractHeisenbergPlugin):
    name = 'ib2epo'

    def calculate(self, ib_addr):
        oh = self.functions.ib2oh.calculate(ib_addr)
        ep = oh.AddressOfEntryPoint.v()
        epo = ib_addr + ep
        return epo
        
    def render_text(self, epo):
        print('EP off: 0x%x' % (epo))

class ReloadSymbols(heisenberg.AbstractHeisenbergPlugin):
    name = 'reload_symbols'

    def calculate(self):
        symbols_by_name = {}
        symbols_by_offset = {}
        print("Resolving symbols, patience")
        for mod in self.core.functions.e2imoml.calculate(self.core.current_context.v()):
            base = mod.DllBase
            name = mod.BaseDllName
            print(name)
            for export in mod.exports():
                if(not export[2].is_valid()): continue
                resolvedName = "%s!%s" % (name, str(export[2]))
                resolvedOffset = base.v() + export[1]
                symbols_by_name[resolvedName] = resolvedOffset
                symbols_by_offset[resolvedOffset] = resolvedName
        self.core.symbols_by_name = symbols_by_name
        self.core.symbols_by_offset = symbols_by_offset
        self.core.symbols_by_name.update(self.core.kernel_symbols_by_name)
        self.core.symbols_by_offset.update(self.core.kernel_symbols_by_offset)

    def render_text(self, sth):
        pass

import volatility.win32 as win32

class ReloadKernelSymbols(heisenberg.AbstractHeisenbergPlugin):
    name = 'reload_kernel_symbols'

    def calculate(self):
        kernel_symbols_by_name = {}
        kernel_symbols_by_offset = {}
        print("Resolving symbols, patience")
        for mod in win32.modules.lsmod(self.core.addrspace):
            base = mod.DllBase
            name = mod.BaseDllName
            print(name)
            for export in mod.exports():
                if(not export[2].is_valid()): continue
                resolvedName = "%s!%s" % (name, str(export[2]))
                resolvedOffset = base.v() + export[1]
                kernel_symbols_by_name[resolvedName] = resolvedOffset
                kernel_symbols_by_offset[resolvedOffset] = resolvedName
        self.core.kernel_symbols_by_name = kernel_symbols_by_name
        self.core.kernel_symbols_by_offset = kernel_symbols_by_offset
        self.core.symbols_by_name.update(self.core.kernel_symbols_by_name)
        self.core.symbols_by_offset.update(self.core.kernel_symbols_by_offset)

    def render_text(self, sth):
        pass

class DecodeOp1(heisenberg.AbstractHeisenbergApiFunction):
    name = 'dec_op1'

    def calculate(self, op1):
        return self.decode_op1(op1)

    def get_register(self, reg):
        return self.core.functions.gr(reg)

    def read(self, addr, length):
        space = (self.core.current_context or self.functions.get_context()).get_process_address_space() 
        return space.read(addr, length)

    def decode_op1(self, op1):
        regs = ["EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP", "ESP", "EIP"]

        my_op = op1
        if(my_op[0] == '['):
            my_op = self.decode_op1(my_op[1:-1])
            my_op = int(struct.unpack("<i", "".join(self.read(my_op, 4)))[0]) & 0xffffffff
            return my_op
        for reg in regs:
            if(my_op.upper() == reg):
                my_op = self.get_register(reg.lower())
                return my_op & 0xffffffff
        if(len(my_op.split("+")) >1):
            (a,b) = my_op.split("+")
            a = self.decode_op1(a)
            b = self.decode_op1(b)
            my_op = a+b
            return my_op & 0xffffffff
        if(len(my_op.split("-")) >1):
            (a,b) = my_op.split("-")
            a = self.decode_op1(a)
            b = self.decode_op1(b)
            my_op = a-b
            return my_op & 0xffffffff
        if(len(my_op.split("*")) >1):
            (a,b) = my_op.split("*")
            a = self.decode_op1(a)
            b = self.decode_op1(b)
            my_op = a*b
            return my_op & 0xffffffff
        return int(my_op, 16) & 0xffffffff

class Si(heisenberg.AbstractHeisenbergPlugin):
    name = 'si'

    def calculate(self):
        gdb.execute("si")
        self.core.functions.update_context.calculate()

class Ni(heisenberg.AbstractHeisenbergPlugin):
    name = 'ni'

    def calculate(self):
        eip = self.core.functions.gr("eip")
        space = (self.core.current_context or self.functions.get_context()).get_process_address_space() 
        factor = 0x20
#        while(factor > 0x0):
#            try:
        data = space.read(eip, factor)
        iterable = distorm3.DecodeGenerator(eip, data, distorm3.Decode32Bits)
        _, size, instruction, _ = iterable.next()
#            except Exception:
#                print("reducing")
#                factor -= 0x1
#                continue
        if(instruction.find("CALL ") > -1):
#        if True:
            neip = eip + size
#            self.core.functions.update_context.calculate()
#            self.core.gshell.log("test")
#            self.core.bp_index.addBpt(Breakpoint(neip), self.core.current_context)
#            gdb.execute("cont")
#            self.core.bp_index.delBpt(neip)
            gdb.execute("until *0x%x" % neip)
        else:
            self.core.functions.si()
        # we need to update context
        self.core.functions.update_context.calculate()
        self.core.reading_context = self.core.current_context

class Until(heisenberg.AbstractHeisenbergPlugin):
    name = 'until'
    
    def calculate(self, addr):
        gdb.execute("until *0x%x" % addr)
        self.core.functions.update_context.calculate()
        self.core.reading_context = self.core.current_context

class SiAndDis(heisenberg.AbstractHeisenbergPlugin):
    name = 'sd'

    def calculate(self):
        self.core.functions.si()
        self.core.functions.dism(None)

class Disassemble(heisenberg.AbstractHeisenbergPlugin):
    name = 'dis'
    dependencies = ['get_context', 'dec_op1']

    def calculate(self, address = None, length = 128, space = None, mode = None):
        """Disassemble code at a given address.

        Disassembles code starting at address for a number of bytes
        given by the length parameter (default: 128).

        Note: This feature requires distorm, available at
            http://www.ragestorm.net/distorm/

        The mode is '32bit' or '64bit'. If not supplied, the disasm
        mode is taken from the profile. 
        """
        if(address == None):
            address = self.core.functions.gr("eip")

        if not space:
#            space = (self.core.reading_context or self.core.current_context)
            space = (self.core.current_context or self.functions.get_context()).get_process_address_space() 

        if not sys.modules.has_key("distorm3"):
            print "ERROR: Disassembly unavailable, distorm not found"
            return
        if not space:
            space = self.eproc.get_process_address_space()

        if not mode:
            mode = space.profile.metadata.get('memory_model', '32bit')

        if mode == '32bit':
            distorm_mode = distorm3.Decode32Bits
        else:
            distorm_mode = distorm3.Decode64Bits

        data = space.read(address, length)
        iterable = distorm3.DecodeGenerator(address, data, distorm_mode)

        lines = []
        for (offset, _size, instruction, hexdump) in iterable:
            if(instruction.find("CALL ") > -1):
                try:
                    op1 = instruction[5:]
                    if(op1.find("DWORD ") == 0):
                        op1 = op1[6:]
                    dst = self.functions.dec_op1(op1)
                    if(self.core.symbols_by_offset.has_key(int(dst))):
                        target = self.core.symbols_by_offset[int(dst)]
                        instruction = "CALL %s" % target
                except Exception:
                    print(instruction)
#            lines.append((offset, hexdump, instruction))
            lines.append((offset, instruction))
        return lines

    def render_text(self, lines):
#        for offset, hexdump, instruction in lines:
        for offset, instruction in lines:
            print "{0:<#8x} {1}".format(offset, instruction)


class DisassembleMid(Disassemble):
    name = 'dism'
    dependencies = ['get_context', 'dec_op1']

    def calculate(self, address = None, line_count = 30, lines_prev=10, length = 356, space = None, mode = None):
        if(address == None):
            address = self.core.functions.gr("eip")

        try_start = address - lines_prev*5

        lines = []
        lineno = 0
        self.line_cur = 0
        self.line_start = 0
        for offset, instruction in Disassemble.calculate(self, try_start, length, space, mode):
            if(offset == address): 
                self.line_cur = lineno
                self.line_start = lineno - lines_prev
            lines.append((offset, instruction))
            if(lineno > self.line_start + line_count): break
            lineno += 1
        return lines, self.line_start, self.line_cur

    def render_text(self, code):
        lines, _, _ = code
        lineno = 0
#        for offset, hexdump, instruction in lines:
        for offset, instruction in lines:
            if(lineno >= self.line_start):
                if(lineno == self.line_cur):
                    print "{0}{1:<#8x} {2}{3}".format('\033[94m', offset, instruction, '\033[0m')
                else:
                    print "{0:<#8x} {1}".format(offset, instruction)
            lineno += 1
                
class Nop(heisenberg.AbstractHeisenbergPlugin):
    name = 'nop'

    def calculate(self):
        pass

    def render_text(self, sth):
        pass

class RestoreSymbols(heisenberg.AbstractHeisenbergPlugin):
    name = 'restore_symbols'

    def calculate(self, filee):
        f = open(filee, "r")
        symbols_by_name, symbols_by_offset, kernel_symbols_by_name, kernel_symbols_by_offset = pickle.load(f)
        self.core.symbols_by_name = symbols_by_name
        self.core.symbols_by_offset = symbols_by_offset
        self.core.kernel_symbols_by_name = kernel_symbols_by_name
        self.core.kernel_symbols_by_offset = kernel_symbols_by_offset
        f.close()

    def render_text(self, sth):
        print("Restored")

class StoreSymbols(heisenberg.AbstractHeisenbergPlugin):
    name = 'store_symbols'

    def calculate(self, filee):
        f = open(filee, "w")
        symbols_by_name = self.core.symbols_by_name
        symbols_by_offset = self.core.symbols_by_offset
        kernel_symbols_by_name = self.core.kernel_symbols_by_name
        kernel_symbols_by_offset = self.core.kernel_symbols_by_offset
        symbols = [symbols_by_name, symbols_by_offset, kernel_symbols_by_name, kernel_symbols_by_offset]
        pickle.dump(symbols, f)
        f.close()

    def render_text(self, sth):
        print("Stored")


                


