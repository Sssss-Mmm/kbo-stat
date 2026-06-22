# React(Vite) 앱 빌드 → nginx 정적 서빙(+ /api 백엔드 프록시) 2단계 빌드.
# build: docker build -t kbo-frontend frontend/

# 1) 빌드 단계: 정적 산출물(dist) 생성
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# 2) 서빙 단계: nginx 로 dist 제공. /api 는 backend 컨테이너로 프록시.
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
