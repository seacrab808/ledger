"""Korean explanation of native measurements, failures and bounded conclusions."""
import statistics
import re
from pathlib import Path

def add_notes(pages,r,helpers):
    e,table,section,link=helpers
    svg=(Path(__file__).resolve().parents[1]/'docs/assets/lmcache-native-screening.svg').read_text(encoding='utf-8')
    svg=svg[svg.index('<svg'):]
    svg=re.sub(r'<style\b[^>]*>.*?</style>','',svg,flags=re.S)
    for identifier in re.findall(r'id="([^"]+)"',svg):
        replacement='native-'+identifier
        svg=svg.replace('id="'+identifier+'"','id="'+replacement+'"').replace('href="#'+identifier+'"','href="#'+replacement+'"').replace('url(#'+identifier+')','url(#'+replacement+')')
    svg=svg.replace('<svg ','<svg style="max-width:100%;height:auto" ',1)
    svg='\n'.join(line.rstrip() for line in svg.splitlines())
    rows=[]
    for v in r['overall']:
        latency=v['seed_summary']['request_wall_mean_ms']
        rows.append([v['chunk'],f"{v['prefill_tokens_saved']:,}",f"{v['recompute_vs_LCP_tokens']:,}",
                     f"{v['disk_write_bytes']/2**20:.0f} MiB",f"{v['file_read_operations']} / {v['file_write_operations']}",
                     v['metadata_file_count'],f"{100*v['unique_read_fraction']:.2f}%",
                     f"{v['request_wall_mean_ms']:.2f} ± {latency['sample_SD']:.2f} ms"])
    batch=[]
    for c in [64,128,256]:
        for mode in ['single','batch']:
            a=[x for x in r['batch_component'] if x['chunk']==c and x['mode']==mode]
            def stat(key):return f"{statistics.mean(x[key] for x in a)*1000:.2f} ± {statistics.stdev(x[key] for x in a)*1000:.2f}"
            batch.append([c,mode,stat('write_seconds'),stat('read_seconds'),'8 / 8','동일; hash 검사 통과'])
    body=section('LMCache native 실측 · 계산은 줄었지만 저장 비용도 증가',
        '<p>2026-10-12에 기존 12 synthetic trace의 264개 prompt token 입력을 그대로 '
        'cold baseline와 C=64/128/256에서 실행했다. 총 48개의 trace 평가이며 '
        '새 대화 생성이나 새 정책은 없다. 동일 trace끼리 비교하며 각 trace에 별도 '
        'cache salt를 사용했다. 모델은 Qwen2.5-0.5B-Instruct FP16이고 출력은 greedy 1 token이다.</p>'
        '<p><strong>정확성 한계:</strong> V1 LocalDisk 경로는 큰 log-probability 차이로 '
        'smoke 실패했다. 기존 MP connector + FSL2Adapter 경로의 작은 smoke는 통과했다. '
        '본 비교 792개에서 greedy 출력은 모두 같고 공통 top-20 log-probability 차이도 '
        f"모두 0.05 이내(최대 {r['quality']['max_abs_logprob_difference']:.5f})였다. "
        '<strong>하지만 14개는 top-20 token 집합이 달라 엄격한 추가 gate는 '
        '778/792만 통과했다.</strong> 사후에 기준을 완화하지 않았다. 아래는 관측된 '
        'screening 수치이며 완전한 correctness 검증이나 최종 성능 주장이 아니다.</p>'
        +table(['chunk tokens','실제 절약 forward tokens','LCP 대비 재계산 tokens','파일 payload 쓰기','파일 읽기 / 쓰기 호출','파일 metadata 수','고유 bytes 재사용률','요청 시간 평균 ± seed SD'],rows)
        +'<p>모든 조건의 입력은 40,574 tokens이다. Native prompt-only 저장 및 trace 안의 '
        '이전 모든 요청을 기준으로 LCP oracle은 25,876 tokens이다. 과거 full-state/세션별 '
        '분석의 25,507과 정의가 달라 숫자를 덮어쓰지 않는다. forward hook으로 실제 입력 '
        'token 수를 셌으며 절약량은 cold minus cached이다. LCP 차이는 경계·미저장 tail·'
        'backend 동작을 포함하므로 전부 chunk boundary 탓이라고 단정하지 않는다.</p>'
        '<p><strong>partial chunk:</strong> 고정 MP source의 TokenHasher는 불완전 chunk를 '
        '버린다. 긴 저장 chunk 중 임의 길이의 prefix를 조회하는 기능은 이 경로에 없다. '
        'V1의 save_unfull_chunk는 tail 저장 옵션이며 partial-prefix 재사용 지원과 다르다. '
        '작은 smoke에서 299-token 저장 후 200-token 요청은 128-token만 복원하고 '
        '72-token을 다시 계산했다.</p>'
        '<p>C=64는 C=128보다 계산을 43.75% 더 절약했지만 payload 쓰기는 14.29%, '
        '파일 쓰기 수는 128.57% 더 많았다. 작은 chunk가 유리한 축과 불리한 축이 '
        '동시에 관찰됐다. C=64에서도 LCP oracle 대비 31.74%가 재계산되어 '
        '검토한 크기 중 어느 것도 모든 손실을 없애지는 못했다. 64 미만 크기나 다른 '
        'backend에서 어떻게 되는지는 실험하지 않았다.</p>'
        '<p>표의 SD는 seed 42/43/44의 합산 또는 요청 평균으로 계산한 sample SD다. '
        '각 seed의 절약 tokens는 5,888/4,096/1,024, 쓰기는 48/42/24 MiB이며 '
        '이 지표의 seed SD는 모두 0이다. Controlled fixture의 구조가 같기 때문이며 '
        '실제 workload의 변동성이 0이라는 뜻이 아니다. Seed별 fixture 결과는 CSV에 있다.</p>'
        '<p><strong>bytes의 분모:</strong> 저장한 고유 payload bytes 중 한 번이라도 '
        '소비된 prefix 영역의 bytes 합집합을 사용했다. Native hash와 실제 forward 감소, '
        '관측 payload bytes/token으로 계산한 파생값이다. 이 fixture에서는 고유 disk-read '
        'bytes와 일치한다. 반복 read bytes를 분자로 써서 100%를 넘는 효율을 만들지 '
        '않았다. 반복 chunk reuse 횟수는 별도 기록했다.</p>'
        '<p>메타데이터는 파일 수 192/84/24, UTF-8 key 파일명 bytes '
        '32,592/14,268/4,068를 직접 집계했다. 파일 내부 metadata header는 source와 '
        'payload 크기에서 0이다. 파일명 bytes는 inode 할당 비용이 아니며 '
        'metadata-only RAM과 filesystem metadata write bytes는 미측정(null)이다. '
        'I/O 횟수는 native 파일 API 호출 수이며 kernel syscall 수가 아니다. '
        '파일 payload bytes도 실제 NAND 쓰기량이 아니다.</p>'
        '<p>Cold baseline 평균 요청 시간은 '
        f"{r['baseline_wall_mean_ms']:.2f} ms였다. Cached 경로는 이 작은 모델·"
        '짧은 입력에서 계산을 절약해도 전체 요청 시간은 더 길었다. 시간은 1-token '
        '요청 wall time이며 GPU prefill만의 시간이 아니다. 읽기/복원, IPC, 스케줄링과 '
        'sampling을 포함한다. OS page cache를 사용했고 전체 cache flush나 fsync는 '
        '하지 않았다. 실행 순서가 baseline→64→128→256이고 공유 GPU의 다른 '
        '작업도 있어 지연 차이를 chunk 크기의 인과효과로 일반화하지 않는다.</p>'
        +'<h3>기존 batch API만으로 해결되는가?</h3>'
        '<p>같은 실제 KV 객체 8개를 native FS adapter에 단일-key 요청 8개 또는 '
        'list 요청 1개로 제출했다. 두 방식 모두 완료 barrier를 사용했고 3회 반복에서 '
        '순서를 교대했다. RAM buffer는 이 component의 입력일 뿐 새 저장 backend가 '
        '아니다. 읽기 hash는 18개 조건 모두 일치했다.</p>'
        +table(['chunk','기존 API','쓰기 ms ± SD','읽기 ms ± SD','파일 읽기 / 쓰기','bytes·correctness'],batch)
        +'<p>Batch 제출은 payload bytes나 파일 수/읽기·쓰기 호출 수를 줄이지 않았다. '
        '시간도 일관되게 개선되지 않았다. 이 FS adapter의 list API는 파일을 순서대로 '
        '처리하며 payload를 한 파일로 합치지 않는다. 따라서 이번 component에서 '
        '기존 batching만으로 관찰된 객체 비용이 해결됐다고 볼 수 없다. 다른 '
        'LocalDisk batch read 병렬화나 connector/controller batching의 효과까지 '
        '반증한 것은 아니다.</p>'
        '<h3>연구 판단과 다음 최소 확인</h3>'
        '<p>관측: 작은 chunk는 계산을 더 줄이나 더 많은 객체와 쓰기를 만든다. 원인 후보: '
        'full-chunk key 경계와 파일별 저장/조회가 서로 다른 비용 축을 만든다. 현재 '
        '결론은 synthetic fixture·단일 모델·MP filesystem 경로의 screening이다. '
        '실제 trace, 정확성 gate 해결, 더 긴 입력과 지연 조건을 통제한 비교 없이 '
        'novel cross-layer mismatch 또는 edge wear 문제를 입증했다고 할 수 없다.</p>'
        '<p>다음 최소 확인은 top-20 집합이 바뀐 14개 요청의 cold/cached 분포를 '
        '더 넓은 logprob 출력으로 진단해 FP16 근접 순위 변화인지 확인하는 것이다. '
        '이는 제안이며 아직 실행하지 않았다. 이후 현실 trace에서 chunk tuning과 '
        '기존 batching으로 없애기 어려운 계산·객체 비용·SLO 상충이 반복되어야 '
        '새 시스템 설계 문제로 발전할 근거가 생긴다.</p>'
        f"<p>관측 최대 사용량: RSS {r['limits']['max_RSS']/2**30:.2f} GiB, GPU {r['limits']['max_GPU']/2**30:.2f} GiB. "
        '4 GiB GPU·8 GiB RSS 상한 안에서 2-CPU affinity/nice 10을 유지했고 '
        '실험 소유 프로세스만 종료했다. 1초 sampling 최대이며 연속 peak 보장은 아니다.</p>'
        '<figure>'+svg+'<figcaption>Controlled synthetic native measurements. '
        '14 top-20 key-set checks failed; screening observations only.</figcaption></figure>'
        '<p>'+link('../records/lmcache-native-summary.json','수치·단위·quality 원본')+' · '
        +link('../results/lmcache_native/seed-summary.csv','trace별 paired 결과 CSV')+'</p>')
    for name in ('kv-screen.html','research-map.html','experiment-log.html','decision-log.html'):
        title,lead,old=pages[name];pages[name]=(title,lead,old+body)
