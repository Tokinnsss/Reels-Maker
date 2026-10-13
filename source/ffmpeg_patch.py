"""Overrides for the bundled utils.ffmpeg_utils module (Python 3.12)."""
import json
import math
import threading
import time
from collections import deque
from utils.smart_export import dimensions, read_srt, write_srt_slice

_job = threading.local()

class CancelledError(Exception):
    pass

def check_cancelled():
    token = getattr(_job, 'cancel', None)
    if token is not None and token.is_set():
        raise CancelledError('Обработка отменена')

def run_process(command, timeout=None, on_line=None, cwd=None, max_lines=160):
    """Drain output off-thread; cancellation never waits on a blocking readline."""
    check_cancelled()
    lines = deque(maxlen=max_lines)
    proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, cwd=cwd)
    def drain():
        for line in proc.stdout:
            lines.append(line.rstrip())
            if on_line:
                try: on_line(line.strip())
                except Exception: logger.exception('Progress callback failed')
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    started = time.monotonic()
    try:
        while proc.poll() is None:
            check_cancelled()
            if timeout and time.monotonic() - started > timeout:
                raise TimeoutError('Превышено время ожидания внешнего процесса')
            time.sleep(0.05)
        check_cancelled()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=3)
        reader.join(timeout=3)
        if not reader.is_alive(): proc.stdout.close()
    output = '\n'.join(lines)
    if proc.returncode:
        raise RuntimeError('Ошибка внешнего процесса (код %s):\n%s' % (proc.returncode, output[-7000:]))
    return output

def run_ffmpeg(cmd, input_file_for_log='', duration=None, progress_callback=None):
    def progress(line):
        if duration and progress_callback and line.startswith('out_time_us='):
            try: progress_callback(min(99, max(0, int(int(line.split('=')[1]) / 1000000 / duration * 100))))
            except ValueError: pass
    command = [FFMPEG_PATH_EFFECTIVE, '-hide_banner', '-loglevel', 'warning', '-nostdin']
    if progress_callback: command += ['-progress', 'pipe:1', '-nostats']
    logger.info('Processing %s', os.path.basename(input_file_for_log))
    return run_process(command + list(cmd), on_line=progress, cwd=getattr(_job, 'cwd', None))

def probe_media(path):
    if not os.path.isfile(path): raise FileNotFoundError('Файл не найден: ' + path)
    output = run_process([FFPROBE_PATH_EFFECTIVE, '-v', 'error', '-show_streams',
        '-show_format', '-of', 'json', os.path.abspath(path)], timeout=30, max_lines=8000)
    info = json.loads(output)
    streams = info.get('streams', [])
    duration = float(info.get('format', {}).get('duration') or 0)
    if not duration:
        duration = max([float(s.get('duration') or 0) for s in streams] or [0])
    info['duration'] = duration if math.isfinite(duration) else 0
    info['video'] = next((s for s in streams if s.get('codec_type') == 'video'), None)
    info['audio'] = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    return info

def get_video_duration(path):
    return probe_media(path)['duration']

def get_video_dimensions(path):
    v = probe_media(path)['video']
    if not v: raise ValueError('В файле нет видеодорожки')
    return display_dimensions(v)

def display_dimensions(video):
    """Match FFmpeg autorotation and normalize non-square source pixels."""
    width,height=int(video['width']),int(video['height'])
    sar=str(video.get('sample_aspect_ratio','1:1')).split(':')
    try: ratio=float(sar[0])/float(sar[1])
    except (ValueError,IndexError,ZeroDivisionError): ratio=1
    if not math.isfinite(ratio) or ratio<=0: ratio=1
    width=max(2,round(width*ratio/2)*2)
    rotation=next((s.get('rotation',0) for s in video.get('side_data_list',[]) if 'rotation' in s),video.get('tags',{}).get('rotate',0))
    if round(float(rotation)/90)%2: width,height=height,width
    return max(2,width//2*2),max(2,height//2*2)

def configure_executables(path=''):
    global FFMPEG_PATH_EFFECTIVE, FFPROBE_PATH_EFFECTIVE
    ff = os.path.abspath(path) if path else find_executable(FFMPEG_PATH_BASE, 'ffmpeg')
    fp = os.path.join(os.path.dirname(ff), 'ffprobe.exe' if os.name == 'nt' else 'ffprobe') if ff else ''
    if not ff or not os.path.isfile(ff) or not os.path.isfile(fp):
        raise ValueError('Нужны ffmpeg.exe и ffprobe.exe в одной папке')
    for executable in (ff, fp): run_process([executable, '-version'], timeout=10)
    FFMPEG_PATH_EFFECTIVE, FFPROBE_PATH_EFFECTIVE = ff, fp

def probe_encoder(codec, timeout=8):
    try:
        run_process([FFMPEG_PATH_EFFECTIVE,'-hide_banner','-loglevel','error','-f','lavfi',
            '-i','color=black:s=256x256:d=0.1','-frames:v','1','-c:v',codec,'-f','null','-'],timeout=timeout)
        return True
    except CancelledError: raise
    except Exception: return False

def detect_crop_dimensions(path):
    duration = get_video_duration(path)
    start = max(0, min(duration / 4, 5))
    output = run_process([FFMPEG_PATH_EFFECTIVE, '-hide_banner', '-nostdin', '-ss', str(start),
        '-i', os.path.abspath(path), '-t', str(max(.1, min(5, duration - start))),
        '-vf', 'cropdetect=limit=24:round=2', '-an', '-f', 'null', '-'], timeout=45)
    matches = re.findall(r'crop=(\d+:\d+:\d+:\d+)', output)
    return 'crop=' + max(set(matches), key=matches.count) if matches else None

def subtitle_force_style(style=None):
    style = style or {}
    def color(key, default):
        rgb = str(style.get(key, default)).lstrip('#')
        if not re.fullmatch(r'[0-9a-fA-F]{6}', rgb): rgb = default.lstrip('#')
        return '&H00' + rgb[4:6] + rgb[2:4] + rgb[0:2]
    font = re.sub(r"[^\w .-]", '', str(style.get('font', 'Arial'))) or 'Arial'
    size = max(8, min(120, int(style.get('font_size', style.get('size', 36)))))
    position = max(1, min(9, int(style.get('position', 2))))
    outline = max(0, min(10, int(style.get('outline_width', 2))))
    shadow = max(0, min(10, int(style.get('shadow', 1))))
    return (f'FontName={font},FontSize={size},PrimaryColour={color("color", "#FFFFFF")},'
        f'OutlineColour={color("outline_color", "#000000")},Outline={outline},Shadow={shadow},'
        f'Bold={-1 if style.get("bold", False) else 0},Alignment={position},BorderStyle=1,'
        'MarginL=25,MarginR=25,MarginV=35')

def next_output_path(path):
    stem, ext = os.path.splitext(os.path.abspath(path))
    candidate = stem + ext
    n = 2
    while os.path.exists(candidate):
        candidate = '%s_%d%s' % (stem, n, ext); n += 1
    return candidate

def _publish_without_overwrite(temp_path, requested):
    # Windows rename fails if the destination exists, including a concurrent writer.
    for attempt in range(1000):
        result = next_output_path(requested)
        try:
            os.rename(temp_path, result)
            return result
        except FileExistsError: continue
    raise RuntimeError('Не удалось выбрать свободное имя результата')

def _tempo(factor):
    result = []
    while factor > 2: result.append('atempo=2'); factor /= 2
    while factor < .5: result.append('atempo=0.5'); factor *= 2
    result.append('atempo=%.8f' % factor)
    return ','.join(result)

def insert_video_banner(args, graph, apply, video, audio, input_index, main_duration, settings, include_audio=True):
    """Insert a finite segment into the rendered timeline, without discarding source frames.

    Main video, subtitles, filler and mixed audio are paused together. Banner time is
    measured after the main clip's speed/trim transformations. Both sides are normalized
    to a 30-fps / 48-kHz timeline so concat has matching frame and sample boundaries.
    """
    path = os.path.abspath(str(settings.get('path') or ''))
    info = probe_media(path)
    if not info['video'] or info['duration'] <= 0:
        raise ValueError('Для видеобаннера нужен видеофайл с известной длительностью')
    start = float(settings.get('start', 0))
    scale = float(settings.get('scale', 100)) / 100
    volume = float(settings.get('volume', 100)) / 100
    similarity = float(settings.get('similarity', .2))
    blend = float(settings.get('blend', .08))
    if not all(math.isfinite(x) for x in (start, scale, volume, similarity, blend)):
        raise ValueError('Некорректные параметры видеобаннера')
    if start < 0 or start > main_duration + .0001:
        raise ValueError('Момент вставки %.2f с выходит за длительность основного ролика %.2f с' % (start, main_duration))
    if not .05 <= scale <= 1 or not 0 <= volume <= 3 or not .00001 <= similarity <= 1 or not 0 <= blend <= 1:
        raise ValueError('Размер, громкость или параметры гринскрина вне допустимого диапазона')
    mode = settings.get('mode', 'overlay')
    if mode not in ('overlay', 'replace'): raise ValueError('Неизвестный режим видеобаннера')
    color = str(settings.get('color', '#00FF00'))
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color): raise ValueError('Цвет гринскрина должен быть в формате #00FF00')
    fps = 30
    main_frames = max(1, round(main_duration * fps))
    banner_frames = max(1, math.ceil(info['duration'] * fps - .000001))
    split_frame = min(main_frames, round(start * fps))
    main_duration = main_frames / fps
    banner_duration = banner_frames / fps
    at = split_frame / fps
    args += ['-i', path]

    video = apply(video, f'fps={fps},tpad=stop_mode=clone:stop=-1,trim=end_frame={main_frames},settb=AVTB,setpts=N/({fps}*TB)')
    labels = ['[bn_freeze]']
    if split_frame > 0: labels.append('[bn_before]')
    if split_frame < main_frames: labels.append('[bn_after]')
    graph.append(video + 'split=%d' % len(labels) + ''.join(labels))
    frame = min(split_frame, main_frames - 1)
    frozen = apply('[bn_freeze]', f'trim=start_frame={frame}:end_frame={frame+1},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop=-1,trim=end_frame={banner_frames},setpts=N/({fps}*TB)')
    graph.append(frozen + 'split=2[bn_background][bn_reference]')
    banner = apply('[%d:v]' % input_index, f'setpts=PTS-STARTPTS,fps={fps},tpad=stop_mode=clone:stop=-1,trim=end_frame={banner_frames},settb=AVTB,setpts=N/({fps}*TB),format=rgba')
    if settings.get('key_enabled', False):
        banner = apply(banner, f'colorkey=0x{color[1:]}:{similarity}:{blend}')
    banner = apply(banner + '[bn_reference]', f'scale=w=trunc(rw*{scale}/2)*2:h=trunc(rh*{scale}/2)*2:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1')
    background = '[bn_background]'
    if mode == 'replace': background = apply(background, 'drawbox=color=black:t=fill')
    positions = {'center':'x=(W-w)/2:y=(H-h)/2', 'top':'x=(W-w)/2:y=0',
        'bottom':'x=(W-w)/2:y=H-h', 'top_left':'x=0:y=0', 'top_right':'x=W-w:y=0',
        'bottom_left':'x=0:y=H-h', 'bottom_right':'x=W-w:y=H-h'}
    position = positions.get(settings.get('position', 'center'), positions['center'])
    inserted = apply(background + banner, 'overlay=' + position + ':shortest=1:format=auto,format=yuv420p,setsar=1')
    parts = []
    if split_frame > 0: parts.append(apply('[bn_before]', f'trim=end_frame={split_frame},setpts=PTS-STARTPTS'))
    parts.append(inserted)
    if split_frame < main_frames: parts.append(apply('[bn_after]', f'trim=start_frame={split_frame},setpts=PTS-STARTPTS'))
    video = apply(''.join(parts), 'concat=n=%d:v=1:a=0' % len(parts))

    if include_audio and (audio or info['audio']):
        samples_per_frame = 48000 // fps
        main_samples = main_frames * samples_per_frame
        banner_samples = banner_frames * samples_per_frame
        split_sample = split_frame * samples_per_frame
        normalize = 'aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo'
        if audio:
            main_audio = apply(audio, normalize + f',apad,atrim=end_sample={main_samples},asetpts=N/SR/TB')
        else:
            main_audio = apply('', f'anullsrc=r=48000:cl=stereo,atrim=end_sample={main_samples},' + normalize + ',asetpts=N/SR/TB')
        if info['audio']:
            banner_audio = apply('[%d:a]' % input_index, 'asetpts=PTS-STARTPTS,' + normalize + f',volume={volume},apad,atrim=end_sample={banner_samples},asetpts=N/SR/TB')
        else:
            banner_audio = apply('', f'anullsrc=r=48000:cl=stereo,atrim=end_sample={banner_samples},' + normalize + ',asetpts=N/SR/TB')
        audio_parts = []
        if 0 < split_frame < main_frames:
            graph.append(main_audio + 'asplit=2[bn_audio_before][bn_audio_after]')
            audio_parts.append(apply('[bn_audio_before]', f'atrim=end_sample={split_sample},asetpts=N/SR/TB'))
            after = apply('[bn_audio_after]', f'atrim=start_sample={split_sample},asetpts=N/SR/TB')
        elif split_frame == main_frames:
            audio_parts.append(main_audio); after = None
        else: after = main_audio
        audio_parts.append(banner_audio)
        if after: audio_parts.append(after)
        audio = apply(''.join(audio_parts), 'concat=n=%d:v=0:a=1' % len(audio_parts))
    return video, audio, main_duration + banner_duration, at + min(banner_duration/2, 1)

def process_single(in_path, out_path, filters, zoom_p, speed_p, overlay_file,
        overlay_pos, output_format, blur_background, mute_audio=False,
        strip_metadata=False, codec='libx264', srt_path=None, subtitle_style=None,
        crop_filter=None, overlay_audio_path=None, original_volume=1.0,
        overlay_volume=1.0, filler_path=None, split_content_height=1080,
        content_on_top=True, uniquify=False, uniquify_methods=None,
        progress_callback=None, _frame=False, _preview_seconds=None, banner_settings=None,
        clip_start=0, clip_end=None, export_settings=None):
    check_cancelled()
    in_path, out_path = os.path.abspath(in_path), os.path.abspath(out_path)
    info = probe_media(in_path)
    if not info['video']: raise ValueError('В файле нет видеодорожки')
    duration = info['duration']
    if duration <= 0: raise ValueError('Не удалось определить длительность видео')
    clip_end = duration if clip_end is None else float(clip_end)
    clip_start = float(clip_start)
    if not all(math.isfinite(n) for n in (clip_start,clip_end)) or not 0 <= clip_start < clip_end <= duration+.1:
        raise ValueError('Некорректные границы клипа')
    clip_end=min(duration,clip_end)
    duration=clip_end-clip_start
    export_settings=export_settings or {}
    source_w,source_h=display_dimensions(info['video'])
    target_size = dimensions(export_settings['profile'],export_settings.get('resolution',1080),
        source_w,source_h) if export_settings.get('profile') else None
    zoom = float(zoom_p) / 100
    speed = float(speed_p) / 100
    if not .1 <= zoom <= 10 or not .1 <= speed <= 10:
        raise ValueError('Скорость и масштаб должны быть от 10 до 1000 процентов')
    unique = build_uniquify_plan(in_path, uniquify_methods) if uniquify else {}
    if unique and abs(speed - 1) < .00001: speed = unique['speed']
    head = min(float(unique.get('head', 0)), duration * .1)
    tail = min(float(unique.get('tail', 0)), duration * .1)
    length = (duration - head - tail) / speed
    if _preview_seconds: length = min(length, _preview_seconds)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    previous_cwd = getattr(_job, 'cwd', None)
    with tempfile.TemporaryDirectory(prefix='reels_job_') as temp_dir:
        _job.cwd = temp_dir
        temp_output = os.path.join(os.path.dirname(out_path), '.' + uuid.uuid4().hex + ('.png' if _frame else '.mp4'))
        try:
            args = ['-y']
            if clip_start: args += ['-ss', '%.6f' % clip_start]
            args += ['-t','%.6f' % duration,'-i',in_path]
            graph = []; counter = [0]
            def apply(node, expression):
                counter[0] += 1; dest = '[n%d]' % counter[0]
                graph.append(node + expression + dest)
                return dest
            video = apply('[0:v]', f'setpts=PTS-STARTPTS,scale={source_w}:{source_h},setsar=1')
            if crop_filter:
                if not re.fullmatch(r'crop=\d+:\d+:\d+:\d+', crop_filter): raise ValueError('Некорректная обрезка')
                # cropdetect reports coordinates before SAR normalization.
                raw_w,raw_h=int(info['video']['width']),int(info['video']['height'])
                rotation=next((s.get('rotation',0) for s in info['video'].get('side_data_list',[]) if 'rotation' in s),0)
                if round(float(rotation)/90)%2: raw_w,raw_h=raw_h,raw_w
                cw,ch,cx,cy=map(int,crop_filter[5:].split(':'))
                cw=max(2,round(cw*source_w/raw_w/2)*2);ch=max(2,round(ch*source_h/raw_h/2)*2)
                cx=max(0,round(cx*source_w/raw_w/2)*2);cy=max(0,round(cy*source_h/raw_h/2)*2)
                cw=min(cw,source_w-cx);ch=min(ch,source_h-cy)
                if cw<2 or ch<2: raise ValueError('Обрезка выходит за границы видео')
                crop_filter=f'crop={cw}:{ch}:{cx}:{cy}'
                video = apply(video, crop_filter)
                source_w,source_h=cw,ch
            # Transform the source before composing background/filler/overlays.
            for name in filters:
                if name == 'Случайный фильтр':
                    name = random.choice([k for k,v in FILTERS.items() if v and v != 'RANDOM_PLACEHOLDER'])
                template=FILTERS.get(name,'')
                if not template or template=='RANDOM_PLACEHOLDER': continue
                template=template.format(br=random.uniform(-.1,.1),ct=random.uniform(.9,1.1),sat=random.uniform(.9,1.2),hue=random.uniform(-10,10))
                video=apply(video,template)
                if name=='Пикселизация': video=apply(video,f'scale={source_w}:{source_h}:flags=neighbor')
            if abs(zoom-1)>.00001:
                if zoom>1:
                    cw=max(2,round(source_w/zoom/2)*2);ch=max(2,round(source_h/zoom/2)*2)
                    video=apply(video,f'crop={cw}:{ch},scale={source_w}:{source_h},setsar=1')
                else:
                    zw=max(2,round(source_w*zoom/2)*2);zh=max(2,round(source_h*zoom/2)*2)
                    video=apply(video,f'scale={zw}:{zh},pad={source_w}:{source_h}:(ow-iw)/2:(oh-ih)/2,setsar=1')
            # Subtitles follow the source time, including subsequent trimming and speed.
            if srt_path:
                caption_count=write_srt_slice(read_srt(srt_path),clip_start,clip_end,os.path.join(temp_dir,'captions.srt'))
                style = subtitle_force_style(subtitle_style) if caption_count else None
            else: style = None
            inputs = 1
            reels = output_format == REELS_FORMAT_NAME
            if target_size: reels = export_settings['profile']=='vertical'
            frame_w,frame_h=target_size or (1080,1920)
            if filler_path:
                if not reels: raise ValueError('Разделение экрана требует формат 1080×1920')
                filler = probe_media(filler_path)
                if not filler['video']: raise ValueError('В залипалке нет видеодорожки')
                args += ['-stream_loop', '-1', '-i', os.path.abspath(filler_path)]
                h = max(2, min(frame_h-2, round(int(split_content_height)*frame_h/1920/2)*2))
                content = apply(video, f'fps=30,scale={frame_w}:{h}:force_original_aspect_ratio=increase,crop={frame_w}:{h},setsar=1')
                bg = apply('[%d:v]' % inputs, f'setpts=PTS-STARTPTS,fps=30,scale={frame_w}:{frame_h-h}:force_original_aspect_ratio=increase,crop={frame_w}:{frame_h-h},setsar=1')
                inputs += 1
                video = apply((content + bg) if content_on_top else (bg + content), 'vstack=inputs=2:shortest=1')
            elif (reels or target_size) and blur_background:
                graph.append(video + 'split=2[sharp][blur]')
                bg = apply('[blur]', f'scale={frame_w}:{frame_h}:force_original_aspect_ratio=increase,crop={frame_w}:{frame_h},gblur=sigma=25,setsar=1')
                fg = apply('[sharp]', f'scale={frame_w}:{frame_h}:force_original_aspect_ratio=decrease,setsar=1')
                video = apply(bg + fg, 'overlay=(W-w)/2:(H-h)/2:shortest=1')
            elif reels or target_size:
                video = apply(video, f'scale={frame_w}:{frame_h}:force_original_aspect_ratio=decrease,pad={frame_w}:{frame_h}:(ow-iw)/2:(oh-ih)/2,setsar=1')
            if overlay_file:
                if not os.path.isfile(overlay_file): raise FileNotFoundError(overlay_file)
                args += (['-stream_loop','-1'] if overlay_file.lower().endswith('.gif') else ['-loop','1']) + ['-i', os.path.abspath(overlay_file)]
                ov = apply('[%d:v]' % inputs, 'format=rgba,setpts=PTS-STARTPTS'); inputs += 1
                video = apply(video + ov, 'overlay=' + OVERLAY_POSITIONS.get(overlay_pos, 'x=(W-w)/2:y=(H-h)/2') + ':shortest=1')
            if style:
                video = apply(video, "subtitles=filename='captions.srt':force_style='" + style + "'")
            video = apply(video, f'trim=start={head}:end={duration-tail},setpts=(PTS-STARTPTS)/{speed},scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,format=yuv420p')
            audio_nodes = []
            if info['audio'] and not mute_audio:
                audio_nodes.append(apply('[0:a]', f'atrim=start={head}:end={duration-tail},asetpts=PTS-STARTPTS,volume={float(original_volume)},' + _tempo(speed)))
            if overlay_audio_path:
                if not probe_media(overlay_audio_path)['audio']: raise ValueError('В выбранном файле нет звука')
                args += ['-stream_loop', '-1', '-i', os.path.abspath(overlay_audio_path)]
                audio_nodes.append(apply('[%d:a]' % inputs, f'asetpts=PTS-STARTPTS,volume={float(overlay_volume)}')); inputs += 1
            audio = None
            if not _frame and audio_nodes:
                audio = audio_nodes[0] if len(audio_nodes) == 1 else apply(''.join(audio_nodes), 'amix=inputs=2:duration=longest:normalize=0')
                if unique.get('pitch', 1) != 1: audio = apply(audio, 'rubberband=pitch=%s' % unique['pitch'])
                audio = apply(audio, f'apad,atrim=duration={length}')
            elif audio_nodes:
                for node in audio_nodes: graph.append(node + 'anullsink')
            preview_at = min(length/2, 1)
            if banner_settings and banner_settings.get('enabled', False):
                video, audio, length, preview_at = insert_video_banner(args, graph, apply, video,
                    audio, inputs, length, banner_settings, include_audio=not _frame)
            if export_settings.get('fps'):
                video = apply(video, 'fps=%d' % export_settings['fps'])
            if _frame:
                video = apply(video, 'select=gte(t\\,%s)' % preview_at)
            args += ['-filter_complex', ';'.join(graph), '-map', video]
            if audio: args += ['-map', audio, '-c:a', 'aac', '-b:a', '192k']
            else: args += ['-an']
            if _frame: args += ['-frames:v', '1', '-update', '1']
            else:
                quality = str(export_settings.get('quality',unique.get('crf', 23)))
                args += ['-c:v', codec]
                size_mb=float(export_settings.get('size_mb',0))
                if size_mb:
                    # Reserve audio and 4% for container overhead. A target, not an exact byte limit.
                    rate=int(size_mb*1000000*8*.96/length)-(192000 if audio else 0)
                    if rate<100000: raise ValueError('Целевой размер слишком мал для этой длительности. Увеличьте размер файла.')
                    args += ['-b:v',str(rate),'-maxrate',str(rate),'-bufsize',str(rate*2)]
                    if codec=='libx264': args += ['-preset','veryfast']
                    elif 'nvenc' in codec: args += ['-rc','vbr','-preset','p4']
                    elif 'amf' in codec: args += ['-rc','vbr_peak']
                elif 'nvenc' in codec: args += ['-cq', quality, '-preset', 'p4']
                elif 'qsv' in codec: args += ['-global_quality', quality]
                elif 'amf' in codec: args += ['-rc', 'cqp', '-qp_i', quality, '-qp_p', quality]
                else: args += ['-preset', 'veryfast', '-crf', quality]
                if unique.get('gop'): args += ['-g', str(unique['gop'])]
                args += ['-t', '%.8f' % length, '-movflags', '+faststart']
                if codec == 'hevc_nvenc': args += ['-tag:v', 'hvc1']
            if strip_metadata: args += ['-map_metadata','-1','-map_chapters','-1']
            args.append(temp_output)
            run_ffmpeg(args, in_path, length, progress_callback)
            check_cancelled()
            if not os.path.isfile(temp_output) or os.path.getsize(temp_output) == 0:
                raise RuntimeError('FFmpeg не создал результат')
            if not _frame:
                check = probe_media(temp_output)
                if not check['video'] or check['duration'] <= 0: raise RuntimeError('Результат не прошёл проверку')
            result = _publish_without_overwrite(temp_output, out_path)
            if progress_callback: progress_callback(100)
            return result
        finally:
            _job.cwd = previous_cwd
            if os.path.exists(temp_output): os.remove(temp_output)

def generate_preview(in_path, out_path, filters, zoom_p, overlay_file, overlay_pos,
        output_format, blur_background, crop_filter=None, filler_path=None,
        split_content_height=1080, content_on_top=True, **options):
    options.setdefault('speed_p', 100)
    options.setdefault('mute_audio', True)
    return process_single(in_path, out_path, filters, zoom_p,
        overlay_file=overlay_file, overlay_pos=overlay_pos, output_format=output_format,
        blur_background=blur_background, crop_filter=crop_filter, filler_path=filler_path,
        split_content_height=split_content_height, content_on_top=content_on_top,
        _frame=True, **options)
