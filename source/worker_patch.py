"""Replace queue execution; Qt's built-in finished signal owns lifecycle."""
import tempfile
import threading
import logging
import json
from utils.smart_export import validate_options, read_srt, write_srt_slice, detect_pauses, select_clips, PROFILES
from utils import ffmpeg_utils as ff
from utils.constants import RANDOM_FILLER

class Worker(QThread):
    progress = pyqtSignal(int, int)
    file_progress = pyqtSignal(int)
    error = pyqtSignal(str)
    file_processing = pyqtSignal(str)
    status_update = pyqtSignal(str)
    result = pyqtSignal(str, str, str)

    def __init__(self, files, filters, zoom_mode, zoom_static, zoom_min, zoom_max,
            speed_mode, speed_static, speed_min, speed_max, overlay_file, overlay_pos,
            out_dir, mute_audio, output_format, blur_background, strip_metadata,
            codec, subtitle_settings, auto_crop, overlay_audio, original_volume,
            overlay_volume, filler_path=None, split_content_height=1080,
            content_on_top=True, uniquify=False, uniquify_methods=None, banner_settings=None, smart_settings=None, export_settings=None):
        QThread.__init__(self)
        values = locals().copy()
        for name, value in values.items():
            if name not in ('self', '__class__'): setattr(self, name, value)
        self.files = list(files)
        self.original_volume = float(original_volume) / 100
        self.overlay_volume = float(overlay_volume) / 100
        self.cancel_event = threading.Event()
        self.output_paths = []
        self.errors = []
        self.cancelled = False
        self.completed_count = 0

    def pick_zoom(self):
        return random.randint(min(self.zoom_min, self.zoom_max), max(self.zoom_min, self.zoom_max)) if self.zoom_mode == 'dynamic' else self.zoom_static

    def pick_speed(self):
        return random.randint(min(self.speed_min, self.speed_max), max(self.speed_min, self.speed_max)) if self.speed_mode == 'dynamic' else self.speed_static

    def stop(self):
        self.cancel_event.set()

    def run(self):
        ff._job.cancel = self.cancel_event
        total = len(self.files)
        try:
            os.makedirs(self.out_dir, exist_ok=True)
            for index, source in enumerate(self.files):
                if self.cancel_event.is_set(): break
                self.file_processing.emit(os.path.basename(source))
                self.file_progress.emit(0)
                try:
                    with tempfile.TemporaryDirectory(prefix='reels_subs_') as temp:
                        ff.check_cancelled()
                        crop = None
                        if self.auto_crop:
                            self.status_update.emit('Анализ чёрных полос…')
                            crop = ff.detect_crop_dimensions(source)
                        subs = self.subtitle_settings or {}
                        smart = self.smart_settings or {}
                        export = self.export_settings or {}
                        validate_options(smart, export)
                        info=ff.probe_media(source)
                        mode = subs.get('mode', 'off')
                        srt = subs.get('srt_path') if mode == 'srt_file' else None
                        speech = smart.get('enabled') and smart.get('method','speech')=='speech'
                        if mode == 'whisper' or (speech and not srt):
                            if not info['audio']:
                                if mode == 'whisper': raise ValueError('Для распознавания речи нужна аудиодорожка.')
                                self.status_update.emit('Нет звука — подбор по длительности')
                            else:
                                audio = os.path.join(temp, 'speech.wav')
                                srt = os.path.join(temp, 'speech.srt')
                                self.status_update.emit('Извлечение аудио…')
                                extract_audio(source, audio)
                                self.status_update.emit('Распознавание речи; первая загрузка модели требует интернета…')
                                settings=subs if mode=='whisper' else smart
                                generate_srt_from_whisper(audio, srt, settings.get('model', 'base'),
                                    settings.get('language', 'Russian'), subs.get('words_per_line',5),
                                    lambda n: self.file_progress.emit(int(n*.2)))
                                if not os.path.getsize(srt): srt=None
                        segments=read_srt(srt) if srt else []
                        if smart.get('enabled'):
                            self.status_update.emit('Подбор фрагментов по речи и паузам…')
                            pauses=[]
                            if info['audio'] and (smart.get('method')=='pauses' or not segments):
                                pauses=detect_pauses(source,info['duration'],lambda n:self.file_progress.emit(int(n*.25)))
                            clips=select_clips(info['duration'],smart,segments if speech else [],pauses,ff.check_cancelled)
                        else:
                            clips=[dict(start=0,end=info['duration'],reason='Видео целиком')]
                        profiles=list(dict.fromkeys(export['profiles'])) if export.get('enabled') else [None]
                        if self.filler_path and export.get('enabled') and any(p!='vertical' for p in profiles):
                            raise ValueError('Залипалка совместима только с форматом 9:16. Отключите её для остальных форматов.')
                        filler = ff.pick_random_filler() if self.filler_path == RANDOM_FILLER else self.filler_path
                        if self.filler_path and not filler: raise ValueError('Не найдены фоновые ролики для разделения экрана')
                        jobs=len(clips)*len(profiles)
                        job=0; source_results=[]; failed=0
                        for clip_index,clip in enumerate(clips,1):
                            zoom,speed=self.pick_zoom(),self.pick_speed()
                            for profile in profiles:
                                ff.check_cancelled()
                                suffix = '_processed' if self.output_format == 'Оригинальный' else '_reels'
                                if smart.get('enabled'): suffix='_clip_%02d' % clip_index
                                if profile: suffix+='_'+profile+'_'+str(export.get('resolution',1080))
                                output = os.path.join(self.out_dir, os.path.splitext(os.path.basename(source))[0] + suffix + '.mp4')
                                label='%d/%d · %s' % (job+1,jobs,PROFILES[profile][0] if profile else self.output_format)
                                self.status_update.emit('Экспорт '+label)
                                try:
                                    result = ff.process_single(source, output, self.filters, zoom, speed,
                                        self.overlay_file, self.overlay_pos, self.output_format, self.blur_background,
                                        mute_audio=self.mute_audio, strip_metadata=self.strip_metadata, codec=self.codec,
                                        srt_path=srt if mode!='off' else None, subtitle_style=subs.get('style', {}), crop_filter=crop,
                                        overlay_audio_path=self.overlay_audio, original_volume=self.original_volume,
                                        overlay_volume=self.overlay_volume, filler_path=filler,
                                        split_content_height=self.split_content_height, content_on_top=self.content_on_top,
                                        uniquify=self.uniquify, uniquify_methods=self.uniquify_methods,
                                        banner_settings=self.banner_settings,
                                        clip_start=clip['start'],clip_end=clip['end'],
                                        export_settings=dict(export,profile=profile) if profile else None,
                                        progress_callback=lambda n, j=job:self.file_progress.emit(25+int((j+n/100)/jobs*75)))
                                    self.output_paths.append(result)
                                    self.completed_count += 1
                                    source_results.append(dict(clip=clip_index,profile=profile,path=result,start=clip['start'],end=clip['end']))
                                except ff.CancelledError: raise
                                except Exception as exc:
                                    logging.exception('Failed variant %s of %s',label,source)
                                    failed+=1; message=label+': '+str(exc)
                                    self.errors.append((source,message)); self.error.emit(os.path.basename(source)+': '+message)
                                job+=1
                        if smart.get('enabled') or export.get('enabled'):
                            report=dict(source=source,smart=smart,export=export,clips=clips,outputs=source_results,
                                note='Локальный подбор по речи, паузам и ключевым словам; оценка не предсказывает популярность.',errors=failed)
                            report_temp=os.path.join(self.out_dir,'.'+uuid.uuid4().hex+'.json')
                            try:
                                with open(report_temp,'w',encoding='utf-8') as stream: json.dump(report,stream,ensure_ascii=False,indent=2)
                                ff._publish_without_overwrite(report_temp,os.path.join(self.out_dir,os.path.splitext(os.path.basename(source))[0]+'_clips.json'))
                            finally:
                                if os.path.exists(report_temp): os.remove(report_temp)
                        self.result.emit(source, 'Готово: %d; ошибок: %d' % (len(source_results),failed), '\n'.join(r['path'] for r in source_results))
                except ff.CancelledError:
                    self.result.emit(source, 'Отменено', '')
                    break
                except Exception as exc:
                    logging.exception('Failed processing %s', source)
                    message = str(exc)
                    self.errors.append((source, message))
                    self.result.emit(source, 'Ошибка', message)
                    self.error.emit(os.path.basename(source) + ': ' + message)
                self.progress.emit(index + 1, total)
        except ff.CancelledError:
            pass
        except Exception as exc:
            logging.exception('Queue failed')
            self.errors.append(('', str(exc)))
            self.error.emit(str(exc))
        finally:
            self.cancelled = self.cancel_event.is_set()
            ff._job.cancel = None
