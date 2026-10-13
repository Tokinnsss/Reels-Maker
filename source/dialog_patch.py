"""Serialize preview requests and retain QThreads until they really finish."""
import threading
from PyQt5.QtCore import QTimer
from utils import ffmpeg_utils as ff
from utils.constants import REELS_FORMAT_NAME

_old_dialog_init=SubtitlePreviewDialog.__init__

class SubtitlePreviewGenerator(QThread):
    finished_signal=pyqtSignal(str)
    error_signal=pyqtSignal(str)
    def __init__(self,video_path,srt_path,style_params,temp_output):
        QThread.__init__(self)
        self.video_path=video_path; self.srt_path=srt_path
        self.style_params=dict(style_params); self.temp_output=temp_output
        self.cancel_event=threading.Event()
    def stop(self): self.cancel_event.set()
    def run(self):
        ff._job.cancel=self.cancel_event
        try:
            path=ff.generate_preview(self.video_path,self.temp_output,[],100,None,'',REELS_FORMAT_NAME,True,
                srt_path=self.srt_path,subtitle_style=self.style_params)
            self.finished_signal.emit(path)
        except ff.CancelledError: pass
        except Exception as exc: self.error_signal.emit(str(exc))
        finally: ff._job.cancel=None

def init_dialog(self,video_path,srt_path,parent=None,initial_style=None):
    self._pending=False; self._closing=False
    self._timer=QTimer(); self._timer.setSingleShot(True)
    self._timer.timeout.connect(self._start_preview)
    _old_dialog_init(self,video_path,srt_path,parent)
    self._timer.setParent(self)
    if initial_style:
        self.current_style.update(initial_style)
        self.font_combo.setCurrentText(self.current_style.get('font','Arial'))
        self.size_spin.setValue(int(self.current_style.get('font_size',self.current_style.get('size',36))))
        self.outline_spin.setValue(int(self.current_style.get('outline_width',2)))
        self.position_combo.setCurrentIndex(max(0,min(8,int(self.current_style.get('position',2))-1)))
    self.update_preview()

def update_preview(self,*args):
    if not self._closing:
        self._pending=True; self._timer.start(200)

def start_preview(self):
    if self._closing or not self._pending: return
    if self.preview_thread and self.preview_thread.isRunning(): return
    self._pending=False
    path=os.path.join(tempfile.gettempdir(),'sub_preview_'+uuid.uuid4().hex+'.png')
    self.temp_files.append(path)
    self.preview_label.setText('Генерация предпросмотра…')
    style=dict(self.current_style)
    style['font_size']=style.get('size',36)
    self.preview_thread=SubtitlePreviewGenerator(self.video_path,self.srt_path,style,path)
    self.preview_thread.finished_signal.connect(self.on_preview_ready)
    self.preview_thread.error_signal.connect(self.on_preview_error)
    self.preview_thread.finished.connect(self._preview_stopped)
    self.preview_thread.start()

def stopped(self):
    if self.preview_thread and self.preview_thread.isRunning(): QTimer.singleShot(50,self._preview_stopped); return
    if self.preview_thread: self.preview_thread.deleteLater()
    self.preview_thread=None
    if self._pending: self._timer.start(100)

def cleanup(self):
    self._closing=True; self._timer.stop()
    if self.preview_thread and self.preview_thread.isRunning():
        self.preview_thread.stop()
        if not self.preview_thread.wait(5000): return False
    for path in self.temp_files:
        try: os.remove(path)
        except OSError: pass
    self.temp_files.clear()
    return True

def done(self,result):
    if self._cleanup_preview(): QDialog.done(self,result)

def close_event(self,event):
    if self._cleanup_preview(): event.accept()
    else: event.ignore()

def get_style(self):
    self.on_style_changed()
    style=dict(self.current_style)
    style['font_size']=style['size']
    return style

SubtitlePreviewDialog.__init__=init_dialog
SubtitlePreviewDialog.update_preview=update_preview
SubtitlePreviewDialog._start_preview=start_preview
SubtitlePreviewDialog._preview_stopped=stopped
SubtitlePreviewDialog._cleanup_preview=cleanup
SubtitlePreviewDialog.done=done
SubtitlePreviewDialog.closeEvent=close_event
SubtitlePreviewDialog.get_style=get_style
