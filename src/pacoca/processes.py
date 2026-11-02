"""Keep the private inference process tied to the application's lifetime."""
import os


class ProcessJob:
    def __init__(self):
        self.handle=None
        if os.name!='nt':
            return
        import ctypes
        from ctypes import wintypes
        class Limits(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),('flags',wintypes.DWORD),
                      ('min_working_set',ctypes.c_size_t),('max_working_set',ctypes.c_size_t),
                      ('active_processes',wintypes.DWORD),('affinity',ctypes.c_size_t),
                      ('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class Counters(ctypes.Structure):
            _fields_=[(n,ctypes.c_uint64) for n in ['read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes']]
        class Extended(ctypes.Structure):
            _fields_=[('limits',Limits),('io',Counters),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),
                      ('peak_process_memory',ctypes.c_size_t),('peak_job_memory',ctypes.c_size_t)]
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateJobObjectW.restype=wintypes.HANDLE
        self.kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
        self.kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        self.handle=self.kernel.CreateJobObjectW(None,None)
        if self.handle:
            limits=Extended();limits.limits.flags=0x2000
            if not self.kernel.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
                self.close()

    def attach(self,process):
        if self.handle:
            self.kernel.AssignProcessToJobObject(self.handle,int(process._handle))

    def cpu_limit(self,percent):
        if not self.handle:
            return False
        import ctypes
        from ctypes import wintypes
        class CpuRate(ctypes.Structure):
            _fields_=[('flags',wintypes.DWORD),('rate',wintypes.DWORD)]
        limits=CpuRate(0x1|0x4,max(100,min(10000,int(percent*100))))
        return bool(self.kernel.SetInformationJobObject(self.handle,15,ctypes.byref(limits),ctypes.sizeof(limits)))

    def attach_pid(self,pid):
        if not self.handle:
            return
        import ctypes
        from ctypes import wintypes
        self.kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        self.kernel.OpenProcess.restype=wintypes.HANDLE
        process=self.kernel.OpenProcess(0x0100|0x0001,False,pid)
        if process:
            try:
                self.kernel.AssignProcessToJobObject(self.handle,process)
            finally:
                self.kernel.CloseHandle(process)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle=None
