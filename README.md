# Regvil App
Regvil-appen håndterer oppfølging av offentlige digitaliseringstiltak som er iverksatt av statlige virksomheter.

## Push new Docker container

```bash
az acr login -n regvildockerregistry
```

```bash
docker build -t regvildockerregistry.azurecr.io/<image_name>:<tag> .
```

```bash
docker push regvildockerregistry.azurecr.io/<image_name>:<tag>
```

```bash
az containerapp up --name regvil-app --resource-group regvil-app-resource --environment regvil-app-environment  --image regvildockerregistry.azurecr.io/<image_name>:<tag> --target-port 80 --ingress external --query properties.configuration.ingress.fqdn
```

```bash
az containerapp show -n regvil-app -g regvil-app-resource
```