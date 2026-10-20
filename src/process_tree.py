"""Own subprocess descendants on Windows and POSIX, including on timeout."""
import os
import signal
import subprocess


class ProcessTree:
    def __init__(self):
        self.handle = None
        self.process = None
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes as w
            class Basic(ctypes.Structure):
                _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                            ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                            ('active', w.DWORD), ('affinity', ctypes.c_size_t),
                            ('priority', w.DWORD), ('scheduling', w.DWORD)]
            class IO(ctypes.Structure):
                _fields_ = [(name, ctypes.c_ulonglong) for name in
                            ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
            class Extended(ctypes.Structure):
                _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                            ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                            ('peak_job', ctypes.c_size_t)]
            self.api = ctypes.WinDLL('kernel32', use_last_error=True)
            self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
            self.api.CreateJobObjectW.restype = w.HANDLE
            self.api.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
            self.api.SetInformationJobObject.restype = w.BOOL
            self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
            self.api.AssignProcessToJobObject.restype = w.BOOL
            self.api.CloseHandle.argtypes = [w.HANDLE]
            self.api.CloseHandle.restype = w.BOOL
            self.handle = self.api.CreateJobObjectW(None, None)
            if not self.handle:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = Extended()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                error = ctypes.WinError(ctypes.get_last_error())
                self.close()
                raise error

    def popen(self, *args, **kwargs):
        if os.name == 'nt':
            kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW
        else:
            kwargs['start_new_session'] = True
        try:
            self.process = subprocess.Popen(*args, **kwargs)
            if self.handle:
                import ctypes
                if not self.api.AssignProcessToJobObject(self.handle, int(self.process._handle)):
                    error = ctypes.WinError(ctypes.get_last_error())
                    self.process.kill()
                    self.process.wait()
                    raise error
            return self.process
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None
        elif os.name != 'nt' and self.process:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
