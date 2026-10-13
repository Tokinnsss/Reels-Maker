"""Persistent settings, complete subtitle styles, safe Qt thread lifecycle."""
import json
import threading
from PyQt5.QtCore import QTimer, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QSizePolicy, QDoubleSpinBox, QColorDialog, QFormLayout
from utils import ffmpeg_utils as ff
from utils.path_utils import user_data_dir

_original_processing_init = ProcessingWidgetContent.__init__
_original_subs_mode = ProcessingWidgetContent.on_subs_mode_changed

def settings_path():
    return os.path.join(user_data_dir(), 'settings.json')

def load_settings():
    defaults = {'ffmpeg_path':'', 'strip_metadata':True, 'theme':'Dark'}
    try:
        with open(settings_path(), encoding='utf-8') as stream: data = json.load(stream)
        if isinstance(data, dict): defaults.update(data)
    except (OSError, ValueError): pass
    if defaults.get('theme') not in ('Dark', 'Light'): defaults['theme'] = 'Dark'
    return defaults

def save_settings(settings):
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + '.' + uuid.uuid4().hex + '.tmp'
    try:
        with open(temp, 'w', encoding='utf-8') as stream:
            json.dump(settings, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.remove(temp)

_PREFS = ['scenario_combo','output_format_combo','blur_background_checkbox','codec_combo',
    'auto_crop_checkbox','zoom_static_radio','zoom_dynamic_radio','zoom_static_spin',
    'zoom_min_spin','zoom_max_spin','speed_static_radio','speed_dynamic_radio','speed_static_spin',
    'speed_min_spin','speed_max_spin','split_group','filler_combo','split_layout_combo','split_pos_combo',
    'subs_off_radio','subs_from_file_radio','subs_generate_radio','subs_model_combo','subs_lang_combo',
    'subs_words_spin','subs_size_spin','mute_checkbox','orig_vol_slider','over_vol_slider',
    'uniquify_group','uq_trim_cb','uq_pitch_cb','uq_speed_cb','uq_encode_cb']

def capture_preferences(self):
    result = {}
    for name in _PREFS:
        widget = getattr(self, name)
        if isinstance(widget, QComboBox): result[name] = widget.currentText().replace(' — нет поддержки','')
        elif isinstance(widget, (QSpinBox, QSlider)): result[name] = widget.value()
        else: result[name] = widget.isChecked()
    result['filters'] = self.selected_filters()
    result['subtitle_style'] = dict(self.subtitle_style)
    result['video_banner'] = self.banner_options()
    result['smart'] = self.smart_options()
    result['export'] = self.export_options()
    return result

def restore_preferences(self, prefs):
    if not isinstance(prefs, dict): return
    for name in _PREFS:
        if name not in prefs: continue
        widget, value = getattr(self, name), prefs[name]
        if isinstance(widget, QComboBox) and isinstance(value, str):
            index = widget.findText(value)
            if index >= 0: widget.setCurrentIndex(index)
        elif isinstance(widget, (QSpinBox, QSlider)) and isinstance(value, int): widget.setValue(value)
        elif isinstance(value, bool): widget.setChecked(value)
    self.subtitle_style = prefs.get('subtitle_style', {}) if isinstance(prefs.get('subtitle_style'),dict) else {}
    selected = prefs.get('filters', [])
    for i in range(self.filter_list.count()):
        item = self.filter_list.item(i)
        if item.data(Qt.UserRole): item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in selected else Qt.Unchecked)
    self.on_zoom_mode_changed(); self.on_speed_mode_changed(); self.on_subs_mode_changed()
    self.restore_banner(prefs.get('video_banner', {}))
    self.restore_advanced(prefs)

def persist(self):
    self.settings['processing'] = self.processing_widget.capture_preferences()
    save_settings(self.settings)

def window_init(self):
    QMainWindow.__init__(self)
    self.temp_dir = tempfile.mkdtemp(prefix='reels_maker_')
    self.temp_files = []
    self.settings = load_settings()
    self._close_pending = False
    try: ff.configure_executables(self.settings.get('ffmpeg_path',''))
    except Exception:
        logging.exception('Custom FFmpeg unavailable; using bundled binaries')
        self.settings['ffmpeg_path'] = ''
        ff.configure_executables('')
    self.init_ui()
    self.setWindowTitle('Reels Maker 1.1.2')
    self.apply_stylesheet(self.settings.get('theme','Dark'))
    self.processing_widget.restore_preferences(self.settings.get('processing',{}))

def show_settings(self):
    dialog = SettingsDialog(self, self.settings)
    if dialog.exec_() != QDialog.Accepted: return
    proposed = dict(self.settings, **dialog.get_settings())
    previous = self.settings
    try:
        ff.configure_executables(proposed.get('ffmpeg_path',''))
        save_settings(proposed)
    except Exception as exc:
        ff.configure_executables(previous.get('ffmpeg_path',''))
        QMessageBox.warning(self, 'Настройки не сохранены', str(exc)); return
    self.settings = proposed
    self.apply_stylesheet(proposed['theme'])
    self.processing_widget.restart_codec_probe()

class CodecProbeWorker(QThread):
    finished_signal = pyqtSignal(dict)
    def __init__(self, parent=None):
        QThread.__init__(self,parent); self.cancel_event = threading.Event()
    def stop(self): self.cancel_event.set()
    def run(self):
        ff._job.cancel = self.cancel_event
        try: self.finished_signal.emit(ff.detect_available_codecs(CODECS))
        except ff.CancelledError: pass
        except Exception: logging.exception('Codec detection failed')
        finally: ff._job.cancel = None

def restart_codec_probe(self):
    if self.codec_probe and self.codec_probe.isRunning():
        self.codec_probe.stop()
        if not self.codec_probe.wait(5000): return
    self.codec_probe = CodecProbeWorker(self)
    self.codec_probe.finished_signal.connect(self.on_codecs_detected)
    self.codec_probe.start()

def processing_init(self, parent_window):
    self.subtitle_style = {}
    self._job_errors = []
    _original_processing_init(self, parent_window)
    self.add_banner_tab()
    self.add_advanced_tabs()
    self.uniquify_group.setTitle('Вариации видео')
    self.uniquify_group.setToolTip('Случайные изменения длительности, скорости, тона и качества кодирования.')
    self.preview_group.setToolTip('Кадр с теми же фильтрами и стилем SRT, что используются при экспорте.')
    self.subs_preview_btn.setText('Настроить стиль')
    actions = QWidget(self)
    layout = QHBoxLayout(actions); layout.setContentsMargins(0,0,0,0)
    self.cancel_button = QPushButton('Отменить', actions)
    self.cancel_button.setEnabled(False)
    self.cancel_button.clicked.connect(self.cancel_processing)
    self.open_output_button = QPushButton('Открыть результат', actions)
    self.open_output_button.setEnabled(False)
    self.open_output_button.clicked.connect(self.open_output)
    layout.addWidget(self.cancel_button); layout.addWidget(self.open_output_button)
    def locate(layout):
        for i in range(layout.count()):
            item=layout.itemAt(i)
            if item.widget() is self.process_button: return layout,i
            if item.layout():
                found=locate(item.layout())
                if found: return found
        return None
    parent_layout,index = locate(self.process_button.parentWidget().layout())
    parent_layout.insertWidget(index+1, actions)
    for combo in self.findChildren(QComboBox):
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(12)
        combo.setMinimumWidth(0)
        combo.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    for tab in self.findChildren(QTabWidget):
        for i in range(tab.count()):
            page = tab.widget(i)
            if isinstance(page, QScrollArea): page.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

def controls(self, enabled):
    self.process_button.setEnabled(enabled)
    self.preview_button.setEnabled(enabled)
    self.left_panel.setEnabled(enabled)
    for tab in self.findChildren(QTabWidget): tab.setEnabled(enabled)
    self.parent_window.settings_btn.setEnabled(enabled)

def on_subs_mode(self, *args):
    _original_subs_mode(self)
    self.update_preview_btn_state()

def style_button_state(self, *args):
    self.subs_preview_btn.setEnabled(not self.subs_off_radio.isChecked())

def selected_style(self):
    style = dict(self.subtitle_style)
    style['size'] = style['font_size'] = self.subs_size_spin.value()
    return style

def add_banner_tab(self):
    page=QWidget(self)
    layout=QVBoxLayout(page)
    intro=QLabel('В выбранный момент основной ролик и его звук ставятся на паузу. '
        'Баннер проигрывается целиком со своим звуком, затем основной ролик продолжается с того же места.',page)
    intro.setWordWrap(True);layout.addWidget(intro)
    self.banner_group=QGroupBox('Вставить видеобаннер',page)
    self.banner_group.setCheckable(True);self.banner_group.setChecked(False)
    form=QFormLayout(self.banner_group)
    file_row=QWidget(self.banner_group);file_layout=QHBoxLayout(file_row);file_layout.setContentsMargins(0,0,0,0)
    self.banner_path_edit=QLineEdit(file_row);self.banner_path_edit.setPlaceholderText('Видео со звуком: MP4, MOV, MKV, WebM…')
    browse=QPushButton('Обзор…',file_row);browse.clicked.connect(self.browse_banner)
    file_layout.addWidget(self.banner_path_edit,1);file_layout.addWidget(browse)
    form.addRow('Файл баннера:',file_row)
    self.banner_start_spin=QDoubleSpinBox(self.banner_group)
    self.banner_start_spin.setRange(0,360000);self.banner_start_spin.setDecimals(2)
    self.banner_start_spin.setSuffix(' с');self.banner_start_spin.setValue(5)
    self.banner_start_spin.setToolTip('Время в основном ролике после изменения скорости и обрезки. Точность — один кадр (1/30 с). 0 — вставка в начало.')
    form.addRow('Момент вставки:',self.banner_start_spin)
    self.banner_mode_combo=QComboBox(self.banner_group)
    self.banner_mode_combo.addItem('Поверх замершего кадра','overlay')
    self.banner_mode_combo.addItem('На чёрном фоне','replace')
    form.addRow('Фон баннера:',self.banner_mode_combo)
    self.banner_scale_spin=QSpinBox(self.banner_group);self.banner_scale_spin.setRange(5,100)
    self.banner_scale_spin.setSuffix(' %');self.banner_scale_spin.setValue(100)
    self.banner_scale_spin.setToolTip('Размер области для баннера относительно кадра. Пропорции видео сохраняются.')
    form.addRow('Размер:',self.banner_scale_spin)
    self.banner_position_combo=QComboBox(self.banner_group)
    for title,value in [('По центру','center'),('Сверху','top'),('Снизу','bottom'),('Сверху слева','top_left'),
            ('Сверху справа','top_right'),('Снизу слева','bottom_left'),('Снизу справа','bottom_right')]:
        self.banner_position_combo.addItem(title,value)
    form.addRow('Расположение:',self.banner_position_combo)
    self.banner_volume_spin=QSpinBox(self.banner_group);self.banner_volume_spin.setRange(0,300)
    self.banner_volume_spin.setSuffix(' %');self.banner_volume_spin.setValue(100)
    form.addRow('Громкость баннера:',self.banner_volume_spin)
    self.banner_key_checkbox=QCheckBox('Удалить цвет фона (гринскрин)',self.banner_group)
    form.addRow(self.banner_key_checkbox)
    self.banner_color='#00FF00'
    self.banner_color_button=QPushButton('Цвет: #00FF00',self.banner_group)
    self.banner_color_button.clicked.connect(self.choose_banner_color)
    self.banner_color_button.setEnabled(False)
    form.addRow('Удаляемый цвет:',self.banner_color_button)
    self.banner_similarity_spin=QDoubleSpinBox(self.banner_group)
    self.banner_similarity_spin.setRange(.1,100);self.banner_similarity_spin.setDecimals(1)
    self.banner_similarity_spin.setSuffix(' %');self.banner_similarity_spin.setValue(20)
    self.banner_similarity_spin.setToolTip('Больше значение — удаляется больше оттенков выбранного цвета.')
    self.banner_similarity_spin.setEnabled(False)
    form.addRow('Чувствительность:',self.banner_similarity_spin)
    self.banner_blend_spin=QDoubleSpinBox(self.banner_group)
    self.banner_blend_spin.setRange(0,100);self.banner_blend_spin.setDecimals(1)
    self.banner_blend_spin.setSuffix(' %');self.banner_blend_spin.setValue(8)
    self.banner_blend_spin.setToolTip('Смягчает края вырезанного объекта. Слишком большое значение делает объект полупрозрачным.')
    self.banner_blend_spin.setEnabled(False)
    form.addRow('Мягкость краёв:',self.banner_blend_spin)
    for control in (self.banner_color_button,self.banner_similarity_spin,self.banner_blend_spin):
        self.banner_key_checkbox.toggled.connect(control.setEnabled)
    self.banner_preview_button=QPushButton('Предпросмотр баннера',self.banner_group)
    self.banner_preview_button.clicked.connect(self.on_update_preview)
    form.addRow(self.banner_preview_button)
    layout.addWidget(self.banner_group)
    note=QLabel('Время задаётся в секундах: 12,5 = 00:12,5. Длительность результата увеличится на длину баннера. '
        'Для очереди одна вставка применяется к каждому ролику. Выход с баннером — 30 кадров/с.',page)
    note.setWordWrap(True);layout.addWidget(note)
    self.banner_preview_label=QLabel('Выберите основной ролик слева и нажмите «Предпросмотр баннера».',page)
    self.banner_preview_label.setWordWrap(True);self.banner_preview_label.setAlignment(Qt.AlignCenter)
    self.banner_preview_label.setMinimumHeight(240);layout.addWidget(self.banner_preview_label)
    layout.addStretch()
    scroll=QScrollArea(self);scroll.setWidgetResizable(True);scroll.setWidget(page)
    self.findChildren(QTabWidget)[0].addTab(scroll,'Видеобаннер')

def banner_options(self):
    return {'enabled':self.banner_group.isChecked(),'path':self.banner_path_edit.text().strip(),
        'start':self.banner_start_spin.value(),'mode':self.banner_mode_combo.currentData(),
        'scale':self.banner_scale_spin.value(),'position':self.banner_position_combo.currentData(),
        'volume':self.banner_volume_spin.value(),'key_enabled':self.banner_key_checkbox.isChecked(),
        'color':self.banner_color,'similarity':self.banner_similarity_spin.value()/100,
        'blend':self.banner_blend_spin.value()/100}

def restore_banner(self,options):
    if not isinstance(options,dict): return
    self.banner_group.setChecked(bool(options.get('enabled',False)))
    self.banner_path_edit.setText(str(options.get('path','')))
    for name,control,default,multiplier in [('start',self.banner_start_spin,5,1),('scale',self.banner_scale_spin,100,1),
            ('volume',self.banner_volume_spin,100,1),('similarity',self.banner_similarity_spin,.2,100),('blend',self.banner_blend_spin,.08,100)]:
        try:
            value=float(options.get(name,default))*multiplier
            if not ff.math.isfinite(value): continue
            control.setValue(int(value) if isinstance(control,QSpinBox) else value)
        except (ValueError,TypeError,OverflowError): pass
    for name,control in [('mode',self.banner_mode_combo),('position',self.banner_position_combo)]:
        index=control.findData(options.get(name))
        if index>=0:control.setCurrentIndex(index)
    color=QColor(str(options.get('color','#00FF00')))
    self.banner_color=color.name() if color.isValid() else '#00ff00'
    self.banner_color_button.setText('Цвет: '+self.banner_color.upper())
    self.banner_key_checkbox.setChecked(bool(options.get('key_enabled',False)))

def browse_banner(self):
    path,_=QFileDialog.getOpenFileName(self,'Выберите видеобаннер',self.banner_path_edit.text(),
        'Видеофайлы (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.gif);;Все файлы (*)')
    if path:self.banner_path_edit.setText(path)

def choose_banner_color(self):
    color=QColorDialog.getColor(QColor(self.banner_color),self,'Цвет фона видеобаннера')
    if color.isValid():
        self.banner_color=color.name();self.banner_color_button.setText('Цвет: '+color.name().upper())

def edit_subtitle_style(self):
    selected = self.video_list_widget.selectedItems()
    if not selected:
        QMessageBox.warning(self,'Нет видео','Выберите видео в списке.'); return
    source = selected[0].data(Qt.UserRole)
    srt = self.subs_srt_path.text().strip() if self.subs_from_file_radio.isChecked() else ''
    sample = not srt
    if sample:
        srt = os.path.join(self.parent_window.temp_dir, 'style_sample.srt')
        with open(srt,'w',encoding='utf-8') as stream:
            stream.write('1\n00:00:00,000 --> 99:59:59,999\nПример оформления субтитров\n')
    elif not os.path.isfile(srt):
        QMessageBox.warning(self,'Нет SRT','Выберите существующий файл SRT.'); return
    dialog = SubtitlePreviewDialog(source, srt, self, initial_style=self.selected_style())
    if sample: dialog.setWindowTitle('Стиль субтитров — пример текста')
    if dialog.exec_() == QDialog.Accepted:
        self.subtitle_style = dict(dialog.get_style())
        self.subs_size_spin.setValue(int(self.subtitle_style.get('size',36)))

def processing_options(self):
    return dict(filters=self.selected_filters(), zoom_mode='dynamic' if self.zoom_dynamic_radio.isChecked() else 'static',
        zoom_static=self.zoom_static_spin.value(),zoom_min=self.zoom_min_spin.value(),zoom_max=self.zoom_max_spin.value(),
        speed_mode='dynamic' if self.speed_dynamic_radio.isChecked() else 'static',speed_static=self.speed_static_spin.value(),
        speed_min=self.speed_min_spin.value(),speed_max=self.speed_max_spin.value(),overlay_file=self.overlay_path.text().strip() or None,
        overlay_pos=self.overlay_pos_combo.currentText(),mute_audio=self.mute_checkbox.isChecked(),
        output_format=self.output_format_combo.currentText(),blur_background=self.blur_background_checkbox.isChecked(),
        strip_metadata=self.parent_window.settings.get('strip_metadata',True),codec=self.codec_combo.currentData() or 'libx264',
        auto_crop=self.auto_crop_checkbox.isChecked(),overlay_audio=self.overlay_audio_path_edit.text().strip() or None,
        original_volume=self.orig_vol_slider.value(),overlay_volume=self.over_vol_slider.value(),filler_path=self.get_filler_path(),
        split_content_height=self.split_layout_combo.currentData(),content_on_top=self.split_pos_combo.currentText()==SPLIT_CONTENT_TOP,
        uniquify=self.uniquify_group.isChecked(),uniquify_methods={'trim':self.uq_trim_cb.isChecked(),'pitch':self.uq_pitch_cb.isChecked(),
            'speed':self.uq_speed_cb.isChecked(),'encode':self.uq_encode_cb.isChecked()},
        subtitle_settings={'mode':'whisper' if self.subs_generate_radio.isChecked() else ('srt_file' if self.subs_from_file_radio.isChecked() else 'off'),
            'srt_path':self.subs_srt_path.text().strip(),'model':self.subs_model_combo.currentText(),
            'language':self.subs_lang_combo.currentText(),'words_per_line':self.subs_words_spin.value(),'style':self.selected_style()},
        banner_settings=self.banner_options(),smart_settings=self.smart_options(),export_settings=self.export_options())

def start_processing(self):
    if self.processing_thread and self.processing_thread.isRunning(): return
    files = [self.video_list_widget.item(i).data(Qt.UserRole) for i in range(self.video_list_widget.count())]
    if not files:
        QMessageBox.warning(self,'Нет видео','Добавьте видео для обработки.'); return
    options = self.processing_options()
    try: validate_options(options['smart_settings'],options['export_settings'])
    except (ValueError,TypeError) as exc:
        QMessageBox.warning(self,'Проверьте настройки',str(exc)); return
    export=options['export_settings']
    if options['filler_path'] and export.get('enabled') and any(p!='vertical' for p in export['profiles']):
        QMessageBox.warning(self,'Залипалка','Для нескольких пропорций отключите залипалку или оставьте только 9:16.'); return
    if options['banner_settings']['enabled'] and not os.path.isfile(options['banner_settings']['path']):
        QMessageBox.warning(self,'Нет видеобаннера','Выберите существующий файл на вкладке «Видеобаннер».'); return
    subs = options['subtitle_settings']
    if subs['mode']=='srt_file' and not os.path.isfile(subs['srt_path']):
        QMessageBox.warning(self,'Нет SRT','Укажите существующий файл SRT.'); return
    if self.split_group.isChecked() and not options['filler_path']:
        QMessageBox.warning(self,'Нет залипалки','Выберите фоновый ролик.'); return
    if options['filler_path'] and not export.get('enabled') and options['output_format'] != REELS_FORMAT_NAME:
        QMessageBox.warning(self,'Формат','Для разделения экрана выберите 1080×1920.'); return
    out = QFileDialog.getExistingDirectory(self,'Папка для результатов',self.parent_window.settings.get('last_output_dir',''))
    if not out: return
    self.parent_window.settings['last_output_dir'] = out
    try: self.parent_window.persist()
    except OSError: logging.exception('Could not save preferences')
    worker = Worker(files=files,out_dir=out,**options)
    self.processing_thread = worker
    self._job_errors = []
    worker.progress.connect(self.on_prog); worker.file_progress.connect(self.on_file_prog)
    worker.file_processing.connect(self.on_file_processing); worker.status_update.connect(self.on_status_update)
    worker.error.connect(self.on_err); worker.result.connect(self.on_result); worker.finished.connect(self.on_done)
    self.progress_bar.setValue(0); self.progress_label.setText('0 / %d' % len(files))
    self.set_controls_enabled(False); self.cancel_button.setEnabled(True)
    self.cancel_button.setText('Отменить'); self.open_output_button.setEnabled(False)
    worker.start()

def on_error(self, message):
    self._job_errors.append(message)
    self.status_label.setText('Ошибка файла; очередь продолжает работу')

def on_result(self, source, status, details):
    for i in range(self.video_list_widget.count()):
        item = self.video_list_widget.item(i)
        if item.data(Qt.UserRole) == source:
            item.setText(status + ' · ' + os.path.basename(source)); item.setToolTip(details or source)

def on_done(self):
    worker = self.processing_thread
    if worker is None: return
    if worker.isRunning():
        QTimer.singleShot(50,self.on_done); return
    self.last_output_path = worker.output_paths[-1] if worker.output_paths else None
    self.open_output_button.setEnabled(bool(self.last_output_path))
    self.cancel_button.setEnabled(False)
    if not self.parent_window._close_pending: self.set_controls_enabled(True)
    summary = '%sГотово: %d. Ошибок: %d.' % ('Отменено. ' if worker.cancelled else '', len(worker.output_paths), len(worker.errors))
    self.status_label.setText(summary)
    if worker.errors and not self.parent_window._close_pending:
        box = QMessageBox(QMessageBox.Warning,'Результат обработки',summary,parent=self)
        box.setDetailedText('\n\n'.join(self._job_errors)); box.exec_()
    self.processing_thread = None
    worker.deleteLater()

def cancel_processing(self):
    if self.processing_thread and self.processing_thread.isRunning():
        self.processing_thread.stop(); self.cancel_button.setEnabled(False)
        self.status_label.setText('Отмена текущей задачи…')

def open_output(self):
    if self.last_output_path: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.last_output_path)))

class PreviewWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    def __init__(self, params):
        QThread.__init__(self); self.params = params; self.cancel_event=threading.Event()
    def stop(self): self.cancel_event.set()
    def run(self):
        ff._job.cancel = self.cancel_event
        try:
            args = dict(self.params)
            if args.pop('auto_crop',False): args['crop_filter']=ff.detect_crop_dimensions(args['in_path'])
            self.finished_signal.emit(ff.generate_preview(**args))
        except ff.CancelledError: pass
        except Exception as exc: self.error_signal.emit(str(exc))
        finally: ff._job.cancel=None

def update_preview(self):
    if self.preview_thread and self.preview_thread.isRunning(): return
    selected=self.video_list_widget.selectedItems()
    if not selected:
        QMessageBox.warning(self,'Нет видео','Выберите видео в списке.'); return
    opts=self.processing_options()
    if opts['banner_settings']['enabled'] and not os.path.isfile(opts['banner_settings']['path']):
        QMessageBox.warning(self,'Нет видеобаннера','Выберите существующий файл на вкладке «Видеобаннер».'); return
    filler=ff.pick_random_filler() if opts['filler_path']==RANDOM_FILLER else opts['filler_path']
    path=os.path.join(self.parent_window.temp_dir,uuid.uuid4().hex+'.png')
    zoom=round((opts['zoom_min']+opts['zoom_max'])/2) if opts['zoom_mode']=='dynamic' else opts['zoom_static']
    speed=round((opts['speed_min']+opts['speed_max'])/2) if opts['speed_mode']=='dynamic' else opts['speed_static']
    args=dict(in_path=selected[0].data(Qt.UserRole),out_path=path,filters=opts['filters'],zoom_p=zoom,
        speed_p=speed,overlay_file=opts['overlay_file'],overlay_pos=opts['overlay_pos'],
        output_format=opts['output_format'],blur_background=opts['blur_background'],auto_crop=opts['auto_crop'],
        filler_path=filler,split_content_height=opts['split_content_height'],content_on_top=opts['content_on_top'],
        srt_path=opts['subtitle_settings']['srt_path'] if opts['subtitle_settings']['mode']=='srt_file' else None,
        subtitle_style=self.selected_style(),banner_settings=opts['banner_settings'])
    export=opts['export_settings']
    if export.get('enabled') and export.get('profiles'):
        args['export_settings']=dict(export,profile=export['profiles'][0])
    self.preview_label.setText('Создание кадра предпросмотра…')
    self.banner_preview_label.setText('Создание кадра предпросмотра…')
    self.set_controls_enabled(False)
    self.preview_thread=PreviewWorker(args)
    self.preview_thread.finished_signal.connect(self.on_preview_finished)
    self.preview_thread.error_signal.connect(self.on_preview_error)
    self.preview_thread.finished.connect(self.preview_stopped)
    self.preview_thread.start()

def preview_ready(self,path):
    self.parent_window.temp_files.append(path)
    self.preview_label.setPixmap(QPixmap(path).scaled(self.preview_label.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
    self.banner_preview_label.setPixmap(QPixmap(path).scaled(self.banner_preview_label.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))

def preview_error(self,message):
    self.preview_label.setText('Ошибка предпросмотра: '+message[-800:])
    self.banner_preview_label.setText('Ошибка предпросмотра: '+message[-800:])

def preview_stopped(self):
    if self.preview_thread and self.preview_thread.isRunning(): QTimer.singleShot(50,self.preview_stopped); return
    if self.preview_thread: self.preview_thread.deleteLater()
    self.preview_thread=None
    if not self.parent_window._close_pending: self.set_controls_enabled(True)

def close_window(self,event):
    widget=self.processing_widget
    threads=[t for t in (widget.processing_thread,widget.preview_thread,widget.codec_probe) if t and t.isRunning()]
    if threads:
        event.ignore()
        if not self._close_pending:
            if widget.processing_thread and widget.processing_thread.isRunning():
                if QMessageBox.question(self,'Завершение','Отменить обработку и закрыть программу?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
            self._close_pending=True
            for thread in threads: thread.stop()
            self.setEnabled(False)
        QTimer.singleShot(100,self.close)
        return
    try: self.persist()
    except OSError: logging.exception('Settings save failed')
    self._cleanup_temp_files()
    event.accept()

for name, function in {'__init__':processing_init,'capture_preferences':capture_preferences,'restore_preferences':restore_preferences,
    'add_banner_tab':add_banner_tab,'banner_options':banner_options,'restore_banner':restore_banner,
    'browse_banner':browse_banner,'choose_banner_color':choose_banner_color,
    'restart_codec_probe':restart_codec_probe,'set_controls_enabled':controls,'on_subs_mode_changed':on_subs_mode,
    'update_preview_btn_state':style_button_state,'selected_style':selected_style,'on_subtitle_preview':edit_subtitle_style,
    'processing_options':processing_options,'start_processing':start_processing,'on_err':on_error,'on_result':on_result,
    'on_done':on_done,'cancel_processing':cancel_processing,'open_output':open_output,'on_update_preview':update_preview,
    'on_preview_finished':preview_ready,'on_preview_error':preview_error,'preview_stopped':preview_stopped}.items():
    setattr(ProcessingWidgetContent,name,function)
VideoUnicApp.__init__=window_init
VideoUnicApp.show_settings_dialog=show_settings
VideoUnicApp.persist=persist
VideoUnicApp.closeEvent=close_window

