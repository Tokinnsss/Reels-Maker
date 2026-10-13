"""Rebuild the PyInstaller archives without modifying its bootloader/dependencies.
Requires Python 3.12 and the original ReelsMakerPro 1.0.0 executable.
"""
import pathlib, struct, zlib, marshal, hashlib, json, sys, types, re

MAGIC=b'MEI\x0c\x0b\x0a\x0b\x0e'
HERE=pathlib.Path(__file__).resolve().parent
PATCHES={'utils.ffmpeg_utils':'ffmpeg_patch.py','workers.worker':'worker_patch.py',
    'utils.subtitle_utils':'subtitle_patch.py','ui.main_window':'ui_patch.py',
    'ui.subtitle_preview_dialog':'dialog_patch.py'}

def read_archive(path):
    data=pathlib.Path(path).read_bytes(); pos=data.rfind(MAGIC)
    if pos<0: raise ValueError('PyInstaller archive not found')
    magic,total,offset,length,version,lib=struct.unpack('!8sIIII64s',data[pos:pos+88])
    if version!=312: raise ValueError('Expected Python 3.12')
    start=pos+88-total; cursor=start+offset; entries=[]
    while cursor<start+offset+length:
        size,off,compressed,raw,flag,kind=struct.unpack('!IIIIBc',data[cursor:cursor+18])
        name=data[cursor+18:cursor+size].rstrip(b'\0').decode()
        payload=data[start+off:start+off+compressed]
        entries.append((name,zlib.decompress(payload) if flag else payload,flag,kind))
        cursor+=size
    return data[:start],entries,version,lib

def rebrand(code):
    values=[]
    for value in code.co_consts:
        if isinstance(value,types.CodeType): value=rebrand(value)
        elif isinstance(value,str):
            value=value.replace('ReelsMaker Pro','Reels Maker')
            if 'https://' in value and any(s in value for s in ('magerdev','donatepay','donatello')):
                value='Tokinns Soft · <a href="https://t.me/tokinnssoft">@tokinnssoft</a>' if '<a ' in value else 'https://t.me/tokinnssoft'
        values.append(value)
    return code.replace(co_consts=tuple(values))

def patched_code(name,original):
    if name.startswith(('ui.','utils.')): original=rebrand(original)
    if name=='utils.constants':
        original=original.replace(co_consts=tuple('1.1.2' if v=='1.0.0' else v for v in original.co_consts))
    if name not in PATCHES: return original
    source='exec("__REELS_ORIGINAL_MODULE__")\n'+(HERE/PATCHES[name]).read_text(encoding='utf-8')
    if name=='ui.main_window':
        source+='\n'+(HERE/'advanced_ui.py').read_text(encoding='utf-8')
        source+='\n'+(HERE/'refresh_ui.py').read_text(encoding='utf-8')
    code=compile(source,'repair/'+PATCHES[name],'exec')
    return code.replace(co_consts=tuple(original if v=='__REELS_ORIGINAL_MODULE__' else v for v in code.co_consts))

def pyz_codes(data):
    toc=dict(marshal.loads(data[struct.unpack('!i',data[8:12])[0]:]))
    return {name:(typ,marshal.loads(zlib.decompress(data[offset:offset+size]))) for name,(typ,offset,size) in toc.items()}

def rebuild_pyz(data):
    modules=pyz_codes(data); body=bytearray(data[:12]); toc=[]
    modules['utils.smart_export']=(0,compile((HERE/'smart_export.py').read_text(encoding='utf-8'),'utils/smart_export.py','exec'))
    for name,(typ,code) in modules.items():
        payload=zlib.compress(marshal.dumps(patched_code(name,code)),9)
        toc.append((name,(typ,len(body),len(payload)))); body.extend(payload)
    offset=len(body); body.extend(marshal.dumps(toc)); body[8:12]=struct.pack('!i',offset)
    return bytes(body)

def build(source,dest):
    prefix,entries,version,lib=read_archive(source)
    payload=bytearray(); toc=bytearray()
    for name,raw,flag,kind in entries:
        if raw.startswith(b'PYZ\0'): raw=rebuild_pyz(raw)
        elif name=='main': raw=marshal.dumps(compile((HERE/'main.py').read_text(encoding='utf-8'),'main.py','exec'))
        encoded=zlib.compress(raw,9) if flag else raw
        namebytes=name.encode()+b'\0'; size=((18+len(namebytes)+15)//16)*16
        toc.extend(struct.pack('!IIIIBc',size,len(payload),len(encoded),len(raw),flag,kind)+namebytes+b'\0'*(size-18-len(namebytes)))
        payload.extend(encoded)
    cookie=struct.pack('!8sIIII64s',MAGIC,len(payload)+len(toc)+88,len(payload),len(toc),version,lib)
    result=prefix+payload+toc+cookie
    dest=pathlib.Path(dest); dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(result)
    print(json.dumps({'output':str(dest),'size':len(result),'sha256':hashlib.sha256(result).hexdigest()}))

if __name__=='__main__':
    if sys.version_info[:2]!=(3,12): raise SystemExit('Use Python 3.12')
    build(sys.argv[1],sys.argv[2])

