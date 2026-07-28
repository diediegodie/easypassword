# How to activate / deactivate docker-compose for the development environment:
```
cd src/infra/docker && docker-compose up -d
cd src/infra/docker && docker-compose down
```

## Rebuild containers
```
cd src/infra/docker && docker-compose build --no-cache
```