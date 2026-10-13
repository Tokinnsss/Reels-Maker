"""Cancelable transcription with language normalization and bounded log output."""
from utils import ffmpeg_utils as ff

def generate_srt_from_whisper(audio_path, srt_path, model_name='base', language='Russian', words_per_line=5, progress_callback=None):
    codes = {'russian':'ru','русский':'ru','english':'en','английский':'en',
        'ukrainian':'uk','украинский':'uk','german':'de','немецкий':'de',
        'french':'fr','французский':'fr','spanish':'es','испанский':'es',
        'italian':'it','итальянский':'it','auto-detect':'','авто':''}
    lang = codes.get(str(language).lower(), str(language).lower())
    if model_name == 'base' and getattr(sys,'frozen',False):
        bundled=os.path.join(os.path.dirname(sys.executable),'models','base')
        if os.path.isfile(os.path.join(bundled,'model.bin')):
            model_name=bundled
    command = _worker_command(audio_path, srt_path, model_name, lang, max(1, int(words_per_line)))
    def line(text):
        if text.startswith('PROGRESS ') and progress_callback:
            try: progress_callback(int(text.split()[1]))
            except ValueError: pass
        elif text.startswith('STAGE '): logger.info('transcriber: %s', text)
    ff.run_process(command, on_line=line)
    if not os.path.isfile(srt_path): raise RuntimeError('Распознавание завершилось без файла субтитров')
    return srt_path
