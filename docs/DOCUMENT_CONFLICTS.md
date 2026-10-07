# 문서 차이와 현재 기준 — provisional

참고 우선순위는 보고서(2026-10-06), 제안서(2026-09-28), 한 장 요약(2026-09-22).
어느 문서도 최종 specification은 아니다. 사용자의 최신 지시가 우선한다.

| 항목 | 과거 또는 후보 | 현재 해석 |
|---|---|---|
| 대상 | LoRA/Flower/federated learning | 최근은 inference/KV. 모두 후보 이력이며 최종 승자가 아님 |
| compute 레버 | gradient checkpointing | 최근에는 KV DROP/re-prefill. Phase 1에서는 둘 다 구현하지 않음 |
| 평가 도구 | MQSim | 최근 보고서는 ftlsim. MQSim 배제 사유는 원자료 없이 독립 확인하지 못함 |
| gate | 압박 소거 비중 20% | 최근 G1과 향후 E0는 다른 질문. E0 기준은 아직 동결하지 않음 |
| C1 | AI 수명 위험 | KV·모델·호출·메모리 조건에 따른 모델 기반 후보 주장 |
| H2 | fill별 회계 표 | 자체 모델 평가. 독립 FTL과 서비스 혼합에서 검증 필요 |
| H4 | 세 목표 동시 만족 | 특정 조건의 결과. 불가능한 예산·높은 복귀율 등 실패 영역 존재 |
| H5 | paced의 세 지표 우월성 | 최신 결과는 지연 악화 예외 포함. 보편 우월성으로 쓰지 않음 |
| Phase 5 | threshold/paced 구현 | 최신 지시: evidence로 solution 선택. 기존 LEDGER를 버려도 됨 |
| 측정 층 | block bytes, ftlsim erases | 하드웨어 NAND 실측과 구분. 673 MiB/명령은 보고된 block bytes |
| 파일명 | 이전 요청의 `(2)` | 실제 파일에는 `(2)` 없음. 이름과 hash로 식별 |
| 장비 의미 | Raspberry Pi를 닮은 VM | 작은 FEMU는 NVMe FTL 모델이며 eMMC/SD 복제가 아님 |
| 일정 | 10월 게이트·12월 제출 | 과거 계획 이력. Phase 1 이후 다음 단계 재결정 |

미제공 자료: ftlsim source, 원시 block trace, 분석 스크립트·외부 부록 결과.
보고 수치를 독립 재현했다고 표시하지 않는다.
