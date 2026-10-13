import os
import sys
import logging
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QIcon
from ui.main_window import VideoUnicApp
from utils.path_utils import user_data_dir, resource_path

def main():
    directory=user_data_dir()
    os.makedirs(directory,exist_ok=True)
    path=os.path.join(directory,'app.log')
    if os.path.exists(path) and os.path.getsize(path)>2000000:
        try: os.replace(path,path+'.1')
        except OSError: pass
    logging.basicConfig(level=logging.INFO,format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        handlers=[logging.FileHandler(path,mode='a',encoding='utf-8')],force=True)
    app=QApplication(sys.argv)
    app.setApplicationName('Reels Maker'); app.setApplicationVersion('1.1.2')
    icon=resource_path('resources/icon.png')
    if os.path.isfile(icon): app.setWindowIcon(QIcon(icon))
    def exception_hook(kind,value,traceback):
        logging.error('Unhandled application error',exc_info=(kind,value,traceback))
        QMessageBox.critical(None,'Ошибка приложения',str(value)+'\n\nПодробности записаны в app.log.')
    sys.excepthook=exception_hook
    logging.info('Reels Maker 1.1.2 started')
    try:
        window=VideoUnicApp(); window.show()
    except Exception:
        sys.excepthook(*sys.exc_info()); return 1
    return app.exec_()

if __name__=='__main__': sys.exit(main())

