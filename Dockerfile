# 后端镜像：Python 3.12 + 全部依赖
# 注意：这里用了国内镜像源前缀 —— 国内直连 Docker Hub 会卡在 auth.docker.io 超时。
# 想换回官方源，把 `docker.m.daocloud.io/library/` 前缀删掉即可。
FROM docker.m.daocloud.io/library/python:3.12-slim

WORKDIR /app

# onnxruntime 依赖 libgomp1，slim 镜像默认没有 —— 少了它 import 会报
# "libgomp.so.1: cannot open shared object file"
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 先只拷贝依赖清单：代码改动不会让依赖层缓存失效，构建更快
COPY requirements.txt .

# pip 加固：pandas 这类包的索引页非常大（300+ 版本），容器里网络较慢时容易半路超时，
# 表现出来就是 "Could not find a version ... (from versions: none)" —— 其实是没拉全索引。
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

EXPOSE 8000

# 必须监听 0.0.0.0：默认的 127.0.0.1 只有容器内部能访问，宿主机连不上
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]