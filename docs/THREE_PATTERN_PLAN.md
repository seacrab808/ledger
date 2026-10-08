# 세 패턴 비교 — 설계만, 실행 미승인

질문은 같은 host bytes의 비용 차이를 **순서의 무작위성**과 **재방문·고르지 않은 coverage**라는 두 비교로 더 좁히는 것이다. 해결책을 구현하는 단계가 아니다. 기계 판독 계획은 `records/phase-02-three-pattern-plan.json`이다.

| 패턴 | 한 round의 요청 | 방문 범위 |
|---|---|---|
| Sequential (S) | 0부터 N−1까지 순서대로 | 모든 주소 정확히 한 번 |
| Random permutation (P) | 전체 주소의 seed 고정 Fisher–Yates shuffle | 모든 주소 정확히 한 번 |
| Replacement random (R) | 같은 주소 집합에서 N회 복원 추출 | 중복 방문과 미방문 허용 |

N=550,502 pages이고 한 round는 약 2.1 GiB이다. S와 P의 주소 multiset은 완전히 같아야 한다. P는 매 round 다른 명시적 seed로 재현 가능한 새 permutation을 사용한다. R은 현재 fio 3.36의 tausworthe64/norandommap=1 방식과 주소 sequence를 보존·검증한다. 이 control에서는 P generator나 trace를 만들거나 실행하지 않는다.

우선 비교 S↔P는 exact coverage를 유지한 순서 효과를 본다. P↔R은 재방문·uneven coverage와 이에 연결된 시간적 locality의 묶음을 비교한다. 세 arm만으로 이 묶음 안의 모든 요인을 분리하거나 원래 90% 차이의 보편적인 인과 비중을 산출하지는 못한다.

모든 arm은 같은 raw4/exposed3 GiB, 70% logical fill, 4 KiB, direct, QD1/job1, 같은 preconditioning history와 fresh process reset을 사용한다. history는 이번 control 검토 후 실행 전에 하나로 고정한다. seed 42–44, 각 3회, S/P/R 순서를 순환 배치하는 9 runs를 제안한다. **아직 승인되지 않았다.** 기존 긴 검증과 같은 공통 ceiling 25.2 GiB 및 4.2 GiB windows를 제안한다. permutation의 수렴 속도는 미측정이므로 특정 arm만 길이를 늘리거나 결과가 잘 나오는 구간을 선택하지 않는다.

가능하면 세 arm 모두 같은 fio libaio replay 경로를 사용해 요청 제출 구현 차이를 줄인다. 기존 직접 S/R 경로와 replay의 offset sequence 및 native counters가 일치하는지 향후 sanity gate로 확인한다. 현재 R sequence를 정확히 재생할 수 없으면 generator를 몰래 바꾸지 않고 계획을 수정한다. fio의 iolog 지원은 실행 중인 버전인 [fio 3.36 공식 문서](https://github.com/axboe/fio/blob/fio-3.36/HOWTO.rst)를 기준으로 확인한다. LFSR은 중복 없는 순회를 지원하지만 uniform shuffle이라고 볼 수 없으므로 이번 P의 정의로 그대로 사용하지 않는다.

승인 후 generator·replay 검증에서는 모든 요청의 크기/범위/정렬/총 bytes, S/P의 distinct count=N과 주소별 빈도=1, seed와 trace SHA256, QD1에서 실제 발행 순서를 확인한다. R은 실제 unique coverage, 중복 요청 수, 주소별 빈도, 재방문 간격을 보고한다. 복원 추출의 약 63.2% coverage는 이론적 참고값이며 결과를 맞추는 합격 기준이 아니다. trace는 프로젝트 내부에 보관하고 Git에는 generator/config/hash/작은 통계만 넣는다.

WAF와 erase/GiB는 native counter delta에서 계산하고 GC pages를 함께 본다. seed별 S↔P, P↔R 차이와 3회 평균·표본 SD를 보고한다. 인접 window를 독립 표본으로 취급하지 않는다. 1% 이내라는 표현은 기술적 near 판정이며 n=3만으로 동등성을 증명하지 않는다. 미수렴·순위 역전·trace mismatch도 그대로 보존한다.

- P≈S<R: 복원 추출·coverage 묶음이 더 중요한 원인 후보.
- S<P≈R: exact coverage여도 무작위 순서가 큰 비용을 만들 수 있음.
- S<P<R: 두 비교 모두 기여하는 후보.
- 차이가 없거나 예상 밖의 순위: 기존 경로와 trace/reset/수렴 검증을 먼저 재검토.

현재는 설계만 남긴다. solution, service/KV, LLM, placement/FDP 및 각종 sweep은 실행하지 않는다.

Control 검토 후 공통 history의 우선 후보는 기존 seed 20261007의 random preconditioning 1회다. 선택한 두 history에서 near gate를 통과했으므로 기존 프로토콜을 유지할 이유가 있다. Permutation의 수렴까지 검증된 것은 아니며, 사용자 검토 후 모든 arm에 같은 history로 동결한다.
