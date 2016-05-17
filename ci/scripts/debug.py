# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

try:
    import readline  # For readline input support
except:
    pass

import sys
import os
import traceback
import signal
import codeop
import cStringIO
import cPickle
import tempfile


def pipename(pid):
    """Return name of pipe to use"""
    return '/'.join([tempfile.gettempdir(), 'debug-%d' % pid])


class NamedPipe(object):
    def __init__(self, name, end=0, mode=0666):
        """Open a pair of pipes, name.in and name.out for communication
        with another process.  One process should pass 1 for end, and the
        other 0.  Data is marshalled with pickle."""
        self.in_name, self.out_name = name + '.in', name + '.out',
        try:
            os.mkfifo(self.in_name, mode)
        except OSError:
            pass
        try:
            os.mkfifo(self.out_name, mode)
        except OSError:
            pass

        # NOTE: The order the ends are opened in is important - both ends
        # of pipe 1 must be opened before the second pipe can be opened.
        if end:
            self.inp = open(self.out_name, 'r')
            self.out = open(self.in_name, 'w')
        else:
            self.out = open(self.out_name, 'w')
            self.inp = open(self.in_name, 'r')
        self._open = True

    def is_open(self):
        return not (self.inp.closed or self.out.closed)

    def put(self, msg):
        if self.is_open():
            data = cPickle.dumps(msg, 1)
            self.out.write("%d\n" % len(data))
            self.out.write(data)
            self.out.flush()
        else:
            raise Exception("Pipe closed")

    def get(self):
        txt = self.inp.readline()
        if not txt:
            self.inp.close()
        else:
            l = int(txt)
            data = self.inp.read(l)
            if len(data) < l:
                self.inp.close()
            return cPickle.loads(data)  # Convert back to python object.

    def close(self):
        self.inp.close()
        self.out.close()
        try:
            os.remove(self.in_name)
        except OSError:
            pass
        try:
            os.remove(self.out_name)
        except OSError:
            pass

    def __del__(self):
        self.close()


def remote_debug(sig, frame):
    """Handler to allow process to be remotely debugged."""

    def _raise_exception(ex):
        """Raise specified exception in the remote process"""
        _raise_exception.ex = ex

    _raise_exception.ex = None

    try:
        # Provide some useful functions.
        locs = {'_raiseEx': _raise_exception, 'frame': frame}
        locs.update(frame.f_locals)  # Unless shadowed.
        globs = frame.f_globals

        pid = os.getpid()  # Use pipe name based on pid

        pipe = NamedPipe(pipename(pid))

        old_stdout, old_stderr = sys.stdout, sys.stderr
        txt = ''
        pipe.put("Interrupting process at following point:\n" +
                 ''.join(traceback.format_stack(frame)) + ">>> ")

        try:
            while pipe.is_open() and _raise_exception.ex is None:
                line = pipe.get()
                if line is None: continue  # EOF
                txt += line
                try:
                    code = codeop.compile_command(txt)
                    if code:
                        sys.stdout = cStringIO.StringIO()
                        sys.stderr = sys.stdout
                        exec code in globs, locs
                        txt = ''
                        pipe.put(sys.stdout.getvalue() + '>>> ')
                    else:
                        pipe.put('... ')
                except:
                    txt = ''  # May be syntax err.
                    sys.stdout = cStringIO.StringIO()
                    sys.stderr = sys.stdout
                    traceback.print_exc()
                    pipe.put(sys.stdout.getvalue() + '>>> ')
        finally:
            sys.stdout = old_stdout  # Restore redirected output.
            sys.stderr = old_stderr
            pipe.close()

    except Exception:  # Don't allow debug exceptions to propogate to real program.
        traceback.print_exc()

    if _raise_exception.ex is not None:
        raise _raise_exception.ex


def debug_process(pid):
    """Interrupt a running process and debug it."""
    os.kill(pid, signal.SIGUSR1)  # Signal process.
    pipe = NamedPipe(pipename(pid), 1)
    try:
        while pipe.is_open():
            txt = raw_input(pipe.get()) + '\n'
            pipe.put(txt)
    except EOFError:
        pass  # Exit.
    pipe.close()


def listen():
    with open("/tmp/dbgpid", "w") as f:
        f.write(str(os.getpid()) + "\n")
    signal.signal(signal.SIGUSR1, remote_debug)  # Register for remote debugging.


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print "Error: Must provide process id to debug"
    else:
        pid = int(sys.argv[1])
        debug_process(pid)
