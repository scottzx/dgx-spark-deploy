from pathlib import Path
import re,json,subprocess,datetime
r=Path('/home/admin/sol-spark-runtime')
print(datetime.datetime.now().isoformat(timespec='seconds'))
print('Verified:', ', '.join(sorted(p.stem for p in (r/'receipts').glob('*.json'))))
for p in (r/'checkpoints').rglob('*.download.log'):
 target=Path(str(p).removesuffix('.download.log'))
 if target.exists():continue
 with p.open('rb') as f:
  f.seek(max(0,p.stat().st_size-15000));s=f.read().decode(errors='replace')
 progress=re.findall(r'\[#[^\]\r\n]+\]',s)
 print(target.name,progress[-1] if progress else s[-150:])
for name in ['runtime-install','targets-install','kernels-build','qwen-build']:
 p=r/(name+'.log')
 print(name, '\n'.join(p.read_text(errors='replace').splitlines()[-5:]) if p.exists() else 'missing')
print(subprocess.run(['free','-h'],capture_output=True,text=True).stdout)
