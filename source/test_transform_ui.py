import test_loader
import pathlib,json,time,sys,traceback
from PyQt5.QtWidgets import QApplication,QTabWidget,QLabel,QStyleOptionViewItem,QStyle
from PyQt5.QtGui import QFontDatabase,QImage,QMouseEvent,QKeyEvent
from PyQt5.QtCore import Qt,QPoint,QPointF,QEvent
class QTest:
    @staticmethod
    def mouseClick(widget,button,modifiers,pos):
        QApplication.sendEvent(widget,QMouseEvent(QEvent.MouseButtonPress,QPointF(pos),button,button,modifiers))
        QApplication.sendEvent(widget,QMouseEvent(QEvent.MouseButtonRelease,QPointF(pos),button,Qt.NoButton,modifiers))
    @staticmethod
    def keyClick(widget,key):
        QApplication.sendEvent(widget,QKeyEvent(QEvent.KeyPress,key,Qt.NoModifier))
        QApplication.sendEvent(widget,QKeyEvent(QEvent.KeyRelease,key,Qt.NoModifier))
from utils import ffmpeg_utils as f
from ui import main_window as u
app=QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeuib.ttf')
root=pathlib.Path(__file__).resolve().parent.parent/'transform-checks';root.mkdir(exist_ok=True)
dest=root/time.strftime('%H%M%S');dest.mkdir()
results=[]
def check(name,fn):
    try:
        detail=fn();results.append(dict(test=name,status='PASS',details=str(detail or '')));print('PASS',name,flush=True)
    except Exception as e:
        results.append(dict(test=name,status='FAIL',error=str(e),traceback=traceback.format_exc()));print('FAIL',name,str(e),flush=True)
source=root/'pattern.mp4';filler=root/'filler.mp4'
if not source.exists():
    f.run_ffmpeg(['-y','-f','lavfi','-i','color=red:s=322x242:r=25:d=2,drawbox=x=0:y=0:w=iw:h=ih/2:color=blue:t=fill','-c:v','libx264',str(source)])
    f.run_ffmpeg(['-y','-f','lavfi','-i','color=lime:s=320x240:r=25:d=2','-c:v','libx264',str(filler)])
base=dict(in_path=str(source),filters=[],zoom_p=100,speed_p=100,overlay_file=None,overlay_pos='',output_format='Оригинальный',blur_background=False)
def frame(name,**opts):
    path=f.process_single(**(base|opts|dict(out_path=str(dest/(name+'.png')),_frame=True)))
    return QImage(path)
def geometry(zoom):
    image=frame('zoom'+str(zoom),zoom_p=zoom)
    assert (image.width(),image.height())==(322,242),(image.width(),image.height())
for z in (25,80,120,150,300):check('zoom keeps canvas '+str(z),lambda z=z:geometry(z))
def split():
    image=frame('split',filters=['Отразить по вертикали'],zoom_p=150,filler_path=str(filler),export_settings={'profile':'vertical','resolution':180})
    bottom=image.pixelColor(90,280);top=image.pixelColor(90,20)
    assert bottom.green()>150 and bottom.red()<50,(bottom.name(),top.name())
    assert top.red()>150 and top.blue()<50,top.name()
check('flip/zoom affect source, preserve filler and layout',split)
def anamorphic():
    path=root/'sar.mp4'
    if not path.exists():f.run_ffmpeg(['-y','-i',str(source),'-vf','setsar=2/1','-c:v','libx264',str(path)])
    image=frame('sar',in_path=str(path))
    assert (image.width(),image.height())==(644,242),(image.width(),image.height())
check('non-square pixels preserve display proportions',anamorphic)
def rotated():
    path=root/'rotated.mp4'
    f.run_ffmpeg(['-y','-display_rotation','90','-i',str(source),'-c','copy',str(path)])
    assert f.probe_media(str(path))['video'].get('side_data_list'),'Test source must contain rotation metadata'
    image=frame('rotated',in_path=str(path),export_settings={'profile':'original','resolution':480})
    assert (image.width(),image.height())==(242,322),(image.width(),image.height())
check('phone rotation and original profile',rotated)
def preview_export():
    options=base|dict(filters=['Отразить по горизонтали'],zoom_p=120,speed_p=150,export_settings={'profile':'square','resolution':180})
    a=f.process_single(**(options|dict(out_path=str(dest/'preview.png'),_frame=True)))
    b=f.process_single(**(options|dict(out_path=str(dest/'video.mp4'))))
    f.run_ffmpeg(['-y','-i',b,'-ss','0.5','-frames:v','1',str(dest/'export.png')])
    ia,ib=QImage(a),QImage(str(dest/'export.png'))
    assert ia.size()==ib.size()
    for x,y in ((40,40),(90,90),(140,140)):
        ca,cb=ia.pixelColor(x,y),ib.pixelColor(x,y)
        assert max(abs(ca.red()-cb.red()),abs(ca.blue()-cb.blue()),abs(ca.green()-cb.green()))<20
    assert abs(f.probe_media(b)['duration']-2/1.5)<.15
check('preview/export composition and speed agree',preview_export)

u.load_settings=lambda:dict(ffmpeg_path='',strip_metadata=True,theme='Dark')
w=u.VideoUnicApp();w.resize(1280,850);w.show();app.processEvents();p=w.processing_widget
tabs=p.findChildren(QTabWidget)[0];tabs.setCurrentIndex(1);app.processEvents()
item=next(p.filter_list.item(i) for i in range(p.filter_list.count()) if p.filter_list.item(i).data(Qt.UserRole))
p.filter_list.scrollToItem(item);app.processEvents()
def clicks():
    item.setCheckState(Qt.Unchecked)
    index=p.filter_list.indexFromItem(item)
    opt=QStyleOptionViewItem();opt.initFrom(p.filter_list);opt.rect=p.filter_list.visualItemRect(item)
    opt.features|=QStyleOptionViewItem.HasCheckIndicator;opt.checkState=Qt.Unchecked
    indicator=p.filter_list.style().subElementRect(QStyle.SE_ItemViewItemCheckIndicator,opt,p.filter_list)
    for pos in (indicator.center(),QPoint(opt.rect.right()-20,opt.rect.center().y())):
        for expected in (Qt.Checked,Qt.Unchecked,Qt.Checked,Qt.Unchecked):
            QTest.mouseClick(p.filter_list.viewport(),Qt.LeftButton,Qt.NoModifier,pos);app.processEvents()
            assert item.checkState()==expected,(pos.x(),item.checkState(),expected)
    p.filter_list.setCurrentItem(item);p.filter_list.setFocus()
    QTest.keyClick(p.filter_list,Qt.Key_Space);assert item.checkState()==Qt.Checked
    QTest.keyClick(p.filter_list,Qt.Key_Space);assert item.checkState()==Qt.Unchecked
check('checkbox, row and keyboard toggle exactly once',clicks)
def radios():
    for static,dynamic,container in ((p.zoom_static_radio,p.zoom_dynamic_radio,p.zoom_dynamic_widget),(p.speed_static_radio,p.speed_dynamic_radio,p.speed_dynamic_widget)):
        for _ in range(3):
            static.click();app.processEvents();assert static.isChecked() and not dynamic.isChecked()
            dynamic.click();app.processEvents();assert dynamic.isChecked() and not static.isChecked() and not container.isHidden()
check('scale and speed mode switching',radios)
def dynamic_preview():
    from PyQt5.QtWidgets import QListWidgetItem
    item=QListWidgetItem('pattern');item.setData(Qt.UserRole,str(source));p.video_list_widget.addItem(item);item.setSelected(True)
    p.zoom_dynamic_radio.setChecked(True);p.zoom_min_spin.setValue(110);p.zoom_max_spin.setValue(130)
    p.speed_dynamic_radio.setChecked(True);p.speed_min_spin.setValue(110);p.speed_max_spin.setValue(150)
    captured={};original=f.generate_preview
    def fake(**kwargs):
        captured.update(kwargs);im=QImage(20,20,QImage.Format_RGB32);im.fill(Qt.black);im.save(kwargs['out_path']);return kwargs['out_path']
    f.generate_preview=fake
    try:
        p.on_update_preview();deadline=time.monotonic()+10
        while p.preview_thread and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert captured['zoom_p']==120 and captured['speed_p']==130,captured
        assert p.process_button.isEnabled()
    finally:f.generate_preview=original
check('random-range preview uses selected range, restores buttons',dynamic_preview)
def formats():
    p.export_group.setChecked(True);app.processEvents();assert not p.output_format_combo.isEnabled()
    p.export_group.setChecked(False);app.processEvents();assert p.output_format_combo.isEnabled()
check('multi-export explains overridden output format',formats)
def branding():
    assert 'Reels Maker' in w.windowTitle()
    texts='\n'.join(x.text() for x in w.findChildren(QLabel))
    assert 'https://t.me/tokinnssoft' in texts and 'magerdev' not in texts and 'donatepay' not in texts
check('name and social link',branding)
tabs.setCurrentIndex(0);w.grab().save(str(dest/'interface-dark.png'))
w.apply_stylesheet('Light');app.processEvents();w.grab().save(str(dest/'interface-light.png'))
w.apply_stylesheet('Dark');tabs.setCurrentIndex(1);app.processEvents();w.grab().save(str(dest/'transform.png'))
p.codec_probe.stop();p.codec_probe.wait(10000);w.close();app.processEvents()
(dest/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('REPORT',dest,flush=True);print('RESULT',sum(r['status']=='PASS' for r in results),'/',len(results),flush=True)
sys.exit(any(r['status']=='FAIL' for r in results))
