"""Two optional tabs integrated with the existing processing queue."""
from utils.smart_export import PROFILES, validate_options

def add_advanced_tabs(self):
    def page(title):
        content=QWidget(self); layout=QVBoxLayout(content)
        scroll=QScrollArea(self); scroll.setWidgetResizable(True); scroll.setWidget(content)
        self.findChildren(QTabWidget)[0].addTab(scroll,title)
        return content,layout
    def spin(parent,minimum,maximum,value,suffix=''):
        widget=QSpinBox(parent); widget.setRange(minimum,maximum);widget.setValue(value);widget.setSuffix(suffix)
        return widget
    content,layout=page('Умная нарезка')
    intro=QLabel('Подбор коротких фрагментов из каждого исходника. Анализ учитывает окончания фраз, '
        'паузы, плотность речи и ключевые слова. Найденные клипы не пересекаются. Число клипов может быть меньше заданного.',content)
    intro.setWordWrap(True);layout.addWidget(intro)
    self.smart_group=QGroupBox('Создавать короткие клипы',content)
    self.smart_group.setCheckable(True);self.smart_group.setChecked(False)
    form=QFormLayout(self.smart_group)
    self.smart_method=QComboBox(self.smart_group)
    self.smart_method.addItem('Речь и окончания фраз (Whisper)','speech')
    self.smart_method.addItem('Паузы в звуке (без модели)','pauses')
    form.addRow('Анализ:',self.smart_method)
    self.smart_min=spin(content,3,600,15,' с');self.smart_target=spin(content,3,600,45,' с')
    self.smart_max=spin(content,3,600,60,' с');self.smart_count=spin(content,1,100,5)
    for label,widget in [('Минимум:',self.smart_min),('Желаемая длина:',self.smart_target),
            ('Максимум:',self.smart_max),('Максимум клипов:',self.smart_count)]: form.addRow(label,widget)
    self.smart_keywords=QLineEdit(content);self.smart_keywords.setPlaceholderText('Например: совет, ошибка, результат')
    form.addRow('Ключевые слова:',self.smart_keywords)
    self.smart_model=QComboBox(content);self.smart_model.addItems(['tiny','base','small','medium','large']);self.smart_model.setCurrentText('base')
    self.smart_language=QComboBox(content);self.smart_language.addItems(['Auto-detect','Russian','English','Ukrainian','German','French','Spanish','Italian'])
    self.smart_language.setCurrentText('Russian')
    form.addRow('Модель Whisper:',self.smart_model);form.addRow('Язык:',self.smart_language)
    def method_changed():
        enabled=self.smart_method.currentData()=='speech'
        for w in (self.smart_model,self.smart_language,self.smart_keywords):w.setEnabled(enabled)
    self.smart_method.currentIndexChanged.connect(method_changed)
    layout.addWidget(self.smart_group)
    note=QLabel('Whisper запускается локально. Модель base включена в установку; другие модели скачиваются при первом использовании. '
        'Если во вкладке «Субтитры» выбран SRT или распознавание, используется та же расшифровка. '
        'Для видео без речи доступны паузы или подбор по длительности. Короткий исходник сохраняется целиком. '
        'Границы и тексты выбранных фрагментов сохраняются рядом с видео в отчёте JSON.',content)
    note.setWordWrap(True);layout.addWidget(note)
    note=QLabel('Все эффекты применяются к каждому клипу. Время видеобаннера отсчитывается от начала клипа; '
        'убедитесь, что оно укладывается в его длительность. Кадровый предпросмотр показывает оформление исходника.',content)
    note.setWordWrap(True);layout.addWidget(note);layout.addStretch()

    content,layout=page('Экспорт')
    intro=QLabel('Создание нескольких версий каждого видео или выбранного клипа за один запуск. '
        'Каждая версия кодируется из исходного видео.',content)
    intro.setWordWrap(True);layout.addWidget(intro)
    self.export_group=QGroupBox('Экспорт в выбранные форматы',content)
    self.export_group.setCheckable(True);self.export_group.setChecked(False)
    form=QFormLayout(self.export_group)
    self.export_profiles={}
    for key,(title,w,h) in PROFILES.items():
        cb=QCheckBox(title,content);cb.setChecked(key=='vertical');self.export_profiles[key]=cb;form.addRow(cb)
    self.export_resolution=QComboBox(content)
    for value in (480,720,1080,1440,2160):self.export_resolution.addItem(str(value)+' px',value)
    self.export_resolution.setCurrentIndex(2)
    form.addRow('Короткая сторона:',self.export_resolution)
    self.export_resolution.setToolTip('9:16 при 1080 px → 1080×1920; 1:1 → 1080×1080; 16:9 → 1920×1080. Исходные пропорции: без увеличения маленького видео.')
    self.export_fps=QComboBox(content);self.export_fps.addItem('Как в обработанном видео',0)
    for value in (24,25,30,50,60):self.export_fps.addItem(str(value),value)
    form.addRow('Кадров в секунду:',self.export_fps)
    self.export_quality=QComboBox(content)
    for title,value in [('Высокое',18),('Сбалансированное',23),('Компактное',28)]:self.export_quality.addItem(title,value)
    self.export_quality.setCurrentIndex(1);form.addRow('Качество:',self.export_quality)
    self.export_size=QDoubleSpinBox(content);self.export_size.setRange(0,10000);self.export_size.setDecimals(1)
    self.export_size.setSuffix(' МБ');self.export_size.setSpecialValueText('По качеству')
    self.export_size.setToolTip('Приблизительный размер каждого файла. Итог зависит от содержимого; это не строгий лимит.')
    form.addRow('Целевой размер ≈:',self.export_size)
    self.export_size.valueChanged.connect(lambda v:self.export_quality.setEnabled(v==0))
    layout.addWidget(self.export_group)
    self.export_summary=QLabel(content);self.export_summary.setWordWrap(True);layout.addWidget(self.export_summary)
    def summary():
        r=self.export_resolution.currentData()
        sizes={'vertical':f'{r}×{round(r*16/9/2)*2}','square':f'{r}×{r}',
            'horizontal':f'{round(r*16/9/2)*2}×{r}','original':'исходные пропорции'}
        self.export_summary.setText('Версии: '+', '.join(sizes[k] for k,cb in self.export_profiles.items() if cb.isChecked()))
    self.export_resolution.currentIndexChanged.connect(summary)
    for cb in self.export_profiles.values():cb.toggled.connect(summary)
    summary()
    note=QLabel('Если этот режим выключен, используется формат на вкладке «Трансформация». '
        'Кодек и размытый фон берутся оттуда же. Залипалка доступна только для 9:16. '
        'Имена файлов содержат номер клипа и формат; существующие результаты не перезаписываются.',content)
    note.setWordWrap(True);layout.addWidget(note);layout.addStretch()

def smart_options(self):
    return dict(enabled=self.smart_group.isChecked(),method=self.smart_method.currentData(),
        min=self.smart_min.value(),target=self.smart_target.value(),max=self.smart_max.value(),
        count=self.smart_count.value(),keywords=self.smart_keywords.text().strip(),
        model=self.smart_model.currentText(),language=self.smart_language.currentText())

def export_options(self):
    return dict(enabled=self.export_group.isChecked(),profiles=[k for k,cb in self.export_profiles.items() if cb.isChecked()],
        resolution=self.export_resolution.currentData(),fps=self.export_fps.currentData(),
        quality=self.export_quality.currentData(),size_mb=self.export_size.value())

def restore_advanced(self,prefs):
    smart=prefs.get('smart',{});export=prefs.get('export',{})
    if not isinstance(smart,dict):smart={}
    if not isinstance(export,dict):export={}
    self.smart_group.setChecked(bool(smart.get('enabled',False)));self.export_group.setChecked(bool(export.get('enabled',False)))
    for key,widget in [('min',self.smart_min),('target',self.smart_target),('max',self.smart_max),('count',self.smart_count)]:
        if isinstance(smart.get(key),int):widget.setValue(smart[key])
    self.smart_keywords.setText(str(smart.get('keywords','')))
    for key,widget in [('model',self.smart_model),('language',self.smart_language)]:
        i=widget.findText(str(smart.get(key,'')))
        if i>=0:widget.setCurrentIndex(i)
    for key,widget,data in [('method',self.smart_method,smart),('resolution',self.export_resolution,export),
            ('fps',self.export_fps,export),('quality',self.export_quality,export)]:
        i=widget.findData(data.get(key))
        if i>=0:widget.setCurrentIndex(i)
    profiles=export.get('profiles',['vertical'])
    for key,cb in self.export_profiles.items():cb.setChecked(key in profiles if isinstance(profiles,list) else key=='vertical')
    try:
        size=float(export.get('size_mb',0))
        if ff.math.isfinite(size):self.export_size.setValue(size)
    except (ValueError,TypeError):pass

ProcessingWidgetContent.add_advanced_tabs=add_advanced_tabs
ProcessingWidgetContent.smart_options=smart_options
ProcessingWidgetContent.export_options=export_options
ProcessingWidgetContent.restore_advanced=restore_advanced

