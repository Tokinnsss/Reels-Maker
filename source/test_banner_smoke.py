import test_loader
import pathlib,time
from utils import ffmpeg_utils as f

root=pathlib.Path(__file__).resolve().parent.parent/'banner-tests'
root.mkdir(exist_ok=True)
main=root/'main.mp4';banner=root/'green-banner.mp4'
f.run_ffmpeg(['-y','-f','lavfi','-i','testsrc2=size=320x240:rate=30:duration=4',
    '-f','lavfi','-i','sine=frequency=440:duration=4','-c:v','libx264','-c:a','aac','-shortest',str(main)])
f.run_ffmpeg(['-y','-f','lavfi','-i','color=0x00FF00:s=200x100:r=24:d=1.5',
    '-f','lavfi','-i','sine=frequency=990:duration=1.5','-vf','drawbox=x=60:y=20:w=80:h=60:color=red:t=fill',
    '-c:v','libx264','-c:a','aac','-shortest',str(banner)])
base=dict(in_path=str(main),out_path=str(root/'smoke.mp4'),filters=[],zoom_p=100,speed_p=100,overlay_file=None,
    overlay_pos='',output_format='Оригинальный',blur_background=False,
    banner_settings={'enabled':True,'path':str(banner),'start':2,'key_enabled':True})
start=time.monotonic();path=f.process_single(**base)
print('PASS',path,f.probe_media(path)['duration'],'elapsed',time.monotonic()-start)
