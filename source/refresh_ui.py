"""Small visual refresh and reliable filter interaction."""
from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QAbstractItemView

class FilterToggleDelegate(QStyledItemDelegate):
    """Own the entire row click; never toggle again through itemClicked."""
    def editorEvent(self,event,model,option,index):
        if not index.data(Qt.UserRole) or not (index.flags() & Qt.ItemIsEnabled): return False
        if event.type()==QEvent.MouseButtonRelease and event.button()==Qt.LeftButton:
            if not option.rect.contains(event.pos()): return False
        elif event.type()==QEvent.KeyPress and event.key() in (Qt.Key_Space,Qt.Key_Select):
            if event.isAutoRepeat(): return True
        elif event.type() in (QEvent.MouseButtonPress,QEvent.MouseButtonDblClick):
            return event.button()==Qt.LeftButton
        else: return False
        state=Qt.Unchecked if index.data(Qt.CheckStateRole)==Qt.Checked else Qt.Checked
        return model.setData(index,state,Qt.CheckStateRole)

_refresh_processing_init=ProcessingWidgetContent.__init__
def refreshed_processing_init(self,parent_window):
    _refresh_processing_init(self,parent_window)
    self.filter_list.itemClicked.disconnect(self.on_filter_clicked)
    self.filter_list.setItemDelegate(FilterToggleDelegate(self.filter_list))
    self.filter_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
    self.filter_list.setToolTip('Нажмите на галочку или строку фильтра. Пробел переключает выбранный фильтр.')
    self.zoom_group.setTitle('Масштаб видео')
    self.zoom_static_radio.setText('Фиксированный')
    self.zoom_dynamic_radio.setText('Случайный в диапазоне')
    self.speed_static_radio.setText('Фиксированная')
    self.speed_dynamic_radio.setText('Случайная в диапазоне')
    for group in (self.zoom_group,self.speed_group):
        group.setToolTip('В случайном режиме значение выбирается один раз для каждого клипа. Предпросмотр использует середину диапазона.')
    self.zoom_static_spin.setToolTip('100% — исходный масштаб. Больше — приближение по центру, меньше — уменьшение с полями.')
    zoom_note=QLabel('Масштаб применяется к основному видео; фон и залипалка сохраняют размер.',self.zoom_group)
    zoom_note.setWordWrap(True);self.zoom_group.layout().addWidget(zoom_note)
    self.process_button.setText('Создать видео')
    self.preview_button.setText('Показать кадр')
    self.preview_group.setTitle('Предпросмотр кадра')
    self.preview_group.setToolTip('Случайные масштаб и скорость показаны по середине выбранного диапазона. Это один кадр, а не воспроизведение видео.')
    for tab in self.findChildren(QTabWidget):
        tab.setUsesScrollButtons(True)
        tab.tabBar().setExpanding(False)
        for i in range(tab.count()):
            if tab.tabText(i)=='Меню': tab.setTabText(i,'Основное')
    self.format_note=QLabel(self)
    self.format_note.setWordWrap(True)
    self.output_format_combo.parentWidget().layout().addWidget(self.format_note)
    def format_state(*args):
        multi=self.export_group.isChecked()
        self.output_format_combo.setEnabled(not multi)
        self.format_note.setText('Форматы заданы на вкладке «Экспорт».' if multi else '')
        self.format_note.setVisible(multi)
    self.export_group.toggled.connect(format_state)
    format_state()

_base_stylesheet=VideoUnicApp.apply_stylesheet
def refreshed_stylesheet(self,mode):
    _base_stylesheet(self,mode)
    # The bundled decorative font and letter spacing made labels too wide.
    font=QFont('Segoe UI',10);font.setLetterSpacing(QFont.AbsoluteSpacing,0)
    QApplication.instance().setFont(font)
    for widget in [self]+self.findChildren(QWidget):
        widget.setFont(font)
    dark=mode.lower()=='dark'
    accent='#8c9bff' if dark else '#4e5ac7'
    selected='#303755' if dark else '#e7eaff'
    ink='#f2f4ff' if dark else '#202538'
    self.setStyleSheet(self.styleSheet()+'''
        QWidget {font-family: "Segoe UI"; font-size: 13px;}
        QLabel#app_title {font-size: 22px; font-weight: 600;}
        QTabBar::tab {padding: 9px 9px; margin-right: 1px; font-weight: 500;}
        QGroupBox {padding: 12px 10px 10px; margin-top: 16px;}
        QPushButton {padding: 7px 12px;}
        QCheckBox, QRadioButton {min-height: 26px;}
        QSpinBox::up-button,QSpinBox::down-button,QDoubleSpinBox::up-button,QDoubleSpinBox::down-button {width: 22px;}
    '''+f'''
        QGroupBox::title,QTabBar::tab:selected {{color: {accent};}}
        QPushButton#process_button {{background: #5865d8; border-color: #6e7bea; color: white;}}
        QPushButton#process_button:hover {{background: #6876ed;}}
        QPushButton#process_button:pressed {{background: #424eb8;}}
        QPushButton#process_button:disabled {{background: {selected}; color: #858995;}}
        QListWidget::item:selected {{background: {selected}; color: {ink};}}
        QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus,QComboBox:focus {{border-color: {accent};}}
        QCheckBox::indicator:checked,QRadioButton::indicator:checked,QGroupBox::indicator:checked,QListWidget::indicator:checked {{background: #6775e8; border-color: {accent};}}
        QProgressBar::chunk {{background: #6775e8;}}
    ''')
    for label in self.findChildren(QLabel):
        if label.objectName()=='app_title': label.setText('Reels Maker')
        if 'href=' in label.text() and any(s in label.text() for s in ('tokinnssoft','magerdev','donatepay','donatello')):
            label.setText(f'Tokinns Soft · <a style="color:{accent}" href="https://t.me/tokinnssoft">Telegram ↗</a>')
            label.setOpenExternalLinks(True);label.setWordWrap(True)
    for widget in self.findChildren(QWidget):
        widget.style().unpolish(widget);widget.style().polish(widget);widget.update()

ProcessingWidgetContent.__init__=refreshed_processing_init
VideoUnicApp.apply_stylesheet=refreshed_stylesheet
