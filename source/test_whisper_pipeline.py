import test_loader
import sys,os,pathlib,json,time
from PyQt5.QtWidgets import QApplication
from workers.worker import Worker
from utils import ffmpeg_utils as ff
from utils import subtitle_utils as su

root=pathlib.Path(__file__).resolve().parent.parent
speech=root/'speech-test'
model=next((speech/'huggingface/hub/models--Systran--faster-whisper-tiny/snapshots').iterdir())
sys.executable=str(root.parent/'outputs/ReelsMakerPro-fixed/ReelsMakerPro.exe')
app=QApplication([])
ff.run_ffmpeg(['-y','-f','lavfi','-i','color=blue:s=320x240:r=15','-i',str(speech/'speech.wav'),
    '-c:v','libx264','-c:a','aac','-shortest',str(speech/'speech.mp4')])
options=dict(files=[str(speech/'speech.mp4')],out_dir=str(speech/'export'),filters=[],zoom_mode='static',zoom_static=100,
    zoom_min=100,zoom_max=100,speed_mode='static',speed_static=100,speed_min=100,speed_max=100,overlay_file=None,
    overlay_pos='',mute_audio=False,output_format='Оригинальный',blur_background=False,strip_metadata=True,codec='libx264',
    subtitle_settings={'mode':'whisper','model':str(model),'language':'English','words_per_line':5,'style':{'size':24}},
    auto_crop=False,overlay_audio=None,original_volume=100,overlay_volume=100)
worker=Worker(**options);worker.start()
end=time.monotonic()+90
while worker.isRunning() and time.monotonic()<end:app.processEvents();time.sleep(.05)
assert not worker.isRunning(),'transcription timeout'
assert not worker.errors,worker.errors
assert len(worker.output_paths)==1
info=ff.probe_media(worker.output_paths[0]);assert info['video'] and info['audio'] and info['duration']>5
result={'status':'PASS','test':'Full Whisper pipeline: extract audio, subprocess recognition, styled subtitle export',
    'model':'tiny (local test cache)','source':'locally synthesized English speech','output':worker.output_paths[0],'duration':info['duration']}
(speech/'pipeline-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
