import shutil, subprocess

def reveng_search(codewords,width=8):
    exe=shutil.which('reveng')
    if not exe: raise RuntimeError('CRC RevEng executable not installed')
    return subprocess.run([exe,'-w',str(width),'-s',*[x.hex() for x in codewords]],capture_output=True,text=True,timeout=30,check=True).stdout
