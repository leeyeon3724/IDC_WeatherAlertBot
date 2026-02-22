## Summary

- 변경 목적:
- 주요 변경사항:
- 리스크/롤백 포인트:

## Quality Checks

- [ ] `python3 -m ruff check .`
- [ ] `python3 -m mypy`
- [ ] `python3 -m scripts.check_architecture_rules`
- [ ] `python3 -m scripts.check_event_docs_sync`
- [ ] `python3 -m scripts.check_alarm_rules_sync`
- [ ] `python3 -m scripts.check_repo_hygiene`
- [ ] `python3 -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc`

## Event/Runbook Impact (if applicable)

`app/observability/events.py` 또는 이벤트 필드 구조를 변경한 경우 모두 체크:

- [ ] `docs/EVENTS.md` 이벤트/필드 사전 반영
- [ ] `docs/OPERATION.md` 알람-대응 매핑 영향 검토
- [ ] 대시보드/알람 룰 영향도 검토(필드명, 이벤트명, 임계값)
- [ ] `scripts.check_event_docs_sync` 통과 확인

## Dooray Webhook Impact (if applicable)

`app/services/notifier.py` 또는 `docs/DOORAY_WEBHOOK_REFERENCE.md`를 변경한 경우 모두 체크:

- [ ] `docs/DOORAY_WEBHOOK_REFERENCE.md` 프로젝트 적용 상태 반영
- [ ] `tests/services/test_notifier.py` 정책 회귀 테스트/수정 반영

## Additional Notes

- 운영 반영 시 필요한 환경변수/절차:
- 후속 과제(선택):
