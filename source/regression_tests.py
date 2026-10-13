import test_loader
import os,sys,pathlib,json,time,threading,traceback,hashlib
from PyQt5.QtWidgets import QApplication
from utils import ffmpeg_utils as f
from utils import constants as c
from workers.worker import Worker
from ui.main_window import VideoUnicApp
from ui.subtitle_preview_dialog import SubtitlePreviewDialog

app=QApplication([])
root=pathlib.Path(__file__).resolve().parent.parent
folder=root/('regression_'+time.strftime('%H%M%S')); folder.mkdir()
source=root/'media/sound.mp4'; silent=root/'media/silent.mp4'
results=[]
def check(name,action):
    started=time.monotonic()
    try:
        detail=action()
        results.append({'test':name,'status':'PASS','seconds':round(time.monotonic()-started,2),'details':str(detail or '')})
        print('PASS',name,flush=True)
    except Exception as e:
        results.append({'test':name,'status':'FAIL','error':str(e),'traceback':traceback.format_exc()})
        print('FAIL',name,str(e),flush=True)

base=dict(in_path=str(source),filters=[],zoom_p=100,speed_p=100,overlay_file=None,overlay_pos='',
    output_format=c.REELS_FORMAT_NAME,blur_background=False,mute_audio=False,strip_metadata=True,codec='libx264')
def render(name,changes=None,expect_audio=True,expected_size=(1080,1920),expected_duration=2):
    path=f.process_single(**(base|dict(out_path=str(folder/(name+'.mp4')))|(changes or {})))
    info=f.probe_media(path)
    assert bool(info['audio'])==expect_audio,(name,'audio',info['audio'])
    if expected_size: assert (info['video']['width'],info['video']['height'])==expected_size,info['video']
    assert abs(info['duration']-expected_duration)<.25,(info['duration'],expected_duration)
    return path

check('normal 9:16',lambda:render('normal'))
check('no audio track',lambda:render('silent',{'in_path':str(silent)},False))
check('mute original',lambda:render('muted',{'mute_audio':True},False))
check('silent + added music',lambda:render('silent_music',{'in_path':str(silent),'overlay_audio_path':str(source)}))
check('blur background',lambda:render('blur',{'blur_background':True}))
check('split screen',lambda:render('split',{'filler_path':str(silent)}))
check('speed 150%',lambda:render('speed',{'speed_p':150},expected_duration=2/1.5))
check('speed 25%',lambda:render('slow',{'speed_p':25},expected_duration=8))
check('zoom 150%',lambda:render('zoom',{'zoom_p':150}))
check('zoom 80%',lambda:render('zoom_out',{'zoom_p':80}))
check('mix audio',lambda:render('mix',{'overlay_audio_path':str(source),'original_volume':.5,'overlay_volume':.2}))
check('NVIDIA H264',lambda:render('nvenc',{'codec':'h264_nvenc'}))
check('NVIDIA HEVC',lambda:render('hevc',{'codec':'hevc_nvenc'}))
check('original dimensions',lambda:render('original',{'output_format':'Оригинальный'},expected_size=(320,240)))

srt=folder/"субтитры ' проверка.srt"
srt.write_text('1\n00:00:00,000 --> 00:00:02,000\nПроверка стиля субтитров\n',encoding='utf-8')
style={'font':'Arial','size':30,'color':'#00FF00','outline_color':'#FF0000','outline_width':3,'position':8,'bold':True}
check('SRT with Cyrillic/quote path and custom style',lambda:render('srt',{'srt_path':str(srt),'subtitle_style':style}))
def styled_frame():
    path=f.generate_preview(str(source),str(folder/'styled.png'),[],100,None,'',c.REELS_FORMAT_NAME,False,srt_path=str(srt),subtitle_style=style)
    from PyQt5.QtGui import QImage
    image=QImage(path)
    green=0
    for y in range(20,650,2):
        for x in range(0,1080,2):
            p=image.pixelColor(x,y)
            if p.green()>160 and p.red()<80 and p.blue()<80: green+=1
    assert green>20,green
    return path
check('subtitle color/position visible in frame',styled_frame)

def no_overwrite():
    target=folder/'existing.mp4'; target.write_bytes(b'original-file-must-survive')
    result=render('existing')
    assert target.read_bytes()==b'original-file-must-survive'
    assert pathlib.Path(result).name=='existing_2.mp4'
    return result
check('existing output preserved',no_overwrite)

def gif_test():
    gif=folder/'source.gif'
    f.run_ffmpeg(['-y','-i',str(source),'-vf','fps=10,scale=160:120',str(gif)])
    return render('gif',{'in_path':str(gif)},False)
check('GIF terminates at source duration',gif_test)
def overlay_test():
    logo=folder/'logo.png'
    f.run_ffmpeg(['-y','-f','lavfi','-i','color=red:s=64x64','-frames:v','1','-update','1',str(logo)])
    return render('overlay',{'overlay_file':str(logo)})
check('static image overlay',overlay_test)
check('short clip crop detection',lambda:f.detect_crop_dimensions(str(source)))
check('variation processing',lambda:f.process_single(**(base|dict(out_path=str(folder/'variations.mp4'),uniquify=True))))

for name in c.FILTERS:
    check('filter: '+name,lambda name=name:render('filter_'+str(len(results)),{'filters':[name],'output_format':'Оригинальный'},expected_size=(320,240)))

def worker_options(files,out):
    return dict(files=list(map(str,files)),out_dir=str(out),filters=[],zoom_mode='static',zoom_static=100,zoom_min=100,zoom_max=100,
        speed_mode='static',speed_static=100,speed_min=100,speed_max=100,overlay_file=None,overlay_pos='',mute_audio=False,
        output_format='Оригинальный',blur_background=False,strip_metadata=True,codec='libx264',subtitle_settings={},
        auto_crop=False,overlay_audio=None,original_volume=100,overlay_volume=100)
def wait_thread(worker,timeout=30):
    end=time.monotonic()+timeout
    while worker.isRunning() and time.monotonic()<end:
        app.processEvents(); time.sleep(.02)
    assert not worker.isRunning(),'thread did not stop'
    app.processEvents()
def queue_test():
    bad=folder/'corrupt.mp4';bad.write_bytes(b'not media')
    other=folder/'second';other.mkdir()
    same=other/source.name;same.write_bytes(source.read_bytes())
    worker=Worker(**worker_options([source,bad,same],folder/'queue'))
    worker.start();wait_thread(worker)
    assert len(worker.output_paths)==2,worker.errors
    assert len(worker.errors)==1,worker.errors
    assert len(set(worker.output_paths))==2
    return worker.output_paths
check('queue continues after corrupt file and preserves duplicate basenames',queue_test)

def cancellation():
    long=folder/'long.mp4'
    f.run_ffmpeg(['-y','-stream_loop','-1','-i',str(source),'-t','60','-c','copy',str(long)])
    opts=worker_options([long,source],folder/'cancelled');opts['output_format']=c.REELS_FORMAT_NAME
    worker=Worker(**opts);worker.start();time.sleep(.4)
    start=time.monotonic();worker.stop();wait_thread(worker,8)
    assert worker.cancelled and not worker.output_paths
    assert not list((folder/'cancelled').glob('*.mp4'))
    assert time.monotonic()-start<5
check('cancel active FFmpeg and discard partial output',cancellation)

def ui_settings():
    w=VideoUnicApp();wait_thread(w.processing_widget.codec_probe)
    p=w.processing_widget;p.subs_size_spin.setValue(44);p.subtitle_style=style.copy()
    w.settings['theme']='Light';w.persist();w.close();app.processEvents()
    w=VideoUnicApp();wait_thread(w.processing_widget.codec_probe)
    assert w.settings['theme']=='Light'
    assert w.processing_widget.subs_size_spin.value()==44
    assert w.processing_widget.subtitle_style['color']=='#00FF00'
    assert w.processing_widget.cancel_button.text()=='Отменить'
    w.close();app.processEvents()
check('UI initializes and preferences survive restart',ui_settings)

def rapid_dialog():
    dialog=SubtitlePreviewDialog(str(source),str(srt),initial_style=style)
    dialog.show()
    for size in range(20,60):
        dialog.size_spin.setValue(size);dialog.update_preview();app.processEvents()
    end=time.monotonic()+.5
    while time.monotonic()<end:app.processEvents();time.sleep(.02)
    dialog.reject();app.processEvents()
    assert not dialog.preview_thread or not dialog.preview_thread.isRunning()
    assert not [p for p in dialog.temp_files if os.path.exists(p)]
check('rapid subtitle changes and close during preview',rapid_dialog)

report=folder/'results.json';report.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('REPORT',report,flush=True)
print('RESULT',sum(r['status']=='PASS' for r in results),'/',len(results),flush=True)
sys.exit(any(r['status']=='FAIL' for r in results))
