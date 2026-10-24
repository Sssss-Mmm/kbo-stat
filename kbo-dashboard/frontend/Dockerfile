# React(Vite) 앱 빌드 → nginx 정적 서빙(+ /api 백엔드 프록시) 2단계 빌드.
# build: docker build -t kbo-frontend frontend/

# 1) 빌드 단계: 정적 산출물(dist) 생성
# 베이스 이미지는 digest 로 고정(재현 가능한 빌드). 의존성은 package-lock.json + npm ci.
FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# 2) 서빙 단계: nginx 로 dist 제공. /api 는 backend 컨테이너로 프록시.
FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
