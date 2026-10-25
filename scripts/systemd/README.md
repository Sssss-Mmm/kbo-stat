# 운영 DB 백업 systemd 사용자 타이머 (초안)

아직 등록하지 않았다. 등록은 별도 승인 후:

```bash
mkdir -p ~/.config/systemd/user
cp scripts/systemd/kbo-backup*.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now kbo-backup.timer kbo-backup-verify.timer
systemctl --user list-timers 'kbo-*'
```

- `ExecStart` 는 운영 체크아웃(`~/kbo-stat`)의 스크립트를 가리킨다 — 워크트리가 아니다.
- **WSL 동작 조건**: 사용자 systemd 는 이 배포판에 사용자 세션이 있을 때만 돈다(`Linger=no`). WSL 이 꺼져 있거나
  세션이 없으면 그 시각에는 돌지 않고, `Persistent=true` 라 다음에 사용자 관리자가 뜰 때 한 번 따라잡는다.
  세션 없이도 돌게 하려면 `sudo loginctl enable-linger $USER`(별도 승인).
- 해제: `systemctl --user disable --now kbo-backup.timer kbo-backup-verify.timer` — 백업 파일은 남는다.
- 결과: `~/kbo-backups/daily/status.json`(마지막 시도·마지막 성공), `backup.log`, `verify.log`.
