#!/bin/bash
# =============================================================================
# CONFIGURACION DE WORKLOAD IDENTITY FEDERATION -- correr en Cloud Shell
# =============================================================================
# Ve a https://console.cloud.google.com, arriba a la derecha click en el
# icono de terminal (Cloud Shell), pega este bloque completo despues de
# reemplazar las 3 variables de abajo con tus datos reales.
# =============================================================================

# --- 1. REEMPLAZA ESTOS 3 VALORES ANTES DE CORRER ---
PROJECT_ID="tu-project-id-aqui"                  # el ID de tu proyecto de Google Cloud
SA_EMAIL="tu-cuenta@tu-project-id.iam.gserviceaccount.com"  # el email de la Service Account que ya creaste
GITHUB_REPO="tu-usuario/tu-repositorio"          # ej: juanperez/cobranza-cloud (SIN https, sin .git)

# --- 2. Habilitar las APIs necesarias ---
gcloud services enable \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sheets.googleapis.com \
  drive.googleapis.com \
  --project="$PROJECT_ID"

# --- 3. Obtener el numero de proyecto (lo necesita el paso de binding) ---
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
echo "Numero de proyecto: $PROJECT_NUMBER"

# --- 4. Crear el Workload Identity Pool ---
gcloud iam workload-identity-pools create "github-pool" \
  --project="$PROJECT_ID" \
  --location="global" \
  --display-name="GitHub Actions Pool"

# --- 5. Crear el Provider OIDC que confia en GitHub Actions ---
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project="$PROJECT_ID" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# --- 6. Darle permiso SOLO a tu repo especifico para "impersonar" la Service Account ---
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${GITHUB_REPO}"

# --- 7. Obtener el nombre completo del Provider (esto es lo que va a GitHub Secrets) ---
echo ""
echo "=============================================="
echo "COPIA ESTOS 2 VALORES A GITHUB SECRETS:"
echo "=============================================="
echo ""
echo "GCP_WORKLOAD_IDENTITY_PROVIDER ="
gcloud iam workload-identity-pools providers describe "github-provider" \
  --project="$PROJECT_ID" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --format="value(name)"
echo ""
echo "GCP_SERVICE_ACCOUNT_EMAIL = $SA_EMAIL"
echo ""
echo "=============================================="
