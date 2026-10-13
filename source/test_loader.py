"""Import the original and patched application modules for offscreen integration tests."""
import os,sys,pathlib,importlib.abc,importlib.util
import tempfile
from build import read_archive,pyz_codes,patched_code

ROOT=pathlib.Path(os.environ.get('REELS_TEST_ROOT',r'T:\ReelsMakerPro'))
INTERNAL=ROOT/'_internal'
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH']=str(INTERNAL/'PyQt5/Qt5/plugins')
os.environ['QT_PLUGIN_PATH']=str(INTERNAL/'PyQt5/Qt5/plugins')
os.environ['APPDATA']=str(pathlib.Path(__file__).resolve().parent.parent/'test_appdata')
_temp=pathlib.Path(__file__).resolve().parent.parent/'test_temp'
_temp.mkdir(exist_ok=True)
tempfile.tempdir=str(_temp)
os.add_dll_directory(str(INTERNAL))
os.add_dll_directory(str(INTERNAL/'PyQt5/Qt5/bin'))
sys.path.insert(0,str(INTERNAL))
sys.frozen=True; sys._MEIPASS=str(INTERNAL)
original=pathlib.Path(__file__).resolve().parent/'original/ReelsMakerPro.exe'
_packed_test=os.environ.get('REELS_TEST_EXE')
if _packed_test: original=pathlib.Path(_packed_test)
if not original.is_file():
    backup=ROOT/'ReelsMakerPro.original-1.0.0.bak'
    original=backup if backup.is_file() else ROOT/'ReelsMakerPro.exe'
_,entries,_,_=read_archive(original)
MODULES=pyz_codes(next(raw for name,raw,flag,kind in entries if raw.startswith(b'PYZ\0')))
if not _packed_test: MODULES['utils.smart_export']=(0,compile((pathlib.Path(__file__).resolve().parent/'smart_export.py').read_text(encoding='utf-8'),'utils/smart_export.py','exec'))

class Loader(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in MODULES and fullname.split('.')[0] in ('ui','utils','workers','PyQt5','qtawesome','qtpy'):
            return importlib.util.spec_from_loader(fullname,self,is_package=MODULES[fullname][0]==1)
    def create_module(self,spec): return None
    def exec_module(self,module):
        typ,code=MODULES[module.__name__]
        module.__file__=str(INTERNAL/module.__name__.replace('.','/'))+('/__init__.py' if typ==1 else '.py')
        if typ==1: module.__path__=[str(INTERNAL/module.__name__.replace('.','/'))]
        exec(code if _packed_test else patched_code(module.__name__,code),module.__dict__)

sys.meta_path.insert(0,Loader())
