"""Exercise relocated bundled runtime, offline base transcription and real EXE startup."""
import test_loader
import os,sys,pathlib,subprocess,time,json
from utils import ffmpeg_utils as ff
from utils import subtitle_utils as su
root=test_loader.ROOT
target=pathlib.Path(os.environ['REELS_SMOKE_DIR']);target.mkdir(parents=True,exist_ok=True)
sys.executable=str(root/'Reels Maker.exe')
os.environ.update(HF_HUB_OFFLINE='1',HF_HOME=str(target/'empty-model-cache'))
speech=pathlib.Path(os.environ['REELS_SPEECH_SAMPLE'])
srt=target/'speech.srt'
captured=[];original=ff.run_process
def observe(command,**kwargs):
    captured.append(list(command));return original(command,**kwargs)
ff.run_process=observe
su.generate_srt_from_whisper(str(speech),str(srt),'base','English')
assert srt.exists() and '-->' in srt.read_text(encoding='utf-8')
assert str(root/'models/base') in captured[-1],captured[-1]
ff.run_process=original
video=target/'export.mp4'
ff.run_ffmpeg(['-y','-f','lavfi','-i','color=blue:s=320x240:r=25:d=1','-c:v','libx264',str(video)])
assert ff.probe_media(str(video))['video']['width']==320
env=dict(os.environ,QT_QPA_PLATFORM='offscreen',APPDATA=str(target/'appdata'),LOCALAPPDATA=str(target/'localappdata'),PATH=os.path.join(os.environ['SystemRoot'],'System32'))
env.pop('QT_PLUGIN_PATH',None);env.pop('QT_QPA_PLATFORM_PLUGIN_PATH',None)
env['PYTHONPATH']='';env['PYTHONHOME']=''
p=subprocess.Popen([str(root/'Reels Maker.exe')],cwd=str(root),env=env,creationflags=subprocess.CREATE_NO_WINDOW)
try:
    time.sleep(5)
    assert p.poll() is None,f'EXE exited: {p.returncode}'
    logs=list((target/'appdata').rglob('app.log'));assert logs
    log=logs[0].read_text(encoding='utf-8')
    assert 'Reels Maker 1.1.2 started' in log and 'Traceback' not in log,log
finally:
    if p.poll() is None:p.terminate();p.wait(timeout=10)
result=dict(status='PASS',runtime=str(root),checks=['base model resolves inside installation','real offline speech recognition with empty external cache','bundled FFmpeg H.264 export and FFprobe','packaged EXE startup with isolated settings and minimal PATH'],recognized_text=srt.read_text(encoding='utf-8'))
(target/'runtime-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
