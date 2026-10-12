"""Analytical replay report and figures, separate from native measurements."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def generate():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    s=json.loads((ROOT/'records/kv-chunk-replay.json').read_text())
    low=next(r for r in s['pooled'] if r['chunk_size']==64)
    high=next(r for r in s['pooled'] if r['chunk_size']==256)
    improvement=100*(high['total_chunk_recomputed_tokens']-low['total_chunk_recomputed_tokens'])/high['total_chunk_recomputed_tokens']
    import csv
    q=list(csv.DictReader((ROOT/'results/kv_chunk_replay/lcp_requests.csv').open(encoding='utf-8')))
    f=ROOT/'results/kv_chunk_replay/figures';f.mkdir(exist_ok=True)
    fig,ax=plt.subplots(figsize=(7,4))
    ax.hist([int(r['lcp_tokens']) for r in q if r['prior_same_session_snapshot']=='True'],bins=list(range(0,353,32)),color='#26776b',edgecolor='white')
    ax.set(xlabel='Exact token LCP with retained prior same-session snapshot',ylabel='Requests',title='Recorded synthetic token trace: 204 noninitial requests')
    fig.tight_layout();fig.savefig(f/'lcp-distribution.svg');plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4));rows=s['pooled'];x=[str(r['chunk_size']) for r in rows]
    a=[100*r['chunk_saved_tokens']/r['oracle_saved_tokens'] for r in rows]
    b=[100*r['boundary_recomputed_tokens']/r['oracle_saved_tokens'] for r in rows]
    c=[100*r['unpersisted_tail_recomputed_tokens']/r['oracle_saved_tokens'] for r in rows]
    ax.bar(x,a,label='Reusable tokens',color='#26776b')
    ax.bar(x,b,bottom=a,label='Stored-chunk boundary loss',color='#c88840')
    ax.bar(x,c,bottom=[u+v for u,v in zip(a,b)],label='Unpersisted tail loss',color='#c4c4c4')
    ax.set(xlabel='Chunk tokens',ylabel='Fraction of token-oracle benefit (%)',title='Analytical reference: retained snapshots, full chunks only',ylim=(0,105))
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.18),frameon=False,ncol=1)
    fig.tight_layout();fig.savefig(f/'chunk-loss-decomposition.svg',bbox_inches='tight');plt.close(fig)
    header='|Chunk|가능 reuse tokens|총 추가 계산|경계 손실|미저장 tail 손실|상한 대비 총 손실|\n|---|---:|---:|---:|---:|---:|\n'
    rows_md='\n'.join(f"|{r['chunk_size']}|{r['chunk_saved_tokens']:,}|{r['total_chunk_recomputed_tokens']:,}|{r['boundary_recomputed_tokens']:,}|{r['unpersisted_tail_recomputed_tokens']:,}|{100*r['total_loss_fraction_of_oracle']:.2f}%|" for r in rows)
    dist='|Workload|후속 요청 수|LCP min / p50 / p90 / p95 / max|\n|---|---:|---|\n'
    for d in s['distributions']:
        a=d['noninitial_requests'];dist+=f"|{d['pattern']}|{a['n']}|"+' / '.join(f'{a[k]:.1f}' for k in ('min','p50','p90','p95','max'))+'|\n'
    details='|Workload|Chunk|총 손실 % 평균 ± sample SD|\n|---|---:|---:|\n'
    for a in s['aggregate']:
        m=a['metrics']['total_loss_fraction_of_oracle'];details+=f"|{a['pattern']}|{a['chunk_size']}|{100*m['mean']:.2f} ± {100*m['sample_sd']:.2f}|\n"
    text=f'''# Paired chunk replay 결과 — 2026-10-12

## 무엇을 실행했나

{len(s['inputs'])//2}개 기록 synthetic trace, {s['request_count']} requests의 token 배열과 저장 version을 읽어
64/128/256/512를 같은 입력으로 offline replay했다. 새 모델 생성·backend 변경·
policy/controller·FEMU·서버 실행은 없다. 분석 code/config/input hashes와 timestamps는
records/kv-chunk-replay.json에 있다. 원본 38 artifact hashes를 먼저 검증했다.

## 실제 token LCP 분포

같은 session의 **엄격히 이전** 저장 상태 전부에 대해 LCP 최대값을 구했다.
동률이면 가장 최근 snapshot을 사용하고 C를 바꿔도 source 선택을 고정했다.
최초 {s['request_count']-s['noninitial_request_count']} requests는 해당 session의 저장 상태가 없어 LCP=0이다. 후속 {s['noninitial_request_count']} requests의 분포:

{dist}

이 LCP는 실제 token 배열에서 계산한 값이지만 **저장 객체가 계속 남는다는 가정** 아래의
potential이다. Native pop-on-lookup으로 실제 가용했던 객체의 LCP와 다르다.
Prompt 전체가 일치한 12건의 마지막 logits refresh를 oracle에서 제외해 총 상한은
{low['oracle_saved_tokens']:,} tokens다. 저장 상태 최대 길이는 {s['max_persisted_snapshot_tokens']} tokens다. 이는 짧은 synthetic fixture다.

## 분석 가정과 단위

same-session retained snapshots, 무제한 용량, 동기 저장, 완전한 chunk만 저장·matching,
partial tail 저장 없음, dedup/padding 없음이다. 새로운 backend 정책을 구현한 것이 아니다.
Native lifecycle replay는 원래 lookup/pop/resident comparison을 유지했으며 모든 C에서
disk reuse=0을 재현했다. 가용성 문제가 chunk 크기 때문에 해결된 것으로 표현하지 않는다.

L=실제 LCP, P=prompt 길이, N=source snapshot 길이이면:
- token oracle O=min(L,P-1)
- 저장 coverage 상한 V=min(L,floor(N/C)*C,P-1)
- chunk reuse R=min(floor(L/C)*C,P-1)
- 미저장 tail 재계산=O-V, 저장된 chunk 내부 경계 재계산=V-R
- 총 추가 재계산=O-R; 마지막 logits refresh는 이미 oracle에 포함한 별도 비용

모든 양은 tokens다. 저장 version별 unique 사용 구간의 union과 반복 reuse events를
분리했다. 같은 prefix의 재저장은 write-instance 분모에 각각 들어간다. Tokens/tokens
utilization만 계산하고 full-state serialized bytes를 chunk KV bytes로 환산하지 않았다.

## Paired 결과

{header}{rows_md}

합계는 각 trace의 paired 결과를 합친 기술적 요약이다. 실제 workload 발생률로
가중한 모집단 추정이 아니다. Workload별 세 fixture의 mean ± sample SD:

{details}

seed별 표: results/kv_chunk_replay/seed_summary.csv. 요청별 LCP/손실, 객체별
고유 사용량/반복 사용, native reference는 같은 폴더의 CSV들에 보존했다.
512의 stored tokens=0이므로 utilization은 **null**, zero가 아니다. Unused=0을
효율 개선으로 부를 수 없다. 이 조건은 아예 persistence coverage가 없다.

## 단순 chunk 크기 조정만으로 해결되는가

256→64는 총 추가 계산 {high['total_chunk_recomputed_tokens']:,}→{low['total_chunk_recomputed_tokens']:,} tokens, **{improvement:.2f}% 감소**이고 oracle reuse
회수율은 {100*high['chunk_saved_tokens']/high['oracle_saved_tokens']:.2f}%→{100*low['chunk_saved_tokens']/low['oracle_saved_tokens']:.2f}%로 높아진다. 크기 조정 효과는 크지만, 시험한 최소 C=64에도
{100*low['total_loss_fraction_of_oracle']:.2f}% 손실이 남아 **이 네 크기 안에서 완전히 해결됐다고 볼 수 없다**.
다만 이 모델은 C를 1로 줄이면 경계 손실이 수학적으로 없어지는 구조다. 잔여 손실이
곧 새 policy 필요성이나 novelty의 증거는 아니다. 더 작은 C의 I/O·metadata·batching·
latency 비용을 측정하지 않아 어느 크기가 시스템적으로 최적인지도 판단할 수 없다.

원래 full-state backend의 native 재사용 0과 scores serialization 비용은 chunk tuning의
해결 대상과 다른 현상이다. 이번 replay는 그것들을 해결하지 않았다. Partial chunks를
저장·truncate-reuse하는 실제 backend는 다른 결과를 낼 수 있으므로 이 표를 그대로
LMCache/실제 SSD 성능으로 옮기면 안 된다. Batching의 효과는 미측정이다.
앞선 full-state smoke의 cold/partial numerical equivalence도 미해결이다.
이번 수치는 LCP 기반 계산 가능량이며 실제 logits·출력 품질 보존을 검증한 결과가 아니다.

## 연구 판단과 다음 최소 검증

Chunk size가 짧은 trace의 재사용 상한을 크게 바꾸는 것은 정량화했다. 실제 chunk
backend의 기전이나 novel cross-layer mismatch를 입증하지는 않았다. 다음 최소
검증 후보는 같은 trace에서 기존 chunk backend의 partial-tail/partial-chunk reuse
semantics가 이 strict reference와 맞는지 확인하는 것이다. 실행은 하지 않았다.
논문 후보가 되려면 현실 trace에서 반복되고 단순 tuning/batching 후에도 비용-이득의
선택 역전이 동일 SLO/recovery 조건에서 보여야 한다. Byte/NAND/latency evidence는 아직 없다.
'''
    (ROOT/'research/kv_chunk_replay_report.md').write_text(text,encoding='utf-8')

def add_notes(pages,s,helpers):
    e,table,section,link=helpers
    low=next(r for r in s['pooled'] if r['chunk_size']==64)
    high=next(r for r in s['pooled'] if r['chunk_size']==256)
    improvement=100*(high['total_chunk_recomputed_tokens']-low['total_chunk_recomputed_tokens'])/high['total_chunk_recomputed_tokens']
    rows=[[str(r['chunk_size']),f"{r['chunk_saved_tokens']:,}",f"{r['boundary_recomputed_tokens']:,}",
            f"{r['unpersisted_tail_recomputed_tokens']:,}",f"{100*r['total_loss_fraction_of_oracle']:.2f}%"] for r in s['pooled']]
    body=section('추가 실행 · 같은 trace의 chunk paired replay',
        '<p>264개 요청의 같은 token trace를 64/128/256/512로 offline 재생했다. 최초 요청 60개는 같은 session의 이전 저장 상태가 없고, 후속 204개에서 실제 token LCP를 구했다. 저장 객체가 남는다는 가정 아래의 분석 상한이며 native chunk backend 실행 결과가 아니다.</p>'+table(['Chunk','가능 reuse tokens','저장된 chunk 경계 손실','미저장 tail 재계산','총 손실 / oracle'],rows))
    for name in ('lcp-distribution.svg','chunk-loss-decomposition.svg'):
        svg=(ROOT/'results/kv_chunk_replay/figures'/name).read_text(encoding='utf-8');svg=svg[svg.index('<svg'):]
        svg=re.sub(r'<style\b[^>]*>.*?</style>','',svg,flags=re.S)
        for identifier in re.findall(r'id="([^"]+)"',svg):
            replacement='replay-'+name[:3]+'-'+identifier
            svg=svg.replace('id="'+identifier+'"','id="'+replacement+'"').replace('href="#'+identifier+'"','href="#'+replacement+'"').replace('url(#'+identifier+')','url(#'+replacement+')')
        svg=svg.replace('<svg ','<svg style="max-width:100%;height:auto" ',1)
        body+=section('기록 token 분포' if name.startswith('lcp') else '분석 reference · 실제 chunk backend 측정 아님','\n'.join(line.rstrip() for line in svg.splitlines()))
    body+=section('판단 · 크기 조정은 크게 완화하지만 아직 시스템 해법은 아니다',f'<p>256→64로 총 추가 계산은 {improvement:.2f}% 줄었지만 C=64에서도 oracle 대비 {100*low["total_loss_fraction_of_oracle"]:.2f}% 손실이 남았다. 더 작은 chunk나 partial-tail 지원으로 해결 가능한지, metadata/I/O 비용과 batching trade-off는 미측정이다. 원래 native 재사용 0은 모든 C에서 그대로이며 retention 문제를 chunk 효과로 섞지 않았다. 512는 저장할 full chunk가 없어 unused=0을 좋은 효율로 읽으면 안 된다.</p>'+link('../research/kv_chunk_replay_report.md','상세 LCP 분포·workload별 평균/SD·가정')+' · '+link('../results/kv_chunk_replay/seed_summary.csv','seed별 paired 결과'))
    title,lead,previous=pages['kv-screen.html'];pages['kv-screen.html']=(title,lead,previous+body)
    note=section('추가 분석 완료 · paired chunk replay','<p>기록 synthetic token trace에서 C=64/128/256/512 분석을 완료했다. Native backend/정책/FEMU는 새로 실행하지 않았다. 실제 trace와 chunk backend 일반화는 보류한다.</p>'+link('kv-screen.html','분포와 손실 결과'))
    for name in ('research-map.html','experiment-log.html','decision-log.html'):
        title,lead,old=pages[name];pages[name]=(title,lead,old+note)

if __name__=='__main__':generate()
