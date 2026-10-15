# ---- 构建阶段：Node 编译出静态文件 ----
# 国内镜像源前缀：直连 Docker Hub 会在 auth.docker.io 超时（换回官方源就把前缀删掉）
FROM docker.m.daocloud.io/library/node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm config set registry https://registry.npmmirror.com \
    && npm install

COPY . .

# 构建时注入接口前缀：容器里由 nginx 反向代理 /api → 后端
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

# ---- 运行阶段：只保留 Nginx + 静态文件（镜像从 ~1GB 降到 ~50MB）----
FROM docker.m.daocloud.io/library/nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80