import test_loader
import pathlib,json,time,threading,sys,traceback
from fractions import Fraction
from PyQt5.QtWidgets import QApplication,QTabWidget
from utils import ffmpeg_utils as f
from utils.smart_export import *
from workers.worker import Worker
from ui.main_window import VideoUnicApp

from PyQt5.QtGui import QFontDatabase
app=QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
root=pathlib.Path(__file__).resolve().parent.parent/'feature-tests';root.mkdir(exist_ok=True)
dest=root/time.strftime('%H%M%S');dest.mkdir()
results=[]
def check(name,fn):
    try:
        detail=fn();results.append(dict(test=name,status='PASS',details=str(detail or '')));print('PASS',name,flush=True)
    except Exception as exc:
        results.append(dict(test=name,status='FAIL',error=str(exc),traceback=traceback.format_exc()));print('FAIL',name,repr(exc),flush=True)

source=root/'source.mp4';silent=root/'silent.mp4'
if not source.exists():
    f.run_ffmpeg(['-y','-f','lavfi','-i','testsrc2=s=320x180:r=25:d=20','-f','lavfi','-i',
        "aevalsrc=0.15*sin(2*PI*440*t)*lt(mod(t\\,5)\\,4):s=48000:d=20",'-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(source)])
    f.run_ffmpeg(['-y','-i',str(source),'-an','-c:v','copy',str(silent)])
srt=root/'speech.srt'
segments=[dict(start=i*5,end=i*5+4,text=t) for i,t in enumerate([
    'Первая законченная мысль о работе.', 'Вторая фраза про новый проект.',
    'Важный совет: как получить результат!', 'Последняя фраза завершает рассказ.'])]
write_srt_slice(segments,0,20,str(srt))
smart=dict(enabled=True,method='speech',min=3,target=5,max=7,count=2,keywords='совет')
export=dict(enabled=True,profiles=['vertical','square','horizontal'],resolution=480,fps=30,quality=23,size_mb=0)
base=dict(in_path=str(source),filters=[],zoom_p=100,speed_p=100,overlay_file=None,overlay_pos='',output_format='Оригинальный',blur_background=False)

def clip_plan():
    clips=select_clips(20,smart,segments)
    assert len(clips)==2,clips
    assert any('совет' in c['text'] for c in clips),clips
    for c in clips: assert 3<=c['end']-c['start']<=7
    assert clips[0]['end']<=clips[1]['start']
    assert any(abs(c['end']-14.15)<.01 for c in clips),clips
    return clips
check('Speech boundaries, keyword priority, duration and no overlap',clip_plan)
def pauses():
    found=detect_pauses(str(source),20)
    assert len(found)>=3,found
    assert abs(found[0][0]-4)<.1,found
    clips=select_clips(20,dict(smart,method='pauses'),pauses=found)
    assert clips and all(c['reason']=='Паузы' for c in clips)
    return found
check('Real audio silence analysis',pauses)
def fallback():
    assert select_clips(2,smart)[0]['end']==2
    assert len(select_clips(120,smart))==2
    for options in [dict(smart,min=70),dict(smart,count=0)]:
        try:validate_options(options)
        except ValueError:pass
        else:raise AssertionError('Invalid options accepted')
    try:validate_options(None,dict(export,profiles=[]))
    except ValueError:pass
    else:raise AssertionError('Empty formats accepted')
check('Short and silent inputs, invalid options',fallback)
def srt_slice():
    path=dest/'slice.srt';write_srt_slice(segments,9,15,str(path));rows=read_srt(path)
    assert len(rows)==1 and rows[0]['start']==1 and rows[0]['end']==5,rows
    assert 'совет' in rows[0]['text']
check('SRT clipping and timestamp rebase',srt_slice)

def render(profile,extra=None):
    options=dict(base,out_path=str(dest/(profile+'.mp4')),clip_start=10,clip_end=12,
        srt_path=str(srt),export_settings=dict(export,profile=profile))
    options.update(extra or {})
    path=f.process_single(**options);info=f.probe_media(path)
    w,h=dimensions(profile,480,320,180)
    assert (info['video']['width'],info['video']['height'])==(w,h),info['video']
    expected=2/(options.get('speed_p',100)/100)
    assert abs(info['duration']-expected)<.12,(info['duration'],expected)
    assert float(Fraction(info['video']['avg_frame_rate']))==30
    assert bool(info['audio'])==(options.get('in_path')!=str(silent))
    return path
for profile in PROFILES:check('Render '+profile,lambda p=profile:render(p))
check('Clip with speed 150% and blur',lambda:render('square',dict(speed_p=150,blur_background=True)))
check('Silent clip export',lambda:render('horizontal',dict(in_path=str(silent))))
def no_captions():
    path=f.process_single(**dict(base,out_path=str(dest/'no-caption.mp4'),clip_start=4.2,clip_end=4.8,srt_path=str(srt)))
    assert f.probe_media(path)['duration']>.5
check('Empty subtitle slice remains exportable',no_captions)
def exact_seek():
    path=f.process_single(**dict(base,out_path=str(dest/'seek.mp4'),clip_start=10,clip_end=12))
    # Compare first decoded frames of a changing test pattern: a wrong seek fails PSNR.
    import re
    output=f.run_process([f.FFMPEG_PATH_EFFECTIVE,'-hide_banner','-i',path,'-ss','10','-i',str(source),
        '-filter_complex','[0:v]trim=end_frame=1,setpts=PTS-STARTPTS[a];[1:v]trim=end_frame=1,setpts=PTS-STARTPTS[b];[a][b]psnr',
        '-an','-f','null','-'])
    match=re.search(r'average:([\d.]+)',output)
    assert match and float(match[1])>28,output
    return match[1]
check('Decoded first frame matches nonzero source seek',exact_seek)

def target_size():
    path=f.process_single(**dict(base,out_path=str(dest/'size.mp4'),clip_start=2,clip_end=10,export_settings=dict(export,profile='horizontal',size_mb=1)))
    assert pathlib.Path(path).stat().st_size<1400000
    return pathlib.Path(path).stat().st_size
check('Approximate target size',target_size)

def worker_options():
    return dict(files=[str(source)],out_dir=str(dest/'queue'),filters=[],zoom_mode='static',zoom_static=100,
        zoom_min=100,zoom_max=100,speed_mode='static',speed_static=100,speed_min=100,speed_max=100,overlay_file=None,
        overlay_pos='',mute_audio=False,output_format='Оригинальный',blur_background=False,strip_metadata=True,codec='libx264',
        subtitle_settings=dict(mode='srt_file',srt_path=str(srt),style={}),auto_crop=False,overlay_audio=None,
        original_volume=100,overlay_volume=100,smart_settings=smart,export_settings=export)
def queue():
    worker=Worker(**worker_options());worker.run()
    assert not worker.errors,worker.errors
    assert len(worker.output_paths)==6,worker.output_paths
    report=json.loads(next((dest/'queue').glob('*_clips.json')).read_text(encoding='utf-8'))
    assert len(report['outputs'])==6 and len(report['clips'])==2
    for path in worker.output_paths: assert f.probe_media(path)['audio']
    return worker.output_paths
check('Full queue: two speech clips × three formats + JSON report',queue)
def bad_file():
    options=worker_options();options.update(files=[str(root/'missing.mp4'),str(silent)],out_dir=str(dest/'errors'),subtitle_settings={'mode':'off'},smart_settings=dict(smart,method='pauses'),export_settings=dict(export,profiles=['square']))
    worker=Worker(**options);worker.run();assert len(worker.errors)==1 and len(worker.output_paths)==2,(worker.errors,worker.output_paths)
check('Bad file does not block following file',bad_file)
def cancellation():
    options=worker_options();options.update(out_dir=str(dest/'cancel'));worker=Worker(**options)
    timer=threading.Timer(.25,worker.stop);timer.start();worker.run();timer.join()
    assert worker.cancelled and not worker.errors
    assert not list((dest/'cancel').glob('.*.mp4'))
check('Cancellation cleans incomplete output',cancellation)
def ui():
    window=VideoUnicApp();p=window.processing_widget
    if p.codec_probe:p.codec_probe.stop();p.codec_probe.wait(10000)
    p.restore_advanced(dict(smart=smart,export=export));prefs=p.capture_preferences()
    assert prefs['smart']==smart|{'model':'base','language':'Russian'},prefs['smart']
    assert prefs['export']==export
    assert len(p.processing_options()['export_settings']['profiles'])==3
    window.resize(1360,960);window.show()
    # Use a concrete Windows font; Qt5 cannot parse CSS fallback font families reliably.
    window.setStyleSheet(window.styleSheet().replace('"Segoe UI", system-ui, sans-serif','"Segoe UI"'))
    tabs=p.findChildren(QTabWidget)[0]
    for title in ('Умная нарезка','Экспорт'):
        index=next(i for i in range(tabs.count()) if tabs.tabText(i)==title);tabs.setCurrentIndex(index)
        app.processEvents();window.grab().save(str(dest/(title+'.png')))
    p.smart_group.setChecked(False);p.export_group.setChecked(False);window.close();app.processEvents()
check('UI controls, settings round trip and screenshots',ui)

(dest/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('RESULTS',dest,flush=True)
sys.exit(1 if any(r['status']=='FAIL' for r in results) else 0)
