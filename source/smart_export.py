"""Local speech/pause clip selection and export settings; no remote AI service."""
import bisect
import math
import re

PROFILES = {'vertical': ('9:16', 9, 16), 'square': ('1:1', 1, 1),
            'horizontal': ('16:9', 16, 9), 'original': ('Исходные пропорции', 0, 0)}

def validate_options(smart=None, export=None):
    smart, export = smart or {}, export or {}
    if smart.get('enabled'):
        lo, target, hi = [float(smart.get(k, d)) for k, d in [('min',15),('target',45),('max',60)]]
        if not all(math.isfinite(x) for x in (lo,target,hi)) or not 3 <= lo <= target <= hi <= 600:
            raise ValueError('Длительность: 3 ≤ минимум ≤ желаемая ≤ максимум ≤ 600 секунд.')
        count = smart.get('count', 5)
        if not isinstance(count,int) or not 1 <= count <= 100:
            raise ValueError('Количество клипов должно быть от 1 до 100.')
        if smart.get('method','speech') not in ('speech','pauses'):
            raise ValueError('Неизвестный способ анализа.')
    if export.get('enabled'):
        profiles = export.get('profiles',[])
        if not profiles or any(p not in PROFILES for p in profiles):
            raise ValueError('Отметьте хотя бы один формат экспорта.')
        if export.get('resolution',1080) not in (480,720,1080,1440,2160):
            raise ValueError('Неизвестное разрешение.')
        if export.get('fps',0) not in (0,24,25,30,50,60):
            raise ValueError('Неизвестная частота кадров.')
        if export.get('quality',23) not in (18,23,28):
            raise ValueError('Неизвестное качество.')
        size=float(export.get('size_mb',0))
        if not math.isfinite(size) or not 0 <= size <= 10000:
            raise ValueError('Некорректный целевой размер файла.')

def dimensions(profile, resolution, width, height):
    if profile not in PROFILES: raise ValueError('Неизвестный профиль экспорта')
    _, w, h = PROFILES[profile]
    if not w: w,h=width,height
    factor = resolution / min(w,h)
    # Original preserves its native resolution when it is already smaller.
    if profile == 'original': factor=min(1,factor)
    return max(2,round(w*factor/2)*2),max(2,round(h*factor/2)*2)

_TIMING=re.compile(r'(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)')
def read_srt(path):
    with open(path,encoding='utf-8-sig',errors='replace') as stream: text=stream.read()
    result=[]
    for block in re.split(r'\n\s*\n',text.replace('\r\n','\n')):
        match=_TIMING.search(block)
        if not match: continue
        g=match.groups()
        def seconds(v): return int(v[0])*3600+int(v[1])*60+int(v[2])+int(v[3])/10**len(v[3])
        a,b=seconds(g[:4]),seconds(g[4:])
        if b>a: result.append({'start':a,'end':b,'text':block[match.end():].strip()})
    return sorted(result,key=lambda x:x['start'])

def write_srt_slice(segments, start, end, path):
    def stamp(t):
        ms=max(0,round(t*1000)); s,ms=divmod(ms,1000); m,s=divmod(s,60); h,m=divmod(m,60)
        return f'{h:02}:{m:02}:{s:02},{ms:03}'
    blocks=[]
    for item in segments:
        a,b=max(start,item['start']),min(end,item['end'])
        if b>a:
            blocks.append(f"{len(blocks)+1}\n{stamp(a-start)} --> {stamp(b-start)}\n{item['text']}\n")
    with open(path,'w',encoding='utf-8') as stream: stream.write('\n'.join(blocks))
    return len(blocks)

def detect_pauses(source, duration, progress=None):
    from utils import ffmpeg_utils as ff
    pauses=[]; opened=[None]
    def line(text):
        begin=re.search(r'silence_start: ([\d.]+)',text)
        end=re.search(r'silence_end: ([\d.]+)',text)
        if begin: opened[0]=float(begin[1])
        if end:
            a=opened[0] if opened[0] is not None else 0
            pauses.append((a,min(duration,float(end[1])))); opened[0]=None
        if progress and text.startswith('out_time_us='):
            try: progress(min(99,int(float(text.split('=')[1])/10000/duration)))
            except ValueError: pass
    ff.run_process([ff.FFMPEG_PATH_EFFECTIVE,'-hide_banner','-nostdin','-i',source,
        '-vn','-af','silencedetect=noise=-35dB:d=0.35','-progress','pipe:1','-nostats','-f','null','-'],on_line=line)
    if opened[0] is not None: pauses.append((opened[0],duration))
    return pauses

def select_clips(duration, options, segments=None, pauses=None, check_cancelled=None):
    """Rank non-overlapping excerpts. Prefer sentence ends; never label scores as virality."""
    validate_options(options)
    if not math.isfinite(duration) or duration<=0: raise ValueError('Неизвестная длительность видео')
    lo,target,hi=[float(options.get(k,d)) for k,d in [('min',15),('target',45),('max',60)]]
    count=options.get('count',5)
    segments=[s for s in (segments or []) if 0<=s['start']<s['end']<=duration+.2]
    merged=[]
    for a,b in sorted(pauses or []):
        a,b=max(0,a),min(duration,b)
        if b<=a:continue
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    pauses=merged
    pause_starts=[a for a,b in pauses];pause_total=[0]
    for a,b in pauses:pause_total.append(pause_total[-1]+b-a)
    def silence_until(t):
        i=bisect.bisect_left(pause_starts,t)
        if not i:return 0
        a,b=pauses[i-1]
        return pause_total[i-1]+max(0,min(t,b)-a)
    words=[w.strip().casefold() for w in re.split(r'[,;\n]',options.get('keywords','')) if w.strip()]
    if duration<=hi:
        return [dict(start=0.0,end=duration,score=1.0,text=' '.join(s['text'] for s in segments),reason='Короткий исходник целиком')]
    boundaries={0.0:1.0,duration:1.0}
    for i,s in enumerate(segments):
        following=segments[i+1]['start'] if i+1<len(segments) else duration
        gap=max(0,following-s['end'])
        sentence=bool(re.search(r'[.!?…][»”"\s]*$',s['text']))
        edge=min(duration,s['end']+min(.15,gap/2))
        boundaries[edge]=max(boundaries.get(edge,0),1.0 if sentence else (.85 if gap>=.35 else .25))
        if i==0 or s['start']-segments[i-1]['end']>=.35:
            boundaries[max(0,s['start']-.1)]=.9
    for a,b in pauses:
        if b>a:
            boundaries[max(0,a)]=.9
            boundaries[min(duration,b)]=.9
    natural=sorted(boundaries)
    # Fallback grid fills long passages with no recognisable boundary.
    step=max(1,min(target/3,10))
    for i in range(1,math.ceil(duration/step)):
        value=i*step
        j=bisect.bisect_left(natural,value)
        if all(abs(value-natural[k])>2 for k in (j-1,j) if 0<=k<len(natural)):
            boundaries[value]=.05
    points=sorted(boundaries)
    # Prefix sums bound analysis cost even for multi-hour transcripts.
    starts=[s['start'] for s in segments]; ends=[s['end'] for s in segments]
    density=[0]; keyword_counts=[0]; distinct=[0]
    for s in segments:
        tokens=re.findall(r'\w+',s['text'].casefold())
        density.append(density[-1]+len(tokens))
        keyword_counts.append(keyword_counts[-1]+sum(s['text'].casefold().count(w) for w in words))
        distinct.append(distinct[-1]+len(set(tokens)))
    candidates=[]
    for index,start in enumerate(points):
        if check_cancelled and index%128==0:check_cancelled()
        lower=bisect.bisect_left(points,start+lo); upper=bisect.bisect_right(points,min(duration,start+hi))
        choices=points[lower:upper]
        if not choices: continue
        # Limit endings to the best boundary/duration compromises.
        choices=sorted(choices,key=lambda end: abs(end-start-target)/target-boundaries[end]*.7)[:4]
        for end in choices:
            length=end-start
            a=bisect.bisect_left(starts,start); b=bisect.bisect_left(starts,end)
            b=max(a,b)
            n=density[b]-density[a]
            silence=silence_until(end)-silence_until(start)
            if pauses and silence/length>.7: continue
            if segments and n<3: continue
            score=2*(boundaries[start]+boundaries[end])-abs(length-target)/target
            score+=min(2,n/length)+min(2,(distinct[b]-distinct[a])/max(1,n))
            score+=min(6,2*(keyword_counts[b]-keyword_counts[a]))-3*silence/length
            candidates.append(dict(start=round(start,3),end=round(end,3),score=round(score,3),
                text=' '.join(s['text'] for s in segments[a:b])[:2000],
                reason='Речь / границы фраз' if segments else ('Паузы' if pauses else 'Длительность; речь и паузы не найдены')))
    chosen=[]
    for item in sorted(candidates,key=lambda c:(-c['score'],c['start'])):
        if any(item['start']<other['end']-.001 and item['end']>other['start']+.001 for other in chosen): continue
        chosen.append(item)
        if len(chosen)>=count: break
    if not chosen: raise ValueError('Подходящие фрагменты не найдены. Измените длительность или способ анализа.')
    return sorted(chosen,key=lambda c:c['start'])
