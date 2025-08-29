# Regvil App
Regvil-appen håndterer oppfølging av offentlige digitaliseringstiltak som er iverksatt av statlige virksomheter.

## 1. Clone the Repository

```bash
git clone https://github.com/<your-org-or-username>/regvil.git
cd regvil
```

## 2. Set up Python Evnironment
```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
```
## 3. Install dependencies
```bash
pip install -r requirements.txt
```
## 3. Run tests
```bash
pytest tests/
```

## 3. Docker build and Azure Deployment 
### Log in to Azure Container Registery
```bash
az acr login -n regvildockerregistry
```
### Log in to Azure Container Registery
```bash
az acr login -n regvildockerregistry
```
### Build Docker Image
```bash
docker build -t regvildockerregistry.azurecr.io/<image-name>:<tag> .
```
### Push Docker Image
```bash
docker push regvildockerregistry.azurecr.io/<image_name>:<tag>
```
### Deploy your Docker Image to Azure Container Apps
```bash
az containerapp up --name regvil-app --resource-group regvil-app-resource --environment regvil-app-environment  --image regvildockerregistry.azurecr.io/<image_name>:<tag> --target-port 80 --ingress external --query properties.configuration.ingress.fqdn
```

## 4. Deploy Test Docker Image to Azure Container Apps

### Get an overview over existing docker images
```bash
az acr repository list --name regvildockerregistry --output table
```

### Pull test docker image
```bash
docker pull regvildockerregistry.azurecr.io/regvil-app-test:latest
```

### Deploy Test Version to Azure Container App
```bash
az containerapp up --name regvil-app --resource-group regvil-app-resource --environment regvil-app-environment  --image regvildockerregistry.azurecr.io/regvil-app-test:latest --target-port 80 --ingress external --query properties.configuration.ingress.fqdn
```

### Check Deployment
```bash
az containerapp show -n regvil-app -g regvil-app-resource
```

###  Deploy Docker Image Locally
```bash
docker run --env-file .env -p 8080:80 regvildockerregistry.azurecr.io/regvil-app:latest
```
## 5. Send Test Data
To send out test "initiell" reports to Altinn, run:
```bash
python upload_skjema.py
```

## Show running Docker Image
```bash
az containerapp show --name "regvil-app" --resource-group "regvil-app-resource" --query "properties.template.containers[0].image"
```

### Clean Up Test Instances
To start from a clean slate and remove all previously submitted test instances:
```bash
python delete_all_instances.py   
```