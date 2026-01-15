# Docker 动构建镜像指南

如果您希望自行构建镜像而不是使用 Docker Hub 上的预构建镜像，请按照以下步骤操作：

1. **构建镜像**

   ```bash
   # 在项目根目录下运行
   docker build -t arknights-mower:latest -f docker/Dockerfile .
   ```

2. **修改配置**

   修改 `docker/docker-compose.yml`，取消 `build` 字段的注释（如果之前使用了预构建镜像），或者直接使用构建好的本地镜像名。

   ```yaml
   services:
     mower:
       build:
         context: ..
         dockerfile: docker/Dockerfile
       image: arknights-mower:latest
       # ...
   ```

3. **启动容器**

   ```bash
   cd docker
   docker compose up -d
   ```
