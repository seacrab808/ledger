"""Render the audited LMCache preparation state; never invent runtime values."""
def add_notes(pages, record, helpers):
    e, table, section, link = helpers
    metrics = [[name, '미측정' if value is None else str(value)]
               for name, value in record['runtime_metrics'].items()]
    body = section('LMCache 실제 backend 비교 · source audit 완료 / 실측 대기',
        '<p>사용자가 64/128/256 비교를 요청했다. LMCache 0.5.5의 고정 commit '
        + e(record['commit']) + '을 확인했다. 기존 token replay는 분석 상한이며 '
        '실제 prefill 절약이나 디스크 비용 측정으로 재사용하지 않는다.</p>'
        '<p>save_unfull_chunk는 마지막 짧은 chunk 저장을 제어한다. 조회 key는 '
        'chunk 전체 token hash이므로 긴 저장 chunk의 임의 prefix를 재사용한다는 '
        '뜻이 아니다. 동일 tail과 연장된 tail의 lookup을 smoke로 구분할 예정이다.</p>'
        '<p>LocalDisk batch write는 key마다 개별 쓰기를 제출한다. Batch read는 '
        'metadata lookup 및 여러 파일 읽기를 병렬 처리한다. Controller 메시지 '
        'batching과 디스크 payload 합치기는 서로 다르다.</p>'
        '<p>공유 GPU 사용 확인이 필요해 설치/추론을 시작하지 않았다. CPU MP 대안의 '
        'POSIX shared memory도 ledger 밖 생성 금지와 조정이 필요하다. 순간 GPU '
        'utilization=0은 비어 있다는 증거가 아니다. 현재 연구 결론은 미정이다.</p>'
        + table(['실제 runtime metric', '현재 상태'], metrics)
        + '<p>' + link('../research/lmcache_comparison_plan.md', 'audit·실행 gate·paired 계측 설계')
        + ' · ' + link('../records/lmcache-audit.json', 'source hash·read-only probe·미측정 기록')
        + '</p>')
    for name in ('kv-screen.html', 'research-map.html', 'experiment-log.html', 'decision-log.html'):
        title, lead, old = pages[name]
        pages[name] = (title, lead, old + body)
