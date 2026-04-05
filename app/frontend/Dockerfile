# 1단계: 빌드 스테이지
FROM node:20-alpine AS build-stage

WORKDIR /app

# 의존성 설치 (캐시 활용)
COPY app/frontend/package*.json ./
RUN npm install

# 소스 복사 및 빌드
COPY app/frontend/ ./
RUN npm run build

# 2단계: 실행 스테이지 (Nginx)
FROM nginx:stable-alpine AS production-stage

# 빌드 결과물 복사
COPY --from=build-stage /app/dist /usr/share/nginx/html

# 전문가용 Nginx 설정 파일 복사
COPY app/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
