"""Integration checks against decoded frames/audio, plus boundary and lifecycle tests."""
import test_loader
import pathlib,subprocess,json,time,math,array,sys
from PyQt5.QtWidgets import QApplication
from utils import ffmpeg_utils as f
from utils.constants import REELS_FORMAT_NAME
from ui.main_window import VideoUnicApp
from workers.worker import Worker

app=QApplication([])
root=pathlib.Path(__file__).resolve().parent.parent/'banner-tests'
root.mkdir(exist_ok=True)
dest=root/time.strftime('run_%H%M%S');dest.mkdir()
main=root/'main.mp4';banner=root/'green-banner.mp4'
main_silent=dest/'main-silent.mp4';banner_silent=dest/'banner-silent.mp4'
for original,target in [(main,main_silent),(banner,banner_silent)]:
    f.run_ffmpeg(['-y','-i',str(original),'-c:v','copy','-an',str(target)])
results=[]
def check(name,func):
    try:
        value=func();results.append({'test':name,'status':'PASS','details':str(value or '')});print('PASS',name,flush=True)
    except Exception as exc:
        import traceback
        results.append({'test':name,'status':'FAIL','error':str(exc),'traceback':traceback.format_exc()});print('FAIL',name,repr(exc),flush=True)

settings={'enabled':True,'path':str(banner),'start':1,'key_enabled':True,'color':'#00FF00','similarity':.2,'blend':.08}
base=dict(in_path=str(main),filters=[],zoom_p=100,speed_p=100,overlay_file=None,overlay_pos='',output_format='Оригинальный',blur_background=False)
def render(name,banner_changes=None,changes=None):
    return f.process_single(**(base|dict(out_path=str(dest/(name+'.mp4')),banner_settings=settings|(banner_changes or {}))|(changes or {})))
def validate(path,length,audio=True,size=(320,240)):
    info=f.probe_media(path)
    assert abs(info['duration']-length)<.06,(info['duration'],length)
    assert bool(info['audio'])==audio
    assert (info['video']['width'],info['video']['height'])==size
    return path
paths={}
def main_export():
    paths['key']=render('key');return validate(paths['key'],5.5)
check('overlay with green removal increases duration by banner length',main_export)
def reference():
    paths['reference']=render('reference',{'enabled':False});return validate(paths['reference'],4)
check('disabled banner preserves original duration',reference)
def opaque():
    paths['opaque']=render('opaque',{'key_enabled':False});return validate(paths['opaque'],5.5)
check('banner without green removal',opaque)

def raw_frames(path):
    p=subprocess.run([f.FFMPEG_PATH_EFFECTIVE,'-v','error','-i',path,'-map','0:v:0','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True)
    size=320*240*3
    return [p.stdout[i:i+size] for i in range(0,len(p.stdout),size)]
frames={}
def mean_difference(a,b,offset=0,length=320*20*3):
    return sum(abs(x-y) for x,y in zip(a[offset:offset+length],b[offset:offset+length]))/length
def pause_frames():
    frames['key']=raw_frames(paths['key']);frames['reference']=raw_frames(paths['reference'])
    out,ref=frames['key'],frames['reference']
    assert len(out)==165 and len(ref)==120,(len(out),len(ref))
    assert mean_difference(out[15],ref[15])<7
    assert mean_difference(out[35],out[65])<4,'background moved during pause'
    assert mean_difference(out[35],ref[30])<7,'wrong frozen frame'
    assert mean_difference(out[75],ref[30])<7,'main did not resume at insertion point'
    assert mean_difference(out[105],ref[60])<7,'post-insert timeline drift'
    return 'All 120 original frames retained; 45 frames inserted. Frozen background and resume checked.'
check('decoded frames: freeze, continuity and resumption',pause_frames)
def color_key_pixels():
    frames['opaque']=raw_frames(paths['opaque'])
    out=frames['key'][40];ref=frames['reference'][30];opaque=frames['opaque'][40]
    # Green banner border covers this rectangle; removing it must reveal the held frame.
    diffs=[]
    for y in range(100,130):
        offset=(y*320+5)*3
        diffs.append(mean_difference(out,ref,offset,20*3))
    assert sum(diffs)/len(diffs)<10,diffs
    pixel=(120*320+10)*3
    assert opaque[pixel+1]>200 and opaque[pixel]<60,opaque[pixel:pixel+3]
    red=(120*320+160)*3
    assert out[red]>180 and out[red+1]<80,'foreground removed with green'
check('decoded pixels: keyed background transparent, red foreground retained',color_key_pixels)

def audio_samples(path):
    p=subprocess.run([f.FFMPEG_PATH_EFFECTIVE,'-v','error','-i',path,'-vn','-ac','1','-ar','16000','-f','s16le','-'],capture_output=True,check=True)
    data=array.array('h');data.frombytes(p.stdout);return data
def chunk(data,t):return data[int(t*16000):int((t+.15)*16000)]
def power(data,freq):
    return math.hypot(sum(v*math.cos(2*math.pi*freq*i/16000) for i,v in enumerate(data)),
        sum(v*math.sin(2*math.pi*freq*i/16000) for i,v in enumerate(data)))/max(1,len(data))
def rms(data):return math.sqrt(sum(v*v for v in data)/max(1,len(data)))
def correct_sound():
    data=audio_samples(paths['key'])
    for t in (.4,3):
        part=chunk(data,t);assert power(part,440)>power(part,990)*30
    part=chunk(data,1.4)
    assert power(part,990)>power(part,440)*30,'main audio leaks into banner'
check('decoded sound: only banner audio during pause; original audio resumes',correct_sound)
def missing_main_audio():
    path=render('no-main-audio',changes={'in_path':str(main_silent)})
    validate(path,5.5)
    data=audio_samples(path)
    assert rms(chunk(data,.3))<10 and rms(chunk(data,3))<10
    assert rms(chunk(data,1.4))>500
check('silent main video plus banner with sound',missing_main_audio)
def missing_banner_audio():
    path=render('no-banner-audio',{'path':str(banner_silent)})
    validate(path,5.5)
    data=audio_samples(path)
    assert rms(chunk(data,1.4))<10
    assert rms(chunk(data,3))>500
check('silent banner pauses main sound and restores it',missing_banner_audio)
check('both videos silent',lambda:validate(render('both-silent',{'path':str(banner_silent)}, {'in_path':str(main_silent)}),5.5,False))
def muted_banner():
    path=render('muted-banner',{'volume':0});data=audio_samples(path)
    assert rms(chunk(data,1.4))<10 and rms(chunk(data,3))>500
check('banner volume zero does not mute resumed main audio',muted_banner)
check('insert at beginning',lambda:validate(render('at-start',{'start':0}),5.5))
check('insert at end',lambda:validate(render('at-end',{'start':4}),5.5))
check('fractional insertion time',lambda:validate(render('fraction',{'start':1.27}),5.5))
check('scaled lower-right banner',lambda:validate(render('corner',{'scale':35,'position':'bottom_right'}),5.5))
check('black background mode',lambda:validate(render('black-background',{'mode':'replace'}),5.5))
check('main speed applied before insertion time',lambda:validate(render('speed',{'start':.5},{'speed_p':200}),3.5))
check('9:16 plus split screen',lambda:validate(render('split',changes={'output_format':REELS_FORMAT_NAME,'filler_path':str(main_silent)}),5.5,True,(1080,1920)))
check('NVIDIA export',lambda:validate(render('gpu',changes={'codec':'h264_nvenc'}),5.5))

def bad_time(value):
    try:render('invalid-time',{'start':value})
    except ValueError as exc:assert 'вставки' in str(exc);return str(exc)
    raise AssertionError('invalid insertion time accepted')
check('reject insertion beyond video duration',lambda:bad_time(7))
check('reject negative insertion time',lambda:bad_time(-1))
def preview():
    path=f.generate_preview(str(main),str(dest/'preview.png'),[],100,None,'','Оригинальный',False,banner_settings=settings)
    from PyQt5.QtGui import QImage
    im=QImage(path);p=im.pixelColor(160,120)
    assert p.red()>180 and p.green()<80,'preview does not show banner'
    return path
check('preview shows the inserted banner',preview)

def wait_thread(worker,timeout=20):
    end=time.monotonic()+timeout
    while worker.isRunning() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert not worker.isRunning(),'thread failed to stop';app.processEvents()
def ui_roundtrip():
    w=VideoUnicApp();wait_thread(w.processing_widget.codec_probe)
    p=w.processing_widget
    config=settings|{'scale':45,'volume':70,'position':'bottom_right','blend':.12,'similarity':.22}
    p.restore_banner(config)
    actual=p.processing_options()['banner_settings']
    assert actual['scale']==45 and actual['enabled'] and actual['key_enabled']
    assert actual['path']==str(banner)
    w.persist();w.close();app.processEvents()
    w=VideoUnicApp();wait_thread(w.processing_widget.codec_probe)
    assert w.processing_widget.banner_options()==actual
    w.processing_widget.banner_group.setChecked(False);w.close();app.processEvents()
check('UI-to-worker wiring and settings persist after restart',ui_roundtrip)

def queue_cancel():
    long_banner=dest/'long-banner.mp4'
    f.run_ffmpeg(['-y','-stream_loop','-1','-i',str(banner),'-t','60','-c','copy',str(long_banner)])
    worker=Worker(files=[str(main)],filters=[],zoom_mode='static',zoom_static=100,zoom_min=100,zoom_max=100,
        speed_mode='static',speed_static=100,speed_min=100,speed_max=100,overlay_file=None,overlay_pos='',out_dir=str(dest/'cancel'),
        mute_audio=False,output_format=REELS_FORMAT_NAME,blur_background=False,strip_metadata=True,codec='libx264',
        subtitle_settings={},auto_crop=False,overlay_audio=None,original_volume=100,overlay_volume=100,
        banner_settings=settings|{'path':str(long_banner)})
    worker.start();time.sleep(.8);worker.stop();wait_thread(worker,8)
    assert worker.cancelled and not worker.errors and not worker.output_paths
    assert not list((dest/'cancel').glob('*.mp4'))
check('cancel banner rendering safely; no partial output',queue_cancel)

(dest/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('REPORT',dest/'results.json')
print('RESULT',sum(r['status']=='PASS' for r in results),'/',len(results))
sys.exit(any(r['status']=='FAIL' for r in results))
