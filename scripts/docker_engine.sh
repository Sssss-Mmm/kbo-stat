# KBO 운영 스택이 있는 Docker 엔진인지 확인한다. source 해서 require_kbo_engine 을 부른다.
#
# 이 머신에는 엔진이 둘이다: Docker Desktop(운영 kbo_backend·kbo_dashboard_db·후보 이미지)과
# WSL 기본 엔진(systemd docker.service — 6월의 옛 이미지, 다른 프로젝트 컨테이너). Desktop 이 꺼져 있으면
# /var/run/docker.sock 이 WSL 기본 엔진을 가리켜, 같은 이름의 낡은 kbo_backend 를 켜거나 엉뚱한 DB 를 다룬다.
# 두 엔진의 docker info OperatingSystem 이 다르다("Docker Desktop" / "Ubuntu 24.04.3 LTS").
KBO_DOCKER_OS="${KBO_DOCKER_OS:-Docker Desktop}"

require_kbo_engine() {
  local info
  info="$(docker info --format '{{.OperatingSystem}}|{{.Name}}|{{.ID}}' 2>/dev/null || true)"
  if [[ -z "${info}" ]]; then
    echo "[error] engine: Docker 데몬에 연결할 수 없다(Docker Desktop 미실행?)" >&2
    return 1
  fi
  if [[ "${info%%|*}" != "${KBO_DOCKER_OS}" ]]; then
    echo "[error] engine: 연결된 엔진이 '${KBO_DOCKER_OS}' 가 아니다 — ${info}" >&2
    echo "[error] engine:   Docker Desktop 을 켜고 'docker info' 가 Docker Desktop 인지 확인한 뒤 다시 실행" >&2
    return 1
  fi
  echo "[engine] ${info} · kbo_backend: $(docker ps -a --filter name='^kbo_backend$' --format '{{.ID}} {{.Image}} {{.Status}}' 2>/dev/null || true)"
}
