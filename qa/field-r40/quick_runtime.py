#!/usr/bin/env python3
"""Early staged-engine diagnostic: uses same full probe, records own JVM threads
if generation does not make progress. It never accepts a timed-out process.
"""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[2]
p=Path(__file__).with_name('run_natural.py');text=p.read_text()
# Leave the complete target-set check in place: this runner only improves failure
# diagnostics and timeout, not coverage or the acceptance conditions.
old="while time.monotonic()<deadline:\n                try:line=events.get(timeout=1)"
new="""dumped=False
            while time.monotonic()<deadline:
                if not dumped and time.monotonic()-start>150:
                    dumped=True
                    dump=subprocess.run(['jcmd',str(proc.pid),'Thread.print'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=25)
                    (OUT/(name+'-threads.txt')).write_text(dump.stdout)
                    print('R40_THREAD_DIAGNOSTIC',name,'recorded',flush=True)
                try:line=events.get(timeout=1)"""
if text.count(old)!=1:raise ValueError('Unexpected runner source')
text=text.replace(old,new,1).replace('time.monotonic()+1100','time.monotonic()+420')
(ROOT/'effective-quick-runtime.py').write_text(text)
exec(compile(text,str(p),'exec'),{'__file__':str(p),'__name__':'__main__'})
